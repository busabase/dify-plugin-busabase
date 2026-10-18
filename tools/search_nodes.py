from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import int_param, text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import NODE_TYPES, choice_param


class SearchNodesTool(Tool):
    """nodes.searchByName — GET /api/v1/nodes/search (name/slug substring; no content scan)"""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        query = text_param(tool_parameters, "query")
        if not query:
            raise BusabaseError("`query` is required: part of a node's name or slug.")
        node_type = choice_param(text_param(tool_parameters, "type"), "type", ("all", *NODE_TYPES), "all")
        limit = int_param(tool_parameters, "limit", default=20, minimum=1, maximum=50)
        # The endpoint has no type filter: fetch its maximum and filter here.
        hits = client.search_nodes_by_name(query, 50 if node_type != "all" else limit)
        if node_type != "all":
            hits = [h for h in hits if h.get("type") == node_type]
        hits = hits[:limit]
        nodes = [
            {"id": h.get("id"), "type": h.get("type"), "slug": h.get("slug"), "name": h.get("name"), "updatedAt": h.get("updatedAt")}
            for h in hits
        ]
        if nodes:
            lines = [f"- [{n['type']}] {n['name']} (slug: {n['slug']}, id: {n['id']})" for n in nodes]
            text = f"{len(nodes)} node(s) whose name or slug contains {query!r}:\n" + "\n".join(lines)
        else:
            what = f"{node_type} node" if node_type != "all" else "node"
            text = (
                f"No {what} name or slug contains {query!r}. This matches names only; "
                "use search_workspace to search inside docs, files and records."
            )
        yield from emit(self, {"query": query, "type": node_type, "nodes": nodes, "count": len(nodes)}, text)
