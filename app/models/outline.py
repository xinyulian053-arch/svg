from __future__ import annotations

from pydantic import BaseModel, Field


class OutlineNode(BaseModel):
    title: str
    children: list["OutlineNode"] = Field(default_factory=list)


class AnswerSection(BaseModel):
    heading: str
    level: int
    number: str = ""
    content: str
    sources: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    children: list["AnswerSection"] = Field(default_factory=list)


OutlineNode.model_rebuild()
AnswerSection.model_rebuild()
