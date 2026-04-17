from __future__ import annotations

from app.models.outline import OutlineNode


class OutlineService:
    MAX_OUTLINE_DEPTH = 3

    def sanitize(self, outline: OutlineNode, fallback_title: str) -> OutlineNode:
        return self._sanitize_tree(outline, fallback_title=fallback_title, depth=1, max_depth=self.MAX_OUTLINE_DEPTH)

    def _sanitize_tree(
        self,
        node: OutlineNode,
        fallback_title: str,
        depth: int = 1,
        max_depth: int = 4,
    ) -> OutlineNode:
        title = (node.title or "").strip() or fallback_title.strip()
        seen: set[str] = set()
        children: list[OutlineNode] = []

        if depth >= max_depth:
            return OutlineNode(title=title, children=[])

        for child in node.children:
            child_title = (child.title or "").strip()
            if not child_title or child_title == title or child_title in seen:
                continue
            seen.add(child_title)
            children.append(
                self._sanitize_tree(
                    child,
                    fallback_title=child_title,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
            )

        return OutlineNode(title=title, children=children)
