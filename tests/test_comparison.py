from decimal import Decimal
from pathlib import Path

import pytest

from mamakscore.comparison import compare_assessments
from mamakscore.contracts import (
    AssessmentSummary,
    ComparisonRequest,
    CriterionScore,
    ImprovementActionDraft,
)
from mamakscore.errors import ServiceError
from mamakscore.rubric import load_rubric
from mamakscore.scoring import build_improvement_actions

R = load_rubric(Path(__file__).parents[1] / "src/mamakscore/data/mamakscore-v3.yaml")


def scores(value):
    return [
        CriterionScore(
            criterion_id=c.id,
            score=value,
            justification="Reason",
            evidence_quote="Evidence",
            source_file="deck.pdf",
            confidence="high",
        )
        for c in R.criteria
    ]


def summary(app, value, digest="same", missing=None):
    return AssessmentSummary(
        application_id=app,
        rubric_version="3.0",
        rubric_digest=digest,
        criterion_scores=scores(value),
        mamak_score=Decimal(value * 10),
        band="Not ready",
        missing_information=missing or [],
    )


def test_improvement_gain_is_code_calculated_and_sorted():
    drafts = [
        ImprovementActionDraft(
            action="Improve market evidence", criterion_id="market", target_score=8, priority="high"
        ),
        ImprovementActionDraft(
            action="Improve team evidence", criterion_id="team", target_score=7, priority="medium"
        ),
    ]
    result = build_improvement_actions(drafts, scores(5), R)
    assert result[0].criterion_id == "market" and result[0].projected_gain == Decimal("4.5")
    assert result[1].projected_gain == Decimal("2.0")


def test_bad_improvement_target_rejected():
    with pytest.raises(ServiceError):
        build_improvement_actions(
            [
                ImprovementActionDraft(
                    action="x", criterion_id="market", target_score=5, priority="low"
                )
            ],
            scores(5),
            R,
        )


def test_comparison_and_rubric_warning():
    result = compare_assessments(
        ComparisonRequest(
            previous=summary("a", 4, "old", ["team"]), current=summary("a", 6, "new", ["market"])
        )
    )
    assert result.comparable is False
    assert result.mamak_score_delta == Decimal("20")
    assert result.resolved_missing_information == ["team"]
    assert result.new_missing_information == ["market"]
    assert len(result.categories) == 9


def test_comparison_requires_same_application():
    with pytest.raises(ServiceError):
        compare_assessments(ComparisonRequest(previous=summary("a", 4), current=summary("b", 5)))
