"""Safe, lineage-preserving parsing of common founder XLSX models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, Literal
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook

from .contracts import FinancialInput, FinancialResult
from .errors import ErrorCode, ServiceError
from .finance import calculate_financials

PeriodLiteral = Literal["monthly", "annual", "point_in_time", "unknown"]


@dataclass(frozen=True)
class WorkbookLimits:
    max_entries: int = 1000
    max_uncompressed_bytes: int = 50 * 1024 * 1024
    max_compression_ratio: float = 100.0


ALIASES = {
    "customers": {"customers", "active customers", "paying customers"},
    "arpu": {"arpu", "average revenue per user", "average revenue per customer"},
    "gross_margin": {"gross margin", "gross margin %"},
    "operating_expenses": {"operating expenses", "opex", "monthly expenses"},
    "cash": {"cash", "cash balance", "ending cash"},
    "customer_lifetime": {"customer lifetime", "customer lifetime months"},
    "cac": {"cac", "customer acquisition cost"},
    "monthly_gross_profit_per_customer": {"monthly gross profit per customer"},
}
FAMILY = {
    "startup": {"revenue forecast", "cost of goods sold", "ebitda", "funding requirements"},
    "simple_sme": {"monthly revenue", "monthly expenses", "profit and loss", "cash balance"},
    "investor": {
        "revenue assumptions",
        "unit economics",
        "customer acquisition",
        "scenario analysis",
    },
}


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).strip().casefold())


def _preflight(data: bytes, limits: WorkbookLimits) -> None:
    if not data.startswith(b"PK\x03\x04"):
        raise ServiceError(
            ErrorCode.UNREADABLE_WORKBOOK,
            "The financial model is not a valid XLSX file.",
            field="financial_model",
        )
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if (
                len(entries) > limits.max_entries
                or sum(i.file_size for i in entries) > limits.max_uncompressed_bytes
            ):
                raise ServiceError(
                    ErrorCode.UNREADABLE_WORKBOOK,
                    "The financial model exceeds safe archive limits.",
                    field="financial_model",
                )
            for item in entries:
                path = PurePosixPath(item.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ServiceError(
                        ErrorCode.UNREADABLE_WORKBOOK,
                        "The financial model contains an unsafe archive path.",
                        field="financial_model",
                    )
                if (
                    item.file_size
                    and item.file_size / max(1, item.compress_size) > limits.max_compression_ratio
                ):
                    raise ServiceError(
                        ErrorCode.UNREADABLE_WORKBOOK,
                        "The financial model exceeds safe compression limits.",
                        field="financial_model",
                    )
    except BadZipFile as exc:
        raise ServiceError(
            ErrorCode.UNREADABLE_WORKBOOK,
            "The financial model is not a valid XLSX file.",
            field="financial_model",
        ) from exc


def _number(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("$", "").replace("€", "").replace("£", "").replace("%", "")
    try:
        result = Decimal(text)
    except InvalidOperation:
        return None
    return -result if negative else result


def _canonical(label: str) -> str | None:
    normalized = _norm(label)
    return next((key for key, values in ALIASES.items() if normalized in values), None)


def _family(labels: set[str]) -> str:
    if "ebitda" in labels or "funding requirements" in labels:
        return "startup"
    if "scenario analysis" in labels or "unit economics" in labels:
        return "investor"
    if "profit and loss" in labels or "monthly revenue" in labels:
        return "simple_sme"
    scores = {name: len(markers & labels) for name, markers in FAMILY.items()}
    name, count = max(scores.items(), key=lambda pair: pair[1])
    return name if count >= 2 else "unknown"


def _period(key: str, label: str, headers: list[str]) -> PeriodLiteral:
    joined = " ".join([_norm(label), *headers])
    if key in {"cash", "customers", "customer_lifetime", "cac"}:
        return "point_in_time"
    if any(
        x in joined
        for x in (
            "month",
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        )
    ):
        return "monthly"
    if any(x in joined for x in ("annual", "year", "fy")):
        return "annual"
    return "unknown"


def parse_workbook(data: bytes, filename: str, limits: WorkbookLimits) -> FinancialResult:
    _preflight(data, limits)
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ServiceError(
            ErrorCode.UNREADABLE_WORKBOOK,
            "The financial model could not be read.",
            field="financial_model",
        ) from exc
    inputs: dict[str, FinancialInput] = {}
    labels: set[str] = set()
    lines: list[str] = []
    warnings: list[str] = []
    try:
        for ws in wb.worksheets:
            if ws.sheet_state != "visible":
                continue
            lines.append(f"[Sheet: {ws.title}]")
            rows = list(ws.iter_rows())
            headers = [_norm(cell.value) for cell in rows[0][1:]] if rows else []
            for row in rows:
                if not row or row[0].value is None:
                    continue
                label = str(row[0].value).strip()
                normalized = _norm(label)
                labels.add(normalized)
                rendered = [str(cell.value) for cell in row if cell.value is not None]
                if rendered:
                    lines.append(" | ".join(rendered))
                key = _canonical(label)
                if not key:
                    continue
                candidates: list[tuple[Any, Decimal]] = []
                for candidate_cell in row[1:]:
                    parsed = _number(candidate_cell.value)
                    if parsed is not None:
                        candidates.append((candidate_cell, parsed))
                if not candidates:
                    warnings.append(f"No cached numeric value for {label} on sheet {ws.title}.")
                    continue
                cell, value = candidates[-1]
                if key == "gross_margin" and ("%" in label or value > 1):
                    value = value / Decimal(100)
                inputs[key] = FinancialInput(
                    name=key,
                    value=value,
                    period=_period(key, label, headers),
                    currency=None,
                    source=f"{ws.title}!{cell.coordinate}",
                )
    finally:
        wb.close()
    result = calculate_financials(inputs)
    return result.model_copy(
        update={
            "provided": True,
            "model_family": _family(labels),
            "warnings": warnings,
            "canonical_text": "\n".join(lines),
        }
    )
