from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook

from mamakscore.errors import ServiceError
from mamakscore.workbook import WorkbookLimits, parse_workbook


def book(rows, title="Model"):
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(["Metric", "Jan", "Feb"])
    for label, a, b in rows:
        ws.append([label, a, b])
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_startup_model_aliases_and_lineage():
    data = book(
        [
            ("Paying Customers", 90, 100),
            ("Average Revenue per Customer", 45, 50),
            ("Gross Margin %", 55, 60),
            ("Operating Expenses", 3900, 4000),
            ("Cash Balance", 10000, 12000),
            ("Customer Lifetime Months", 20, 24),
            ("Customer Acquisition Cost", 320, 300),
            ("EBITDA", 0, 100),
        ],
        "Forecast",
    )
    result = parse_workbook(data, "finance.xlsx", WorkbookLimits())
    assert result.model_family == "startup"
    assert result.inputs["customers"].value == 100
    assert result.inputs["gross_margin"].value == Decimal("0.6")
    assert result.inputs["customers"].source == "Forecast!C2"
    assert result.metrics["runway"].value == 12
    assert "[Sheet: Forecast]" in result.canonical_text


def test_three_model_families_are_classified():
    startup = book(
        [
            ("Revenue Forecast", 1, 2),
            ("Cost of Goods Sold", 1, 2),
            ("EBITDA", 1, 2),
            ("Funding Requirements", 1, 2),
        ]
    )
    sme = book(
        [
            ("Monthly Revenue", 1, 2),
            ("Monthly Expenses", 1, 2),
            ("Profit and Loss", 1, 2),
            ("Cash Balance", 1, 2),
        ]
    )
    investor = book(
        [
            ("Revenue Assumptions", 1, 2),
            ("Unit Economics", 1, 2),
            ("Customer Acquisition", 1, 2),
            ("Scenario Analysis", 1, 2),
        ]
    )
    assert parse_workbook(startup, "a.xlsx", WorkbookLimits()).model_family == "startup"
    assert parse_workbook(sme, "b.xlsx", WorkbookLimits()).model_family == "simple_sme"
    assert parse_workbook(investor, "c.xlsx", WorkbookLimits()).model_family == "investor"


def test_corrupt_or_wrong_magic_is_controlled():
    with pytest.raises(ServiceError) as exc:
        parse_workbook(b"not xlsx", "bad.xlsx", WorkbookLimits())
    assert exc.value.code == "UNREADABLE_WORKBOOK"


def test_path_traversal_zip_is_rejected():
    from zipfile import ZipFile

    out = BytesIO()
    with ZipFile(out, "w") as z:
        z.writestr("../bad.xml", "x")
    with pytest.raises(ServiceError):
        parse_workbook(out.getvalue(), "bad.xlsx", WorkbookLimits())
