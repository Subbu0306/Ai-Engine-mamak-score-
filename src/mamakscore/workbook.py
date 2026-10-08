"""Financial model parser and extractor for Excel workbooks."""

from decimal import Decimal
import hashlib
import io
import re
from typing import Any, Dict, List, Optional
import zipfile

import openpyxl
from pydantic import BaseModel

from mamakscore.contracts import FinancialResult, SourceFile
from mamakscore.errors import ErrorCode, ServiceError
from mamakscore.finance import calculate_financials


class WorkbookLimits(BaseModel):
    max_workbook_bytes: int = 10 * 1024 * 1024  # 10 MB
    max_sheets: int = 10
    max_rows: int = 1000
    max_columns: int = 50
    max_uncompressed_bytes: int = 50 * 1024 * 1024  # 50 MB


def _col_to_letter(col_idx: int) -> str:
    """Converts a 1-based column index to an Excel column letter (1 -> A, 3 -> C)."""
    result = ""
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _normalize_key(label: str) -> str:
    """Normalizes label text into snake_case lookup key."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", label)
    return re.sub(r"\s+", "_", cleaned.strip().lower())


def _check_zip_bomb(data: bytes, limits: WorkbookLimits) -> None:
    """Validates zip compression limits and guards against path traversal."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            total_size = 0
            for info in zf.infolist():
                if info.filename.startswith("/") or ".." in info.filename:
                    raise ServiceError(
                        ErrorCode.UNREADABLE_WORKBOOK,
                        "Workbook contains forbidden path traversal entry.",
                        field="financial_model",
                    )
                total_size += info.file_size
                if total_size > limits.max_uncompressed_bytes:
                    raise ServiceError(
                        ErrorCode.FILE_TOO_LARGE,
                        "Uncompressed workbook size exceeds safety limit.",
                        field="financial_model",
                    )
    except zipfile.BadZipFile as exc:
        raise ServiceError(
            ErrorCode.UNREADABLE_WORKBOOK,
            "File is not a valid zip archive or Excel workbook.",
            field="financial_model",
        ) from exc

def _classify_model_family(sheet_names: List[str], metrics_found: Dict[str, Any]) -> str:
    """Classifies financial models into startup, simple_sme, or investor."""
    # Replace underscores with spaces so key matches both "monthly revenue" and "monthly_revenue"
    names_str = " ".join(sheet_names).lower().replace("_", " ")
    keys_str = " ".join(str(k) for k in metrics_found.keys()).lower().replace("_", " ")
    combined = f"{names_str} {keys_str}"

    if "monthly revenue" in combined or "profit and loss" in combined or "monthly expenses" in combined:
        return "simple_sme"
    if "unit economics" in combined or "scenario" in combined or "assumptions" in combined:
        return "investor"
    return "startup"


def parse_workbook(
    data: bytes,
    filename: str,
    limits: Optional[WorkbookLimits] = None,
) -> FinancialResult:
    """Parses an Excel workbook with safety checks and derives standard metrics."""
    limits = limits or WorkbookLimits()

    if len(data) > limits.max_workbook_bytes:
        raise ServiceError(
            ErrorCode.FILE_TOO_LARGE,
            "Financial model exceeds file size limit.",
            field="financial_model",
        )

    # 1. Zip bomb and path traversal security validation
    _check_zip_bomb(data, limits)

    # 2. Parse workbook with openpyxl in read-only / data-only mode
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    except Exception as exc:
        raise ServiceError(
            ErrorCode.UNREADABLE_WORKBOOK,
            "Failed to parse Excel workbook contents.",
            field="financial_model",
        ) from exc

    try:
        sheet_names = wb.sheetnames
        if len(sheet_names) > limits.max_sheets:
            raise ServiceError(
                ErrorCode.FILE_TOO_LARGE,
                "Workbook has too many sheets.",
                field="financial_model",
            )

        extracted_raw_inputs: Dict[str, Any] = {}
        canonical_lines: List[str] = []

        for name in sheet_names:
            ws = wb[name]
            canonical_lines.append(f"[Sheet: {name}]")

            for row_idx, row in enumerate(ws.iter_rows(values_only=False), start=1):
                if row_idx > limits.max_rows:
                    break
                if not row or row[0].value is None:
                    continue

                label = str(row[0].value).strip()
                norm_label = _normalize_key(label)

                # Look for the last non-empty numeric cell in the row
                for col_idx in range(len(row) - 1, 0, -1):
                    cell = row[col_idx]
                    val = cell.value
                    if val is not None and isinstance(val, (int, float, Decimal)):
                        col_letter = _col_to_letter(col_idx + 1)
                        cell_coord = f"{name}!{col_letter}{row_idx}"
                        extracted_raw_inputs[norm_label] = {
                            "value": Decimal(str(val)),
                            "source": cell_coord,
                        }
                        canonical_lines.append(f"{label}: {val} ({cell_coord})")
                        break

        detected_family = _classify_model_family(sheet_names, extracted_raw_inputs)

        source_file = SourceFile(
            filename=filename,
            name=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

        return calculate_financials(
            inputs=extracted_raw_inputs,
            source_file=source_file,
            detected_model_family=detected_family,
            canonical_text="\n".join(canonical_lines),
        )
    finally:
        wb.close()