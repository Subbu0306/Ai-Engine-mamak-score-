"""PDF Extraction module with PyMuPDF, safety limits, and vision-assisted fallback."""

import base64
import hashlib
import os
import re
from typing import Any, Dict, List, Optional, Protocol
import httpx
import pymupdf as fitz
from pydantic import BaseModel, Field

from mamakscore.contracts import (
    ExtractionLimits,
    ExtractionResult,
    PageDiagnostic,
    SourceFile,
)
from mamakscore.errors import ServiceError


class DeficientPage(BaseModel):
    """Container for deficient slides passed to batch vision transcribers."""
    number: int
    image_bytes: bytes


class VisionExtractor(Protocol):
    """Protocol for vision-based slide OCR and transcription."""
    def transcribe(self, pages: List[Any]) -> Dict[int, str]:
        ...


class OpenAIVisionExtractor:
    """Uses GPT-4o multimodal vision to transcribe slide text and data tables."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = 45.0,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-4o")
        self.timeout = timeout

    def transcribe(self, pages: List[Any]) -> Dict[int, str]:
        results: Dict[int, str] = {}
        for p in pages:
            num = getattr(p, "number", 1)
            img_bytes = getattr(p, "image_bytes", b"")
            results[num] = self._transcribe_single_page(img_bytes, num)
        return results

    def _transcribe_single_page(self, image_bytes: bytes, page_number: int) -> str:
        if not self.api_key:
            return f"[Slide {page_number}: Vision transcription skipped (No API key)]"

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a precise document transcription OCR engine. "
                        "Transcribe ALL visible text, labels, headlines, bullet points, numbers, "
                        "and metrics from this pitch deck slide verbatim. "
                        "Do not add conversational fluff or commentary. Output raw slide content only."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Transcribe slide #{page_number}."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                        },
                    ],
                },
            ],
            "temperature": 0.0,
            "max_tokens": 1200,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                if resp.status_code >= 400:
                    return f"[Slide {page_number}: Vision API error {resp.status_code}]"
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"[Slide {page_number}: Vision transcription failed ({str(e)})]"


def normalize_whitespace(text: str) -> str:
    """Normalizes multiple consecutive whitespace characters and strips line edges."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def extract_pdf(
    pdf_bytes: Optional[bytes] = None,
    deck_filename: str = "deck.pdf",
    limits: Optional[ExtractionLimits] = None,
    vision: Optional[Any] = None,
    data: Optional[bytes] = None,
    filename: Optional[str] = None,
    **kwargs: Any,
) -> ExtractionResult:
    """Extracts text from a pitch deck PDF supporting both pdf_bytes and data keyword arguments."""
    payload_bytes = pdf_bytes if pdf_bytes is not None else data
    if payload_bytes is None:
        raise ServiceError(code="INVALID_PDF", message="No PDF data bytes provided to extract_pdf.")

    target_filename = filename or deck_filename or "deck.pdf"
    limits = limits or ExtractionLimits()

    # 1. Payload size bound
    max_bytes = getattr(limits, "max_pdf_bytes", None) or getattr(limits, "max_total_bytes", 20 * 1024 * 1024)
    if len(payload_bytes) > max_bytes:
        raise ServiceError(
            code="FILE_TOO_LARGE",
            message=f"PDF payload exceeds max limit of {max_bytes} bytes",
        )

    # 2. Magic bytes / open document stream
    if not payload_bytes.startswith(b"%PDF"):
        raise ServiceError(
            code="INVALID_PDF",
            message="Invalid PDF: missing '%PDF' header magic bytes.",
        )

    try:
        doc = fitz.open(stream=payload_bytes, filetype="pdf")
    except Exception as e:
        raise ServiceError(code="INVALID_PDF", message=f"Failed to open PDF stream: {e}")

    # 3. Encryption check
    if doc.is_encrypted:
        raise ServiceError(code="ENCRYPTED_PDF", message="Password-protected PDFs are rejected.")

    # 4. Page count bounds
    page_count = len(doc)
    if page_count == 0:
        raise ServiceError(code="EMPTY_PDF", message="PDF contains 0 pages.")

    if page_count > limits.max_pages:
        raise ServiceError(
            code="EXCEEDED_PAGE_LIMIT",
            message=f"PDF has {page_count} pages, exceeding max allowed ({limits.max_pages}).",
        )

    page_texts: List[str] = []
    diagnostics: List[PageDiagnostic] = []
    deficient_pages: List[DeficientPage] = []
    deficient_indices: List[int] = []

    for page_idx in range(page_count):
        page = doc[page_idx]
        extracted_text = page.get_text("text") or ""
        clean_text = normalize_whitespace(extracted_text)

        total_chars = len(clean_text)
        alpha_chars = sum(1 for c in clean_text if c.isalnum())
        printable_chars = sum(1 for c in clean_text if c.isprintable() or c in "\n\r\t")

        alpha_ratio = (alpha_chars / total_chars) if total_chars > 0 else 0.0
        printable_ratio = (printable_chars / total_chars) if total_chars > 0 else 1.0

        is_deficient = (
            total_chars < limits.min_page_characters
            or alpha_ratio < limits.min_alphanumeric_ratio
        )

        if is_deficient:
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            deficient_pages.append(DeficientPage(number=page_idx + 1, image_bytes=img_bytes))
            deficient_indices.append(page_idx)
            page_texts.append("")
            diagnostics.append(
                PageDiagnostic(
                    page=page_idx + 1,
                    method="vision" if vision is not None else "empty",
                    characters=0,
                    alphanumeric_ratio=0.0,
                    printable_ratio=0.0,
                )
            )
        else:
            page_texts.append(f"[Page {page_idx + 1}]\n{clean_text}")
            diagnostics.append(
                PageDiagnostic(
                    page=page_idx + 1,
                    method="direct",
                    characters=total_chars,
                    alphanumeric_ratio=alpha_ratio,
                    printable_ratio=printable_ratio,
                )
            )

    doc.close()

    if deficient_pages:
        if vision is None:
            if len(deficient_pages) == page_count:
                raise ServiceError(
                    code="VISION_REQUIRED",
                    message="All pages are image-only or low-text; vision OCR fallback is required.",
                )
        else:
            transcriptions = vision.transcribe(deficient_pages)
            for page_obj in deficient_pages:
                idx = page_obj.number - 1
                transcribed = transcriptions.get(page_obj.number, "")
                clean_transcribed = normalize_whitespace(transcribed)
                page_texts[idx] = f"[Page {page_obj.number}]\n{clean_transcribed}"
                diagnostics[idx] = PageDiagnostic(
                    page=page_obj.number,
                    method="vision",
                    characters=len(clean_transcribed),
                    alphanumeric_ratio=1.0,
                    printable_ratio=1.0,
                )

    canonical_text = "\n\n".join(t for t in page_texts if t.strip()).strip()

    max_text_chars = getattr(limits, "max_text_characters", 120_000)
    if len(canonical_text) > max_text_chars:
        raise ServiceError(
            code="DOCUMENT_TOO_LARGE",
            message=f"Extracted text has {len(canonical_text)} characters, exceeding limit of {max_text_chars}.",
        )

    has_direct = any(d.method == "direct" for d in diagnostics)
    has_vision = any(d.method == "vision" for d in diagnostics)

    if has_direct and has_vision:
        method = "hybrid"
    elif has_vision:
        method = "vision"
    else:
        method = "direct"

    sha256_hash = hashlib.sha256(payload_bytes).hexdigest()
    source = SourceFile(
        filename=target_filename,
        name=target_filename,
        media_type="application/pdf",
        size_bytes=len(payload_bytes),
        sha256=sha256_hash,
    )

    return ExtractionResult(
        canonical_text=canonical_text,
        diagnostics=diagnostics,
        source_file=source,
        source=source,
        method=method,
        page_count=page_count,
    )


__all__ = [
    "DeficientPage",
    "ExtractionLimits",
    "PageDiagnostic",
    "ExtractionResult",
    "VisionExtractor",
    "OpenAIVisionExtractor",
    "normalize_whitespace",
    "extract_pdf",
]