"""Ground model quotations in caller-supplied source text."""

import re
import unicodedata
from collections.abc import Mapping, Sequence

from .contracts import CriterionScore, RedFlag
from .errors import ErrorCode, ServiceError

TRANSLATION: dict[int, str] = {
    ord("“"): '"',
    ord("”"): '"',
    ord("‘"): "'",
    ord("’"): "'",
    ord("–"): "-",
    ord("—"): "-",
}


def normalize_evidence(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return (
        re.sub(
            r"\s+",
            " ",
            text.translate(TRANSLATION),
        )
        .strip()
        .casefold()
    )


def _is_grounded(quote: str, source: str) -> bool:
    return normalize_evidence(quote) in normalize_evidence(source)


def verify_category_evidence(
    scores: Sequence[CriterionScore], sources: Mapping[str, str], not_stated_justification: str
) -> None:
    failed = []
    for item in scores:
        quote = item.evidence_quote.strip()
        if not quote:
            if item.score != 0 or item.justification.strip() != not_stated_justification:
                failed.append(item.criterion_id)
            continue
        source = sources.get(item.source_file)
        if source is None or not _is_grounded(quote, source):
            failed.append(item.criterion_id)
    if failed:
        raise ServiceError(
            ErrorCode.UNGROUNDED_EVIDENCE,
            "One or more evidence quotations could not be verified.",
            details={"criterion_ids": sorted(failed)},
        )


def verify_red_flag_evidence(flags: Sequence[RedFlag], sources: Mapping[str, str]) -> None:
    failed = []
    for index, flag in enumerate(flags):
        quote = flag.evidence_quote.strip()
        if not quote:
            continue
        source = sources.get(flag.source_file or "")
        if source is None or not _is_grounded(quote, source):
            failed.append(index)
    if failed:
        raise ServiceError(
            ErrorCode.UNGROUNDED_EVIDENCE,
            "One or more red-flag quotations could not be verified.",
            details={"flag_indexes": failed},
        )
