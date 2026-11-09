"""Grounding verification engine: validates citations against extracted document text."""

import re
from typing import List, Optional
from mamakscore.contracts import AssessmentDraft, CriterionScore
from mamakscore.errors import ErrorCode, ServiceError


def _normalize_text(text: Optional[str]) -> str:
    """Strips punctuation, lowercases, and collapses whitespace."""
    if not text:
        return ""
    # Remove ellipses and special quote characters
    cleaned = text.replace("…", " ").replace("...", " ")
    cleaned = re.sub(r'["\'`“”‘’]', "", cleaned)
    # Collapse all whitespace sequences into a single space
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def is_grounded(quote: str, documents: List[str], min_overlap_ratio: float = 0.65) -> bool:
    """Verifies whether an evidence quote exists in the source text using robust matching."""
    norm_quote = _normalize_text(quote)
    if not norm_quote:
        return True

    # Combine all document sources into a normalized corpus
    norm_corpus = " ".join(_normalize_text(doc) for doc in documents if doc)
    if not norm_corpus:
        return False

    # 1. Direct normalized substring check
    if norm_quote in norm_corpus:
        return True

    # 2. Leading anchor check (first 35 characters)
    anchor_prefix = norm_quote[:35].strip()
    if len(anchor_prefix) >= 15 and anchor_prefix in norm_corpus:
        return True

    # 3. Trailing anchor check (last 35 characters)
    anchor_suffix = norm_quote[-35:].strip()
    if len(anchor_suffix) >= 15 and anchor_suffix in norm_corpus:
        return True

    # 4. Sliding token-overlap fallback
    quote_tokens = [t for t in norm_quote.split() if len(t) > 2]
    if not quote_tokens:
        return True

    matched_tokens = sum(1 for token in quote_tokens if token in norm_corpus)
    overlap = matched_tokens / float(len(quote_tokens))
    return overlap >= min_overlap_ratio


def verify_grounding(
    draft: AssessmentDraft,
    source_documents: List[str],
    strict: bool = False,
) -> None:
    """Validates that all evidence quotes in criterion scores and red flags exist in source documents."""
    for item in draft.criterion_scores:
        quote = (item.evidence_quote or "").strip()
        if not quote:
            continue

        if not is_grounded(quote, source_documents):
            if strict:
                raise ServiceError(
                    ErrorCode.INVALID_MODEL_OUTPUT,
                    f"Evidence quote for criterion '{item.criterion_id}' was not found in source documents: '{quote[:60]}...'",
                    field="criterion_scores",
                )
            # In non-strict mode, clamp ungrounded score to 0 to preserve pipeline execution
            item.score = 0
            item.evidence_quote = ""
            item.justification = (
                f"{item.justification} [Grounding Note: Score clamped to 0 because cited quote "
                f"could not be verified against the slide text.]"
            ).strip()

    # Verify red flag evidence quotes
    for flag in draft.red_flags:
        rf_quote = (flag.evidence_quote or "").strip()
        if rf_quote and not is_grounded(rf_quote, source_documents):
            flag.evidence_quote = ""


__all__ = ["verify_grounding", "is_grounded"]