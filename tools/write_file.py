from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import (
    FILE_TREE_TYPES,
    change_result,
    choice_param,
    node_label,
    node_of,
    node_ref,
    resolve_node,
    status_text,
)


class WriteFileTool(Tool):
    """fileTrees.createChangeRequest — POST /api/v1/file-trees/{nodeId}/change-requests

    Reads the file first: an existing file is sent as `update` with its
    `baseContentHash` (so a concurrent edit is a 409, not a silent overwrite); a
    missing one as `create`. The server's own `update` of a missing path quietly
    creates it, so `mode: update` is enforced here.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        mode = choice_param(text_param(tool_parameters, "mode"), "mode", ("auto", "create", "update"), "auto")
        path = text_param(tool_parameters, "path").lstrip("/")
        if not path:
            raise BusabaseError("`path` is required: the file's path inside the node, e.g. SKILL.md or notes/plan.md.")
        content = tool_parameters.get("content")
        if content is None:
            raise BusabaseError("`content` is required: the file's full new text.")
        content = str(content)
        node = node_of(resolve_node(client, text_param(tool_parameters, "node"), FILE_TREE_TYPES))
        node_id = str(node["id"])

        try:
            current: dict[str, Any] | None = client.read_file(node_id, path)
        except BusabaseError as exc:
            if exc.status_code != 404:
                raise
            current = None
        if current is None and mode == "update":
            paths = [str(f.get("path")) for f in client.list_files(node_id)]
            raise BusabaseError(
                f"No file {path!r} in {node_label(node)} to update. Files: {', '.join(paths[:40]) or 'none'}. "
                "Use mode create (or auto) to add a new file."
            )
        if current is not None and mode == "create":
            raise BusabaseError(f"{path!r} already exists in {node_label(node)}. Use mode update (or auto) to change it.")

        base = {"node": node_ref(node), "path": path}
        if current is not None and current.get("encoding") == "utf8" and current.get("content") == content:
            yield from emit(
                self,
                {"status": "unchanged", "merged": False, "changeRequestId": None, "nodeId": node_id, "operation": "none", **base},
                f"No change: {path} in {node_label(node)} already has exactly this content.",
            )
            return

        operation: dict[str, Any] = {"kind": "update" if current else "create", "path": path, "content": content}
        if current and current.get("contentHash"):
            operation["baseContentHash"] = current["contentHash"]
        action = "updated" if current else "created"
        message = text_param(tool_parameters, "message") or (
            f"{'Update' if current else 'Add'} {path} via Dify"
        )
        try:
            response = client.file_change_request(node_id, [operation], message)
        except BusabaseError as exc:
            if exc.status_code == 409:
                raise BusabaseError(
                    f"{exc} — the file changed since it was read. Read it again with read_file and redo the edit.",
                    exc.status_code,
                    exc.body,
                ) from exc
            raise
        result = change_result(client, response)
        result["nodeId"] = result.get("nodeId") or node_id
        text = status_text(
            result,
            f"{action.capitalize()} {path} in {node_label(node)}",
            f"to {'update' if current else 'create'} {path} in {node_label(node)}",
        )
        yield from emit(self, {**result, **base, "operation": action, "message": message}, text)
