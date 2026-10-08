"""LLM Provider abstractions: Offline deterministic provider and OpenAI compatible provider."""

import json
import os
import time
from typing import Any, List, Optional
import httpx
from pydantic import BaseModel
from mamakscore.contracts import (
    AssessmentDraft,
    CriterionScore,
    ImprovementActionDraft,
    InvestorQuestion,
    RedFlag,
)
from mamakscore.errors import ErrorCode, ServiceError
from mamakscore.prompt import ProviderRequest
from mamakscore.rubric import RubricDefinition


class ProviderResponse(BaseModel):
    draft: AssessmentDraft
    provider: str
    model_id: str
    tokens_used: int = 120
    input_tokens: int = 100
    output_tokens: int = 20
    estimated_cost_usd: float = 0.005


class OfflineProvider:
    """Offline deterministic provider that generates grounded draft assessments."""

    def __init__(self, rubric: RubricDefinition, source_filename: str = "deck.pdf"):
        self.rubric = rubric
        self.source_filename = source_filename
        self.provider_name = "offline"
        self.model_id = "offline-fixture-v1"

    def assess(self, request: ProviderRequest) -> ProviderResponse:
        user_text = request.user_content or request.user_prompt or ""
        body = user_text

        if "<untrusted_submission>" in user_text:
            body = user_text.split("<untrusted_submission>")[1].split("</untrusted_submission>")[0].strip()
        elif "=== BEGIN UNTRUSTED APPLICANT PITCH DECK CONTENT ===" in user_text:
            body = user_text.split("=== BEGIN UNTRUSTED APPLICANT PITCH DECK CONTENT ===")[1].split("=== END UNTRUSTED APPLICANT PITCH DECK CONTENT ===")[0].strip()

        quote = ""
        for line in body.splitlines():
            s = line.strip()
            if s.startswith("[Page") or not s:
                continue
            if len(s) >= 15:
                quote = s[:45].strip()
                break

        if not quote:
            clean_body = " ".join(body.split())
            if len(clean_body) >= 15:
                quote = clean_body[:40].strip()
            else:
                quote = clean_body if clean_body else "Clinics lose 20 hours weekly"

        scores: List[CriterionScore] = []
        for c in self.rubric.criteria:
            scores.append(
                CriterionScore(
                    criterion_id=c.id,
                    score=4,  # Sum: 4 * 10 = 40.0
                    justification=f"Substantiated analysis for {c.name}.",
                    evidence_quote=quote,
                    source_file=self.source_filename,
                    confidence="medium",
                )
            )

        red_flags: List[RedFlag] = [
            RedFlag(
                flag_type="unrealistic_tam",
                flag="unrealistic_tam",
                severity="medium",
                summary="High projection requiring verification",
                evidence_quote=quote,
                source_file=self.source_filename,
            )
        ]

        improvement_actions = [
            ImprovementActionDraft(
                action=f"Expand market evidence for {self.rubric.criteria[0].id}",
                criterion_id=self.rubric.criteria[0].id,
                target_score=8,
                priority="high",
            ),
            ImprovementActionDraft(
                action=f"Add unit economics breakdown for {self.rubric.criteria[1].id}",
                criterion_id=self.rubric.criteria[1].id,
                target_score=7,
                priority="medium",
            ),
        ]

        questions = [
            InvestorQuestion(
                question=f"What are the direct conversion rates for {c.name}?",
                criterion_ids=[c.id],
            )
            for c in self.rubric.criteria[:5]
        ]

        draft = AssessmentDraft(
            criterion_scores=scores,
            red_flags=red_flags,
            improvement_actions=improvement_actions,
            investor_questions=questions,
            missing_information=[],
        )

        return ProviderResponse(
            draft=draft,
            provider=self.provider_name,
            model_id=self.model_id,
            tokens_used=120,
            input_tokens=100,
            output_tokens=20,
            estimated_cost_usd=0.005,
        )


class OpenAICompatibleProvider:
    """Provider for hosted OpenAI compatible APIs with retries and error isolation."""

    def __init__(
        self,
        base_url_or_key: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        http_client: Optional[Any] = None,
        sleeper: Optional[Any] = None,
    ):
        if base_url_or_key and base_url_or_key.startswith("http"):
            self.base_url = base_url_or_key
            self.api_key = api_key or "secret"
            self.model_name = model_name or "open-model"
        else:
            self.base_url = os.getenv("OPENAI_BASE_URL")
            self.api_key = base_url_or_key or api_key or os.getenv("OPENAI_API_KEY", "")
            self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-4o")

        self.http_client = http_client
        self.sleeper = sleeper or time.sleep
        self.provider_name = "openai-compatible"
        self.model_id = self.model_name

    def assess(self, request: ProviderRequest) -> ProviderResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt or request.user_content or ""},
            ],
            "response_format": {"type": "json_object"},
            "temperature": request.temperature,
        }

        client = self.http_client or httpx.Client()
        url = (
            f"{self.base_url.rstrip('/')}/chat/completions"
            if self.base_url
            else "https://api.openai.com/v1/chat/completions"
        )

        response = None
        for attempt in range(2):
            try:
                res = client.post(url, headers=headers, json=payload)
            except Exception as exc:
                raise ServiceError(
                    ErrorCode.PROVIDER_ERROR, f"Connection failed: {str(exc)}", retryable=False
                )

            if res.status_code == 429:
                if attempt == 0:
                    self.sleeper(1.0)
                    continue
                raise ServiceError(
                    ErrorCode.OVER_CAPACITY, "Provider rate limit reached.", retryable=True
                )
            if res.status_code in (401, 403):
                raise ServiceError(
                    ErrorCode.AUTH_ERROR,
                    "Authentication failed with LLM provider.",
                    retryable=False,
                )
            if res.status_code >= 400:
                raise ServiceError(
                    ErrorCode.PROVIDER_ERROR,
                    f"Provider returned error status {res.status_code}",
                    retryable=False,
                )

            response = res
            break

        if response is None:
            raise ServiceError(
                ErrorCode.PROVIDER_ERROR, "No response from LLM provider.", retryable=False
            )

        data = response.json()
        raw_msg = data["choices"][0]["message"]["content"]
        draft_dict = json.loads(raw_msg)
        draft = AssessmentDraft.model_validate(draft_dict)

        usage = data.get("usage", {})
        inp_toks = usage.get("prompt_tokens", 100)
        out_toks = usage.get("completion_tokens", 20)
        tot_toks = usage.get("total_tokens", inp_toks + out_toks)

        return ProviderResponse(
            draft=draft,
            provider=self.provider_name,
            model_id=self.model_name,
            tokens_used=tot_toks,
            input_tokens=inp_toks,
            output_tokens=out_toks,
            estimated_cost_usd=0.005,
        )


OpenAIProvider = OpenAICompatibleProvider
__all__ = ["OfflineProvider", "OpenAIProvider", "OpenAICompatibleProvider", "ProviderResponse"]