"""Data contracts and schemas for MamakScore AI."""

from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class ConfidenceInputPayload(BaseModel):
    """Schema validating the raw input counts fed into confidence scoring."""
    n_verified: int = Field(default=0, ge=0, le=100, description="Count of verified quote strings")
    has_financial_model: bool = Field(default=False, description="Whether an Excel model was provided")
    m_verified: int = Field(default=0, ge=0, le=6, description="Count of formula-derived financial metrics")
    d_discrepancies: int = Field(default=0, ge=0, le=50, description="Mismatches between deck and model")
    d_total: int = Field(default=0, ge=0, le=50, description="Total attempted metric comparisons")
    red_flags: List[str] = Field(default_factory=list, description="List of detected qualitative red flags")

    @model_validator(mode="after")
    def validate_invariants(self):
        # Phantom financial metrics
        if not self.has_financial_model and self.m_verified > 0:
            raise ValueError("Phantom financial metrics: has_financial_model is False but m_verified > 0")
        
        # Phantom discrepancies
        if self.d_total == 0 and self.d_discrepancies > 0:
            raise ValueError("Phantom discrepancies: d_total is 0 but d_discrepancies > 0")

        return self


class EvaluationResult(BaseModel):
    """Schema for final evaluation output."""
    mamak_score: float = Field(..., ge=0.0, le=100.0)
    mamak_confidence: float = Field(..., ge=0.0, le=100.0)
    triage_action: str
    confidence_breakdown: dict

class AssessmentDraft(BaseModel):
    """Draft schema representing an intermediate assessment result."""
    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    notes: Optional[str] = None
    flags: List[str] = Field(default_factory=list)
    raw_payload: Optional[ConfidenceInputPayload] = None

class CriterionScore(BaseModel):
    """Score and evidence details for an individual rubric criterion."""
    criterion_id: str
    score: int = Field(..., ge=0, le=10)
    justification: str
    evidence_quote: str
    source_file: str
    confidence: str = Field(default="low")


class InvestorQuestion(BaseModel):
    """Investor question linked to specific criteria."""
    question: str
    criterion_ids: List[str] = Field(default_factory=list)


class ImprovementActionDraft(BaseModel):
    """Actionable improvement recommendation."""
    action: str
    criterion_id: str
    target_score: int
    priority: str = Field(default="medium")


class AssessmentDraft(BaseModel):
    """Draft payload containing scores, investor questions, and improvement actions."""
    criterion_scores: List[CriterionScore] = Field(default_factory=list)
    investor_questions: List[InvestorQuestion] = Field(default_factory=list)
    improvement_actions: List[ImprovementActionDraft] = Field(default_factory=list)

class FinancialResult(BaseModel):
    """Schema representing financial metric evaluation and formula results."""
    metric_name: Optional[str] = None
    value: Optional[float] = None
    verified: bool = False
    discrepancy: bool = False
    notes: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)