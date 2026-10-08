"""Evidence grounding verifier: confirms quotes exist in source text."""

import re
import unicodedata
from typing import List, Optional, Set
from mamakscore.contracts import AssessmentDraft, CriterionScore, RedFlag
from mamakscore.errors import ErrorCode, ServiceError


def normalize_text(text: str) -> str:
    """Normalizes text for grounding verification:
    - Normalizes unicode characters (NFKD)
    - Replaces typographic curly quotes and dashes with ASCII equivalents
    - Collapses all consecutive whitespaces into a single space
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    # Replace smart quotes and special apostrophes
    normalized = (
        normalized.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
        .replace("`", "'")
        .replace("–", "-")
        .replace("—", "-")
    )
    # Collapse whitespace
    return re.sub(r"\s+", " ", normalized).strip().lower()


def is_grounded(quote: str, source_text: str) -> bool:
    """Returns True if the normalized quote exists as a substring of normalized source_text."""
    norm_quote = normalize_text(quote)
    if not norm_quote:
        return False
    norm_source = normalize_text(source_text)
    return norm_quote in norm_source


def verify_grounding(
    draft: AssessmentDraft,
    source_texts: List[str],
) -> None:
    """Verifies all evidence quotes in the draft against source texts.
    Raises ServiceError(ErrorCode.UNGROUNDED_EVIDENCE) if any non-empty quote is fabricated.
    """
    combined_source = "\n\n".join(source_texts)

    # 1. Verify criterion scores
    for item in draft.criterion_scores:
        quote = item.evidence_quote.strip()
        if not quote:
            # Empty quotes are only permissible if score is 0
            if item.score != 0:
                raise ServiceError(
                    ErrorCode.UNGROUNDED_EVIDENCE,
                    f"Criterion '{item.criterion_id}' has a non-zero score ({item.score}) but an empty evidence quote.",
                    field=item.criterion_id,
                )
            continue

        if not is_grounded(quote, combined_source):
            raise ServiceError(
                ErrorCode.UNGROUNDED_EVIDENCE,
                f"Evidence quote for criterion '{item.criterion_id}' was not found in source documents: '{quote[:60]}...'",
                field=item.criterion_id,
            )

    # 2. Verify red flag evidence quotes
    for flag in draft.red_flags:
        quote = flag.evidence_quote.strip()
        if quote and not is_grounded(quote, combined_source):
            raise ServiceError(
                ErrorCode.UNGROUNDED_EVIDENCE,
                f"Evidence quote for red flag '{flag.flag or flag.summary}' was not found in source documents: '{quote[:60]}...'",
                field="red_flags",
            )
def _extract_source_text(source: Union[str, Dict[str, str], List[str]]) -> str:
    if isinstance(source, dict):
        return "\n\n".join(source.values())
    if isinstance(source, list):
        return "\n\n".join(source)
    return str(source)


def verify_category_evidence(
    scores: Union[CriterionScore, List[CriterionScore]],
    source_text: Union[str, Dict[str, str]],
    absent_rationale: Optional[str] = None,
) -> None:
    score_list = scores if isinstance(scores, list) else [scores]
    combined_source = _extract_source_text(source_text)

    for item in score_list:
        quote = item.evidence_quote.strip()
        if not quote:
            if item.score != 0:
                raise ServiceError(
                    ErrorCode.UNGROUNDED_EVIDENCE,
                    f"Evidence quote could not be verified for criterion '{item.criterion_id}'.",
                    field=item.criterion_id,
                )
            if absent_rationale and item.justification.strip() != absent_rationale.strip():
                raise ServiceError(
                    ErrorCode.UNGROUNDED_EVIDENCE,
                    f"Empty quote must use exact absent rationale.",
                    field=item.criterion_id,
                )
            continue

        if not is_grounded(quote, combined_source):
            raise ServiceError(
                ErrorCode.UNGROUNDED_EVIDENCE,
                f"Evidence quote could not be verified: '{quote}'",
                field=item.criterion_id,
            )


def verify_red_flag_evidence(
    flags: Union[RedFlag, List[RedFlag]],
    source_text: Union[str, Dict[str, str]],
) -> None:
    flag_list = flags if isinstance(flags, list) else [flags]
    combined_source = _extract_source_text(source_text)

    for flag in flag_list:
        quote = flag.evidence_quote.strip()
        if quote and not is_grounded(quote, combined_source):
            raise ServiceError(
                ErrorCode.UNGROUNDED_EVIDENCE,
                f"Evidence quote could not be verified for red flag: '{quote}'",
                field="red_flags",
            )