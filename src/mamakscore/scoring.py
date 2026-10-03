"""Deterministic MamakScore, routing bands, and improvement impacts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal

from .contracts import BandResult, CriterionScore, ImprovementAction, ImprovementActionDraft
from .errors import ErrorCode, ServiceError
from .rubric import RubricDefinition

CLIENT_BANDS = [
    (Decimal("90"), "Due diligence recommended"),
    (Decimal("75"), "Strong candidate"),
    (Decimal("60"), "Potential consideration"),
    (Decimal("40"), "Needs significant validation"),
    (Decimal("0"), "Not ready"),
]


def calculate_mamak_score(scores: Sequence[CriterionScore], rubric: RubricDefinition) -> Decimal:
    by_id = {item.criterion_id: item for item in scores}
    expected = {item.id for item in rubric.criteria}
    if set(by_id) != expected or len(by_id) != len(scores):
        raise ServiceError(
            ErrorCode.INVALID_MODEL_OUTPUT, "Exactly nine unique category scores are required."
        )
    total = sum(Decimal(by_id[item.id].score) * Decimal(item.weight) for item in rubric.criteria)
    return (total / Decimal(10)).quantize(Decimal("0.1"))


def classify_score(score: Decimal) -> BandResult:
    if not Decimal(0) <= score <= Decimal(100):
        raise ValueError("MamakScore must be between 0 and 100")
    label = next(label for minimum, label in CLIENT_BANDS if score >= minimum)
    escalation = any(
        Decimal(0) < boundary - score <= Decimal(5)
        for boundary, _ in CLIENT_BANDS
        if boundary > score
    )
    return BandResult(label=label, boundary_escalation=escalation, human_review_required=True)


def build_improvement_actions(
    drafts: Sequence[ImprovementActionDraft],
    scores: Sequence[CriterionScore],
    rubric: RubricDefinition,
) -> list[ImprovementAction]:
    current = {item.criterion_id: item.score for item in scores}
    weights = {item.id: item.weight for item in rubric.criteria}
    seen: set[str] = set()
    actions: list[tuple[int, ImprovementAction]] = []
    for index, draft in enumerate(drafts):
        key = re.sub(r"\s+", " ", draft.action).strip().casefold()
        if key in seen:
            continue
        if (
            draft.criterion_id not in current
            or not current[draft.criterion_id] < draft.target_score <= 10
        ):
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                "Improvement target must raise a known category score.",
            )
        seen.add(key)
        gain = (
            Decimal(draft.target_score - current[draft.criterion_id])
            * Decimal(weights[draft.criterion_id])
            / Decimal(10)
        ).quantize(Decimal("0.1"))
        actions.append((index, ImprovementAction(**draft.model_dump(), projected_gain=gain)))
    return [
        item for _, item in sorted(actions, key=lambda pair: (-pair[1].projected_gain, pair[0]))
    ]
