"""Strict loading and hashing of the client rubric."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

EXPECTED_IDS = {
    "problem",
    "market",
    "product",
    "business_model",
    "traction",
    "competitive_advantage",
    "financials",
    "team",
    "scalability",
}


class RubricCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    weight: int = Field(gt=0)
    evidence_to_look_for: list[str]
    anchors: dict[str, str]


class RubricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    score_name: str
    scale: list[int]
    not_stated_justification: str
    criteria: list[RubricCriterion]

    @model_validator(mode="after")
    def validate_methodology(self) -> RubricDefinition:
        ids = [item.id for item in self.criteria]
        if len(ids) != 9 or set(ids) != EXPECTED_IDS or len(set(ids)) != len(ids):
            raise ValueError("rubric must contain the exact nine unique client categories")
        if sum(item.weight for item in self.criteria) != 100:
            raise ValueError("rubric weights must total 100")
        if self.scale != [0, 10]:
            raise ValueError("rubric scale must be 0-10")
        expected = {"0-2", "3-4", "5-6", "7-8", "9-10"}
        if any(set(item.anchors) != expected for item in self.criteria):
            raise ValueError("each category must define all five client anchor bands")
        return self

    def digest(self) -> str:
        payload = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def load_rubric(path: Path) -> RubricDefinition:
    return RubricDefinition.model_validate(yaml.safe_load(path.read_text()))
