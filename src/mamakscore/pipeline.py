"""Evaluation Pipeline Orchestrator."""

import hashlib
from decimal import Decimal
from typing import Any, Dict, List, Optional

from mamakscore.cache import ReplayCache
from mamakscore.confidence import calculate_mamak_confidence
from mamakscore.contracts import (
    AssessmentResult,
    ConfidenceContainer,
    ExtractionLimits,
    FinancialResult,
    Provenance,
    WorkbookLimits,
)
from mamakscore.errors import ErrorCode, ServiceError
from mamakscore.extraction import VisionExtractor, extract_pdf
from mamakscore.grounding import verify_grounding
from mamakscore.intelligence import validate_assessment_draft
from mamakscore.prompt import (
    build_system_prompt,
    build_user_prompt,
    compute_prompt_digest,
)
from mamakscore.provider import OfflineProvider, OpenAIProvider, ProviderRequest
from mamakscore.report import render_report
from mamakscore.rubric import RubricDefinition
from mamakscore.scoring import (
    build_improvement_actions,
    calculate_mamak_score,
    classify_score,
)
from mamakscore.workbook import parse_workbook


class EvaluationPipeline:
    """Orchestrates end-to-end evaluation of pitch decks and financial models."""

    def __init__(
        self,
        rubric: RubricDefinition,
        provider: Any,
        cache: Optional[ReplayCache] = None,
        vision: Optional[VisionExtractor] = None,
        extraction_limits: Optional[ExtractionLimits] = None,
        workbook_limits: Optional[WorkbookLimits] = None,
        expose_confidence: bool = True,
    ):
        self.rubric = rubric
        self.provider = provider
        self.cache = cache
        self.vision = vision
        self.extraction_limits = extraction_limits or ExtractionLimits()
        self.workbook_limits = workbook_limits or WorkbookLimits()
        self.expose_confidence = expose_confidence
        self.system_prompt = build_system_prompt(self.rubric)
        self.prompt_digest = compute_prompt_digest(self.system_prompt)

    def evaluate(
        self,
        application_id: str,
        pitch_deck_bytes: bytes,
        pitch_deck_filename: str = "deck.pdf",
        financial_model_bytes: Optional[bytes] = None,
        financial_model_filename: Optional[str] = None,
        use_cache: bool = True,
    ) -> AssessmentResult:
        # 1. PDF Extraction
        extraction = extract_pdf(
            data=pitch_deck_bytes,
            filename=pitch_deck_filename,
            limits=self.extraction_limits,
            vision=self.vision,
        )

        # 2. Workbook Parsing (Optional)
        financials: Optional[FinancialResult] = None
        if financial_model_bytes:
            try:
                financials = parse_workbook(
                    data=financial_model_bytes,
                    filename=financial_model_filename or "finance.xlsx",
                    limits=self.workbook_limits,
                )
            except Exception:
                financials = None

        # Fallback when no financial model is submitted or it fails safely
        if financials is None:
            financials = FinancialResult(
                has_model=False,
                provided=False,
                model_family="none",
                metrics={},
            )

        # 3. Prompt Preparation
        user_prompt = build_user_prompt(extraction.canonical_text, financials)
        input_digest = hashlib.sha256(
            f"{extraction.source_file.sha256}:{financial_model_bytes is not None}".encode("utf-8")
        ).hexdigest()

        # 4. Check Replay Cache
        model_id = getattr(self.provider, "model_id", "default")
        cache_key = None
        draft = None
        from_cache = False

        if self.cache and self.cache.enabled and use_cache:
            cache_key = self.cache.compute_cache_key(
                input_digest=input_digest,
                model_id=model_id,
                rubric_digest=self.rubric.digest,
                prompt_digest=self.prompt_digest,
            )
            draft = self.cache.get(cache_key)
            if draft is not None:
                from_cache = True

        # 5. Call Provider on Cache Miss
        tokens_used = 0
        estimated_cost = 0.0
        provider_name = getattr(self.provider, "provider_name", "offline")

        if draft is None:
            request = ProviderRequest(
                system_prompt=self.system_prompt,
                user_prompt=user_prompt,
                rubric_digest=self.rubric.digest,
                prompt_digest=self.prompt_digest,
            )
            response = self.provider.assess(request)
            draft = response.draft
            tokens_used = getattr(response, "tokens_used", 120)
            estimated_cost = getattr(response, "estimated_cost_usd", 0.005)
            provider_name = getattr(response, "provider", provider_name)
            model_id = getattr(response, "model_id", model_id)

            if self.cache and self.cache.enabled and cache_key:
                self.cache.put(cache_key, draft)

        # Build provenance
        provenance = Provenance(
            model_id=model_id,
            provider=provider_name,
            rubric_digest=self.rubric.digest,
            prompt_digest=self.prompt_digest,
            from_cache=from_cache,
            tokens_used=tokens_used,
            estimated_cost_usd=estimated_cost,
        )

        # 6. Validate Draft against Rubric
        validated_draft = validate_assessment_draft(draft, self.rubric)

        # 7. Grounding Verification
        verify_grounding(validated_draft, [extraction.canonical_text])

        # 8. Deterministic Scoring & Banding
        mamak_score = calculate_mamak_score(validated_draft.criterion_scores, self.rubric)
        
        # Dual-Gate Critical Flaw Score Cap
        has_critical = any(
            (getattr(rf, "severity", "") or "").lower() == "critical"
            for rf in validated_draft.red_flags
        )
        if has_critical:
            mamak_score = min(mamak_score, Decimal("39.9"))

        band = classify_score(mamak_score)
        improvement_actions = build_improvement_actions(
            validated_draft.improvement_actions,
            validated_draft.criterion_scores,
            self.rubric,
        )

        # 9. Provisional Confidence
        if self.expose_confidence:
            m_verified = (
                len([m for m in financials.metrics.values() if getattr(m, "value", None) is not None])
                if financials.provided
                else 0
            )
            d_total = len(financials.metrics) if financials.provided else 0
            conf_val = calculate_mamak_confidence(
                verified_quotes_count=len([s for s in validated_draft.criterion_scores if (s.evidence_quote or "").strip()]),
                total_verified_quotes=len([s for s in validated_draft.criterion_scores if (s.evidence_quote or "").strip()]),
                calculated_metrics_count=m_verified,
                contradictions_count=0,
                total_comparisons=d_total,
                red_flags=validated_draft.red_flags,
                has_financial_model=financials.provided,
            )
            conf_obj = ConfidenceContainer(
                score=conf_val,
                mamak_confidence=conf_val,
                status="PROVISIONAL_NOT_CLIENT_APPROVED",
            )
        else:
            conf_val = None
            conf_obj = ConfidenceContainer(status="PROVISIONAL_NOT_CLIENT_APPROVED")

        result = AssessmentResult(
            application_id=application_id,
            mamak_score=mamak_score,
            band=band,
            criterion_scores=validated_draft.criterion_scores,
            red_flags=validated_draft.red_flags,
            improvement_actions=improvement_actions,
            investor_questions=validated_draft.investor_questions,
            missing_information=validated_draft.missing_information,
            financials=financials,
            provenance=provenance,
            mamak_confidence=conf_obj,
            provisional_confidence=conf_val,
        )

        rendered_report = render_report(result)
        result.report_html = rendered_report
        result.html_report = rendered_report
        return result