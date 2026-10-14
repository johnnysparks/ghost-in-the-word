from __future__ import annotations

from collections import Counter, defaultdict
import random
from typing import Iterable, Mapping

USEFUL_VALUES = {"yes", "no", "uncertain"}
DIFFERENCE_TYPES = {"wording", "likely meaning", "source-text issue", "alignment issue", "unclear"}
CONFIDENCE_VALUES = {"low", "medium", "high"}
BLIND_ITEM_FIELDS = {
    "id",
    "reference",
    "book",
    "chapter",
    "verse",
    "leftText",
    "rightText",
}
FORBIDDEN_BLIND_FIELDS = {
    "rank",
    "score",
    "lexicalDistance",
    "embeddingDistance",
    "wordingDistance",
}
REVIEW_RESPONSE_FIELDS = {"id", "useful", "differenceType", "confidence", "evidence"}

NATURAL_GENRE_BOOKS = {
    "narrative": {
        "GEN", "EXO", "NUM", "JOS", "JDG", "RUT", "1SA", "2SA", "1KI", "2KI",
        "1CH", "2CH", "EZR", "NEH", "EST", "MAT", "MRK", "LUK", "JHN", "ACT",
    },
    "poetry": {"JOB", "PSA", "PRO", "ECC", "SNG", "LAM"},
    "law": {"LEV", "DEU"},
    "argument": {"ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH", "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN", "JUD"},
}


def _unit_value(unit: Mapping[str, object], camel: str, snake: str) -> object:
    return unit[camel] if camel in unit else unit.get(snake)


def validate_review_packet(packet: Mapping[str, object]) -> dict[str, object]:
    """Validate a score-blinded packet before sending it to reviewers.

    The packet is deliberately a narrow interface: every item must carry the
    displayed reference and both renderings, while model scores and ranks are
    rejected even if a caller tries to add them as extra fields. Returning a
    compact summary gives command-line workflows a machine-readable check
    without exposing the private selection key.
    """

    if packet.get("kind") != "blind-review-packet":
        raise ValueError("review packet kind must be blind-review-packet")
    if packet.get("schemaVersion") != 1:
        raise ValueError("unsupported review packet schema version")
    source = packet.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("review packet needs a source object")
    for side in ("leftEdition", "rightEdition"):
        edition = source.get(side)
        if not isinstance(edition, Mapping) or not isinstance(edition.get("id"), str) or not edition["id"].strip():
            raise ValueError(f"review packet source needs a {side} id")
    selection = packet.get("selection")
    if not isinstance(selection, Mapping):
        raise ValueError("review packet needs a selection object")
    strategy = selection.get("strategy")
    if not isinstance(strategy, str) or not strategy.strip():
        raise ValueError("review packet selection needs a strategy")
    items = packet.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("review packet needs a non-empty items array")
    ids: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("review packet items must be objects")
        leaked = FORBIDDEN_BLIND_FIELDS.intersection(item)
        if leaked:
            raise ValueError(f"review packet exposes forbidden score/rank fields: {', '.join(sorted(leaked))}")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError("review packet items need non-empty ids")
        if item_id in ids:
            raise ValueError(f"review packet contains duplicate item id: {item_id}")
        for field in ("reference", "book", "verse"):
            if not isinstance(item.get(field), (str, int)) or not str(item[field]).strip():
                raise ValueError(f"review packet item {item_id!r} needs {field}")
        if not isinstance(item.get("chapter"), int):
            raise ValueError(f"review packet item {item_id!r} needs an integer chapter")
        if not isinstance(item.get("leftText"), str) or not isinstance(item.get("rightText"), str):
            raise ValueError(f"review packet item {item_id!r} needs both display texts")
        unknown = set(item) - BLIND_ITEM_FIELDS
        if unknown:
            raise ValueError(f"review packet item {item_id!r} contains unsupported fields: {', '.join(sorted(unknown))}")
        ids.append(item_id)
    selected_count = selection.get("selectedCount")
    if selected_count is not None and selected_count != len(items):
        raise ValueError("review packet selectedCount does not match items")
    requested_count = selection.get("requestedCount")
    if requested_count is not None and (not isinstance(requested_count, int) or requested_count < len(items)):
        raise ValueError("review packet requestedCount must cover the selected items")
    candidate_count = selection.get("candidateCount")
    if candidate_count is not None and (not isinstance(candidate_count, int) or candidate_count < len(items)):
        raise ValueError("review packet candidateCount must cover the selected items")
    return {
        "schemaVersion": 1,
        "kind": "blind-review-packet",
        "itemCount": len(items),
        "itemIds": ids,
        "strategy": strategy,
        "leftEdition": str(source["leftEdition"]["id"]),
        "rightEdition": str(source["rightEdition"]["id"]),
    }


def select_review_items(
    comparison: Mapping[str, object],
    *,
    count: int,
    metric_field: str,
    seed: int,
) -> dict[str, object]:
    """Create a blinded review packet from a comparison artifact.

    The packet mixes the highest-scoring matched units with a seeded random
    sample and omits score and rank fields. Reviewers can see both renderings
    and the metric description without being told which items were selected
    because of their score.
    """

    selected, ranked, high_count = _select_candidates(comparison, count=count, metric_field=metric_field, seed=seed)

    metadata = comparison.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    metric = metadata.get("metric")
    metric = metric if isinstance(metric, Mapping) else {}
    left_edition = metadata.get("leftEdition")
    right_edition = metadata.get("rightEdition")
    packet_items = []
    for unit in selected:
        packet_items.append(
            {
                "id": unit.get("id"),
                "reference": unit.get("reference"),
                "book": unit.get("book"),
                "chapter": unit.get("chapter"),
                "verse": unit.get("verse"),
                "leftText": _unit_value(unit, "leftText", "left_text"),
                "rightText": _unit_value(unit, "rightText", "right_text"),
            }
        )
    return {
        "schemaVersion": 1,
        "kind": "blind-review-packet",
        "source": {
            "leftEdition": left_edition,
            "rightEdition": right_edition,
            "metric": {
                "id": metric.get("id"),
                "label": metric.get("label"),
                "description": metric.get("description"),
            },
        },
        "selection": {
            "strategy": "top-half-plus-seeded-random",
            "seed": seed,
            "requestedCount": count,
            "selectedCount": len(packet_items),
            "candidateCount": len(ranked),
        },
        "items": packet_items,
    }


def select_natural_benchmark(
    comparison: Mapping[str, object],
    *,
    count: int = 200,
    metric_field: str = "lexicalDistance",
    seed: int = 20261014,
    books: Iterable[str] | None = None,
    exclude_books: Iterable[str] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Select a natural benchmark packet and its private rank key.

    The first 30 items are the globally highest-scoring matched passages. The
    remainder is a seeded, genre-stratified sample across narrative, poetry,
    law, and argument, with short and long renderings mixed within each genre.
    This makes the benchmark useful for both the top-ranked usefulness gate
    and representative error analysis while keeping scores out of the packet.
    """

    if count < 30:
        raise ValueError("natural benchmark count must be at least 30")
    metadata = comparison.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    metric = metadata.get("metric")
    metric = metric if isinstance(metric, Mapping) else {}
    included_books = {str(book).upper() for book in books} if books else None
    excluded_books = {str(book).upper() for book in exclude_books} if exclude_books else set()
    if included_books and excluded_books.intersection(included_books):
        overlap = ", ".join(sorted(excluded_books.intersection(included_books)))
        raise ValueError(f"books cannot be both included and excluded: {overlap}")
    all_candidates = _review_candidates(comparison, metric_field)
    if included_books is not None:
        all_candidates = [unit for unit in all_candidates if str(unit.get("book", "")).upper() in included_books]
    if excluded_books:
        all_candidates = [unit for unit in all_candidates if str(unit.get("book", "")).upper() not in excluded_books]
    if not all_candidates:
        raise ValueError("book scope contains no eligible review candidates")
    if len(all_candidates) < count:
        raise ValueError(f"comparison has only {len(all_candidates)} eligible review candidates; need {count}")
    ranked_all = sorted(all_candidates, key=lambda unit: (-float(unit[metric_field]), str(unit["id"])))
    top_count = min(30, count)
    top = ranked_all[:top_count]
    top_ids = {str(unit["id"]) for unit in top}
    remaining = [unit for unit in ranked_all[top_count:] if str(unit["id"]) not in top_ids]
    background_count = count - top_count
    genre_candidates: dict[str, list[Mapping[str, object]]] = {genre: [] for genre in NATURAL_GENRE_BOOKS}
    for unit in remaining:
        genre = _genre_for_book(str(unit.get("book", "")))
        if genre in genre_candidates:
            genre_candidates[genre].append(unit)
    quotas = _balanced_quotas(background_count, tuple(genre_candidates))
    background: list[Mapping[str, object]] = []
    background_key: dict[str, tuple[str, str]] = {}
    generator = random.Random(seed)
    for genre, quota in quotas.items():
        candidates = genre_candidates[genre]
        if len(candidates) < quota:
            raise ValueError(f"genre {genre!r} has only {len(candidates)} eligible candidates; need {quota}")
        short, long = _split_length_bands(candidates)
        short_count = min(len(short), quota // 2)
        long_count = min(len(long), quota - short_count)
        if short_count + long_count < quota:
            short_count = min(len(short), quota - long_count)
        chosen = generator.sample(short, short_count) + generator.sample(long, long_count)
        if len(chosen) < quota:
            chosen_ids = {str(unit["id"]) for unit in chosen}
            fill = [unit for unit in candidates if str(unit["id"]) not in chosen_ids]
            chosen.extend(generator.sample(fill, quota - len(chosen)))
        for unit in chosen:
            band = "short" if unit in short else "long"
            background_key[str(unit["id"])] = (genre, band)
        background.extend(chosen)
    selected = top + background
    generator.shuffle(selected)
    packet_items = [_blind_review_item(unit) for unit in selected]
    packet = {
        "schemaVersion": 1,
        "kind": "blind-review-packet",
        "source": {
            "leftEdition": metadata.get("leftEdition"),
            "rightEdition": metadata.get("rightEdition"),
            "metric": {
                "id": metric.get("id"),
                "label": metric.get("label"),
                "description": metric.get("description"),
            },
        },
        "selection": {
            "strategy": "natural-genre-stratified-top-plus-random",
            "seed": seed,
            "requestedCount": count,
            "selectedCount": len(packet_items),
            "candidateCount": len(all_candidates),
            "topCount": top_count,
            "backgroundCount": background_count,
            "genres": {genre: quota for genre, quota in quotas.items()},
            "scope": {
                "includeBooks": sorted(included_books) if included_books is not None else None,
                "excludeBooks": sorted(excluded_books),
            },
        },
        "items": packet_items,
    }
    rank_by_id = {str(unit["id"]): index + 1 for index, unit in enumerate(ranked_all)}
    key_items = []
    for unit in selected:
        item_id = str(unit["id"])
        if item_id in top_ids:
            genre = _genre_for_book(str(unit.get("book", "")))
            band = _length_band(unit)
            bucket = "top-ranked"
        else:
            genre, band = background_key[item_id]
            bucket = "seeded-random"
        key_items.append({"id": item_id, "rank": rank_by_id[item_id], "bucket": bucket, "genre": genre, "lengthBand": band})
    key = {
        "schemaVersion": 1,
        "kind": "blind-review-key",
        "selection": {
            "strategy": "natural-genre-stratified-top-plus-random",
            "seed": seed,
            "metric": metric_field,
            "requestedCount": count,
            "selectedCount": len(packet_items),
            "candidateCount": len(all_candidates),
            "topCount": top_count,
            "scope": {
                "includeBooks": sorted(included_books) if included_books is not None else None,
                "excludeBooks": sorted(excluded_books),
            },
        },
        "items": key_items,
    }
    return packet, key


def build_review_key(
    comparison: Mapping[str, object],
    *,
    count: int,
    metric_field: str,
    seed: int,
) -> dict[str, object]:
    """Create a private key that maps blinded items back to score rank.

    Keep this document separate from the packet sent to reviewers. It contains
    no text, so an evaluator can retain it with the report without duplicating
    the review material, but it does reveal which items were selected because
    they ranked highest.
    """

    selected, ranked, high_count = _select_candidates(comparison, count=count, metric_field=metric_field, seed=seed)
    selected_ids = {str(unit["id"]) for unit in selected}
    top_ids = {str(unit["id"]) for unit in ranked[:high_count]}
    return {
        "schemaVersion": 1,
        "kind": "blind-review-key",
        "selection": {
            "strategy": "top-half-plus-seeded-random",
            "seed": seed,
            "metric": metric_field,
            "requestedCount": count,
            "selectedCount": len(selected),
            "candidateCount": len(ranked),
            "topCount": high_count,
        },
        "items": [
            {
                "id": str(unit["id"]),
                "rank": index + 1,
                "bucket": "top-ranked" if str(unit["id"]) in top_ids else "seeded-random",
            }
            for index, unit in enumerate(ranked)
            if str(unit["id"]) in selected_ids
        ],
    }


def _review_candidates(comparison: Mapping[str, object], metric_field: str) -> list[Mapping[str, object]]:
    units = comparison.get("units")
    if not isinstance(units, list):
        raise ValueError("comparison artifact must contain a units array")
    candidates = [
        unit
        for unit in units
        if isinstance(unit, Mapping)
        and unit.get("status") == "matched"
        and isinstance(unit.get(metric_field), (int, float))
        and _unit_value(unit, "leftText", "left_text") is not None
        and _unit_value(unit, "rightText", "right_text") is not None
    ]
    if not candidates:
        raise ValueError(f"comparison contains no matched units with numeric {metric_field}")
    ids = [unit.get("id") for unit in candidates]
    if any(not isinstance(item_id, str) or not item_id for item_id in ids):
        raise ValueError("every review candidate must have a non-empty id")
    if len(ids) != len(set(ids)):
        raise ValueError("review candidates must have unique ids")
    return candidates


def _blind_review_item(unit: Mapping[str, object]) -> dict[str, object]:
    return {
        "id": unit.get("id"),
        "reference": unit.get("reference"),
        "book": unit.get("book"),
        "chapter": unit.get("chapter"),
        "verse": unit.get("verse"),
        "leftText": _unit_value(unit, "leftText", "left_text"),
        "rightText": _unit_value(unit, "rightText", "right_text"),
    }


def _genre_for_book(book: str) -> str:
    return next((genre for genre, books in NATURAL_GENRE_BOOKS.items() if book in books), "other")


def _balanced_quotas(total: int, groups: tuple[str, ...]) -> dict[str, int]:
    if not groups:
        return {}
    base, remainder = divmod(total, len(groups))
    return {group: base + (index < remainder) for index, group in enumerate(groups)}


def _length_band(unit: Mapping[str, object]) -> str:
    left = _unit_value(unit, "leftText", "left_text")
    right = _unit_value(unit, "rightText", "right_text")
    length = len(str(left or "")) + len(str(right or ""))
    return "short" if length <= 180 else "long"


def _split_length_bands(candidates: list[Mapping[str, object]]) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]]]:
    short = [unit for unit in candidates if _length_band(unit) == "short"]
    long = [unit for unit in candidates if _length_band(unit) == "long"]
    return short, long


def _select_candidates(
    comparison: Mapping[str, object],
    *,
    count: int,
    metric_field: str,
    seed: int,
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]], int]:
    if count < 1:
        raise ValueError("review sample count must be positive")
    candidates = _review_candidates(comparison, metric_field)
    ids = [str(unit["id"]) for unit in candidates]

    ranked = sorted(candidates, key=lambda unit: (-float(unit[metric_field]), str(unit["id"])))
    selected_count = min(count, len(ranked))
    high_count = min(max(1, selected_count // 2), selected_count)
    selected = ranked[:high_count]
    remaining = ranked[high_count:]
    if selected_count > high_count:
        generator = random.Random(seed)
        selected.extend(generator.sample(remaining, selected_count - high_count))
    random.Random(seed + 1).shuffle(selected)
    return selected, ranked, high_count


def summarize_reviews(
    review_documents: Iterable[Mapping[str, object]],
    *,
    selection_key: Mapping[str, object] | None = None,
    packet: Mapping[str, object] | None = None,
    bootstrap_samples: int = 2000,
    bootstrap_seed: int | None = None,
) -> dict[str, object]:
    """Aggregate independent review documents without hiding abstentions.

    When ``packet`` is supplied, every response is checked against the exact
    blinded item IDs. This prevents an evaluator from accidentally combining
    responses from different runs or accepting a reviewer-side score leak.
    """

    if bootstrap_samples < 0:
        raise ValueError("bootstrap_samples must be non-negative")
    by_item: dict[str, list[dict[str, object]]] = defaultdict(list)
    reviewer_counts: Counter[str] = Counter()
    documents = list(review_documents)
    packet_summary = validate_review_packet(packet) if packet is not None else None
    packet_ids = set(packet_summary["itemIds"]) if packet_summary else None
    seen_reviewers: set[str] = set()
    for document in documents:
        if document.get("schemaVersion", 1) != 1:
            raise ValueError("unsupported review document schema version")
        reviewer = document.get("reviewerId")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("each review document needs a non-empty reviewerId")
        if reviewer in seen_reviewers:
            raise ValueError(f"reviewer {reviewer!r} appears in more than one document")
        seen_reviewers.add(reviewer)
        items = document.get("items")
        if not isinstance(items, list):
            raise ValueError(f"reviewer {reviewer!r} must provide an items array")
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, Mapping):
                raise ValueError(f"reviewer {reviewer!r} contains a non-object item")
            leaked = FORBIDDEN_BLIND_FIELDS.intersection(item)
            if leaked:
                raise ValueError(f"reviewer {reviewer!r} response exposes forbidden score/rank fields: {', '.join(sorted(leaked))}")
            unknown = set(item) - REVIEW_RESPONSE_FIELDS
            if unknown:
                raise ValueError(f"reviewer {reviewer!r} response contains unsupported fields: {', '.join(sorted(unknown))}")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"reviewer {reviewer!r} has an item without an id")
            if packet_ids is not None and item_id not in packet_ids:
                raise ValueError(f"reviewer {reviewer!r} returned unknown packet item {item_id!r}")
            if item_id in seen:
                raise ValueError(f"reviewer {reviewer!r} reviews item {item_id!r} more than once")
            seen.add(item_id)
            useful = item.get("useful")
            difference_type = item.get("differenceType")
            confidence = item.get("confidence")
            evidence = item.get("evidence", "")
            if useful not in USEFUL_VALUES:
                raise ValueError(f"invalid useful value for {item_id!r}: {useful!r}")
            if difference_type not in DIFFERENCE_TYPES:
                raise ValueError(f"invalid differenceType for {item_id!r}: {difference_type!r}")
            if confidence not in CONFIDENCE_VALUES:
                raise ValueError(f"invalid confidence for {item_id!r}: {confidence!r}")
            if not isinstance(evidence, str):
                raise ValueError(f"evidence for {item_id!r} must be text")
            by_item[item_id].append(
                {
                    "reviewerId": reviewer,
                    "useful": useful,
                    "differenceType": difference_type,
                    "confidence": confidence,
                    "evidence": evidence,
                }
            )
            reviewer_counts[reviewer] += 1

    item_reports = []
    binary_agreement: list[bool] = []
    consensus_useful: list[str] = []
    for item_id in sorted(by_item):
        votes = by_item[item_id]
        useful_votes = [str(vote["useful"]) for vote in votes]
        binary_votes = [vote for vote in useful_votes if vote in {"yes", "no"}]
        counts = Counter(useful_votes)
        majority = "uncertain"
        if binary_votes and counts["yes"] != counts["no"]:
            majority = "yes" if counts["yes"] > counts["no"] else "no"
            consensus_useful.append(majority)
        agreement: bool | None = None
        if len(binary_votes) >= 2:
            agreement = len(set(binary_votes)) == 1
            binary_agreement.append(agreement)
        item_reports.append(
            {
                "id": item_id,
                "reviewCount": len(votes),
                "usefulVotes": dict(counts),
                "majorityUseful": majority,
                "binaryAgreement": agreement,
                "votes": votes,
            }
        )

    total_consensus = len(consensus_useful)
    report: dict[str, object] = {
        "schemaVersion": 1,
        "reviewerCount": len(documents),
        "reviewerItems": dict(reviewer_counts),
        "itemCount": len(item_reports),
        "consensusItems": total_consensus,
        "majorityUsefulYes": consensus_useful.count("yes"),
        "majorityUsefulNo": consensus_useful.count("no"),
        "majorityUsefulRate": round(consensus_useful.count("yes") / total_consensus, 6) if total_consensus else None,
        "binaryAgreementItems": sum(binary_agreement),
        "binaryComparedItems": len(binary_agreement),
        "binaryAgreementRate": round(sum(binary_agreement) / len(binary_agreement), 6) if binary_agreement else None,
        "items": item_reports,
    }
    if selection_key is not None:
        if packet_ids is not None:
            key_items = selection_key.get("items")
            if isinstance(key_items, list):
                unknown_key_ids = {
                    str(item.get("id"))
                    for item in key_items
                    if isinstance(item, Mapping) and str(item.get("id", "")) not in packet_ids
                }
                if unknown_key_ids:
                    raise ValueError(f"selection key contains ids outside the review packet: {', '.join(sorted(unknown_key_ids))}")
        report["selection"] = _summarize_selection(
            item_reports,
            selection_key,
            packet=packet,
            bootstrap_samples=bootstrap_samples,
            bootstrap_seed=bootstrap_seed,
        )
        report["naturalEvaluation"] = _natural_evaluation_status(
            report["selection"],
            reviewer_count=len(documents),
        )
    if packet_summary is not None:
        reviewed_ids = set(by_item)
        report["packet"] = {
            "itemCount": packet_summary["itemCount"],
            "reviewedItemCount": len(reviewed_ids),
            "unreviewedItemCount": int(packet_summary["itemCount"]) - len(reviewed_ids),
            "coverage": round(len(reviewed_ids) / int(packet_summary["itemCount"]), 6),
        }
    return report


def _natural_evaluation_status(selection: object, *, reviewer_count: int) -> dict[str, object]:
    """Report eligibility for the plan's natural-review gate.

    The gate is intentionally conservative: it needs at least two reviewers,
    two votes on every selected top-ranked item, and at least thirty top-ranked
    items in the packet. A rate is still reported for incomplete runs, but
    ``passed`` remains false until those conditions are met.
    """

    selection = selection if isinstance(selection, Mapping) else {}
    top = selection.get("topRanked")
    top = top if isinstance(top, Mapping) else {}
    selected_count = int(top.get("selectedCount", 0) or 0)
    reviewed_count = int(top.get("reviewedCount", 0) or 0)
    target_count = 30
    rate = top.get("majorityUsefulRate")
    prerequisites = {
        "minimumReviewers": 2,
        "reviewerCount": reviewer_count,
        "reviewerCountMet": reviewer_count >= 2,
        "minimumTopRankedItems": target_count,
        "topRankedItemCount": selected_count,
        "topRankedItemCountMet": selected_count >= target_count,
        "topRankedComplete": reviewed_count == selected_count and selected_count >= target_count,
        "topRankedIndependentlyReviewed": bool(top.get("allItemsReviewedByTwo", False)),
    }
    eligible = all(
        bool(prerequisites[key])
        for key in ("reviewerCountMet", "topRankedItemCountMet", "topRankedComplete", "topRankedIndependentlyReviewed")
    )
    passed = bool(eligible and isinstance(rate, (int, float)) and rate >= 0.70)
    return {
        "threshold": 0.70,
        "metric": "top-ranked majority useful rate",
        "eligible": eligible,
        "passed": passed,
        "rate": rate,
        "prerequisites": prerequisites,
    }


def _summarize_selection(
    item_reports: list[dict[str, object]],
    selection_key: Mapping[str, object],
    *,
    packet: Mapping[str, object] | None = None,
    bootstrap_samples: int = 2000,
    bootstrap_seed: int | None = None,
) -> dict[str, object]:
    if selection_key.get("kind") != "blind-review-key":
        raise ValueError("selection key must have kind blind-review-key")
    key_items = selection_key.get("items")
    if not isinstance(key_items, list):
        raise ValueError("selection key must contain an items array")
    report_by_id = {str(item["id"]): item for item in item_reports}
    packet_books: dict[str, str] = {}
    if packet is not None and isinstance(packet.get("items"), list):
        packet_books = {
            str(item.get("id")): str(item.get("book"))
            for item in packet["items"]
            if isinstance(item, Mapping) and item.get("id") and item.get("book")
        }
    buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in key_items:
        if not isinstance(item, Mapping):
            raise ValueError("selection key contains a non-object item")
        item_id = item.get("id")
        bucket = item.get("bucket")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("selection key item needs a non-empty id")
        if bucket not in {"top-ranked", "seeded-random"}:
            raise ValueError(f"invalid selection bucket for {item_id!r}: {bucket!r}")
        buckets[str(bucket)].append({"id": item_id, "rank": item.get("rank")})

    selection = selection_key.get("selection")
    selection = dict(selection) if isinstance(selection, Mapping) else {}
    seed = bootstrap_seed if bootstrap_seed is not None else int(selection.get("seed", 20261014))

    def summarize_bucket(items: list[dict[str, object]], bucket_offset: int) -> dict[str, object]:
        reviewed = [report_by_id[item["id"]] for item in items if item["id"] in report_by_id]
        consensus = [str(item["majorityUseful"]) for item in reviewed if item["majorityUseful"] in {"yes", "no"}]
        agreements = [item["binaryAgreement"] for item in reviewed if isinstance(item.get("binaryAgreement"), bool)]
        review_counts = [int(item.get("reviewCount", 0)) for item in reviewed]
        grouped_consensus: dict[str, list[float]] = defaultdict(list)
        for item in reviewed:
            majority = item.get("majorityUseful")
            if majority not in {"yes", "no"}:
                continue
            group = packet_books.get(str(item["id"]), str(item["id"]))
            grouped_consensus[group].append(1.0 if majority == "yes" else 0.0)
        return {
            "selectedCount": len(items),
            "reviewedCount": len(reviewed),
            "unreviewedCount": len(items) - len(reviewed),
            "minimumReviewCount": min(review_counts) if review_counts else 0,
            "allItemsReviewedByTwo": len(reviewed) == len(items) and all(count >= 2 for count in review_counts),
            "majorityUsefulYes": consensus.count("yes"),
            "majorityUsefulNo": consensus.count("no"),
            "majorityUsefulRate": round(consensus.count("yes") / len(consensus), 6) if consensus else None,
            "binaryAgreementRate": round(sum(1 for value in agreements if value) / len(agreements), 6) if agreements else None,
            "majorityUsefulRate95CI": _cluster_bootstrap_interval(
                grouped_consensus,
                samples=bootstrap_samples,
                seed=seed + bucket_offset,
                unit="book" if packet_books else "item",
            ),
        }

    return {
        "metric": selection.get("metric"),
        "topRanked": summarize_bucket(buckets.get("top-ranked", []), 0),
        "seededRandom": summarize_bucket(buckets.get("seeded-random", []), 1),
    }


def _cluster_bootstrap_interval(
    grouped_values: Mapping[str, list[float]],
    *,
    samples: int,
    seed: int,
    unit: str,
) -> dict[str, object] | None:
    """Bootstrap cluster means without treating verses in one book as independent."""

    groups = [values for values in grouped_values.values() if values]
    if not groups or samples == 0:
        return None
    generator = random.Random(seed)
    rates: list[float] = []
    for _ in range(samples):
        sampled_groups = [generator.choice(groups) for _ in groups]
        values = [value for group in sampled_groups for value in group]
        rates.append(sum(values) / len(values))
    return {
        "samples": samples,
        "seed": seed,
        "unit": unit,
        "ci95": [_percentile(rates, 0.025), _percentile(rates, 0.975)],
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 6)
