"""Rubric loader and schema definitions."""

import hashlib
from pathlib import Path
from typing import Any, Dict, List
import yaml
from pydantic import BaseModel, Field, model_validator

# Locate the rubric YAML inside package data or project directory
PACKAGE_RUBRIC_PATH = Path(__file__).resolve().parent / "data" / "mamakscore-v3.yaml"
REPO_RUBRIC_PATH = Path(__file__).resolve().parents[2] / "rubric" / "mamakscore-v3.yaml"


class RubricCriterion(BaseModel):
    id: str
    name: str
    weight: float
    description: str = ""
    scoring_guide: Dict[str, str] = Field(default_factory=dict)
    anchors: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def populate_anchors(cls, data: Any) -> Any:
        if isinstance(data, dict):
            guide = data.get("scoring_guide") or data.get("anchors") or {
                "0-2": "Very Weak",
                "3-4": "Below Average",
                "5-6": "Acceptable",
                "7-8": "Strong",
                "9-10": "Exceptional",
            }
            data["scoring_guide"] = guide
            data["anchors"] = guide
        return data


class RubricDefinition(BaseModel):
    version: str
    criteria: List[RubricCriterion]
    digest: str = ""
    scale: List[int] = Field(default_factory=lambda: [0, 10])

    def get_criterion(self, criterion_id: str) -> RubricCriterion:
        for c in self.criteria:
            if c.id == criterion_id:
                return c
        raise KeyError(f"Criterion '{criterion_id}' not found in rubric version {self.version}")
def compute_rubric_digest(raw_yaml_text: str) -> str:
    return hashlib.sha256(raw_yaml_text.strip().encode("utf-8")).hexdigest()


def load_rubric(path: Path | None = None) -> RubricDefinition:
    target_path = path or PACKAGE_RUBRIC_PATH
    if not target_path.exists() and REPO_RUBRIC_PATH.exists():
        target_path = REPO_RUBRIC_PATH

    if not target_path.exists():
        # Fallback to current working directory rubric/
        cwd_rubric = Path("rubric/mamakscore-v3.yaml")
        if cwd_rubric.exists():
            target_path = cwd_rubric
        else:
            raise FileNotFoundError(f"Rubric file not found at: {target_path}")

    raw_text = target_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text)
    rubric = RubricDefinition.model_validate(data)
    rubric.digest = compute_rubric_digest(raw_text)
    return rubric

RubricCriterion.model_rebuild()
RubricDefinition.model_rebuild()