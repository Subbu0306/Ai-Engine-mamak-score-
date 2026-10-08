"""Intelligence validation: verifies LLM output draft meets strict rubric requirements."""

from typing import Set
from mamakscore.contracts import AssessmentDraft
from mamakscore.errors import ErrorCode, ServiceError
from mamakscore.rubric import RubricDefinition


def validate_assessment_draft(
    draft: AssessmentDraft,
    rubric: RubricDefinition,
) -> AssessmentDraft:
    """Validates an AssessmentDraft against the rubric constraints:
    - Must contain exactly the 9 rubric criteria (no duplicates, no omissions)
    - Empty evidence quote is only valid if score == 0 with an exact rationale
    - Investor questions count must be between 5 and 10 with unique strings
    - Improvement actions must target known rubric criteria and set target > current
    - Red flags and actions must only reference known criteria
    """
    rubric_ids: Set[str] = {c.id for c in rubric.criteria}
    score_map = {}

    # 1. Criteria count & uniqueness check
    for item in draft.criterion_scores:
        if item.criterion_id not in rubric_ids:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Unknown criterion_id '{item.criterion_id}' in assessment draft.",
                field="criterion_scores",
            )
        if item.criterion_id in score_map:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Duplicate criterion_id '{item.criterion_id}' found in assessment draft.",
                field="criterion_scores",
            )
        score_map[item.criterion_id] = item.score

    if set(score_map.keys()) != rubric_ids:
        missing = rubric_ids - set(score_map.keys())
        raise ServiceError(
            ErrorCode.INVALID_MODEL_OUTPUT,
            f"Assessment draft is missing required criteria: {missing}",
            field="criterion_scores",
        )

    # 2. Empty evidence quote rules
    for item in draft.criterion_scores:
            if not (item.evidence_quote or "").strip() and item.score != 0:
                raise ServiceError(
                    ErrorCode.INVALID_MODEL_OUTPUT,
                    f"Criterion '{item.criterion_id}' has score {item.score} but empty evidence.",
                    field="criterion_scores",
                )

    # 3. Investor questions constraints (5 to 10 unique questions)
    # 3. Investor questions constraints (5 to 10 unique questions)
    q_count = len(draft.investor_questions)
    if not (5 <= q_count <= 10):
        raise ServiceError(
            ErrorCode.INVALID_MODEL_OUTPUT,
            f"Investor questions count must be between 5 and 10, got {q_count}.",
            field="investor_questions",
        )
    
    # Check uniqueness by string representation
    question_texts = [q.question if hasattr(q, "question") else str(q) for q in draft.investor_questions]
    if len(set(question_texts)) != q_count:
        raise ServiceError(
            ErrorCode.INVALID_MODEL_OUTPUT,
            "Investor questions must be unique without duplicates.",
            field="investor_questions",
        )

    # Validate that question criterion references match rubric criteria
    for q in draft.investor_questions:
        if hasattr(q, "criterion_ids"):
            for cid in q.criterion_ids:
                if cid not in rubric_ids:
                    raise ServiceError(
                        ErrorCode.INVALID_MODEL_OUTPUT,
                        f"Investor question references unknown criterion '{cid}'.",
                        field="investor_questions",
                    )

    # 4. Improvement action targets
    for action in draft.improvement_actions:
        if action.criterion_id not in rubric_ids:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Improvement action targets unknown criterion '{action.criterion_id}'.",
                field="improvement_actions",
            )
        current_score = score_map.get(action.criterion_id, 0)
        if action.target_score <= current_score:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Improvement action target score ({action.target_score}) must be greater than current score ({current_score}).",
                field="improvement_actions",
            )

    # 5. Red flags criteria references
    for flag in draft.red_flags:
        # If flag includes an explicit criterion_id tag, verify it
        cid = getattr(flag, "criterion_id", None)
        if cid and cid not in rubric_ids:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                f"Red flag references unknown criterion '{cid}'.",
                field="red_flags",
            )
    

    return draft