from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.models.diagram import DiagramModule, DiagramSpec
from app.models.outline import OutlineNode
from app.schemas.diagram import DiagramGenerateRequest, DiagramGenerateResponse
from app.services.diagram_service import DiagramService
from app.services.outline_service import OutlineService

router = APIRouter(prefix="/api/diagram", tags=["diagram"])


@router.post("/generate", response_model=DiagramGenerateResponse)
def generate_diagram(payload: DiagramGenerateRequest) -> DiagramGenerateResponse:
    try:
        raw_obj = json.loads(payload.diagram_outline_text)
        normalized_obj = _normalize_outline_json(raw_obj)
        raw_outline = OutlineNode.model_validate(normalized_obj)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"图稿结构格式不正确，请提供合法的 JSON 结构。{exc}") from exc

    outline = OutlineService().sanitize(raw_outline, fallback_title="研究主题")
    diagram_spec = _build_spec_from_raw_outline(normalized_obj)
    service = DiagramService()
    return DiagramGenerateResponse(
        outline=outline,
        diagram_mermaid=service.to_mermaid(outline),
        diagram_layered_svg=service.to_showcase_svg(outline, [], diagram_spec),
    )


def _build_spec_from_raw_outline(raw_obj: object) -> DiagramSpec | None:
    if not isinstance(raw_obj, dict):
        return None
    children = raw_obj.get("children")
    if not isinstance(children, list):
        return None

    modules: list[DiagramModule] = []
    has_row_group = False
    for child in children:
        if not isinstance(child, dict):
            continue
        title = str(child.get("title", "")).strip()
        if not title:
            continue

        row_group_raw = str(child.get("row_group", "")).strip()
        row_group = row_group_raw or None
        if row_group is not None:
            has_row_group = True

        examples: list[str] = []
        raw_children = child.get("children")
        if isinstance(raw_children, list):
            for leaf in raw_children:
                if isinstance(leaf, dict):
                    leaf_title = str(leaf.get("title", "")).strip()
                    if leaf_title:
                        examples.append(leaf_title)
        modules.append(DiagramModule(title=title, examples=examples, row_group=row_group))

    if not has_row_group or not modules:
        return None
    root_title = str(raw_obj.get("title", "研究主题")).strip() or "研究主题"
    return DiagramSpec(title=root_title, modules=modules)


def _normalize_outline_json(raw_obj: object) -> object:
    if isinstance(raw_obj, dict):
        normalized = dict(raw_obj)
        if "title" not in normalized and "name" in normalized:
            normalized["title"] = normalized["name"]
        if "children" in normalized and isinstance(normalized["children"], list):
            normalized["children"] = [_normalize_outline_json(item) for item in normalized["children"]]
        return normalized
    if isinstance(raw_obj, list):
        return [_normalize_outline_json(item) for item in raw_obj]
    return raw_obj
