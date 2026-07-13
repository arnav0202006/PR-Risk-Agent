"""Pydantic schemas for requests and the structured PR risk analysis response."""
from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator

MAX_DIFF_CHARS = 50_000
MAX_TITLE_CHARS = 300
MAX_DESCRIPTION_CHARS = 5_000
MAX_CONTEXT_CHARS = 5_000


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class MergeRecommendation(str, Enum):
    approve = "approve"
    approve_with_caution = "approve_with_caution"
    request_changes = "request_changes"
    block = "block"


class FindingCategory(str, Enum):
    correctness = "correctness"
    security = "security"
    performance = "performance"
    reliability = "reliability"
    maintainability = "maintainability"


class Severity(str, Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TestPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class AnalyzeRequest(BaseModel):
    pr_title: str = Field(default="", max_length=MAX_TITLE_CHARS)
    pr_description: str = Field(default="", max_length=MAX_DESCRIPTION_CHARS)
    diff: str = Field(..., min_length=1, max_length=MAX_DIFF_CHARS)
    context: str = Field(default="", max_length=MAX_CONTEXT_CHARS)

    @field_validator("pr_title", "pr_description", "diff", "context", mode="before")
    @classmethod
    def strip_whitespace(cls, value: str | None) -> str:
        if value is None:
            return ""
        return value.strip()

    @field_validator("diff")
    @classmethod
    def diff_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("diff must not be empty")
        return value


class Finding(BaseModel):
    category: FindingCategory
    severity: Severity
    title: str
    explanation: str
    evidence: str = ""
    suggested_fix: str = ""


class MissingTest(BaseModel):
    test: str
    reason: str = ""
    priority: TestPriority = TestPriority.medium


class PRAnalysis(BaseModel):
    summary: str
    risk_level: RiskLevel
    merge_recommendation: MergeRecommendation
    confidence_score: float = Field(ge=0, le=100)
    findings: List[Finding] = Field(default_factory=list)
    missing_tests: List[MissingTest] = Field(default_factory=list)
    deployment_considerations: List[str] = Field(default_factory=list)
    rollback_plan: List[str] = Field(default_factory=list)
    positive_observations: List[str] = Field(default_factory=list)
    final_reasoning: str = ""

    @field_validator("confidence_score", mode="before")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(100.0, value))