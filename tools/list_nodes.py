from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.core import int_param, text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import (
    NODE_TYPES,
    choice_param,
    flatten_tree,
    node_ref,
    node_vo,
    outline,
    resolve_parent_folder,
)


class ListNodesTool(Tool):
    """nodes.list — GET /api/v1/nodes (depth-bounded tree, or a flat list filtered by type)

    `parentId` is resolved to a folder id first (a slug there returns `[]`), and
    type + parent is filtered here because the server ignores `parentId`
    whenever `types` is set.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        node_type = choice_param(text_param(tool_parameters, "type"), "type", ("all", *NODE_TYPES), "all")
        depth = int_param(tool_parameters, "depth", default=2, minimum=1, maximum=5)
        limit = int_param(tool_parameters, "limit", default=200, minimum=1, maximum=500)
        parent = resolve_parent_folder(client, text_param(tool_parameters, "parent"))

        if node_type != "all" and parent is None:
            nodes = [{**node_vo(n), "depth": 0} for n in client.list_nodes(types=[node_type])]
        elif parent is None:
            tree = client.list_nodes(depth=depth)
            roots = tree[0].get("children", []) if len(tree) == 1 and tree[0].get("parentId") is None else tree
            nodes = flatten_tree(roots)
        else:
            tree = client.list_nodes(parent_id=parent["id"], depth=5 if node_type != "all" else depth)
            nodes = flatten_tree(tree)
            if node_type != "all":
                nodes = [{**n, "depth": 0} for n in nodes if n["type"] == node_type]

        total = len(nodes)
        nodes = nodes[:limit]
        where = f"folder {parent['name']!r}" if parent else "the workspace"
        kind = f"{node_type} node(s)" if node_type != "all" else "node(s)"
        if nodes:
            text = f"{total} {kind} in {where}:\n" + outline(nodes, indent=node_type == "all")
            if total > limit:
                text += f"\n… {total - limit} more not shown — narrow with `parent` or `type`."
        else:
            text = f"No {kind} in {where}."
        if any(n.get("hasMoreChildren") for n in nodes):
            text += "\nFolders marked (+ more inside) have deeper content: list again with that folder as `parent`."
        yield from emit(
            self,
            {
                "parent": node_ref(parent) if parent else None,
                "type": node_type,
                "nodes": nodes,
                "count": len(nodes),
                "total": total,
                "truncated": total > limit,
            },
            text,
        )
