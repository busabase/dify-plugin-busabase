from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.core import int_param, text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import FILE_TREE_TYPES, file_vo, node_label, node_of, node_ref, resolve_node


class ListFilesTool(Tool):
    """fileTrees.listFiles — GET /api/v1/file-trees/{nodeId}/files (skill / drive / airapp)"""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        limit = int_param(tool_parameters, "limit", default=200, minimum=1, maximum=1000)
        node = node_of(resolve_node(client, text_param(tool_parameters, "node"), FILE_TREE_TYPES))
        files = [file_vo(f) for f in client.list_files(str(node["id"]))]
        prefix = text_param(tool_parameters, "prefix").lstrip("/")
        if prefix:
            files = [f for f in files if str(f["path"]).startswith(prefix)]
        total = len(files)
        files = files[:limit]
        if files:
            text = f"{total} file(s) in {node_label(node)}:\n" + "\n".join(
                f"- {f['path']} ({f['size']} bytes)" for f in files
            )
            if total > limit:
                text += f"\n… {total - limit} more — narrow with `prefix`."
        else:
            text = f"No files{f' under {prefix!r}' if prefix else ''} in {node_label(node)}."
        yield from emit(
            self,
            {"node": node_ref(node), "files": files, "count": len(files), "total": total, "truncated": total > limit},
            text,
        )
