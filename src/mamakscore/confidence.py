"""MamakConfidence calculation engine strictly adhering to v2.0 hardened specification."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


SEVERITY_PENALTIES = {
    "low": Decimal("0.04"),
    "medium": Decimal("0.12"),
    "high": Decimal("0.25"),
    "critical": Decimal("0.50"),
}


class ConfidenceInput(BaseModel):
    verified_quotes_count: int = Field(default=0, ge=0)
    total_verified_quotes: int = Field(default=0, ge=0)
    calculated_metrics_count: int = Field(default=0, ge=0)
    total_comparisons: int = Field(default=0, ge=0)
    contradictions_count: int = Field(default=0, ge=0)
    red_flags: List[Any] = Field(default_factory=list)
    has_financial_model: bool = False
    is_pre_revenue: bool = False


def calculate_mamak_confidence(*args: Any, **kwargs: Any) -> float:
    """Calculates MamakConfidence without moral-hazard fallbacks and with exact Decimal precision."""
    payload = args[0] if args and isinstance(args[0], (ConfidenceInput, dict)) else kwargs.get("payload")

    if isinstance(payload, ConfidenceInput):
        n_categories = payload.verified_quotes_count
        total_quotes = payload.total_verified_quotes or payload.verified_quotes_count
        m_verified = payload.calculated_metrics_count
        d_total = payload.total_comparisons
        d_contradictions = payload.contradictions_count
        rf_list = payload.red_flags
        has_model = payload.has_financial_model
    elif isinstance(payload, dict):
        n_categories = payload.get("verified_quotes_count") or payload.get("n_verified", 0)
        total_quotes = payload.get("total_verified_quotes") or n_categories
        m_verified = payload.get("calculated_metrics_count") or payload.get("m_verified", 0)
        d_total = payload.get("total_comparisons") or payload.get("d_total", 0)
        d_contradictions = payload.get("contradictions_count") or payload.get("d_discrepancies", 0)
        rf_list = payload.get("red_flags", [])
        has_model = payload.get("has_financial_model", False)
    else:
        n_categories = kwargs.get("verified_quotes_count") or kwargs.get("n_verified") or 0
        total_quotes = kwargs.get("total_verified_quotes") or n_categories
        has_model = kwargs.get("has_financial_model") or kwargs.get("has_model") or False
        m_verified = kwargs.get("calculated_metrics_count") or kwargs.get("m_verified") or 0
        d_total = kwargs.get("total_comparisons") or kwargs.get("total_checks_count") or kwargs.get("d_total") or 0
        d_contradictions = kwargs.get("contradictions_count") or kwargs.get("discrepancies_count") or 0
        rf_list = kwargs.get("red_flags") or kwargs.get("flags") or []

    # 1. Grounding (G): 75% category coverage + 25% citation depth (saturating at 18)
    cat_ratio = Decimal(min(max(n_categories, 0), 9)) / Decimal("9")
    quote_depth = Decimal(min(max(total_quotes, 0), 18)) / Decimal("18")
    g_score = (Decimal("0.75") * cat_ratio) + (Decimal("0.25") * quote_depth)

    # 2. Financial Completeness (F): Missing model gives 0.0 (NO FREE MARKS)
    if not has_model:
        f_score = Decimal("0.0")
    else:
        f_score = Decimal(min(max(m_verified, 0), 6)) / Decimal("6")

    # 3. Consistency (C): requires >= 3 comparisons, otherwise INACTIVE with weight redistribution
    if d_total >= 3:
        c_score = Decimal("1.0") - (Decimal(d_contradictions) / Decimal(d_total))
        c_score = max(Decimal("0.0"), min(Decimal("1.0"), c_score))
        w_g = Decimal("0.40")
        w_f = Decimal("0.35")
        w_c = Decimal("0.25")
        base_score = (w_g * g_score) + (w_f * f_score) + (w_c * c_score)
    else:
        # Dynamic redistribution of w_c to G and F
        w_g = Decimal("0.40") / Decimal("0.75")
        w_f = Decimal("0.35") / Decimal("0.75")
        base_score = (w_g * g_score) + (w_f * f_score)

    # 4. Tiered Red Flag Multipliers: max 25 flags, floor at 0.02
    phi = Decimal("1.0")
    for item in rf_list[:25]:
        sev = (getattr(item, "severity", None) or (item.get("severity") if isinstance(item, dict) else "medium") or "medium").lower()
        p_k = SEVERITY_PENALTIES.get(sev, Decimal("0.12"))
        phi *= (Decimal("1.0") - p_k)

    phi = max(Decimal("0.02"), phi)

    # 5. Composite Final Confidence
    confidence = base_score * phi * Decimal("100.0")
    confidence = max(Decimal("0.0"), min(Decimal("100.0"), confidence))

    return float(confidence.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


__all__ = ["calculate_mamak_confidence", "ConfidenceInput", "SEVERITY_PENALTIES"]