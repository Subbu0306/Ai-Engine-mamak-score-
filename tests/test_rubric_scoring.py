from decimal import Decimal
from pathlib import Path

import pytest

from mamakscore.contracts import CriterionScore
from mamakscore.errors import ServiceError
from mamakscore.rubric import load_rubric
from mamakscore.scoring import calculate_mamak_score, classify_score

RUBRIC = Path(__file__).parents[1] / "rubric" / "mamakscore-v3.yaml"
IDS = {
    "problem",
    "market",
    "product",
    "business_model",
    "traction",
    "competitive_advantage",
    "financials",
    "team",
    "scalability",
}


def scores(value: int):
    return [
        CriterionScore(
            criterion_id=i,
            score=value,
            justification="Evidence assessed.",
            evidence_quote="Evidence assessed.",
            source_file="deck.pdf",
            confidence="high",
        )
        for i in IDS
    ]


def test_client_rubric_is_complete():
    rubric = load_rubric(RUBRIC)
    assert len(rubric.criteria) == 9
    assert sum(item.weight for item in rubric.criteria) == 100
    assert {item.id for item in rubric.criteria} == IDS
    assert rubric.scale == [0, 10]
    assert all(len(item.anchors) == 5 for item in rubric.criteria)


def test_score_extremes():
    rubric = load_rubric(RUBRIC)
    assert calculate_mamak_score(scores(0), rubric) == Decimal("0.0")
    assert calculate_mamak_score(scores(10), rubric) == Decimal("100.0")


@pytest.mark.parametrize(
    ("value", "label", "escalated"),
    [
        ("0", "Not ready", False),
        ("39.9", "Not ready", True),
        ("40", "Needs significant validation", False),
        ("59.9", "Needs significant validation", True),
        ("60", "Potential consideration", False),
        ("74.9", "Potential consideration", True),
        ("75", "Strong candidate", False),
        ("89.9", "Strong candidate", True),
        ("90", "Due diligence recommended", False),
        ("100", "Due diligence recommended", False),
    ],
)
def test_client_band_boundaries(value, label, escalated):
    band = classify_score(Decimal(value))
    assert band.label == label
    assert band.boundary_escalation is escalated
    assert band.human_review_required is True


def test_duplicate_or_missing_scores_are_rejected():
    rubric = load_rubric(RUBRIC)
    with pytest.raises(ServiceError):
        calculate_mamak_score(scores(5)[:-1], rubric)
