# End-to-end AI Engine orchestration.
from __future__ import annotations

import hashlib
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from .cache import ReplayCache
from .confidence import FORMULA_VERSION, calculate_confidence
from .contracts import AssessmentResult, FinancialResult, Provenance, RedFlag, SourceFile, Timing
from .errors import ErrorCode, ServiceError
from .extraction import ExtractionLimits, extract_pdf
from .grounding import normalize_evidence, verify_category_evidence, verify_red_flag_evidence
from .intelligence import validate_assessment_draft
from .prompt import PROMPT_VERSION, build_provider_request, prompt_digest
from .report import render_report
from .rubric import RubricDefinition
from .scoring import build_improvement_actions, calculate_mamak_score, classify_score
from .workbook import WorkbookLimits, parse_workbook


class EvaluationPipeline:
    def __init__(
        self,
        rubric: RubricDefinition,
        provider: Any,
        *,
        cache: ReplayCache | None = None,
        extraction_limits: ExtractionLimits | None = None,
        workbook_limits: WorkbookLimits | None = None,
        expose_confidence: bool = False,
    ) -> None:
        self.rubric = rubric
        self.provider = provider
        self.cache = (
            cache if cache is not None else ReplayCache(Path(".cache/replay.sqlite3"), False)
        )
        self.extraction_limits = extraction_limits or ExtractionLimits()
        self.workbook_limits = workbook_limits or WorkbookLimits()
        self.expose_confidence = expose_confidence

    @staticmethod
    def _normalize_contradictions(
        flags: list[RedFlag], financials: FinancialResult
    ) -> list[RedFlag]:
        output = []
        for flag in flags:
            if flag.computed_metric:
                metric = financials.metrics.get(flag.computed_metric)
                if metric is None or metric.value is None or flag.claimed_value is None:
                    raise ServiceError(
                        ErrorCode.INVALID_MODEL_OUTPUT,
                        "A financial contradiction references an unavailable metric.",
                        status_code=502,
                    )
                denominator = abs(metric.value)
                difference = abs(flag.claimed_value - metric.value)
                relative = (
                    Decimal(0)
                    if denominator == 0 and difference == 0
                    else (difference / denominator if denominator else Decimal(1))
                )
                flag = flag.model_copy(
                    update={"relative_difference": relative.quantize(Decimal("0.001"))}
                )
            output.append(flag)
        return output

    def evaluate(
        self,
        application_id: str,
        pitch_deck: bytes,
        deck_filename: str,
        financial_model: bytes | None = None,
        financial_filename: str | None = None,
        use_cache: bool = False,
    ) -> AssessmentResult:
        started = time.perf_counter()
        extraction = extract_pdf(
            pitch_deck,
            deck_filename,
            self.extraction_limits,
            vision=self.provider if getattr(self.provider, "vision_model", None) else None,
        )
        extraction_elapsed = time.perf_counter() - started
        source_files = [extraction.source]
        if financial_model is None:
            from .finance import calculate_financials

            financials = calculate_financials({}).model_copy(update={"model_family": "none"})
        else:
            name = financial_filename or "financial-model.xlsx"
            source_files.append(
                SourceFile(
                    name=name,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    size_bytes=len(financial_model),
                    sha256=hashlib.sha256(financial_model).hexdigest(),
                )
            )
            try:
                financials = parse_workbook(financial_model, name, self.workbook_limits)
            except ServiceError as exc:
                from .finance import calculate_financials

                financials = calculate_financials({}).model_copy(
                    update={"provided": True, "model_family": "unknown", "warnings": [str(exc)]}
                )
        request = build_provider_request(
            self.rubric, extraction.canonical_text, deck_filename, financials
        )
        pdigest = prompt_digest(request.system_prompt, request.response_schema)
        input_digest = hashlib.sha256(
            "".join(item.sha256 for item in source_files).encode()
        ).hexdigest()
        key = ReplayCache.make_key(
            input_digest, self.provider.model_id, self.rubric.digest(), pdigest, FORMULA_VERSION
        )
        provider_started = time.perf_counter()
        cached = self.cache.get(key) if use_cache else None
        if cached is None:
            provider_response = self.provider.assess(request)
            draft = provider_response.draft
            if use_cache:
                self.cache.put(key, draft)
            from_cache = False
        else:
            draft = cached
            from_cache = True
            from .provider import ProviderResponse

            provider_response = ProviderResponse(
                draft=draft, provider="replay-cache", model_id=self.provider.model_id
            )
        provider_elapsed = time.perf_counter() - provider_started
        draft = validate_assessment_draft(draft, self.rubric)
        sources = {deck_filename: extraction.canonical_text}
        if financial_model is not None and financial_filename:
            sources[financial_filename] = financials.canonical_text
        verify_category_evidence(
            draft.criterion_scores, sources, self.rubric.not_stated_justification
        )
        verify_red_flag_evidence(draft.red_flags, sources)
        for question in draft.investor_questions:
            if question.evidence_quote and not any(
                normalize_evidence(question.evidence_quote) in normalize_evidence(text)
                for text in sources.values()
            ):
                raise ServiceError(
                    ErrorCode.UNGROUNDED_EVIDENCE,
                    "An investor-question quotation could not be verified.",
                )
        flags = self._normalize_contradictions(draft.red_flags, financials)
        score = calculate_mamak_score(draft.criterion_scores, self.rubric)
        band = classify_score(score)
        actions = build_improvement_actions(
            draft.improvement_actions, draft.criterion_scores, self.rubric
        )
        confidence = calculate_confidence(
            draft.criterion_scores, flags, expose=self.expose_confidence
        )
        total = time.perf_counter() - started
        provenance = Provenance(
            provider=provider_response.provider,
            model_id=provider_response.model_id,
            rubric_version=self.rubric.version,
            rubric_digest=self.rubric.digest(),
            prompt_version=PROMPT_VERSION,
            prompt_digest=pdigest,
            input_digest=input_digest,
            confidence_formula_version=FORMULA_VERSION,
            from_cache=from_cache,
            input_tokens=provider_response.input_tokens,
            output_tokens=provider_response.output_tokens,
            estimated_cost_usd=Decimal(str(provider_response.estimated_cost_usd))
            if provider_response.estimated_cost_usd is not None
            else None,
        )
        result = AssessmentResult(
            application_id=application_id,
            source_files=source_files,
            extraction=extraction,
            financials=financials,
            criterion_scores=draft.criterion_scores,
            mamak_score=score,
            band=band,
            mamak_confidence=confidence,
            red_flags=flags,
            investor_questions=draft.investor_questions,
            improvement_plan=actions,
            missing_information=draft.missing_information,
            report_html="",
            provenance=provenance,
            timing=Timing(
                extraction_seconds=round(extraction_elapsed, 4),
                provider_seconds=round(provider_elapsed, 4),
                total_seconds=round(total, 4),
            ),
        )
        return result.model_copy(update={"report_html": render_report(result)})
