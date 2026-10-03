"""Client-supplied financial formulas using Decimal arithmetic."""

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation

from .contracts import FinancialInput, FinancialMetric, FinancialResult

FORMULAS = {
    "revenue": "Customers × Average Revenue per Customer",
    "gross_profit": "Revenue × Gross Margin",
    "burn": "Operating Expenses − Gross Profit",
    "runway": "Cash ÷ Monthly Burn",
    "ltv": "ARPU × Gross Margin × Customer Lifetime",
    "cac_payback": "CAC ÷ Monthly Gross Profit per Customer",
}


def _metric(
    name: str,
    value: Decimal | None = None,
    reason: str | None = None,
    inputs: Sequence[str] = (),
    unit: str = "currency",
) -> FinancialMetric:
    return FinancialMetric(
        name=name,
        value=value,
        unit=unit,
        formula=FORMULAS[name],
        source_inputs=list(inputs),
        unavailable_reason=reason,
    )


def _missing(name: str, inputs: Sequence[str]) -> FinancialMetric:
    return _metric(
        name,
        reason="MISSING_INPUT",
        inputs=inputs,
        unit="months" if name in {"runway", "cac_payback"} else "currency",
    )


def calculate_financials(inputs: Mapping[str, FinancialInput]) -> FinancialResult:
    metrics: dict[str, FinancialMetric] = {}
    customers, arpu = inputs.get("customers"), inputs.get("arpu")
    if customers and arpu:
        revenue = customers.value * arpu.value
        metrics["revenue"] = _metric("revenue", revenue, inputs=("customers", "arpu"))
    else:
        revenue = None
        metrics["revenue"] = _missing("revenue", ("customers", "arpu"))
    margin_input = inputs.get("gross_margin")
    margin = None
    if margin_input:
        try:
            margin = margin_input.value / 100 if margin_input.value > 1 else margin_input.value
            if not Decimal(0) <= margin <= Decimal(1):
                margin = None
        except InvalidOperation:
            margin = None
    if revenue is None or margin_input is None:
        gross = None
        metrics["gross_profit"] = _missing("gross_profit", ("revenue", "gross_margin"))
    elif margin is None:
        gross = None
        metrics["gross_profit"] = _metric(
            "gross_profit", reason="INVALID_INPUT", inputs=("revenue", "gross_margin")
        )
    else:
        gross = revenue * margin
        metrics["gross_profit"] = _metric("gross_profit", gross, inputs=("revenue", "gross_margin"))
    opex = inputs.get("operating_expenses")
    if opex is None or gross is None:
        burn = None
        metrics["burn"] = _missing("burn", ("operating_expenses", "gross_profit"))
    elif arpu and opex.period not in {"unknown", arpu.period}:
        burn = None
        metrics["burn"] = _metric(
            "burn", reason="INCOMPATIBLE_PERIOD", inputs=("operating_expenses", "gross_profit")
        )
    else:
        burn = opex.value - gross
        metrics["burn"] = _metric("burn", burn, inputs=("operating_expenses", "gross_profit"))
    cash = inputs.get("cash")
    if cash is None or burn is None:
        metrics["runway"] = _missing("runway", ("cash", "burn"))
    elif burn <= 0:
        metrics["runway"] = _metric(
            "runway", reason="NON_POSITIVE_BURN", inputs=("cash", "burn"), unit="months"
        )
    else:
        metrics["runway"] = _metric(
            "runway", cash.value / burn, inputs=("cash", "burn"), unit="months"
        )
    lifetime = inputs.get("customer_lifetime")
    if arpu is None or margin_input is None or lifetime is None:
        metrics["ltv"] = _missing("ltv", ("arpu", "gross_margin", "customer_lifetime"))
        ltv = None
    elif margin is None:
        metrics["ltv"] = _metric(
            "ltv", reason="INVALID_INPUT", inputs=("arpu", "gross_margin", "customer_lifetime")
        )
        ltv = None
    else:
        ltv = arpu.value * margin * lifetime.value
        metrics["ltv"] = _metric("ltv", ltv, inputs=("arpu", "gross_margin", "customer_lifetime"))
    cac = inputs.get("cac")
    mpg = inputs.get("monthly_gross_profit_per_customer")
    divisor = mpg.value if mpg else (arpu.value * margin if arpu and margin is not None else None)
    if cac is None or divisor is None:
        metrics["cac_payback"] = _missing(
            "cac_payback", ("cac", "monthly_gross_profit_per_customer")
        )
    elif divisor == 0:
        metrics["cac_payback"] = _metric(
            "cac_payback",
            reason="ZERO_DENOMINATOR",
            inputs=("cac", "monthly_gross_profit_per_customer"),
            unit="months",
        )
    elif divisor < 0:
        metrics["cac_payback"] = _metric(
            "cac_payback",
            reason="INVALID_INPUT",
            inputs=("cac", "monthly_gross_profit_per_customer"),
            unit="months",
        )
    else:
        metrics["cac_payback"] = _metric(
            "cac_payback",
            cac.value / divisor,
            inputs=("cac", "monthly_gross_profit_per_customer"),
            unit="months",
        )
    return FinancialResult(
        provided=bool(inputs), model_family="unknown", inputs=dict(inputs), metrics=metrics
    )
