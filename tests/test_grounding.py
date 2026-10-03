import pytest

from mamakscore.contracts import CriterionScore, RedFlag
from mamakscore.errors import ServiceError
from mamakscore.grounding import verify_category_evidence, verify_red_flag_evidence


def score(value=8, quote="We interviewed 120 customers in Adelaide.", source="deck.pdf"):
    return CriterionScore(
        criterion_id="market",
        score=value,
        justification="Evidence assessed.",
        evidence_quote=quote,
        source_file=source,
        confidence="high",
    )


def test_normalisation_accepts_smart_quotes_and_whitespace():
    verify_category_evidence(
        [score(quote="Customers said “yes” — 120 times.")],
        {"deck.pdf": 'Customers said "yes" -  120 times.'},
        "Not addressed in the submitted material.",
    )


def test_altered_number_is_rejected():
    with pytest.raises(ServiceError, match="could not be verified"):
        verify_category_evidence(
            [score(quote="We interviewed 150 customers in Adelaide.")],
            {"deck.pdf": "We interviewed 120 customers in Adelaide."},
            "Not addressed in the submitted material.",
        )


def test_empty_quote_only_valid_for_absent_score():
    absent = CriterionScore(
        criterion_id="market",
        score=0,
        justification="Not addressed in the submitted material.",
        evidence_quote="",
        source_file="deck.pdf",
        confidence="high",
    )
    verify_category_evidence(
        [absent], {"deck.pdf": "text"}, "Not addressed in the submitted material."
    )
    with pytest.raises(ServiceError):
        verify_category_evidence(
            [absent.model_copy(update={"score": 1})],
            {"deck.pdf": "text"},
            "Not addressed in the submitted material.",
        )


def test_flag_quote_must_be_grounded():
    flag = RedFlag(
        flag_type="unsupported_claim",
        severity="high",
        summary="Claim lacks support",
        evidence_quote="10,000 customers",
        source_file="deck.pdf",
    )
    with pytest.raises(ServiceError):
        verify_red_flag_evidence([flag], {"deck.pdf": "Only 100 customers"})
