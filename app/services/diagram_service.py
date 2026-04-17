from __future__ import annotations

import html
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from app.models.diagram import DiagramModule, DiagramSpec
from app.models.outline import AnswerSection, OutlineNode


@dataclass
class TextLayout:
    lines: list[str]
    font_size: int
    line_height: int

    @property
    def height(self) -> int:
        return max(1, len(self.lines)) * self.line_height


@dataclass
class ModuleLayout:
    title: str
    title_layout: TextLayout
    chips: list[tuple[str, TextLayout, float, float, int, int]]
    chip_row_heights: list[float]
    chip_cols: int
    chip_row_counts: list[int]
    height: float
    row_group: str | None = None


@dataclass
class TreeNodeLayout:
    title: str
    text_layout: TextLayout
    box_width: float
    box_height: float
    subtree_width: float
    children: list["TreeNodeLayout"]
    depth: int
    x: float = 0.0
    y: float = 0.0


class DiagramService:
    MODULE_COLORS = [
        ("#B75A21", "#D99154", "#F5D1B4"),
        ("#A66518", "#D8A645", "#F5E0AF"),
        ("#4B8D42", "#75BE6B", "#D9F0D4"),
        ("#2B6EA9", "#4A9ADE", "#D8ECFA"),
        ("#7B5BB7", "#A386DB", "#E7DCF9"),
        ("#8E4A59", "#C77D8C", "#F3D7DE"),
    ]

    LAYOUT_NOISE = {
        "目次",
        "目录",
        "附件",
        "附录",
        "摘要",
        "前言",
        "封面",
        "页码",
        "索引",
        "说明",
        "概述",
        "小结",
        "研究主题",
        "结构重点图",
    }

    GENERIC_NOISE = {
        "相关要求",
        "落实重点",
        "制度构建",
        "数据安全",
        "现有资料",
        "整体内容",
        "部分支撑",
        "资料表明",
        "资料显示",
    }

    def to_mermaid(self, outline: OutlineNode) -> str:
        lines = ["graph TD"]
        counter = 0

        def walk(node: OutlineNode, parent_id: str | None = None) -> None:
            nonlocal counter
            current_id = f"N{counter}"
            counter += 1
            title = node.title.replace('"', "'")
            lines.append(f'    {current_id}["{title}"]')
            if parent_id:
                lines.append(f"    {parent_id} --> {current_id}")
            for child in node.children:
                walk(child, current_id)

        walk(outline)
        return "\n".join(lines)

    def to_layered_svg(
        self,
        outline: OutlineNode,
        sections: list[AnswerSection] | None = None,
        diagram_spec: DiagramSpec | None = None,
    ) -> str:
        return self._render_exact_tree_svg(outline)

    def to_showcase_svg(
        self,
        outline: OutlineNode,
        sections: list[AnswerSection] | None = None,
        diagram_spec: DiagramSpec | None = None,
    ) -> str:
        safe_sections = sections or []
        return self._render_dynamic_svg(outline, safe_sections, diagram_spec)

    def _render_exact_tree_svg(self, outline: OutlineNode) -> str:
        horizontal_gap = 32.0
        vertical_gap = 46.0
        padding_x = 48.0
        padding_y = 40.0
        caption_gap = 28.0
        min_canvas_width = 960.0
        preferred_canvas_width = 1200.0
        max_canvas_width = 1480.0

        tree = self._measure_tree(outline, depth=0, horizontal_gap=horizontal_gap)
        self._position_tree(tree, padding_x, padding_y, horizontal_gap=horizontal_gap, vertical_gap=vertical_gap)

        natural_width = tree.subtree_width + padding_x * 2
        if natural_width > max_canvas_width:
            tree_scale = max_canvas_width / natural_width
            canvas_width = int(max_canvas_width)
        elif natural_width < preferred_canvas_width:
            tree_scale = min(1.2, preferred_canvas_width / natural_width)
            canvas_width = int(max(min_canvas_width, natural_width * tree_scale))
        else:
            tree_scale = 1.0
            canvas_width = int(max(min_canvas_width, natural_width))

        bottom = self._tree_bottom(tree)
        caption_layout = self._fit_text(
            f"图示：{outline.title} 结构图",
            max_width=canvas_width - 120,
            preferred_font=20,
            min_font=14,
            max_lines=2,
            allow_truncate=False,
        )
        scaled_tree_height = (bottom + padding_y) * tree_scale
        canvas_height = int(scaled_tree_height + caption_gap + caption_layout.height + padding_y)
        tree_translate_x = (canvas_width - natural_width * tree_scale) / 2
        tree_translate_y = padding_y * (1 - tree_scale)

        parts = [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}" height="{canvas_height}" '
                f'viewBox="0 0 {canvas_width} {canvas_height}" role="img" '
                f'aria-label="{self._escape(outline.title)} 结构图">'
            ),
            "<defs>",
            '<filter id="treeShadow" x="-20%" y="-20%" width="140%" height="160%">',
            '<feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#6B4F35" flood-opacity="0.12"/>',
            "</filter>",
            "</defs>",
            '<rect width="100%" height="100%" rx="24" fill="#FFF9F1"/>',
        ]

        parts.append(
            f'<g data-auto-scale="{tree_scale:.4f}" transform="translate({tree_translate_x:.1f},{tree_translate_y:.1f}) scale({tree_scale:.4f})">'
        )
        parts.extend(self._draw_tree_edges(tree))
        parts.extend(self._draw_tree_nodes(tree))
        parts.append("</g>")
        parts.extend(
            self._draw_text_block(
                x=canvas_width / 2,
                box_y=scaled_tree_height + caption_gap,
                box_height=caption_layout.height,
                layout=caption_layout,
                fill="#34434E",
                font_weight="700",
            )
        )
        parts.append("</svg>")
        return "\n".join(parts)

    def _render_dynamic_svg(
        self,
        outline: OutlineNode,
        sections: list[AnswerSection],
        diagram_spec: DiagramSpec | None = None,
    ) -> str:
        modules = self._build_modules(outline, sections, diagram_spec)
        width = 1280
        page_padding_x = 64
        top_y = 28
        body_gap = 12
        module_gap = 18
        bottom_padding = 44
        caption_gap = 22

        base_x = page_padding_x
        base_width = width - page_padding_x * 2

        roof_title_max_width = min(base_width - 260, base_width * 0.72)
        roof_layout = self._fit_text(
            outline.title,
            max_width=roof_title_max_width,
            preferred_font=28,
            min_font=14,
            max_lines=6,
            allow_truncate=False,
        )
        roof_height = max(150, roof_layout.height + 120)
        body_y = top_y + roof_height + body_gap
        body_inner_padding = 22

        rows = self._group_modules_into_rows(modules)
        laid_out_rows = self._layout_rows(rows, base_width - body_inner_padding * 2)
        modules_height = sum(row["height"] for row in laid_out_rows) + max(0, len(laid_out_rows) - 1) * module_gap
        body_height = body_inner_padding * 2 + modules_height

        caption_layout = self._fit_text(
            f"图示：{outline.title} 结构重点图",
            max_width=base_width - 80,
            preferred_font=22,
            min_font=16,
            max_lines=2,
            allow_truncate=False,
        )
        canvas_height = int(body_y + body_height + caption_gap + caption_layout.height + bottom_padding)

        parts = [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{canvas_height}" '
                f'viewBox="0 0 {width} {canvas_height}" role="img" '
                f'aria-label="{self._escape(outline.title)} 结构重点图">'
            ),
            "<defs>",
            '<linearGradient id="roofGrad" x1="0%" x2="100%" y1="0%" y2="100%">',
            '<stop offset="0%" stop-color="#C63624"/>',
            '<stop offset="100%" stop-color="#8F150F"/>',
            "</linearGradient>",
            '<linearGradient id="bodyGrad" x1="0%" x2="0%" y1="0%" y2="100%">',
            '<stop offset="0%" stop-color="#FFF4E8"/>',
            '<stop offset="100%" stop-color="#FEF9F3"/>',
            "</linearGradient>",
            '<filter id="softShadow" x="-20%" y="-20%" width="140%" height="170%">',
            '<feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#7A5E42" flood-opacity="0.14"/>',
            "</filter>",
            "</defs>",
            '<rect width="100%" height="100%" rx="24" fill="#FFF9F1"/>',
        ]

        roof_points = [
            (base_x + 60, body_y - 6),
            (width / 2, top_y + 6),
            (width - base_x - 60, body_y - 6),
            (width - base_x - 22, body_y - 6),
            (width - base_x - 30, body_y + 16),
            (base_x + 30, body_y + 16),
            (base_x + 22, body_y - 6),
        ]
        parts.append(
            f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in roof_points)}" fill="url(#roofGrad)" filter="url(#softShadow)"/>'
        )
        title_plate_width = min(base_width - 220, roof_title_max_width + 64)
        title_plate_height = roof_layout.height + 22
        title_plate_x = (width - title_plate_width) / 2
        title_plate_y = max(top_y + 22, body_y - title_plate_height - 24)
        parts.append(
            f'<rect x="{title_plate_x:.1f}" y="{title_plate_y:.1f}" width="{title_plate_width:.1f}" height="{title_plate_height:.1f}" rx="18" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.26)" stroke-width="1.2"/>'
        )
        parts.extend(
            self._draw_text_block(
                x=width / 2,
                box_y=title_plate_y,
                box_height=title_plate_height,
                layout=roof_layout,
                fill="#FFFFFF",
                font_weight="700",
            )
        )

        parts.append(
            (
                f'<rect x="{base_x}" y="{body_y}" width="{base_width}" height="{body_height}" rx="30" '
                f'fill="url(#bodyGrad)" stroke="#C56C2B" stroke-width="3" filter="url(#softShadow)"/>'
            )
        )
        parts.append(
            f'<rect x="{base_x + 10}" y="{body_y + 10}" width="{base_width - 20}" height="{body_height - 20}" rx="24" fill="#FFF7EE" stroke="#E2B487" stroke-width="1.5"/>'
        )

        current_y = body_y + body_inner_padding
        module_index = 0
        for row in laid_out_rows:
            row_items = row["items"]
            row_height = row["height"]
            row_gap = 18.0
            row_width = base_width - body_inner_padding * 2
            row_count = len(row_items)
            item_width = (row_width - max(0, row_count - 1) * row_gap) / row_count
            current_x = base_x + body_inner_padding

            for layout in row_items:
                border_color, accent_color, surface_color = self.MODULE_COLORS[module_index % len(self.MODULE_COLORS)]
                parts.extend(
                    self._draw_module(
                        x=current_x,
                        y=current_y,
                        width=item_width,
                        layout=layout,
                        border_color=border_color,
                        accent_color=accent_color,
                        surface_color=surface_color,
                        box_height=row_height,
                    )
                )
                current_x += item_width + row_gap
                module_index += 1
            current_y += row_height + module_gap

        parts.extend(
            self._draw_text_block(
                x=width / 2,
                box_y=body_y + body_height + caption_gap,
                box_height=caption_layout.height,
                layout=caption_layout,
                fill="#34434E",
                font_weight="700",
            )
        )
        parts.append("</svg>")
        return "\n".join(parts)

    def _measure_tree(self, node: OutlineNode, depth: int, horizontal_gap: float) -> TreeNodeLayout:
        preferred_font = 30 if depth == 0 else 22 if depth == 1 else 17
        min_font = 18 if depth == 0 else 14 if depth == 1 else 12
        max_width = 320 if depth == 0 else 240 if depth == 1 else 220
        text_layout = self._fit_text(
            node.title,
            max_width=max_width - 28,
            preferred_font=preferred_font,
            min_font=min_font,
            max_lines=3 if depth == 0 else 2,
            allow_truncate=False,
        )
        box_width = max(140.0, min(float(max_width), self._estimate_layout_width(text_layout) + 30.0))
        box_height = max(52.0, float(text_layout.height + 24))
        children = [self._measure_tree(child, depth + 1, horizontal_gap) for child in node.children]
        children_total_width = self._children_total_width(children, horizontal_gap)
        subtree_width = max(box_width, children_total_width)
        return TreeNodeLayout(
            title=node.title,
            text_layout=text_layout,
            box_width=box_width,
            box_height=box_height,
            subtree_width=subtree_width,
            children=children,
            depth=depth,
        )

    def _position_tree(
        self,
        node: TreeNodeLayout,
        left: float,
        top: float,
        horizontal_gap: float,
        vertical_gap: float,
    ) -> None:
        node.x = left + (node.subtree_width - node.box_width) / 2
        node.y = top

        if not node.children:
            return

        children_total_width = self._children_total_width(node.children, horizontal_gap)
        child_left = left + (node.subtree_width - children_total_width) / 2
        child_top = top + node.box_height + vertical_gap

        for child in node.children:
            self._position_tree(
                child,
                left=child_left,
                top=child_top,
                horizontal_gap=horizontal_gap,
                vertical_gap=vertical_gap,
            )
            child_left += child.subtree_width + horizontal_gap

    def _children_total_width(self, children: list[TreeNodeLayout], horizontal_gap: float) -> float:
        if not children:
            return 0.0
        return sum(child.subtree_width for child in children) + horizontal_gap * max(0, len(children) - 1)

    def _tree_bottom(self, node: TreeNodeLayout) -> float:
        bottom = node.y + node.box_height
        for child in node.children:
            bottom = max(bottom, self._tree_bottom(child))
        return bottom

    def _draw_tree_edges(self, node: TreeNodeLayout) -> list[str]:
        parts: list[str] = []
        parent_x = node.x + node.box_width / 2
        parent_y = node.y + node.box_height

        for child in node.children:
            child_x = child.x + child.box_width / 2
            child_y = child.y
            mid_y = (parent_y + child_y) / 2
            parts.append(
                (
                    f'<path d="M {parent_x:.1f} {parent_y:.1f} '
                    f'L {parent_x:.1f} {mid_y:.1f} '
                    f'L {child_x:.1f} {mid_y:.1f} '
                    f'L {child_x:.1f} {child_y:.1f}" '
                    f'stroke="#B98755" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                )
            )
            parts.extend(self._draw_tree_edges(child))
        return parts

    def _draw_tree_nodes(self, node: TreeNodeLayout) -> list[str]:
        fill, border, text_fill = self._node_style(node.depth)
        parts = [
            f'<g data-title="{self._escape(node.title)}" data-depth="{node.depth}">',
            (
                f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="{node.box_width:.1f}" height="{node.box_height:.1f}" '
                f'rx="16" fill="{fill}" stroke="{border}" stroke-width="2.4" filter="url(#treeShadow)"/>'
            )
        ]
        parts.extend(
            self._draw_text_block(
                x=node.x + node.box_width / 2,
                box_y=node.y,
                box_height=node.box_height,
                layout=node.text_layout,
                fill=text_fill,
                font_weight="700" if node.depth <= 1 else "600",
            )
        )
        for child in node.children:
            parts.extend(self._draw_tree_nodes(child))
        parts.append("</g>")
        return parts

    def _node_style(self, depth: int) -> tuple[str, str, str]:
        if depth == 0:
            return ("#B92B1D", "#8F160E", "#FFFFFF")
        if depth == 1:
            border, accent, _surface = self.MODULE_COLORS[(depth - 1) % len(self.MODULE_COLORS)]
            return (border, border, "#FFFFFF")
        palette_index = (depth - 2) % len(self.MODULE_COLORS)
        border, accent, surface = self.MODULE_COLORS[palette_index]
        return ("#FFFFFF", accent, "#31404A")

    def _estimate_layout_width(self, layout: TextLayout) -> float:
        if not layout.lines:
            return 0.0
        return max(self._estimate_text_width(line, layout.font_size) for line in layout.lines)

    def _build_modules(
        self,
        outline: OutlineNode,
        sections: list[AnswerSection],
        diagram_spec: DiagramSpec | None = None,
    ) -> list[dict[str, list[str] | str]]:
        nodes = outline.children or [outline]
        node_map = {self._normalize_title_key(node.title): node for node in nodes if self._normalize_title_key(node.title)}
        section_map = {self._normalize_title_key(section.heading): section for section in sections}

        if diagram_spec and diagram_spec.modules:
            spec_map: dict[str, DiagramModule] = {}
            ordered_keys: list[str] = []
            for module in diagram_spec.modules:
                key = self._normalize_title_key(module.title)
                if not key or key not in node_map or key in spec_map:
                    continue
                spec_map[key] = module
                ordered_keys.append(key)

            modules: list[dict[str, list[str] | str]] = []
            for key in ordered_keys + [item for item in node_map if item not in spec_map]:
                node = node_map[key]
                section = section_map.get(key)
                source_module = spec_map.get(key)
                examples = self._extract_outline_examples(node, node.title, outline.title)

                if not examples:
                    if source_module is not None:
                        examples = [
                            cleaned
                            for cleaned in (self._normalize_phrase(example) for example in source_module.examples)
                            if self._is_valid_example(cleaned, node.title, outline.title)
                        ]
                if not examples:
                    examples = self._extract_examples(node.title, outline.title, section, node)
                if not examples:
                    continue

                modules.append(
                    {
                        "title": node.title,
                        "examples": examples,
                        "row_group": source_module.row_group if source_module is not None else None,
                    }
                )
            if modules:
                return modules

        modules: list[dict[str, list[str] | str]] = []
        for node in nodes:
            section = section_map.get(self._normalize_title_key(node.title))
            examples = self._extract_outline_examples(node, node.title, outline.title)
            if not examples:
                examples = self._extract_examples(node.title, outline.title, section, node)
            if examples:
                modules.append({"title": node.title, "examples": examples, "row_group": None})
        return modules

    def _extract_outline_examples(self, node: OutlineNode, module_title: str, root_title: str) -> list[str]:
        examples: list[str] = []
        seen: set[str] = set()
        for child in node.children:
            cleaned = self._normalize_phrase(child.title)
            if not cleaned:
                continue
            if cleaned in {module_title, root_title}:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            examples.append(cleaned)
        return examples

    def _extract_examples(
        self,
        module_title: str,
        root_title: str,
        section: AnswerSection | None,
        node: OutlineNode,
    ) -> list[str]:
        candidates: Counter[str] = Counter()

        for child in node.children[:6]:
            phrase = self._normalize_phrase(child.title)
            if self._is_valid_example(phrase, module_title, root_title):
                candidates[phrase] += 8

        if section:
            for child in section.children[:6]:
                phrase = self._normalize_phrase(child.heading)
                if self._is_valid_example(phrase, module_title, root_title):
                    candidates[phrase] += 7

            for evidence in section.evidence[:4]:
                title_phrase = self._normalize_phrase(evidence.title)
                if self._is_valid_example(title_phrase, module_title, root_title):
                    candidates[title_phrase] += 5

                for part in evidence.section_path[-3:]:
                    phrase = self._normalize_phrase(part)
                    if self._is_valid_example(phrase, module_title, root_title):
                        candidates[phrase] += 4

                for phrase in self._extract_candidate_phrases(evidence.text):
                    if self._is_valid_example(phrase, module_title, root_title):
                        candidates[phrase] += 2

        return [phrase for phrase, _ in candidates.most_common(3)]

    def _extract_candidate_phrases(self, text: str) -> list[str]:
        candidates: list[str] = []
        for match in re.findall(r"《[^》]{2,20}》", text or ""):
            candidates.append(match)
        for match in re.findall(r"\b[A-Z]{1,3}/?T?\s?\d{4,6}-\d{4}\b", text or ""):
            candidates.append(match)
        for match in re.findall(
            r"(?:^|[。；\n])(?:一是|二是|三是|四是|五是|（一）|（二）|（三）|1[、.]|2[、.]|3[、.])\s*([^\n。；]{2,15})",
            text or "",
        ):
            candidates.append(match)
        normalized: list[str] = []
        for item in candidates:
            phrase = self._normalize_phrase(item)
            if phrase:
                normalized.append(phrase)
        return normalized

    def _layout_module(self, module: dict[str, list[str] | str | None], available_width: float) -> ModuleLayout:
        title = str(module["title"])
        examples = [str(item) for item in list(module["examples"])]
        row_group = str(module.get("row_group")) if module.get("row_group") else None
        title_layout = self._fit_text(
            title,
            max_width=available_width - 120,
            preferred_font=19,
            min_font=15,
            max_lines=2,
            allow_truncate=False,
        )

        chips: list[tuple[str, TextLayout, float, float, int, int]] = []
        chip_row_heights: list[float] = []
        chip_row_counts: list[int] = []
        chip_cols = 0
        if examples:
            chip_gap = 16
            chip_count = len(examples)
            if chip_count == 1:
                chip_cols = 1
            elif chip_count in {2, 4}:
                chip_cols = 2
            else:
                chip_cols = 3
            chip_width = (available_width - 36 - (chip_cols - 1) * chip_gap) / chip_cols
            for idx, example in enumerate(examples):
                row_idx = idx // chip_cols
                col_idx = idx % chip_cols
                layout = self._fit_text(
                    example,
                    max_width=chip_width - 18,
                    preferred_font=15,
                    min_font=11,
                    max_lines=2,
                    allow_truncate=False,
                )
                current_height = max(48.0, layout.height + 18.0)
                while len(chip_row_heights) <= row_idx:
                    chip_row_heights.append(0.0)
                    chip_row_counts.append(0)
                chip_row_heights[row_idx] = max(chip_row_heights[row_idx], current_height)
                chip_row_counts[row_idx] += 1
                chips.append((example, layout, chip_width, current_height, row_idx, col_idx))

        module_height = 14.0 + max(36.0, title_layout.height + 14.0) + 16.0
        if chips:
            module_height += 12.0 + sum(chip_row_heights) + max(0, len(chip_row_heights) - 1) * 12.0 + 16.0
        return ModuleLayout(
            title=title,
            title_layout=title_layout,
            chips=chips,
            chip_row_heights=chip_row_heights,
            chip_cols=chip_cols,
            chip_row_counts=chip_row_counts,
            height=module_height,
            row_group=row_group,
        )

    def _group_modules_into_rows(self, modules: list[dict[str, list[str] | str | None]]) -> list[list[dict[str, list[str] | str | None]]]:
        rows: list[list[dict[str, list[str] | str | None]]] = []
        consumed: set[int] = set()

        for index, module in enumerate(modules):
            if index in consumed:
                continue
            row_group = module.get("row_group")
            if row_group:
                row = [item for item in modules if item.get("row_group") == row_group]
                row_indices = [i for i, item in enumerate(modules) if item.get("row_group") == row_group]
                for row_index in row_indices:
                    consumed.add(row_index)
                rows.append(row[:3])
                continue
            consumed.add(index)
            rows.append([module])

        return rows

    def _layout_rows(
        self,
        rows: list[list[dict[str, list[str] | str | None]]],
        available_width: float,
    ) -> list[dict[str, object]]:
        laid_out_rows: list[dict[str, object]] = []
        row_gap = 18.0

        for row in rows:
            row_count = len(row)
            item_width = (available_width - max(0, row_count - 1) * row_gap) / row_count
            items = [self._layout_module(module, item_width) for module in row]
            row_height = max((item.height for item in items), default=0.0)
            laid_out_rows.append({"items": items, "height": row_height})

        return laid_out_rows

    def _draw_module(
        self,
        x: float,
        y: float,
        width: float,
        layout: ModuleLayout,
        border_color: str,
        accent_color: str,
        surface_color: str,
        box_height: float | None = None,
    ) -> list[str]:
        outer_height = box_height if box_height is not None else layout.height
        parts = [
            (
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{outer_height:.1f}" rx="22" '
                f'fill="{surface_color}" stroke="{border_color}" stroke-width="2.6"/>'
            )
        ]
        header_height = max(36.0, layout.title_layout.height + 14.0)
        header_y = y + 14
        parts.append(
            f'<rect x="{x + 16:.1f}" y="{header_y:.1f}" width="{width - 32:.1f}" height="{header_height:.1f}" rx="14" fill="{border_color}"/>'
        )
        parts.extend(
            self._draw_text_block(
                x=x + width / 2,
                box_y=header_y,
                box_height=header_height,
                layout=layout.title_layout,
                fill="#FFFFFF",
                font_weight="700",
            )
        )

        if not layout.chips:
            return parts

        chip_gap = 16
        chip_y_start = header_y + header_height + 12
        for _, text_layout, chip_width, chip_height, row_idx, col_idx in layout.chips:
            row_count = layout.chip_row_counts[row_idx] if row_idx < len(layout.chip_row_counts) else layout.chip_cols
            row_count = max(1, row_count)
            row_total_width = row_count * chip_width + max(0, row_count - 1) * chip_gap
            full_row_width = layout.chip_cols * chip_width + max(0, layout.chip_cols - 1) * chip_gap
            row_offset = max(0.0, (full_row_width - row_total_width) / 2)
            chip_x = x + 18 + row_offset + col_idx * (chip_width + chip_gap)
            chip_y = chip_y_start + sum(layout.chip_row_heights[:row_idx]) + row_idx * 12.0
            parts.append(
                (
                    f'<rect x="{chip_x:.1f}" y="{chip_y:.1f}" width="{chip_width:.1f}" height="{chip_height:.1f}" '
                    f'rx="13" fill="#FFFFFF" stroke="{accent_color}" stroke-width="2"/>'
                )
            )
            parts.extend(
                self._draw_text_block(
                    x=chip_x + chip_width / 2,
                    box_y=chip_y,
                    box_height=chip_height,
                    layout=text_layout,
                    fill="#31404A",
                    font_weight="600",
                )
            )
        return parts

    def _is_valid_example(self, phrase: str, module_title: str, root_title: str) -> bool:
        if not phrase:
            return False
        if phrase in {module_title, root_title}:
            return False
        if "资料中未提供充分依据" in phrase:
            return False
        if len(phrase) < 2:
            return False
        if phrase in self.LAYOUT_NOISE or phrase in self.GENERIC_NOISE:
            return False
        if re.fullmatch(r"[ivxIVX0-9]+", phrase):
            return False
        if re.search(r"[，。；：:、].*[，。；：:、]", phrase):
            return False
        if any(noise in phrase for noise in {"目次", "目录", "附件", "附录", "摘要", "前言", "封面"}):
            return False
        return True

    @staticmethod
    def _normalize_phrase(text: str) -> str:
        phrase = " ".join((text or "").replace("\u3000", " ").split())
        phrase = re.sub(r"^[一二三四五六七八九十0-9\.\、\(\)（）]+", "", phrase)
        phrase = phrase.strip("，。；、：: ")
        phrase = re.sub(r"^(概述|小结|一是|二是|三是|四是|五是)[：:，、]?", "", phrase)
        return phrase.strip()

    def _normalize_title_key(self, text: str) -> str:
        return self._normalize_phrase(text)[:30]

    def _fit_text(
        self,
        text: str,
        max_width: float,
        preferred_font: int,
        min_font: int,
        max_lines: int,
        allow_truncate: bool = True,
    ) -> TextLayout:
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return TextLayout(lines=[""], font_size=preferred_font, line_height=int(preferred_font * 1.35))

        for font_size in range(preferred_font, min_font - 1, -1):
            lines, truncated = self._wrap_text_by_width(cleaned, max_width, font_size, max_lines, allow_truncate)
            if lines and (allow_truncate or not truncated):
                return TextLayout(
                    lines=lines,
                    font_size=font_size,
                    line_height=max(int(font_size * 1.35), font_size + 4),
                )

        if not allow_truncate:
            lines = self._wrap_text_without_limit(cleaned, max_width, min_font)
            return TextLayout(lines=lines, font_size=min_font, line_height=max(int(min_font * 1.35), min_font + 4))

        lines, _ = self._wrap_text_by_width(cleaned, max_width, min_font, max_lines, allow_truncate)
        return TextLayout(lines=lines, font_size=min_font, line_height=max(int(min_font * 1.35), min_font + 4))

    def _wrap_text_by_width(
        self,
        text: str,
        max_width: float,
        font_size: int,
        max_lines: int,
        allow_truncate: bool,
    ) -> tuple[list[str], bool]:
        if self._estimate_text_width(text, font_size) <= max_width:
            return [text], False

        lines: list[str] = []
        current = ""
        truncated = False

        for char in text:
            candidate = current + char
            if not current or self._estimate_text_width(candidate, font_size) <= max_width:
                current = candidate
                continue

            lines.append(current)
            current = char
            if len(lines) >= max_lines:
                truncated = True
                break

        if len(lines) < max_lines and current:
            lines.append(current)

        consumed = sum(len(line) for line in lines)
        if consumed < len(text):
            truncated = True
            if allow_truncate and lines:
                lines[-1] = self._truncate_with_ellipsis(lines[-1] + text[consumed:], max_width, font_size)

        if not lines:
            fallback = self._truncate_with_ellipsis(text, max_width, font_size) if allow_truncate else text[: max(1, max_lines)]
            return [fallback], True
        return lines[:max_lines], truncated

    def _truncate_with_ellipsis(self, text: str, max_width: float, font_size: int) -> str:
        ellipsis = "…"
        if self._estimate_text_width(text, font_size) <= max_width:
            return text

        truncated = text
        while truncated and self._estimate_text_width(truncated + ellipsis, font_size) > max_width:
            truncated = truncated[:-1]
        return (truncated or text[:1]) + ellipsis

    def _wrap_text_without_limit(self, text: str, max_width: float, font_size: int) -> list[str]:
        if self._estimate_text_width(text, font_size) <= max_width:
            return [text]

        lines: list[str] = []
        current = ""
        for char in text:
            candidate = current + char
            if not current or self._estimate_text_width(candidate, font_size) <= max_width:
                current = candidate
                continue
            lines.append(current)
            current = char
        if current:
            lines.append(current)
        return lines or [text]

    def _estimate_text_width(self, text: str, font_size: int) -> float:
        total = 0.0
        for char in text:
            total += self._char_width_ratio(char) * font_size
        return total

    @staticmethod
    def _char_width_ratio(char: str) -> float:
        if char.isspace():
            return 0.28
        east_width = unicodedata.east_asian_width(char)
        if east_width in {"W", "F"}:
            return 1.0
        if char.isdigit():
            return 0.58
        if char.isupper():
            return 0.64
        if char in ",.;:!?'\"`":
            return 0.32
        if char in "-_/\\|":
            return 0.38
        return 0.56

    def _draw_text_block(
        self,
        x: float,
        box_y: float,
        box_height: float,
        layout: TextLayout,
        fill: str,
        font_weight: str,
    ) -> list[str]:
        line_count = max(1, len(layout.lines))
        start_y = box_y + box_height / 2 - ((line_count - 1) * layout.line_height) / 2
        parts = [
            (
                f'<text text-anchor="middle" dominant-baseline="middle" '
                f'font-family="Microsoft YaHei, PingFang SC, Source Han Sans SC, sans-serif" '
                f'font-size="{layout.font_size}" font-weight="{font_weight}" fill="{fill}">'
            )
        ]
        for index, line in enumerate(layout.lines):
            line_y = start_y + index * layout.line_height
            parts.append(f'<tspan x="{x:.1f}" y="{line_y:.1f}">{self._escape(line)}</tspan>')
        parts.append("</text>")
        return parts

    @staticmethod
    def _escape(text: str) -> str:
        return html.escape(text, quote=True)
