"""PDF extraction module with PyMuPDF and optional vision fallback."""

import hashlib
import re
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple
import fitz as pymupdf

from mamakscore.contracts import (
    ExtractionLimits,
    ExtractionResult,
    PageDiagnostic,
    SourceFile,
)
from mamakscore.errors import ErrorCode, ServiceError

class RenderedPage:
    def __init__(self, number: int, image_bytes: bytes):
        self.number = number
        self.image = image_bytes

class VisionExtractor(Protocol):
    """Protocol for vision model transcription when text is sparse or image-only."""
    def transcribe(self, images: List[bytes]) -> Dict[int, str]:
        ...


def _ratios(text: str) -> Tuple[int, float, float]:
    """Calculates character count, alphanumeric ratio, and printable ratio."""
    count = len(text)
    if count == 0:
        return 0, 0.0, 0.0

    alpha = sum(1 for ch in text if ch.isalnum()) / count
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t") / count
    return count, alpha, printable


def _render(page: Any, page_number: int, max_side: int) -> bytes:
    """Renders a PDF page to PNG bytes for vision transcription."""
    pix = page.get_pixmap(dpi=150)
    return pix.tobytes("png")


def extract_pdf(
    data: bytes,
    filename: str,
    limits: ExtractionLimits,
    vision: Optional[VisionExtractor] = None,
) -> ExtractionResult:
    """Extracts canonical text from a PDF, enforcing security limits and handling vision fallback."""
    if not data.startswith(b"%PDF-"):
        raise ServiceError(
            ErrorCode.UNSUPPORTED_FILE,
            "The pitch deck is not a valid PDF.",
            field="pitch_deck",
        )

    if len(data) > limits.max_pdf_bytes:
        raise ServiceError(
            ErrorCode.FILE_TOO_LARGE,
            "The pitch deck exceeds the configured size limit.",
            field="pitch_deck",
        )

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ServiceError(
            ErrorCode.UNREADABLE_PDF,
            "The pitch deck could not be read.",
            field="pitch_deck",
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
                ErrorCode.UNREADABLE_PDF,
                "The pitch deck has no pages.",
                field="pitch_deck",
            )

        if doc.page_count > limits.max_pages:
            raise ServiceError(
                ErrorCode.FILE_TOO_LARGE,
                "The pitch deck exceeds the page limit.",
                field="pitch_deck",
            )

        texts: Dict[int, str] = {}
        diagnostics: List[PageDiagnostic] = []
        deficient: List[int] = []

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

        used_vision: List[int] = []
        if deficient and vision is not None:
            rendered = [
                RenderedPage(number, _render(doc[number - 1], number, limits.max_render_side))
                for number in deficient
            ]
            transcribed: Dict[int, str] = {}
            for start in range(0, len(rendered), 4):
                batch_res = vision.transcribe(rendered[start : start + 4])
                transcribed.update(batch_res)

            for number in deficient:
                t_text = transcribed.get(number, "").strip()
                if t_text:
                    texts[number] = t_text
                    used_vision.append(number)
                    count, alpha, printable = _ratios(t_text)
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

        # Passes both filename and name to ensure Pydantic contract compliance
        source = SourceFile(
            filename=filename,
            name=filename,
            media_type="application/pdf",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

        return ExtractionResult(
            canonical_text=canonical,
            diagnostics=diagnostics,
            source_file=source,
            method=method,
            page_count=doc.page_count,
        
        )
    finally:
        doc.close()