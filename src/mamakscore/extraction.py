"""In-memory PDF extraction with bounded optional vision fallback."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import pymupdf

from .contracts import ExtractionResult, PageDiagnostic, SourceFile
from .errors import ErrorCode, ServiceError


@dataclass(frozen=True)
class ExtractionLimits:
    max_pdf_bytes: int = 20 * 1024 * 1024
    max_pages: int = 60
    max_text_characters: int = 120_000
    min_page_characters: int = 40
    min_alphanumeric_ratio: float = 0.35
    max_render_side: int = 2048


@dataclass(frozen=True)
class RenderedPage:
    number: int
    png: bytes


class VisionExtractor(Protocol):
    def transcribe(self, pages: Sequence[RenderedPage]) -> Mapping[int, str]: ...


def _ratios(text: str) -> tuple[int, float, float]:
    compact = [c for c in text if not c.isspace()]
    count = len(compact)
    if not count:
        return 0, 0.0, 0.0
    return (
        count,
        sum(c.isalnum() for c in compact) / count,
        sum(c.isprintable() for c in compact) / count,
    )


def _render(page: Any, number: int, limit: int) -> RenderedPage:
    longest = max(page.rect.width, page.rect.height)
    zoom = min(2.0, limit / longest) if longest else 1.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)  # type: ignore[no-untyped-call]
    return RenderedPage(number=number, png=pix.tobytes("png"))


def extract_pdf(
    data: bytes, filename: str, limits: ExtractionLimits, vision: VisionExtractor | None = None
) -> ExtractionResult:
    if not data.startswith(b"%PDF-"):
        raise ServiceError(
            ErrorCode.UNSUPPORTED_FILE, "The pitch deck is not a valid PDF.", field="pitch_deck"
        )
    if len(data) > limits.max_pdf_bytes:
        raise ServiceError(
            ErrorCode.FILE_TOO_LARGE,
            "The pitch deck exceeds the configured size limit.",
            field="pitch_deck",
        )
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as exc:
        raise ServiceError(
            ErrorCode.UNREADABLE_PDF, "The pitch deck could not be read.", field="pitch_deck"
        ) from exc
    try:
        if doc.needs_pass:
            raise ServiceError(
                ErrorCode.ENCRYPTED_PDF,
                "Password-protected pitch decks are not supported.",
                field="pitch_deck",
            )
        if doc.page_count < 1:
            raise ServiceError(
                ErrorCode.UNREADABLE_PDF, "The pitch deck has no pages.", field="pitch_deck"
            )
        if doc.page_count > limits.max_pages:
            raise ServiceError(
                ErrorCode.FILE_TOO_LARGE,
                "The pitch deck exceeds the page limit.",
                field="pitch_deck",
            )
        texts: dict[int, str] = {}
        diagnostics: list[PageDiagnostic] = []
        deficient: list[int] = []
        for index in range(doc.page_count):
            page: Any = doc[index]
            number = index + 1
            text = page.get_text("text", sort=True).strip()
            count, alpha, printable = _ratios(text)
            bad = count < limits.min_page_characters or alpha < limits.min_alphanumeric_ratio
            texts[number] = text
            diagnostics.append(
                PageDiagnostic(
                    page=number,
                    method="empty" if bad else "direct",
                    characters=count,
                    alphanumeric_ratio=round(alpha, 4),
                    printable_ratio=round(printable, 4),
                )
            )
            if bad:
                deficient.append(number)
        used_vision: list[int] = []
        if deficient and vision is not None:
            rendered = [
                _render(doc[number - 1], number, limits.max_render_side) for number in deficient
            ]
            transcribed: dict[int, str] = {}
            for start in range(0, len(rendered), 4):
                transcribed.update(vision.transcribe(rendered[start : start + 4]))
            for number in deficient:
                text = transcribed.get(number, "").strip()
                if text:
                    texts[number] = text
                    used_vision.append(number)
                    count, alpha, printable = _ratios(text)
                    diagnostics[number - 1] = PageDiagnostic(
                        page=number,
                        method="vision",
                        characters=count,
                        alphanumeric_ratio=round(alpha, 4),
                        printable_ratio=round(printable, 4),
                    )
        if all(not text.strip() for text in texts.values()):
            code = ErrorCode.VISION_REQUIRED if vision is None else ErrorCode.UNREADABLE_PDF
            message = (
                "Image-based pitch deck requires a configured vision model."
                if vision is None
                else "No usable text could be extracted from the pitch deck."
            )
            raise ServiceError(code, message, field="pitch_deck")
        canonical = "\n\n".join(
            f"[Page {number}]\n{text}" for number, text in texts.items() if text.strip()
        )
        if len(canonical) > limits.max_text_characters:
            raise ServiceError(
                ErrorCode.DOCUMENT_TOO_LARGE,
                "The extracted pitch deck exceeds the model-input limit.",
                field="pitch_deck",
            )
        method: Literal["direct", "vision", "hybrid"] = (
            "direct"
            if not used_vision
            else ("vision" if len(used_vision) == doc.page_count else "hybrid")
        )
        source = SourceFile(
            name=filename,
            media_type="application/pdf",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        return ExtractionResult(
            source=source,
            method=method,
            page_count=doc.page_count,
            canonical_text=canonical,
            pages=diagnostics,
            text_characters=len(canonical),
        )
    finally:
        doc.close()  # type: ignore[no-untyped-call]
