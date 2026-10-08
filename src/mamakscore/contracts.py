"""Pydantic schemas and data contracts for MamakScore AI Engine."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- Base Utilities & Comparators ---

class ComparableDelta(str):
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Decimal):
            try:
                return Decimal(self) == other
            except Exception:
                return False
        return super().__eq__(other) or str(self) == str(other)


# --- Input Files & Extraction ---

class SourceFile(BaseModel):
    filename: str = Field(default="")
    name: Optional[str] = None
    media_type: str = "application/pdf"
    size_bytes: int = 0
    sha256: str = ""

    @model_validator(mode="before")
    @classmethod
    def reconcile_filename(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("filename") or data.get("name") or "deck.pdf"
            data["filename"] = val
            data["name"] = val
        return data


class PageDiagnostic(BaseModel):
    page: int
    method: Literal["direct", "vision", "empty"]
    characters: int
    alphanumeric_ratio: float
    printable_ratio: float


class ExtractionResult(BaseModel):
    canonical_text: str
    diagnostics: List[PageDiagnostic]
    source_file: SourceFile
    source: Optional[SourceFile] = None
    method: Literal["direct", "vision", "hybrid"]
    page_count: int = 1

    @model_validator(mode="before")
    @classmethod
    def set_source_and_count(cls, data: Any) -> Any:
        if isinstance(data, dict):
            src = data.get("source_file") or data.get("source")
            data["source_file"] = src
            data["source"] = src
            if "page_count" not in data and "diagnostics" in data:
                data["page_count"] = len(data["diagnostics"])
        return data


class ExtractionLimits(BaseModel):
    max_pdf_bytes: int = 20 * 1024 * 1024       # 20MB
    max_pages: int = 60
    max_text_characters: int = 120_000
    min_page_characters: int = 40
    min_alphanumeric_ratio: float = 0.35
    max_render_side: int = 2048


class WorkbookLimits(BaseModel):
    max_workbook_bytes: int = 10 * 1024 * 1024   # 10MB
    max_sheets: int = 10
    max_rows: int = 1000
    max_columns: int = 50
    max_uncompressed_bytes: int = 50 * 1024 * 1024


# --- Financial Contracts ---

class MetricValue(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    value: Optional[Decimal] = None
    metric_value: Optional[Decimal] = None
    unavailable_reason: Optional[str] = None
    source_formula: Optional[str] = None
    source: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def reconcile_metric_value(cls, data: Any) -> Any:
        if isinstance(data, dict):
            v = data.get("value")
            if v is None:
                v = data.get("metric_value")
            if v is not None:
                try:
                    data["value"] = Decimal(str(v))
                    data["metric_value"] = Decimal(str(v))
                except Exception:
                    pass
        return data


class FinancialInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    has_model: bool = False
    value: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    metric_value: Optional[Decimal] = None
    period: str = "monthly"
    currency: str = "AUD"
    source: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[Any] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def reconcile_financial_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            v = data.get("value")
            if v is None:
                v = data.get("amount")
            if v is None:
                v = data.get("metric_value")
            if v is not None:
                try:
                    data["value"] = Decimal(str(v))
                except Exception:
                    pass
        return data


class FinancialResult(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    has_model: bool = False
    provided: bool = False
    model_family: str = "none"
    detected_model_family: str = "none"
    inputs: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    source_file: Optional[SourceFile] = None
    canonical_text: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def reconcile_family(cls, data: Any) -> Any:
        if isinstance(data, dict):
            fam = data.get("model_family") or data.get("detected_model_family") or "none"
            data["model_family"] = fam
            data["detected_model_family"] = fam
            if "has_model" in data and "provided" not in data:
                data["provided"] = data["has_model"]
            elif "provided" in data and "has_model" not in data:
                data["has_model"] = data["provided"]
        return data


# --- Scoring & Intelligence Contracts ---

class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    score: int = Field(ge=0, le=10)
    justification: str
    evidence_quote: str = ""
    source_file: str = "deck.pdf"
    confidence: Literal["low", "medium", "high"] = "medium"


class RedFlag(BaseModel):
    flag: str = Field(default="")
    flag_type: Optional[str] = None
    severity: Literal["low", "medium", "high", "critical"] = "high"
    summary: str = ""
    evidence_quote: str = ""
    source_file: str = "deck.pdf"

    @model_validator(mode="before")
    @classmethod
    def reconcile_flag(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("flag") or data.get("flag_type") or data.get("summary") or "red_flag"
            data["flag"] = val
            data["flag_type"] = val
            if not data.get("summary"):
                data["summary"] = val
        return data


class ImprovementActionDraft(BaseModel):
    action: str
    criterion_id: str
    target_score: int = Field(ge=0, le=10)
    priority: Literal["low", "medium", "high"] = "medium"


class ImprovementAction(BaseModel):
    action: str
    criterion_id: str
    target_score: int
    priority: str
    projected_gain: Decimal = Field(default=Decimal("0.0"))


class InvestorQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    target_criterion_id: Optional[str] = None
    criterion_ids: List[str] = Field(default_factory=list)
    reasoning: Optional[str] = None

    def __str__(self) -> str:
        return self.question


class AssessmentDraft(BaseModel):
    criterion_scores: List[CriterionScore]
    red_flags: List[RedFlag] = Field(default_factory=list)
    improvement_actions: List[ImprovementActionDraft] = Field(default_factory=list)
    investor_questions: List[Union[str, InvestorQuestion]] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)


class BandResult(BaseModel):
    band_name: str = Field(default="")
    label: Optional[str] = None
    boundary_escalation: bool = False
    human_review_required: bool = True

    @model_validator(mode="before")
    @classmethod
    def reconcile_band(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("band_name") or data.get("label") or "Not ready"
            data["band_name"] = val
            data["label"] = val
        return data


class AssessmentSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    application_id: str
    rubric_version: str
    rubric_digest: str
    criterion_scores: List[CriterionScore]
    mamak_score: Decimal
    band: str
    missing_information: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None


class ComparisonRequest(BaseModel):
    previous: AssessmentSummary
    current: AssessmentSummary
    assessment_a_id: Optional[str] = None
    assessment_b_id: Optional[str] = None

    @model_validator(mode="after")
    def populate_ids(self) -> "ComparisonRequest":
        if not self.assessment_a_id and self.previous:
            self.assessment_a_id = getattr(self.previous, "application_id", "a")
        if not self.assessment_b_id and self.current:
            self.assessment_b_id = getattr(self.current, "application_id", "b")
        return self


class ComparisonResult(BaseModel):
    comparable: bool = True
    application_id: str
    mamak_score_delta: Any
    previous_score: str
    current_score: str
    previous_band: str
    current_band: str
    criterion_deltas: Dict[str, Any] = Field(default_factory=dict)
    resolved_missing_information: List[str] = Field(default_factory=list)
    new_missing_information: List[str] = Field(default_factory=list)
    categories: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def reconcile_scores(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "mamak_score_delta" in data and data["mamak_score_delta"] is not None:
                data["mamak_score_delta"] = ComparableDelta(str(data["mamak_score_delta"]))
            for k in ("previous_score", "current_score"):
                if k in data and data[k] is not None:
                    data[k] = str(data[k])
        return data


class ConfidenceInputPayload(BaseModel):
    n_verified: int = Field(default=0, ge=0, le=100)
    has_financial_model: bool = Field(default=False)
    m_verified: int = Field(default=0, ge=0, le=6)
    d_discrepancies: int = Field(default=0, ge=0, le=50)
    d_total: int = Field(default=0, ge=0, le=50)
    red_flags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_invariants(self) -> "ConfidenceInputPayload":
        if not self.has_financial_model and self.m_verified > 0:
            raise ValueError("Phantom financial metrics: has_financial_model is False but m_verified > 0")
        if self.d_total == 0 and self.d_discrepancies > 0:
            raise ValueError("Phantom discrepancies: d_total is 0 but d_discrepancies > 0")
        return self


class ConfidenceContainer(BaseModel):
    model_config = ConfigDict(extra="allow")

    score: Optional[float] = None
    mamak_confidence: Optional[float] = None
    status: str = "PROVISIONAL_NOT_CLIENT_APPROVED"
    breakdown: Dict[str, Any] = Field(default_factory=dict)


class Provenance(BaseModel):
    model_id: str
    provider: str
    rubric_digest: str
    prompt_digest: str
    from_cache: bool = False
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0


class AssessmentResult(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    application_id: str
    mamak_score: Decimal
    band: BandResult
    criterion_scores: List[CriterionScore]
    red_flags: List[RedFlag] = Field(default_factory=list)
    improvement_actions: List[ImprovementAction] = Field(default_factory=list)
    provisional_confidence: Optional[float] = None
    mamak_confidence: ConfidenceContainer = Field(default_factory=ConfidenceContainer)
    investor_questions: List[Union[str, InvestorQuestion]] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    financials: Optional[FinancialResult] = None
    provenance: Provenance
    report_html: str = ""
    html_report: str = ""


# Rebuild models to resolve forward references
AssessmentDraft.model_rebuild()
AssessmentResult.model_rebuild()
FinancialResult.model_rebuild()
ComparisonResult.model_rebuild()