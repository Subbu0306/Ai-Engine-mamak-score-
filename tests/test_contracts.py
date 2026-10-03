import pytest
from pydantic import ValidationError

from mamakscore.contracts import CriterionScore


def test_criterion_score_rejects_out_of_range_and_extra_fields():
    base = dict(
        criterion_id="market",
        score=5,
        justification="Reason",
        evidence_quote="A $10m market",
        source_file="deck.pdf",
        confidence="high",
    )
    assert CriterionScore(**base).score == 5
    with pytest.raises(ValidationError):
        CriterionScore(**{**base, "score": 11})
    with pytest.raises(ValidationError):
        CriterionScore(**{**base, "invented": True})
