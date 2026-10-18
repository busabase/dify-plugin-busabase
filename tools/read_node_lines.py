from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import int_param, text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import (
    FILE_TREE_TYPES,
    LINE_TYPES,
    MAX_LINE_RANGE,
    node_label,
    node_of,
    node_ref,
    resolve_node,
)


class ReadNodeLinesTool(Tool):
    """nodes.readLines — GET /api/v1/nodes/{nodeId}/lines (doc / html / whiteboard / workflow)

    For a file inside a skill / drive / airapp (`path`), the range is cut from
    fileTrees.readFile — `nodes.readLines` answers those nodes with a
    misleading "Node not found".
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        start = int_param(tool_parameters, "start_line", default=1, minimum=1, maximum=10**9)
        end = int_param(tool_parameters, "end_line", default=start + 199, minimum=1, maximum=10**9)
        if end < start:
            raise BusabaseError(f"`end_line` ({end}) must be ≥ `start_line` ({start}).")
        end = min(end, start + MAX_LINE_RANGE - 1)
        path = text_param(tool_parameters, "path").lstrip("/")
        detail = resolve_node(client, text_param(tool_parameters, "node"), (*LINE_TYPES, *FILE_TREE_TYPES))
        node = node_of(detail)
        node_type = detail.get("type") or node.get("type")

        if node_type in FILE_TREE_TYPES:
            if not path:
                files = ", ".join(str(f.get("path")) for f in (detail.get("files") or [])[:30])
                raise BusabaseError(
                    f"{node_label(node)} is a file tree: give `path`, the file to read. Files: {files or 'none'}"
                )
            file = client.read_file(str(node["id"]), path)
            if file.get("encoding") != "utf8":
                raise BusabaseError(f"{path} is a binary file ({file.get('mimeType')}); it has no lines to read.")
            all_lines = str(file.get("content") or "").splitlines()
            total = len(all_lines)
            lines = all_lines[start - 1 : end]
        else:
            result = client.read_node_lines(str(node["id"]), start, end)
            lines = [str(x) for x in result.get("lines") or []]
            total = int(result.get("totalLines") or 0)
            path = ""

        last = start + len(lines) - 1 if lines else start - 1
        where = f"{path} in {node_label(node)}" if path else node_label(node)
        if lines:
            # The lines go once, in the JSON (`lines`, starting at `startLine`) — see get_node.
            text = f"Lines {start}–{last} of {total} from {where} are in `lines` (lines[0] is line {start})."
            if last < total:
                text += f" Line {total} remains." if last + 1 == total else f" Lines {last + 1}–{total} remain."
        else:
            text = f"{where} has {total} line(s); nothing at line {start}."
        data = {
            "node": node_ref(node),
            "path": path or None,
            "startLine": start,
            "endLine": last,
            "totalLines": total,
            "lines": lines,
            "hasMore": last < total,
        }
        yield from emit(self, data, text)
