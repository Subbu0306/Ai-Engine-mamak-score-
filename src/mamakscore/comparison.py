"""Deterministic comparison of two assessment versions."""

from .contracts import CategoryMovement, ComparisonRequest, ComparisonResult
from .errors import ErrorCode, ServiceError


def compare_assessments(request: ComparisonRequest) -> ComparisonResult:
    old, new = request.previous, request.current
    if old.application_id != new.application_id:
        raise ServiceError(
            ErrorCode.INVALID_REQUEST,
            "Assessments must belong to the same application.",
            field="application_id",
        )
    old_scores = {item.criterion_id: item.score for item in old.criterion_scores}
    new_scores = {item.criterion_id: item.score for item in new.criterion_scores}
    if (
        set(old_scores) != set(new_scores)
        or len(old_scores) != len(old.criterion_scores)
        or len(new_scores) != len(new.criterion_scores)
    ):
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Assessment category sets must match.")
    comparable = old.rubric_digest == new.rubric_digest
    return ComparisonResult(
        application_id=old.application_id,
        comparable=comparable,
        warning=None
        if comparable
        else "Rubric versions differ; score movement is not directly comparable.",
        categories=[
            CategoryMovement(
                criterion_id=i,
                previous_score=old_scores[i],
                current_score=new_scores[i],
                delta=new_scores[i] - old_scores[i],
            )
            for i in old_scores
        ],
        previous_mamak_score=old.mamak_score,
        current_mamak_score=new.mamak_score,
        mamak_score_delta=new.mamak_score - old.mamak_score,
        previous_band=old.band,
        current_band=new.band,
        resolved_missing_information=sorted(
            set(old.missing_information) - set(new.missing_information)
        ),
        new_missing_information=sorted(set(new.missing_information) - set(old.missing_information)),
    )
