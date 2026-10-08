"""Deterministic confidence calculation module for MamakScore AI."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional


def calculate_mamak_confidence(
    verified_quotes_count: int,
    calculated_metrics_count: int,
    contradictions_count: int,
    total_comparisons: int,
    red_flags: Optional[List[str]] = None,
    has_financial_model: bool = True,
    expected_quotes_target: int = 18,
    total_metrics_target: int = 6,
) -> float:
    if red_flags is None:
        red_flags = []

    # 1. Evidence Grounding (G): Capped strictly at 1.0
    g = min(1.0, max(0.0, verified_quotes_count / max(1, expected_quotes_target)))

    # 2. Financial Model Verification (F)
    if has_financial_model:
        f = min(1.0, max(0.0, calculated_metrics_count / max(1, total_metrics_target)))
    else:
        f = 0.15

    # 3. Cross-Document Consistency (C)
    if has_financial_model and total_comparisons > 0:
        c = max(0.0, 1.0 - (contradictions_count / total_comparisons))
    else:
        c = 0.50

    base = (0.35 * g) + (0.35 * f) + (0.30 * c)

    # 4. Feasibility Red-Flag Penalty Multiplier
    prod = 1.0
    for _ in red_flags:
        prod *= (1.0 - 0.15)
    penalty_multiplier = max(0.40, prod)

    raw_score = base * penalty_multiplier * 100.0
    d_score = Decimal(str(raw_score)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return float(d_score)


calculate_confidence = calculate_mamak_confidence


def get_confidence_breakdown(
    verified_quotes_count: int,
    calculated_metrics_count: int,
    contradictions_count: int,
    total_comparisons: int,
    red_flags: Optional[List[str]] = None,
    has_financial_model: bool = True,
) -> Dict[str, Any]:
    if red_flags is None:
        red_flags = []

    g = min(1.0, max(0.0, verified_quotes_count / 18))
    f = min(1.0, max(0.0, calculated_metrics_count / 6)) if has_financial_model else 0.15
    c = max(0.0, 1.0 - (contradictions_count / total_comparisons)) if (has_financial_model and total_comparisons > 0) else 0.50

    prod = 1.0
    for _ in red_flags:
        prod *= 0.85
    penalty_multiplier = max(0.40, prod)

    final_score = calculate_mamak_confidence(
        verified_quotes_count=verified_quotes_count,
        calculated_metrics_count=calculated_metrics_count,
        contradictions_count=contradictions_count,
        total_comparisons=total_comparisons,
        red_flags=red_flags,
        has_financial_model=has_financial_model,
    )

    return {
        "mamak_confidence": final_score,
        "grounding_score": round(g, 4),
        "financial_completeness": round(f, 4),
        "consistency_score": round(c, 4),
        "penalty_multiplier": round(penalty_multiplier, 4),
        "red_flags_detected": len(red_flags),
    }