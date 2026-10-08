"""Comparison engine for assessing pitch deck revisions and before/after improvements."""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from mamakscore.contracts import (
    AssessmentSummary,
    ComparableDelta,
    ComparisonRequest,
    ComparisonResult,
)
from mamakscore.errors import ErrorCode, ServiceError


def compare_assessments(request: ComparisonRequest) -> ComparisonResult:
    """Compares two assessments, computing score differences and rubric warnings."""
    prev = request.previous
    curr = request.current

    if prev.application_id != curr.application_id:
        raise ServiceError(
            ErrorCode.APPLICATION_MISMATCH,
            f"Cannot compare assessments for different applications: '{prev.application_id}' vs '{curr.application_id}'.",
        )

    prev_missing = set(getattr(prev, "missing_information", []) or [])
    curr_missing = set(getattr(curr, "missing_information", []) or [])
    resolved = sorted(list(prev_missing - curr_missing))
    new_missing = sorted(list(curr_missing - prev_missing))

    warnings: List[str] = []
    comparable = True
    if prev.rubric_version != curr.rubric_version or prev.rubric_digest != curr.rubric_digest:
        comparable = False
        warnings.append(
            f"Rubric versions differ between assessments ({prev.rubric_version} vs {curr.rubric_version})."
        )

    delta = curr.mamak_score - prev.mamak_score
    delta_val = ComparableDelta(f"{delta:g}")

    prev_scores = {s.criterion_id: s.score for s in prev.criterion_scores}
    curr_scores = {s.criterion_id: s.score for s in curr.criterion_scores}

    criterion_deltas: Dict[str, Any] = {}
    all_keys = set(prev_scores.keys()) | set(curr_scores.keys())
    for k in sorted(all_keys):
        p_val = prev_scores.get(k, 0)
        c_val = curr_scores.get(k, 0)
        criterion_deltas[k] = {
            "previous": p_val,
            "current": c_val,
            "delta": c_val - p_val,
        }

    return ComparisonResult(
        comparable=comparable,
        application_id=curr.application_id,
        mamak_score_delta=delta_val,
        previous_score=f"{prev.mamak_score:g}",
        current_score=f"{curr.mamak_score:g}",
        previous_band=prev.band,
        current_band=curr.band,
        criterion_deltas=criterion_deltas,
        resolved_missing_information=resolved,
        new_missing_information=new_missing,
        categories=criterion_deltas,
        warnings=warnings,
    )