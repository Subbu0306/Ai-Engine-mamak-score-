"""Deterministic financial and venture assessment scoring calculations."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from mamakscore.contracts import (
    BandResult,
    ConfidenceContainer,
    ConfidenceInputPayload,
    CriterionScore,
    ImprovementAction,
    ImprovementActionDraft,
)
from mamakscore.rubric import RubricDefinition


def calculate_mamak_score(
    criterion_scores: List[CriterionScore],
    rubric: RubricDefinition,
) -> Decimal:
    """Calculates the weighted MamakScore on a 0.0 - 100.0 scale using exact Decimal arithmetic."""
    weight_map: Dict[str, Decimal] = {c.id: Decimal(str(c.weight)) for c in rubric.criteria}
    total_weight = sum(weight_map.values()) or Decimal("100.0")

    weighted_sum = Decimal("0.0")
    for item in criterion_scores:
        score = Decimal(str(item.score))
        weight = weight_map.get(item.criterion_id, Decimal("0.0"))
        # Score is 0-10, scale to weight percentage (score / 10 * weight)
        weighted_sum += (score / Decimal("10.0")) * weight

    normalized_score = (weighted_sum / total_weight) * Decimal("100.0")
    return normalized_score.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def determine_band(score: Decimal) -> BandResult:
    """Assigns an institutional due diligence tier based on the calculated score."""
    val = float(score)
    if val >= 80.0:
        return BandResult(
            band_name="Strong Contender",
            label="Strong Contender",
            boundary_escalation=False,
            human_review_required=False,
        )
    elif val >= 65.0:
        return BandResult(
            band_name="Priority Consideration",
            label="Priority Consideration",
            boundary_escalation=False,
            human_review_required=True,
        )
    elif val >= 50.0:
        return BandResult(
            band_name="Validation Track",
            label="Validation Track",
            boundary_escalation=True,
            human_review_required=True,
        )
    else:
        return BandResult(
            band_name="Not Ready for Institutional Capital",
            label="Not Ready for Institutional Capital",
            boundary_escalation=False,
            human_review_required=True,
        )


# Direct alias expected by pipeline.py
classify_score = determine_band


def build_improvement_actions(
    actions: List[ImprovementActionDraft],
    criterion_scores: List[CriterionScore],
    rubric: RubricDefinition,
) -> List[ImprovementAction]:
    """Projects score delta improvements for each draft recommendation."""
    score_map: Dict[str, int] = {cs.criterion_id: cs.score for cs in criterion_scores}
    weight_map: Dict[str, Decimal] = {c.id: Decimal(str(c.weight)) for c in rubric.criteria}

    results: List[ImprovementAction] = []
    for a in actions:
        current_score = score_map.get(a.criterion_id, 0)
        target = a.target_score
        weight = weight_map.get(a.criterion_id, Decimal("10.0"))

        if target > current_score:
            score_diff = Decimal(str(target - current_score))
            projected = (score_diff / Decimal("10.0")) * weight
            gain = projected.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        else:
            gain = Decimal("0.0")

        results.append(
            ImprovementAction(
                action=a.action,
                criterion_id=a.criterion_id,
                target_score=target,
                priority=a.priority,
                projected_gain=gain,
            )
        )

    # Sort actions by highest potential score gain first
    results.sort(key=lambda x: x.projected_gain, reverse=True)
    return results


def calculate_mamak_confidence(
    payload: Optional[ConfidenceInputPayload] = None,
    n_verified: Optional[int] = None,
    verified_quotes_count: Optional[int] = None,
    has_financial_model: Optional[bool] = None,
    m_verified: Optional[int] = None,
    verified_financial_metrics_count: Optional[int] = None,
    d_discrepancies: Optional[int] = None,
    discrepancies_count: Optional[int] = None,
    d_total: Optional[int] = None,
    total_checks_count: Optional[int] = None,
    red_flags: Optional[List[Any]] = None,
    **kwargs: Any,
) -> ConfidenceContainer:
    """Calculates deterministic confidence calibration score supporting legacy & formal aliases."""
    # 1. Resolve aliases
    n = (
        n_verified
        if n_verified is not None
        else (verified_quotes_count if verified_quotes_count is not None else kwargs.get("verified_quotes", 0))
    )
    has_model = (
        has_financial_model
        if has_financial_model is not None
        else kwargs.get("has_model", False)
    )
    m = (
        m_verified
        if m_verified is not None
        else (
            verified_financial_metrics_count
            if verified_financial_metrics_count is not None
            else kwargs.get("verified_metrics", 0)
        )
    )
    d_disc = (
        d_discrepancies
        if d_discrepancies is not None
        else (
            discrepancies_count
            if discrepancies_count is not None
            else kwargs.get("discrepancies", 0)
        )
    )
    d_tot = (
        d_total
        if d_total is not None
        else (
            total_checks_count
            if total_checks_count is not None
            else kwargs.get("total_checks", 0)
        )
    )
    rf_list = red_flags if red_flags is not None else kwargs.get("flags", [])

    if payload is not None:
        n = payload.n_verified
        has_model = payload.has_financial_model
        m = payload.m_verified
        d_disc = payload.d_discrepancies
        d_tot = payload.d_total
        rf_list = payload.red_flags

    # Invariant safety: prevent phantom verified metrics if no financial model is attached
    if not has_model:
        m = 0

    # 2. Rubric quote coverage score G (0.0 to 1.0) across 9 canonical criteria
    g_score = min(1.0, max(0.0, float(n) / 9.0))

    # 3. Financial model verification F (0.0 to 1.0)
    if not has_model:
        f_score = 0.5  # Neutral baseline for early pre-seed decks without spreadsheets
    else:
        f_score = min(1.0, max(0.0, float(m) / 6.0))

    # 4. Consistency factor C (0.0 to 1.0)
    if d_tot == 0:
        c_score = 1.0
    else:
        discrepancy_ratio = min(1.0, float(d_disc) / float(d_tot))
        c_score = max(0.0, 1.0 - discrepancy_ratio)

    # 5. Red flag severity penalty product (Phi)
    phi = 1.0
    for flag in rf_list:
        sev = getattr(flag, "severity", "medium") if hasattr(flag, "severity") else "medium"
        if isinstance(sev, str):
            sev = sev.lower()
        if sev == "critical":
            phi *= (1.0 - 0.50)
        elif sev == "high":
            phi *= (1.0 - 0.25)
        elif sev == "medium":
            phi *= (1.0 - 0.12)
        else:
            phi *= (1.0 - 0.04)

    # Composite confidence score
    raw_confidence = (0.50 * g_score + 0.30 * f_score + 0.20 * c_score) * phi * 100.0
    final_confidence = round(max(0.0, min(100.0, raw_confidence)), 1)

    return ConfidenceContainer(
        score=final_confidence,
        mamak_confidence=final_confidence,
        status="PROVISIONAL_NOT_CLIENT_APPROVED",
        breakdown={
            "n_verified_quotes": n,
            "grounding_factor": round(g_score, 3),
            "financial_factor": round(f_score, 3),
            "consistency_factor": round(c_score, 3),
            "penalty_multiplier": round(phi, 3),
            "has_financial_model": has_model,
        },
    )


__all__ = [
    "calculate_mamak_score",
    "determine_band",
    "classify_score",
    "build_improvement_actions",
    "calculate_mamak_confidence",
]