from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    url: str
    title: str | None = None
    snippets: list[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    travel: list[EvidenceItem] = Field(default_factory=list)
    finance: list[EvidenceItem] = Field(default_factory=list)
    health: list[EvidenceItem] = Field(default_factory=list)


class RiskItem(BaseModel):
    risk: str
    severity: Literal["low", "medium", "high"]
    mitigation: str


class AgentEnvelope(BaseModel):
    agent: Literal["travel", "financial", "health"]
    version: str
    questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    plan: dict[str, Any] = Field(default_factory=dict)
    risks: list[RiskItem] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
