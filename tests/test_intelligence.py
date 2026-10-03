from pathlib import Path

import pytest

from mamakscore.contracts import (
    AssessmentDraft,
    CriterionScore,
    ImprovementActionDraft,
    InvestorQuestion,
)
from mamakscore.errors import ServiceError
from mamakscore.intelligence import validate_assessment_draft
from mamakscore.rubric import load_rubric

R = load_rubric(Path(__file__).parents[1] / "src/mamakscore/data/mamakscore-v3.yaml")


def score(c):
    return CriterionScore(
        criterion_id=c.id,
        score=4,
        justification="Reason",
        evidence_quote="Evidence line",
        source_file="deck.pdf",
        confidence="low",
    )


def draft():
    return AssessmentDraft(
        criterion_scores=[score(c) for c in R.criteria],
        investor_questions=[
            InvestorQuestion(question=f"Question {i}?", criterion_ids=[R.criteria[i % 9].id])
            for i in range(5)
        ],
        improvement_actions=[
            ImprovementActionDraft(
                action="Add customer interview evidence",
                criterion_id="market",
                target_score=6,
                priority="high",
            )
        ],
    )


def test_valid_draft_passes():
    assert validate_assessment_draft(draft(), R) == draft()


def test_missing_or_duplicate_criterion_fails():
    bad = draft().model_copy(update={"criterion_scores": draft().criterion_scores[:-1]})
    with pytest.raises(ServiceError):
        validate_assessment_draft(bad, R)


def test_question_count_and_unknown_reference_fail():
    with pytest.raises(ServiceError):
        validate_assessment_draft(
            draft().model_copy(update={"investor_questions": draft().investor_questions[:4]}), R
        )
    questions = draft().investor_questions
    questions[0] = questions[0].model_copy(update={"criterion_ids": ["unknown"]})
    with pytest.raises(ServiceError):
        validate_assessment_draft(draft().model_copy(update={"investor_questions": questions}), R)


def test_empty_evidence_requires_zero_and_exact_reason():
    items = draft().criterion_scores
    items[0] = items[0].model_copy(update={"evidence_quote": ""})
    with pytest.raises(ServiceError):
        validate_assessment_draft(draft().model_copy(update={"criterion_scores": items}), R)
