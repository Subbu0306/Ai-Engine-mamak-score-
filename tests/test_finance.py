from decimal import Decimal

from mamakscore.contracts import FinancialInput
from mamakscore.finance import calculate_financials


def inp(name, value, period="monthly"):
    return FinancialInput(
        name=name, value=Decimal(value), period=period, currency="AUD", source=f"Sheet!{name}"
    )


def full(margin="0.60"):
    return {
        "customers": inp("customers", "100", "point_in_time"),
        "arpu": inp("arpu", "50"),
        "gross_margin": inp("gross_margin", margin, "unknown"),
        "operating_expenses": inp("operating_expenses", "4000"),
        "cash": inp("cash", "12000", "point_in_time"),
        "customer_lifetime": inp("customer_lifetime", "24", "point_in_time"),
        "cac": inp("cac", "300", "point_in_time"),
    }


def test_all_client_formulas():
    result = calculate_financials(full())
    assert result.metrics["revenue"].value == Decimal("5000")
    assert result.metrics["gross_profit"].value == Decimal("3000")
    assert result.metrics["burn"].value == Decimal("1000")
    assert result.metrics["runway"].value == Decimal("12")
    assert result.metrics["ltv"].value == Decimal("720")
    assert result.metrics["cac_payback"].value == Decimal("10")


def test_percent_margin_and_missing_inputs():
    assert calculate_financials(full("60")).metrics["gross_profit"].value == Decimal("3000")
    result = calculate_financials({"cash": inp("cash", "1000", "point_in_time")})
    assert result.metrics["revenue"].value is None
    assert result.metrics["revenue"].unavailable_reason == "MISSING_INPUT"


def test_non_positive_burn_and_zero_denominator_are_unavailable():
    values = full()
    values["operating_expenses"] = inp("operating_expenses", "2000")
    assert calculate_financials(values).metrics["runway"].unavailable_reason == "NON_POSITIVE_BURN"
    values = full()
    values["arpu"] = inp("arpu", "0")
    assert (
        calculate_financials(values).metrics["cac_payback"].unavailable_reason == "ZERO_DENOMINATOR"
    )


def test_invalid_margin_is_reported_not_guessed():
    result = calculate_financials(full("140"))
    assert result.metrics["gross_profit"].unavailable_reason == "INVALID_INPUT"
