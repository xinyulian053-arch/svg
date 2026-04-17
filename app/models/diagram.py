from __future__ import annotations

from pydantic import BaseModel, Field


class DiagramModule(BaseModel):
    title: str
    examples: list[str] = Field(default_factory=list)
    row_group: str | None = None


class DiagramSpec(BaseModel):
    title: str
    modules: list[DiagramModule] = Field(default_factory=list)
