"""Unit and boundary test suite for MamakConfidence."""

import pytest
from pydantic import ValidationError

from mamakscore.confidence import calculate_mamak_confidence, get_confidence_breakdown
from mamakscore.contracts import ConfidenceInputPayload


# -----------------------------------------------------------------------------
# 1. Pure Mathematical & Boundary Verification Tests
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "n_quotes, m_metrics, d_disc, d_tot, k_flags, has_model, expected",
    [
        # Nominal Scenarios from Client Proposal
        (5, 0, 0, 0, 2, False, 21.7),   # Scenario A: Unsubstantiated Hype
        (18, 5, 0, 5, 0, True, 94.2),   # Scenario B: Transparent Early-Stage

        # Boundary Minimums and Maximums
        (0, 0, 0, 0, 10, False, 8.1),   # Absolute minimum evidence (floor active)
        (24, 6, 0, 6, 0, True, 100.0),  # Upper saturation (N > 18 capped at 1.0)
        (18, 6, 0, 6, 0, True, 100.0),  # Exact saturation boundary

        # Zero-Division & Neutral Fallbacks
        (12, 4, 0, 0, 0, True, 61.7),   # d_tot == 0 safely yields C = 0.50 fallback
        (18, 0, 0, 0, 0, False, 55.3),  # Missing model: F=0.15, C=0.50 -> 55.3%

        # Red-Flag Penalty Multiplier Clamping (max(0.40, ...))
        (18, 6, 0, 6, 1, True, 85.0),   # K = 1: 0.85
        (18, 6, 0, 6, 5, True, 44.4),   # K = 5: (0.85)^5 ≈ 0.4437
        (18, 6, 0, 6, 6, True, 40.0),   # K = 6: (0.85)^6 ≈ 0.3771 -> clamped to 0.40
        (18, 6, 0, 6, 15, True, 40.0),  # K = 15: strictly clamped to 0.40 floor

        # Discrepancy Overflow Clamping
        (18, 6, 8, 5, 0, True, 70.0),   # d_disc > d_tot: C clamped to 0.0 via max(0.0, ...)
        (18, 6, 5, 5, 0, True, 70.0),   # d_disc == d_tot: C = 0.0
    ],
)
def test_confidence_mathematical_boundaries(n_quotes, m_metrics, d_disc, d_tot, k_flags, has_model, expected):
    flags = [f"flag_{i}" for i in range(k_flags)]
    score = calculate_mamak_confidence(
        verified_quotes_count=n_quotes,
        calculated_metrics_count=m_metrics,
        contradictions_count=d_disc,
        total_comparisons=d_tot,
        red_flags=flags,
        has_financial_model=has_model,
    )
    assert score == pytest.approx(expected, abs=0.1)


def test_confidence_breakdown_helper():
    """Verify that intermediate metrics dictionary matches final calculation."""
    res = get_confidence_breakdown(
        verified_quotes_count=5,
        calculated_metrics_count=0,
        contradictions_count=0,
        total_comparisons=0,
        red_flags=["unrealistic_tam", "no_competitors"],
        has_financial_model=False,
    )
    assert res["mamak_confidence"] == 21.7
    assert res["red_flags_detected"] == 2
    assert res["financial_completeness"] == 0.15
    assert res["consistency_score"] == 0.50


# -----------------------------------------------------------------------------
# 2. Schema Validation & State Contradiction Tests
# -----------------------------------------------------------------------------

def test_valid_payload():
    payload = ConfidenceInputPayload(
        n_verified=18,
        has_financial_model=True,
        m_verified=6,
        d_discrepancies=0,
        d_total=6,
        red_flags=[],
    )
    assert payload.n_verified == 18
    assert payload.has_financial_model is True


def test_reject_phantom_financial_metrics():
    """Fail if financial metrics are supplied when model is marked absent."""
    with pytest.raises(ValidationError) as exc:
        ConfidenceInputPayload(
            n_verified=10,
            has_financial_model=False,
            m_verified=4,  # Invalid state
            d_discrepancies=0,
            d_total=0,
            red_flags=[],
        )
    assert "Phantom financial metrics" in str(exc.value)


def test_reject_phantom_discrepancies():
    """Fail if discrepancies exist when total comparisons is 0."""
    with pytest.raises(ValidationError) as exc:
        ConfidenceInputPayload(
            n_verified=10,
            has_financial_model=True,
            m_verified=4,
            d_discrepancies=3,  # Invalid state
            d_total=0,
            red_flags=[],
        )
    assert "Phantom discrepancies" in str(exc.value)


def test_reject_negative_integers():
    """Fail if counts are negative."""
    with pytest.raises(ValidationError):
        ConfidenceInputPayload(
            n_verified=-5,
            has_financial_model=True,
            m_verified=6,
            d_discrepancies=0,
            d_total=6,
        )
# Alias to support both naming conventions across existing tests and codebase
calculate_confidence = calculate_mamak_confidence