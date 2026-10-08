"""Deterministic financial metrics calculation module."""

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Union

from mamakscore.contracts import FinancialInput, FinancialResult, MetricValue, SourceFile


def _to_decimal(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    # Prioritize model fields over raw object conversion
    if hasattr(val, "value") and getattr(val, "value") is not None:
        return _to_decimal(getattr(val, "value"))
    if hasattr(val, "amount") and getattr(val, "amount") is not None:
        return _to_decimal(getattr(val, "amount"))
    if hasattr(val, "metric_value") and getattr(val, "metric_value") is not None:
        return _to_decimal(getattr(val, "metric_value"))
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    if isinstance(val, dict):
        for k in ("value", "amount", "metric_value"):
            if k in val and val[k] is not None:
                return _to_decimal(val[k])
    if isinstance(val, str):
        cleaned = val.strip().replace(",", "").replace("$", "").replace("%", "")
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def calculate_financials(
    inputs: Union[Dict[str, Any], FinancialInput],
    source_file: Optional[SourceFile] = None,
    detected_model_family: Optional[str] = None,
    canonical_text: Optional[str] = None,
) -> FinancialResult:
    if isinstance(inputs, FinancialInput):
        data = inputs.metrics or {}
    elif isinstance(inputs, dict):
        data = inputs
    else:
        data = {}

    metrics: Dict[str, MetricValue] = {}
    warnings: List[str] = []
    normalized_inputs: Dict[str, Any] = {}

    def get_val(*keys: str) -> Optional[Decimal]:
        for k in keys:
            if k in data:
                raw = data[k]
                d = _to_decimal(raw)
                if d is not None:
                    src = getattr(raw, "source", None) or (
                        raw.get("source") if isinstance(raw, dict) else None
                    )
                    stored = d
                    if keys[0] == "gross_margin" and d > Decimal("1.0"):
                        stored = d / Decimal("100")
                    normalized_inputs[keys[0]] = MetricValue(
                        value=stored, metric_value=stored, source=src
                    )
                    return d
        return None

    customers = get_val("customers", "paying_customers", "customer_count")
    arpu = get_val("arpu", "average_revenue_per_customer", "price_per_user")
    revenue = get_val("revenue", "arr", "mrr_annualized", "monthly_revenue", "revenue_forecast")
    gross_margin_pct = get_val("gross_margin", "gross_margin_pct", "gross_margin_percentage")
    cogs = get_val("cogs", "cost_of_goods_sold")
    gross_profit = get_val("gross_profit")
    opex = get_val("operating_expenses", "opex", "monthly_expenses")
    cash = get_val("cash", "cash_balance", "bank_balance")
    customer_lifetime = get_val("customer_lifetime", "customer_lifetime_months", "lifetime_months")
    cac = get_val("cac", "customer_acquisition_cost")

    # 1. Revenue = Customers * ARPU
    if revenue is None and customers is not None and arpu is not None:
        revenue = customers * arpu
        metrics["revenue"] = MetricValue(
            value=revenue,
            metric_value=revenue,
            source_formula="customers * arpu",
            inputs={"customers": customers, "arpu": arpu},
        )
    elif revenue is not None:
        metrics["revenue"] = MetricValue(value=revenue, metric_value=revenue)
    else:
        metrics["revenue"] = MetricValue(unavailable_reason="MISSING_INPUT")

    # 2. Gross Profit = Revenue * Gross Margin
    margin_fraction = None
    if gross_margin_pct is not None:
        if gross_margin_pct > Decimal("100") or gross_margin_pct < Decimal("0"):
            warnings.append("Gross margin exceeds 100%.")
            metrics["gross_profit"] = MetricValue(
                unavailable_reason="INVALID_INPUT",
                inputs={"gross_margin_pct": gross_margin_pct},
            )
        else:
            margin_fraction = (
                gross_margin_pct / Decimal("100")
                if gross_margin_pct > Decimal("1.0")
                else gross_margin_pct
            )
            if revenue is not None:
                gross_profit = revenue * margin_fraction
                metrics["gross_profit"] = MetricValue(
                    value=gross_profit,
                    metric_value=gross_profit,
                    source_formula="revenue * gross_margin",
                    inputs={"revenue": revenue, "gross_margin": gross_margin_pct},
                )
            else:
                metrics["gross_profit"] = MetricValue(unavailable_reason="MISSING_INPUT")
    elif gross_profit is None and revenue is not None and cogs is not None:
        gross_profit = revenue - cogs
        margin_fraction = gross_profit / revenue if revenue > Decimal("0") else None
        metrics["gross_profit"] = MetricValue(
            value=gross_profit,
            metric_value=gross_profit,
            source_formula="revenue - cogs",
            inputs={"revenue": revenue, "cogs": cogs},
        )
    elif gross_profit is not None:
        metrics["gross_profit"] = MetricValue(value=gross_profit, metric_value=gross_profit)
    else:
        metrics["gross_profit"] = MetricValue(unavailable_reason="MISSING_INPUT")

    # 3. Burn = Operating Expenses - Gross Profit
    burn = None
    if opex is not None:
        gp_val = (
            metrics["gross_profit"].value
            if metrics["gross_profit"].value is not None
            else Decimal("0")
        )
        burn = opex - gp_val
        metrics["burn"] = MetricValue(
            value=burn,
            metric_value=burn,
            source_formula="operating_expenses - gross_profit",
            inputs={"operating_expenses": opex, "gross_profit": gp_val},
        )
        metrics["net_burn"] = metrics["burn"]
    else:
        metrics["burn"] = MetricValue(unavailable_reason="MISSING_INPUT")
        metrics["net_burn"] = metrics["burn"]

    # 4. Runway = Cash / Burn
    if cash is not None:
        if burn is not None:
            if burn <= Decimal("0"):
                metrics["runway"] = MetricValue(
                    unavailable_reason="NON_POSITIVE_BURN",
                    inputs={"cash": cash, "burn": burn},
                )
            else:
                runway = cash / burn
                metrics["runway"] = MetricValue(
                    value=Decimal(str(int(runway))) if runway == int(runway) else round(runway, 1),
                    metric_value=Decimal(str(int(runway))) if runway == int(runway) else round(runway, 1),
                    source_formula="cash / burn",
                    inputs={"cash": cash, "burn": burn},
                )
        else:
            metrics["runway"] = MetricValue(unavailable_reason="MISSING_INPUT")
    else:
        metrics["runway"] = MetricValue(unavailable_reason="MISSING_INPUT")

    # 5. LTV = ARPU * Gross Margin * Customer Lifetime
    if arpu is not None and margin_fraction is not None and customer_lifetime is not None:
        ltv = arpu * margin_fraction * customer_lifetime
        metrics["ltv"] = MetricValue(
            value=Decimal(str(int(ltv))) if ltv == int(ltv) else round(ltv, 2),
            metric_value=Decimal(str(int(ltv))) if ltv == int(ltv) else round(ltv, 2),
            source_formula="arpu * gross_margin * customer_lifetime",
            inputs={"arpu": arpu, "gross_margin": margin_fraction, "customer_lifetime": customer_lifetime},
        )
    else:
        metrics["ltv"] = MetricValue(unavailable_reason="MISSING_INPUT")

    # 6. CAC Payback = CAC / (ARPU * Gross Margin)
    if cac is not None and arpu is not None and margin_fraction is not None:
        monthly_gp_per_customer = arpu * margin_fraction
        if monthly_gp_per_customer == Decimal("0"):
            metrics["cac_payback"] = MetricValue(
                unavailable_reason="ZERO_DENOMINATOR",
                inputs={"cac": cac, "monthly_gp": monthly_gp_per_customer},
            )
        else:
            payback = cac / monthly_gp_per_customer
            metrics["cac_payback"] = MetricValue(
                value=Decimal(str(int(payback))) if payback == int(payback) else round(payback, 1),
                metric_value=Decimal(str(int(payback))) if payback == int(payback) else round(payback, 1),
                source_formula="cac / (arpu * gross_margin)",
                inputs={"cac": cac, "monthly_gp": monthly_gp_per_customer},
            )
    else:
        metrics["cac_payback"] = MetricValue(unavailable_reason="MISSING_INPUT")

    has_model_flag = any(m.value is not None for m in metrics.values()) or (
        isinstance(inputs, FinancialInput) and inputs.has_model
    )

    return FinancialResult(
        has_model=has_model_flag,
        provided=has_model_flag,
        model_family=detected_model_family or "none",
        detected_model_family=detected_model_family or "none",
        inputs=normalized_inputs,
        metrics=metrics,
        warnings=warnings,
        source_file=source_file,
        canonical_text=canonical_text,
    )