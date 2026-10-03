# Semantic validation beyond structural Pydantic checks.
import re

from .contracts import AssessmentDraft
from .errors import ErrorCode, ServiceError
from .rubric import RubricDefinition


def _fail(message: str) -> None:
    raise ServiceError(ErrorCode.INVALID_MODEL_OUTPUT, message, retryable=False, status_code=502)


def validate_assessment_draft(draft: AssessmentDraft, rubric: RubricDefinition) -> AssessmentDraft:
    expected = {c.id for c in rubric.criteria}
    ids = [s.criterion_id for s in draft.criterion_scores]
    if len(ids) != 9 or set(ids) != expected or len(set(ids)) != len(ids):
        _fail("Model output must contain the exact nine unique criteria.")
    current = {s.criterion_id: s.score for s in draft.criterion_scores}
    for score in draft.criterion_scores:
        if not score.evidence_quote.strip() and (
            score.score != 0 or score.justification.strip() != rubric.not_stated_justification
        ):
            _fail("Empty evidence is valid only for a not-addressed score of zero.")
    if not 5 <= len(draft.investor_questions) <= 10:
        _fail("Model output must contain five to ten investor questions.")
    normalized = []
    for question in draft.investor_questions:
        if not question.criterion_ids or not set(question.criterion_ids) <= expected:
            _fail("Investor question references an unknown criterion.")
        normalized.append(re.sub(r"\s+", " ", question.question).strip().casefold())
    if len(set(normalized)) != len(normalized):
        _fail("Investor questions must be unique.")
    for flag in draft.red_flags:
        if not set(flag.criterion_ids) <= expected:
            _fail("Red flag references an unknown criterion.")
    for action in draft.improvement_actions:
        if (
            action.criterion_id not in expected
            or action.target_score <= current[action.criterion_id]
        ):
            _fail("Improvement action must increase a known category score.")
    return draft
