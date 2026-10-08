"""System prompts, prompt digest hashing, and JSON schemas for LLM assessment."""
import hashlib
from typing import Any, Dict, Optional
from pydantic import BaseModel, model_validator
from mamakscore.contracts import FinancialResult
from mamakscore.rubric import RubricDefinition


class ProviderRequest(BaseModel):
    system_prompt: str
    user_prompt: str = ""
    user_content: Optional[str] = None
    rubric_digest: str = ""
    prompt_digest: str = ""
    response_schema: Optional[Dict[str, Any]] = None
    temperature: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def reconcile_prompts(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("user_prompt") or data.get("user_content") or ""
            data["user_prompt"] = val
            data["user_content"] = val
        return data


ProviderRequest.model_rebuild()


def compute_prompt_digest(system_prompt: str, response_schema: Any = None) -> str:
    """Computes SHA-256 digest of system prompt and optional schema."""
    composite = system_prompt.strip()
    if response_schema:
        composite += f":{json.dumps(response_schema, sort_keys=True) if isinstance(response_schema, dict) else str(response_schema)}"
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()


prompt_digest = compute_prompt_digest


def build_system_prompt(rubric: RubricDefinition) -> str:
    criteria_lines = []
    for c in rubric.criteria:
        criteria_lines.append(f"- **{c.id}** ({c.name}, Weight: {c.weight}): {c.description}")

    criteria_block = "\n".join(criteria_lines)

    return f"""You are MamakScore AI, an elite venture capital due diligence assessment engine.
Your task is to evaluate an early-stage startup submission against the client's rubric.

RUBRIC CRITERIA (Version {rubric.version}):
{criteria_block}

STRICT OPERATIONAL RULES:
1. You must assess every single criterion listed above exactly once.
2. For each criterion, assign an integer score from 0 to 10.
3. For every non-zero score, provide a verbatim evidence quote copied directly from the pitch deck text.
   - Do NOT edit or fix punctuation or grammar. Quotes must be verbatim substrings from the source document.
   - If evidence is completely absent, assign a score of 0 with an empty evidence quote and a clear justification.
4. Detect feasibility red flags: identify ungrounded assertions, market size contradictions, or operational impossibilities.
5. Provide 5 to 10 unique, probing investor questions for due diligence triage.
6. Provide actionable improvement actions: each action must target an identified criterion and set a target_score strictly higher than the current score.
7. Do not calculate MamakScore; Python code computes all weighted totals deterministically.
"""


def build_user_prompt(
    deck_text: str,
    financials: Optional[FinancialResult] = None,
) -> str:
    prompt = f"<untrusted_submission>\n{deck_text.strip()}\n</untrusted_submission>\n\n"

    if financials and getattr(financials, "has_model", False):
        prompt += "<financial_model>\n"
        for k, v in financials.metrics.items():
            if v.value is not None:
                prompt += f"- {k}: {v.value}\n"
            elif v.unavailable_reason:
                prompt += f"- {k}: [Unavailable: {v.unavailable_reason}]\n"
        prompt += "</financial_model>\n\n"

    prompt += "Please generate the complete AssessmentDraft conforming to the required schema."
    return prompt


def build_provider_request(
    rubric: RubricDefinition,
    deck_text: str,
    filename_or_financials: Any = "deck.pdf",
    financials: Optional[FinancialResult] = None,
) -> ProviderRequest:
    fin_obj = None
    if isinstance(filename_or_financials, FinancialResult):
        fin_obj = filename_or_financials
    elif isinstance(financials, FinancialResult):
        fin_obj = financials

    sys_prompt = build_system_prompt(rubric)
    usr_prompt = build_user_prompt(deck_text, fin_obj)
    p_digest = compute_prompt_digest(sys_prompt)
    return ProviderRequest(
        system_prompt=sys_prompt,
        user_prompt=usr_prompt,
        user_content=usr_prompt,
        rubric_digest=rubric.digest,
        prompt_digest=p_digest,
    )

ProviderRequest.model_rebuild()