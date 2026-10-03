# Replaceable offline and OpenAI-compatible assessment providers.
from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from .contracts import AssessmentDraft, CriterionScore, ImprovementActionDraft, InvestorQuestion
from .errors import ErrorCode, ServiceError
from .extraction import RenderedPage
from .prompt import ProviderRequest
from .rubric import RubricDefinition


@dataclass(frozen=True)
class ProviderResponse:
    draft: AssessmentDraft
    provider: str
    model_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        vision_model: str | None = None,
        timeout: float = 45.0,
        http_client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model
        self.vision_model = vision_model
        self.timeout = timeout
        self.client = http_client or httpx.Client(timeout=timeout)
        self.sleeper = sleeper

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(2):
            try:
                response = self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                    timeout=self.timeout,
                )
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    continue
                raise ServiceError(
                    ErrorCode.PROVIDER_TIMEOUT,
                    "The AI provider timed out.",
                    retryable=True,
                    status_code=504,
                ) from exc
            except httpx.RequestError as exc:
                if attempt == 0:
                    continue
                raise ServiceError(
                    ErrorCode.PROVIDER_UNAVAILABLE,
                    "The AI provider is unavailable.",
                    retryable=True,
                    status_code=503,
                ) from exc
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt == 0:
                try:
                    delay = min(2.0, max(0.0, float(response.headers.get("Retry-After", "0"))))
                except ValueError:
                    delay = 0.0
                self.sleeper(delay)
                continue
            if response.status_code >= 400:
                raise ServiceError(
                    ErrorCode.PROVIDER_UNAVAILABLE,
                    "The AI provider rejected the request.",
                    retryable=retryable,
                    status_code=503,
                )
            try:
                payload: dict[str, Any] = response.json()
                return payload
            except ValueError as exc:
                raise ServiceError(
                    ErrorCode.INVALID_MODEL_OUTPUT,
                    "The AI provider returned invalid JSON.",
                    status_code=502,
                ) from exc
        raise AssertionError("provider retry loop exhausted")

    @staticmethod
    def _content(payload: Mapping[str, Any]) -> Any:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                "The AI provider response shape is invalid.",
                status_code=502,
            ) from exc
        try:
            return json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError as exc:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                "The AI provider returned malformed structured output.",
                status_code=502,
            ) from exc

    def assess(self, request: ProviderRequest) -> ProviderResponse:
        body = {
            "model": self.model_id,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "mamakscore_assessment",
                    "strict": True,
                    "schema": request.response_schema,
                },
            },
        }
        payload = self._post(body)
        try:
            draft = AssessmentDraft.model_validate(self._content(payload))
        except ValidationError as exc:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                "The AI provider output did not match the assessment contract.",
                status_code=502,
            ) from exc
        usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
        return ProviderResponse(
            draft=draft,
            provider="openai-compatible",
            model_id=self.model_id,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )

    def transcribe(self, pages: Sequence[RenderedPage]) -> Mapping[int, str]:
        if not self.vision_model:
            raise ServiceError(ErrorCode.VISION_REQUIRED, "A vision model is not configured.")
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": "Transcribe each slide verbatim. Return JSON with pages containing page and text fields.",
            }
        ]
        for page in pages:
            content += [
                {"type": "text", "text": f"Page {page.number}"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64," + base64.b64encode(page.png).decode()
                    },
                },
            ]
        payload = self._post(
            {
                "model": self.vision_model,
                "temperature": 0,
                "messages": [{"role": "user", "content": content}],
                "response_format": {"type": "json_object"},
            }
        )
        parsed = self._content(payload)
        try:
            return {int(item["page"]): str(item["text"]) for item in parsed["pages"]}
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceError(
                ErrorCode.INVALID_MODEL_OUTPUT,
                "Vision transcription output is invalid.",
                status_code=502,
            ) from exc


class OfflineProvider:
    model_id = "offline-fixture-v1"

    def __init__(self, rubric: RubricDefinition, source_filename: str) -> None:
        self.rubric = rubric
        self.source_filename = source_filename

    def assess(self, request: ProviderRequest) -> ProviderResponse:
        match = re.search(
            r"<untrusted_submission>\s*(.*?)\s*</untrusted_submission>", request.user_content, re.S
        )
        raw = match.group(1) if match else request.user_content
        try:
            payload = json.loads(raw)
            deck = payload.get("deck_text", raw)
            source_filename = payload.get("deck_filename", self.source_filename)
        except json.JSONDecodeError:
            deck = raw
            source_filename = self.source_filename
        lines = [
            line.strip()
            for line in str(deck).splitlines()
            if len(line.strip()) >= 20 and not line.startswith("[Page ")
        ]
        quote = lines[0] if lines else str(deck).strip()[:200]
        scores = [
            CriterionScore(
                criterion_id=c.id,
                score=4,
                justification="Offline fixture score for pipeline verification only.",
                evidence_quote=quote,
                source_file=source_filename,
                confidence="low",
            )
            for c in self.rubric.criteria
        ]
        questions = [
            InvestorQuestion(
                question=f"What stronger evidence can you provide for {c.name}?",
                criterion_ids=[c.id],
                evidence_quote=quote,
            )
            for c in self.rubric.criteria[:5]
        ]
        actions = [
            ImprovementActionDraft(
                action=f"Add quantified evidence for {c.name}.",
                criterion_id=c.id,
                target_score=6,
                priority="high",
            )
            for c in self.rubric.criteria[:3]
        ]
        draft = AssessmentDraft(
            criterion_scores=scores,
            investor_questions=questions,
            improvement_actions=actions,
            missing_information=["Offline fixture: real model evaluation not run."],
        )
        return ProviderResponse(draft=draft, provider="offline", model_id=self.model_id)
