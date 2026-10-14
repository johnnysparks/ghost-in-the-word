"""Latent reference estimates for a translation panel.

The reference in this module is an estimated representation of a named panel,
not an observed language-independent meaning or a translation-quality label.
Vectors are normalized before aggregation so the result is defined in the same
cosine-distance space as the comparison artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math
from typing import Iterable, Mapping, Sequence

from .embeddings import cosine_distance


@dataclass(frozen=True)
class ReferenceEstimate:
    """A weighted panel centroid and diagnostics for one passage."""

    vector: tuple[float, ...]
    included_editions: tuple[str, ...]
    excluded_editions: tuple[str, ...]
    weights: tuple[tuple[str, float], ...]
    medoid_edition: str
    dispersion: float
    distances: tuple[tuple[str, float], ...]
    pairwise_distances: tuple[tuple[str, str, float], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "referenceVector": list(self.vector),
            "includedEditions": list(self.included_editions),
            "excludedEditions": list(self.excluded_editions),
            "weights": {edition: weight for edition, weight in self.weights},
            "medoidEdition": self.medoid_edition,
            "dispersion": self.dispersion,
            "distanceToReference": {edition: distance for edition, distance in self.distances},
            "pairwiseDistances": [
                {"leftEdition": left, "rightEdition": right, "distance": distance}
                for left, right, distance in self.pairwise_distances
            ],
        }


def estimate_reference(
    vectors: Mapping[str, Sequence[float]],
    *,
    exclude: Iterable[str] = (),
    weights: Mapping[str, float] | None = None,
    families: Mapping[str, str] | None = None,
    family_cap: float | None = 1.0,
) -> ReferenceEstimate:
    """Estimate a normalized weighted reference vector for one passage.

    ``exclude`` should contain the editions being compared. This prevents the
    compared pair from defining its own midpoint and then appearing equally
    close to that midpoint. ``families`` groups related editions; when a cap is
    supplied, all editions in one family receive at most that combined weight,
    distributed in proportion to their requested weights.
    """

    if not vectors:
        raise ValueError("a reference panel needs at least one vector")
    excluded = {str(edition) for edition in exclude}
    unknown_excluded = excluded.difference(vectors)
    if unknown_excluded:
        raise ValueError(f"excluded editions are not in the panel: {sorted(unknown_excluded)}")
    included = tuple(sorted(edition for edition in vectors if edition not in excluded))
    if not included:
        raise ValueError("excluding the compared editions leaves no reference panel")

    normalized = {edition: _normalize(vector) for edition, vector in vectors.items()}
    dimensions = {len(vector) for vector in normalized.values()}
    if len(dimensions) != 1:
        raise ValueError("reference vectors must have matching dimensions")
    included_vectors = {edition: normalized[edition] for edition in included}
    effective = _effective_weights(included, weights=weights, families=families, family_cap=family_cap)
    total_weight = sum(effective.values())
    centroid = _normalize(
        [
            sum(effective[edition] * included_vectors[edition][index] for edition in included) / total_weight
            for index in range(len(next(iter(included_vectors.values()))))
        ]
    )
    distances = {edition: cosine_distance(included_vectors[edition], centroid) for edition in included}
    pairwise_distances = tuple(
        (left, right, cosine_distance(included_vectors[left], included_vectors[right]))
        for left, right in combinations(included, 2)
    )
    dispersion = round(sum(effective[edition] * distances[edition] for edition in included) / total_weight, 6)
    medoid = min(included, key=lambda edition: (_medoid_cost(edition, included_vectors, effective), edition))
    return ReferenceEstimate(
        vector=tuple(round(value, 9) for value in centroid),
        included_editions=included,
        excluded_editions=tuple(sorted(excluded)),
        weights=tuple((edition, round(effective[edition], 9)) for edition in included),
        medoid_edition=medoid,
        dispersion=dispersion,
        distances=tuple((edition, distances[edition]) for edition in included),
        pairwise_distances=pairwise_distances,
    )


def distance_to_reference(vector: Sequence[float], reference: Sequence[float]) -> float:
    """Return the same bounded cosine distance used by comparison artifacts."""

    return cosine_distance(_normalize(vector), _normalize(reference))


def _normalize(vector: Sequence[float]) -> tuple[float, ...]:
    if not vector:
        raise ValueError("embedding vectors cannot be empty")
    values = tuple(float(value) for value in vector)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("embedding vectors must contain only finite numbers")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise ValueError("embedding vectors cannot have zero magnitude")
    return tuple(value / norm for value in values)


def _effective_weights(
    editions: Sequence[str],
    *,
    weights: Mapping[str, float] | None,
    families: Mapping[str, str] | None,
    family_cap: float | None,
) -> dict[str, float]:
    if family_cap is not None and (not math.isfinite(family_cap) or family_cap <= 0):
        raise ValueError("family_cap must be positive when supplied")
    requested: dict[str, float] = {}
    for edition in editions:
        value = 1.0 if weights is None else float(weights.get(edition, 1.0))
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"weight for {edition} must be positive and finite")
        requested[edition] = value
    if not families or family_cap is None:
        return requested
    groups: dict[str, list[str]] = {}
    for edition in editions:
        family = str(families.get(edition, edition))
        groups.setdefault(family, []).append(edition)
    effective: dict[str, float] = {}
    for members in groups.values():
        total = sum(requested[edition] for edition in members)
        scale = min(1.0, family_cap / total)
        for edition in members:
            effective[edition] = requested[edition] * scale
    return effective


def _medoid_cost(edition: str, vectors: Mapping[str, Sequence[float]], weights: Mapping[str, float]) -> float:
    others = [candidate for candidate in vectors if candidate != edition]
    if not others:
        return 0.0
    denominator = sum(weights[candidate] for candidate in others)
    return sum(weights[candidate] * cosine_distance(vectors[edition], vectors[candidate]) for candidate in others) / denominator
