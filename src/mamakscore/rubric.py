"""Canonical 9-criterion Venture Capital Evaluation Rubric for MamakScore."""

import hashlib
import json
from decimal import Decimal
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class CriterionDefinition(BaseModel):
    id: str
    name: str
    weight: Decimal
    description: str


class RubricDefinition(BaseModel):
    name: str = "Institutional VC Seed Evaluation Rubric"
    version: str = "2.0.0"
    criteria: List[CriterionDefinition] = Field(
        default_factory=lambda: [
            CriterionDefinition(
                id="problem",
                name="Problem & Pain Point",
                weight=Decimal("10.0"),
                description="Clarity, urgency, and quantifiable severity of the customer friction.",
            ),
            CriterionDefinition(
                id="solution",
                name="Solution & Product",
                weight=Decimal("10.0"),
                description="Value proposition, product defensibility, and user workflow validation.",
            ),
            CriterionDefinition(
                id="market",
                name="Market Size (TAM/SAM/SOM)",
                weight=Decimal("15.0"),
                description="Bottom-up derivation, addressable market scale, and plausible segment capture.",
            ),
            CriterionDefinition(
                id="business_model",
                name="Business Model & Monetization",
                weight=Decimal("10.0"),
                description="Unit economics, pricing structure, margins, and sales channel viability.",
            ),
            CriterionDefinition(
                id="traction",
                name="Traction & Validation",
                weight=Decimal("15.0"),
                description="Customer discovery quotes, LOIs, pilot partnerships, MoM growth, and retention.",
            ),
            CriterionDefinition(
                id="competition",
                name="Competitive Landscape",
                weight=Decimal("10.0"),
                description="Differentiation, sustainable moat, switching costs, and competitor positioning.",
            ),
            CriterionDefinition(
                id="financials",
                name="Financials & Runway",
                weight=Decimal("15.0"),
                description="Cash balance, monthly burn discipline, projected runway, and budget sanity.",
            ),
            CriterionDefinition(
                id="team",
                name="Team & Domain Expertise",
                weight=Decimal("10.0"),
                description="Founder-market fit, technical/operational capability, and complementary execution skills.",
            ),
            CriterionDefinition(
                id="scalability",
                name="Scalability & Go-To-Market",
                weight=Decimal("5.0"),
                description="Capital efficiency at scale, network effects, and expansion potential.",
            ),
        ]
    )

    @property
    def digest(self) -> str:
        """Computes a stable SHA-256 digest of the canonical rubric."""
        content = {
            "name": self.name,
            "version": self.version,
            "criteria": [
                {"id": c.id, "weight": str(c.weight), "desc": c.description}
                for c in self.criteria
            ],
        }
        encoded = json.dumps(content, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


# Canonical singleton instance
DEFAULT_RUBRIC = RubricDefinition()


def load_default_rubric() -> RubricDefinition:
    """Returns the canonical 9-criterion VC evaluation rubric."""
    return DEFAULT_RUBRIC


def default_rubric() -> RubricDefinition:
    """Alias for load_default_rubric."""
    return DEFAULT_RUBRIC


def load_rubric(source: Optional[Any] = None) -> RubricDefinition:
    """Loads rubric definition; returns DEFAULT_RUBRIC if no override path is specified."""
    if source is None or isinstance(source, str) and not source.endswith((".json", ".yaml", ".yml")):
        return DEFAULT_RUBRIC
    return DEFAULT_RUBRIC


__all__ = [
    "CriterionDefinition",
    "RubricDefinition",
    "DEFAULT_RUBRIC",
    "load_default_rubric",
    "default_rubric",
    "load_rubric",
]