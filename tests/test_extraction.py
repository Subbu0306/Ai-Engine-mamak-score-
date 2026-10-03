import fitz
import pytest

from mamakscore.errors import ServiceError
from mamakscore.extraction import ExtractionLimits, extract_pdf


def pdf(*texts):
    doc = fitz.open()
    for text in texts:
        page = doc.new_page()
        if text:
            page.insert_textbox(fitz.Rect(72, 72, 500, 700), text, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


class FakeVision:
    def __init__(self):
        self.page_numbers = []

    def transcribe(self, pages):
        self.page_numbers.extend(p.number for p in pages)
        return {
            p.number: "Vision fallback text with enough characters for a useful startup slide."
            for p in pages
        }


def test_text_pdf_extracts_directly():
    data = pdf(
        "Problem: Clinics lose 20 hours weekly. We interviewed 120 practice managers and built a working prototype."
    )
    result = extract_pdf(data, "deck.pdf", ExtractionLimits())
    assert result.method == "direct" and result.page_count == 1
    assert "120 practice managers" in result.canonical_text
    assert len(result.source.sha256) == 64


def test_image_only_uses_fake_vision():
    vision = FakeVision()
    result = extract_pdf(pdf(""), "deck.pdf", ExtractionLimits(), vision=vision)
    assert result.method == "vision"
    assert vision.page_numbers == [1]
    assert "Vision fallback text" in result.canonical_text


def test_mixed_pdf_only_sends_deficient_page():
    vision = FakeVision()
    result = extract_pdf(
        pdf(
            "A concrete problem statement with more than forty useful characters for extraction.",
            "",
        ),
        "deck.pdf",
        ExtractionLimits(),
        vision=vision,
    )
    assert result.method == "hybrid" and vision.page_numbers == [2]


def test_all_blank_without_vision_is_controlled():
    with pytest.raises(ServiceError) as exc:
        extract_pdf(pdf(""), "deck.pdf", ExtractionLimits())
    assert exc.value.code == "VISION_REQUIRED"


def test_bad_magic_size_and_page_limits():
    with pytest.raises(ServiceError):
        extract_pdf(b"bad", "deck.pdf", ExtractionLimits())
    with pytest.raises(ServiceError):
        extract_pdf(pdf("x" * 100), "deck.pdf", ExtractionLimits(max_pdf_bytes=10))
    with pytest.raises(ServiceError):
        extract_pdf(
            pdf("good text " * 20, "more text " * 20), "deck.pdf", ExtractionLimits(max_pages=1)
        )


def test_text_limit_is_controlled():
    with pytest.raises(ServiceError) as exc:
        extract_pdf(
            pdf("long evidence " * 100), "deck.pdf", ExtractionLimits(max_text_characters=100)
        )
    assert exc.value.code == "DOCUMENT_TOO_LARGE"


def test_encrypted_pdf_is_rejected():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    doc.close()
    with pytest.raises(ServiceError) as exc:
        extract_pdf(data, "deck.pdf", ExtractionLimits())
    assert exc.value.code == "ENCRYPTED_PDF"
