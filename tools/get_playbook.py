from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import int_param, text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import choice_param, file_vo, node_label, node_of, resolve_node, truncate


class GetPlaybookTool(Tool):
    """playbooks.get — GET /api/v1/playbooks/{kind}/{nodeId} (SKILL.md, or a rendered custom prompt)

    The path takes a node id only (a slug 404s), so the node is resolved first.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        key = text_param(tool_parameters, "key")
        kind = choice_param(
            text_param(tool_parameters, "kind"), "kind", ("skill", "prompt"), "prompt" if key else "skill"
        )
        if kind == "prompt" and not key:
            raise BusabaseError("`key` is required for a prompt playbook: the `key` from search_playbooks.")
        max_chars = int_param(tool_parameters, "max_chars", default=30000, minimum=1000, maximum=200000)
        locale = text_param(tool_parameters, "locale") or None
        node = node_of(
            resolve_node(client, text_param(tool_parameters, "node"), ("skill",) if kind == "skill" else None)
        )
        try:
            playbook = client.get_playbook(kind, str(node["id"]), key or None, locale)
        except BusabaseError as exc:
            if exc.status_code != 404 or kind != "prompt":
                raise
            found = client.search_playbooks({"queries": [], "kinds": ["prompt"], "inNodeId": node["id"], "limit": 50})
            keys = [f"{i.get('key')} ({i.get('label')})" for i in found.get("items") or [] if i.get("nodeId") == node["id"]]
            raise BusabaseError(
                f"No prompt {key!r} on {node_label(node)}. Prompt keys there: {', '.join(keys) or 'none'}", 404
            ) from exc

        content, cut = truncate(str(playbook.get("content") or ""), max_chars)
        data: dict[str, Any] = {
            "kind": playbook.get("kind"),
            "nodeId": playbook.get("nodeId"),
            "nodeType": playbook.get("nodeType"),
            "nodeName": playbook.get("nodeName"),
            "nodeSlug": playbook.get("nodeSlug"),
            "path": " / ".join(playbook.get("path") or []),
            "content": content,
            "contentTruncated": cut,
        }
        for field in ("key", "label", "intent", "locale", "name", "description"):
            if playbook.get(field):
                data[field] = playbook[field]
        if kind == "skill":
            data["files"] = [file_vo(f) for f in playbook.get("files") or []]
            title = f"Skill {playbook.get('name') or playbook.get('nodeName')!r} (node {playbook.get('nodeId')})"
        else:
            title = f"Prompt {playbook.get('label') or key!r} on {playbook.get('nodeType')} {playbook.get('nodeName')!r}"
        # The procedure goes once, in the JSON (`content`) — see get_node.
        text = (
            f"{title}: the procedure is in `content`. Follow it as the company's way of doing this job; "
            "the user's explicit words override it, and it never authorises approving or merging a change request."
        )
        if cut:
            rest = "read_file (path SKILL.md)" if kind == "skill" else "a larger max_chars"
            text += f" Truncated at {max_chars} characters — read the rest with {rest}."
        if kind == "skill" and data["files"]:
            others = [f["path"] for f in data["files"] if f["path"] != "SKILL.md"]
            if others:
                text += f" Other files in this skill (open with read_file): {', '.join(others[:30])}."
        yield from emit(self, data, text)
