from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.core import base_vo, int_param, text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import (
    FILE_TREE_TYPES,
    LINE_TYPES,
    NODE_TYPES,
    choice_param,
    file_vo,
    line_count,
    node_of,
    node_vo,
    resolve_node,
    truncate,
)

MAX_FILES = 200


class GetNodeTool(Tool):
    """nodes.get — GET /api/v1/nodes/{nodeId} (typed detail)

    doc → body (truncated past `max_chars`), folder → children, skill/drive/airapp
    → file list, base → fields (bases.get), file → asset metadata.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        node_type = choice_param(text_param(tool_parameters, "type"), "type", ("any", *NODE_TYPES), "any")
        max_chars = int_param(tool_parameters, "max_chars", default=12000, minimum=500, maximum=100000)
        detail = resolve_node(
            client, text_param(tool_parameters, "node"), None if node_type == "any" else (node_type,)
        )
        node = node_of(detail)
        kind = detail.get("type") or node.get("type")
        data: dict[str, Any] = {"node": {**node_vo(node), "description": node.get("description") or ""}}
        header = f"{str(kind).capitalize()} {node.get('name')!r} (slug: {node.get('slug')}, id: {node.get('id')})"
        body_text = ""

        if kind == "doc":
            body = str(detail.get("body") or "")
            shown, cut = truncate(body, max_chars)
            data.update({"body": shown, "totalLines": line_count(body), "totalChars": len(body), "bodyTruncated": cut})
            # The body travels once, in the JSON (`body`): Dify shows an Agent both
            # the text and the JSON message, so repeating it here would double it.
            body_text = f"{line_count(body)} line(s), {len(body)} characters; the markdown is in `body`."
            if cut:
                body_text += (
                    f" Truncated: `body` holds the first {len(shown)} characters. "
                    f"Read the rest with read_node_lines (node {node.get('id')}, lines 1–{line_count(body)})."
                )
        elif kind == "folder":
            children = [node_vo(c) for c in detail.get("children") or []]
            data.update({"children": children, "childCount": len(children)})
            body_text = f"{len(children)} item(s):\n" + "\n".join(
                f"- [{c['type']}] {c['name']} (slug: {c['slug']}, id: {c['id']})" for c in children
            )
        elif kind in FILE_TREE_TYPES:
            files = detail.get("files")
            if files is None:
                files = client.list_files(str(node["id"]))
            vos = [file_vo(f) for f in files]
            data.update(
                {
                    "entryFile": detail.get("entryFile"),
                    "version": detail.get("version"),
                    "files": vos[:MAX_FILES],
                    "fileCount": len(vos),
                }
            )
            body_text = f"{len(vos)} file(s), entry file {detail.get('entryFile')!r}:\n" + "\n".join(
                f"- {f['path']} ({f['size']} bytes)" for f in vos[:MAX_FILES]
            )
            body_text += "\nOpen one with read_file."
        elif kind == "base" and node.get("baseId"):
            base = base_vo(client.get_base(str(node["baseId"])))
            data["base"] = base
            body_text = "Fields: " + (
                ", ".join(f"{f['slug']} ({f['type']})" for f in base["fields"]) or "none"
            ) + "\nRead its records with list_records / find_records."
        elif kind == "file":
            asset = detail.get("asset") or {}
            data["file"] = {k: asset.get(k) for k in ("name", "fileName", "mimeType", "size", "contentKind", "url")}
            body_text = f"File {asset.get('fileName') or asset.get('name')!r}, {asset.get('mimeType')}, {asset.get('size')} bytes."
        elif kind in LINE_TYPES:
            body_text = "Read its content with read_node_lines."

        data["type"] = kind
        text = header + (f" — {node.get('description')}" if node.get("description") else "") + "\n" + body_text
        if node.get("parentId"):
            text += f"\nParent id: {node.get('parentId')}"
        yield from emit(self, data, text.strip())
