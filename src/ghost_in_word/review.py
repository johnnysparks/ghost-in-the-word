from __future__ import annotations

from collections import Counter, defaultdict
import random
from typing import Iterable, Mapping

USEFUL_VALUES = {"yes", "no", "uncertain"}
DIFFERENCE_TYPES = {"wording", "likely meaning", "source-text issue", "alignment issue", "unclear"}
CONFIDENCE_VALUES = {"low", "medium", "high"}


def _unit_value(unit: Mapping[str, object], camel: str, snake: str) -> object:
    return unit[camel] if camel in unit else unit.get(snake)


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


def _select_candidates(
    comparison: Mapping[str, object],
    *,
    count: int,
    metric_field: str,
    seed: int,
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]], int]:
    if count < 1:
        raise ValueError("review sample count must be positive")
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
    missing_ids = [unit for unit in candidates if not isinstance(unit.get("id"), str) or not unit.get("id")]
    if missing_ids:
        raise ValueError("every review candidate must have a non-empty id")
    ids = [str(unit["id"]) for unit in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("review candidates must have unique ids")

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
) -> dict[str, object]:
    """Aggregate independent review documents without hiding abstentions."""

    by_item: dict[str, list[dict[str, object]]] = defaultdict(list)
    reviewer_counts: Counter[str] = Counter()
    documents = list(review_documents)
    seen_reviewers: set[str] = set()
    for document in documents:
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
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"reviewer {reviewer!r} has an item without an id")
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
        report["selection"] = _summarize_selection(item_reports, selection_key)
    return report


def _summarize_selection(item_reports: list[dict[str, object]], selection_key: Mapping[str, object]) -> dict[str, object]:
    if selection_key.get("kind") != "blind-review-key":
        raise ValueError("selection key must have kind blind-review-key")
    key_items = selection_key.get("items")
    if not isinstance(key_items, list):
        raise ValueError("selection key must contain an items array")
    report_by_id = {str(item["id"]): item for item in item_reports}
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

    def summarize_bucket(items: list[dict[str, object]]) -> dict[str, object]:
        reviewed = [report_by_id[item["id"]] for item in items if item["id"] in report_by_id]
        consensus = [str(item["majorityUseful"]) for item in reviewed if item["majorityUseful"] in {"yes", "no"}]
        agreements = [item["binaryAgreement"] for item in reviewed if isinstance(item.get("binaryAgreement"), bool)]
        return {
            "selectedCount": len(items),
            "reviewedCount": len(reviewed),
            "unreviewedCount": len(items) - len(reviewed),
            "majorityUsefulYes": consensus.count("yes"),
            "majorityUsefulNo": consensus.count("no"),
            "majorityUsefulRate": round(consensus.count("yes") / len(consensus), 6) if consensus else None,
            "binaryAgreementRate": round(sum(1 for value in agreements if value) / len(agreements), 6) if agreements else None,
        }

    selection = selection_key.get("selection")
    selection = dict(selection) if isinstance(selection, Mapping) else {}
    return {
        "metric": selection.get("metric"),
        "topRanked": summarize_bucket(buckets.get("top-ranked", [])),
        "seededRandom": summarize_bucket(buckets.get("seeded-random", [])),
    }
