from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.outline import OutlineNode


class DiagramGenerateRequest(BaseModel):
    diagram_outline_text: str = Field(min_length=2, max_length=100000)


class DiagramGenerateResponse(BaseModel):
    outline: OutlineNode
    diagram_mermaid: str
    diagram_layered_svg: str
