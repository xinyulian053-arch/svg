from app.models.outline import OutlineNode
from app.api.diagram import _normalize_outline_json
from app.services.diagram_service import DiagramService


def test_mermaid_exactly_follows_input_json_titles() -> None:
    outline = OutlineNode(
        title="住房公积金数据安全管理法律法规",
        children=[
            OutlineNode(
                title="数据安全共享机制构建策略",
                children=[
                    OutlineNode(title="跨部门协同存在的问题", children=[]),
                    OutlineNode(title="技术与人才短板", children=[]),
                ],
            ),
            OutlineNode(
                title="数据安全管理制度",
                children=[
                    OutlineNode(title="数据安全管理制度与意识", children=[]),
                    OutlineNode(title="网络安全防护与监测", children=[]),
                ],
            ),
        ],
    )

    mermaid = DiagramService().to_mermaid(outline)

    assert "住房公积金数据安全管理法律法规" in mermaid
    assert "数据安全共享机制构建策略" in mermaid
    assert "跨部门协同存在的问题" in mermaid
    assert "技术与人才短板" in mermaid
    assert "数据安全管理制度" in mermaid
    assert "数据安全管理制度与意识" in mermaid
    assert "网络安全防护与监测" in mermaid


def test_svg_exactly_preserves_json_node_titles() -> None:
    outline = OutlineNode(
        title="住房公积金数据安全管理法律法规",
        children=[
            OutlineNode(
                title="数据安全共享机制构建策略",
                children=[
                    OutlineNode(title="跨部门协同存在的问题", children=[]),
                    OutlineNode(title="技术与人才短板", children=[]),
                ],
            ),
            OutlineNode(
                title="数据安全管理制度",
                children=[
                    OutlineNode(title="数据安全管理制度与意识", children=[]),
                    OutlineNode(title="网络安全防护与监测", children=[]),
                ],
            ),
        ],
    )

    svg = DiagramService().to_layered_svg(outline, [], None)

    assert 'data-title="住房公积金数据安全管理法律法规"' in svg
    assert 'data-title="数据安全共享机制构建策略"' in svg
    assert 'data-title="跨部门协同存在的问题"' in svg
    assert 'data-title="技术与人才短板"' in svg
    assert 'data-title="数据安全管理制度"' in svg
    assert 'data-title="数据安全管理制度与意识"' in svg
    assert 'data-title="网络安全防护与监测"' in svg


def test_diagram_endpoint_normalizer_accepts_name_field() -> None:
    raw = {
        "name": "住房公积金数据安全管理法律法规",
        "children": [
            {
                "name": "数据安全共享机制构建策略",
                "children": [{"name": "跨部门协同存在的问题"}],
            }
        ],
    }
    normalized = _normalize_outline_json(raw)
    outline = OutlineNode.model_validate(normalized)
    assert outline.title == "住房公积金数据安全管理法律法规"
    assert outline.children[0].title == "数据安全共享机制构建策略"
    assert outline.children[0].children[0].title == "跨部门协同存在的问题"


def test_svg_contains_auto_scale_marker_for_wide_tree() -> None:
    outline = OutlineNode(
        title="根节点",
        children=[
            OutlineNode(title=f"一级节点{i}", children=[OutlineNode(title=f"二级节点{i}-{j}", children=[]) for j in range(4)])
            for i in range(10)
        ],
    )

    svg = DiagramService().to_layered_svg(outline, [], None)

    assert 'data-auto-scale="' in svg
