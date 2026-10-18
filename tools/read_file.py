from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import int_param, text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import FILE_TREE_TYPES, line_count, node_label, node_of, node_ref, resolve_node, truncate


class ReadFileTool(Tool):
    """fileTrees.readFile — GET /api/v1/file-trees/{nodeId}/files/{+filePath}"""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        max_chars = int_param(tool_parameters, "max_chars", default=20000, minimum=500, maximum=200000)
        path = text_param(tool_parameters, "path").lstrip("/")
        if not path:
            raise BusabaseError("`path` is required: the file's path inside the node, e.g. SKILL.md (see list_files).")
        node = node_of(resolve_node(client, text_param(tool_parameters, "node"), FILE_TREE_TYPES))
        try:
            file = client.read_file(str(node["id"]), path)
        except BusabaseError as exc:
            if exc.status_code != 404:
                raise
            paths = [str(f.get("path")) for f in client.list_files(str(node["id"]))]
            raise BusabaseError(
                f"No file {path!r} in {node_label(node)}. Files: {', '.join(paths[:40]) or 'none'}",
                404,
            ) from exc

        data: dict[str, Any] = {
            "node": node_ref(node),
            "path": file.get("path"),
            "mimeType": file.get("mimeType"),
            "contentHash": file.get("contentHash"),
            "encoding": file.get("encoding"),
        }
        if file.get("encoding") != "utf8":
            url = str(file.get("assetUrl") or "")
            if url.startswith("/"):
                url = client.base_url + url
            data["assetUrl"] = url or None
            text = f"{path} in {node_label(node)} is a binary file ({file.get('mimeType')}): {url or 'no URL'}"
        else:
            content = str(file.get("content") or "")
            shown, cut = truncate(content, max_chars)
            data.update({"content": shown, "totalLines": line_count(content), "totalChars": len(content), "contentTruncated": cut})
            # Content goes once, in the JSON (`content`) — see get_node.
            text = (
                f"{path} in {node_label(node)}: {line_count(content)} line(s), {len(content)} characters; "
                "the text is in `content`."
            )
            if cut:
                text += (
                    f" Truncated: `content` holds the first {len(shown)} characters. "
                    f"Read the rest with read_node_lines (node {node['id']}, path {path})."
                )
        yield from emit(self, data, text)
