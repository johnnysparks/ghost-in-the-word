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

    ranked = sorted(candidates, key=lambda unit: (-float(unit[metric_field]), str(unit.get("id", ""))))
    selected_count = min(count, len(ranked))
    high_count = min(max(1, selected_count // 2), selected_count)
    selected = ranked[:high_count]
    remaining = ranked[high_count:]
    if selected_count > high_count:
        generator = random.Random(seed)
        selected.extend(generator.sample(remaining, selected_count - high_count))
    random.Random(seed + 1).shuffle(selected)

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
            "candidateCount": len(candidates),
        },
        "items": packet_items,
    }


def summarize_reviews(review_documents: Iterable[Mapping[str, object]]) -> dict[str, object]:
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
    return {
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
