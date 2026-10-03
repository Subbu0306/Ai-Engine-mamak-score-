import json
from pathlib import Path

import httpx
import pytest

from mamakscore.contracts import (
    AssessmentDraft,
    CriterionScore,
    ImprovementActionDraft,
    InvestorQuestion,
)
from mamakscore.errors import ServiceError
from mamakscore.prompt import ProviderRequest
from mamakscore.provider import OfflineProvider, OpenAICompatibleProvider
from mamakscore.rubric import load_rubric

R = load_rubric(Path(__file__).parents[1] / "src/mamakscore/data/mamakscore-v3.yaml")


def payload():
    d = AssessmentDraft(
        criterion_scores=[
            CriterionScore(
                criterion_id=c.id,
                score=4,
                justification="Reason",
                evidence_quote="Evidence line long enough",
                source_file="deck.pdf",
                confidence="low",
            )
            for c in R.criteria
        ],
        investor_questions=[
            InvestorQuestion(question=f"Question {i}?", criterion_ids=[R.criteria[i].id])
            for i in range(5)
        ],
        improvement_actions=[
            ImprovementActionDraft(
                action="Add evidence", criterion_id="market", target_score=6, priority="high"
            )
        ],
    )
    return d.model_dump(mode="json")


def request():
    return ProviderRequest(
        system_prompt="system",
        user_content="<untrusted_submission>Evidence line long enough</untrusted_submission>",
        response_schema=AssessmentDraft.model_json_schema(),
    )


def test_hosted_provider_parses_structured_response():
    def handler(req):
        assert req.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(payload())}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatibleProvider(
        "https://example.test/v1",
        "secret",
        "open-model",
        http_client=client,
        sleeper=lambda _: None,
    )
    result = p.assess(request())
    assert len(result.draft.criterion_scores) == 9 and result.input_tokens == 100


def test_retry_once_on_429():
    calls = 0

    def handler(req):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(payload())}}]}
        )

    p = OpenAICompatibleProvider(
        "https://example.test/v1",
        "secret",
        "model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _: None,
    )
    p.assess(request())
    assert calls == 2


def test_no_retry_or_body_leak_on_auth_error():
    p = OpenAICompatibleProvider(
        "https://example.test/v1",
        "secret",
        "model",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(401, text="sensitive body"))
        ),
        sleeper=lambda _: None,
    )
    with pytest.raises(ServiceError) as exc:
        p.assess(request())
    assert "sensitive" not in str(exc.value) and exc.value.retryable is False


def test_offline_provider_is_deterministic_and_grounded():
    p = OfflineProvider(R, "deck.pdf")
    one = p.assess(
        ProviderRequest(
            system_prompt="x",
            user_content="<untrusted_submission>Evidence line long enough to quote safely.\nMore source text.</untrusted_submission>",
            response_schema={},
        )
    )
    two = p.assess(
        ProviderRequest(
            system_prompt="y",
            user_content="<untrusted_submission>Evidence line long enough to quote safely.\nMore source text.</untrusted_submission>",
            response_schema={},
        )
    )
    assert one.draft == two.draft and one.model_id == "offline-fixture-v1"
