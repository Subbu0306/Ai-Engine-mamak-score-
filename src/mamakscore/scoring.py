"""Rubric aggregation, score banding, and improvement gain calculation."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple
from mamakscore.contracts import (
    BandResult,
    CriterionScore,
    ImprovementAction,
    ImprovementActionDraft,
)
from mamakscore.rubric import RubricDefinition
from mamakscore.errors import ErrorCode, ServiceError

# Client-defined evaluation bands
CLIENT_BANDS: List[Tuple[Decimal, str]] = [
    (Decimal("90.0"), "Due diligence recommended"),
    (Decimal("75.0"), "Strong candidate"),
    (Decimal("60.0"), "Potential consideration"),
    (Decimal("40.0"), "Needs significant validation"),
    (Decimal("0.0"), "Not ready"),
]


def classify_score(score: Decimal) -> BandResult:
    """Assigns score band and flags whether score is within 5 points of the next boundary."""
    if not (Decimal("0.0") <= score <= Decimal("100.0")):
        raise ValueError("MamakScore must be between 0 and 100")

    # Match first band from top down
    label = next(name for threshold, name in CLIENT_BANDS if score >= threshold)

    # Escalation: score is within 5 points (0 < boundary - score <= 5) of a higher tier
    escalation = any(
        Decimal("0.0") < boundary - score <= Decimal("5.0")
        for boundary, _ in CLIENT_BANDS
        if boundary > score
    )

    return BandResult(
        band_name=label,
        label=label,
        boundary_escalation=escalation,
        human_review_required=True,
    )


def calculate_mamak_score(
    scores: List[CriterionScore], rubric: RubricDefinition
) -> Decimal:
    """Calculates weighted MamakScore sum: sum(score * weight / 10)."""
    rubric_ids = {c.id for c in rubric.criteria}
    provided_ids = [s.criterion_id for s in scores]

    # Validate exact match without missing or duplicates
    if len(provided_ids) != len(set(provided_ids)):
        raise ServiceError(
            ErrorCode.INVALID_MODEL_OUTPUT,
            "Duplicate criteria scores provided in assessment draft.",
        )
    if set(provided_ids) != rubric_ids:
        raise ServiceError(
            ErrorCode.INVALID_MODEL_OUTPUT,
            f"Scores must match the 9 rubric criteria. Missing: {rubric_ids - set(provided_ids)}",
        )

    weight_map = {c.id: Decimal(str(c.weight)) for c in rubric.criteria}
    total = Decimal("0.0")

    for item in scores:
        w = weight_map[item.criterion_id]
        total += (Decimal(str(item.score)) * w) / Decimal("10.0")

    return total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def build_improvement_actions(
    drafts: List[ImprovementActionDraft],
    current_scores: List[CriterionScore],
    rubric: RubricDefinition,
) -> List[ImprovementAction]:
    score_map = {s.criterion_id: s.score for s in current_scores}
    weight_map = {c.id: Decimal(str(c.weight)) for c in rubric.criteria}

    actions: List[Tuple[int, ImprovementAction]] = []

    for idx, draft in enumerate(drafts):
        if draft.criterion_id not in score_map:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Unknown criterion_id '{draft.criterion_id}' in improvement action.",
            )
        current_score = score_map[draft.criterion_id]
        if draft.target_score <= current_score or draft.target_score > 10:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Target score ({draft.target_score}) must be greater than current score ({current_score}) and <= 10.",
            )

        weight = weight_map.get(draft.criterion_id, Decimal("0.0"))
        gain = (Decimal(str(draft.target_score - current_score)) * weight) / Decimal("10.0")

        action_obj = ImprovementAction(
            action=draft.action,
            criterion_id=draft.criterion_id,
            target_score=draft.target_score,
            priority=draft.priority,
            projected_gain=gain.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
        )
        actions.append((idx, action_obj))

    actions.sort(key=lambda pair: (-pair[1].projected_gain, pair[0]))
    return [item for _, item in actions]