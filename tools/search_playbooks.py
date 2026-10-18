from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.core import int_param, text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import (
    broaden_queries,
    choice_param,
    node_of,
    parse_queries,
    playbook_title,
    playbook_vo,
    resolve_node,
)


class SearchPlaybooksTool(Tool):
    """playbooks.search — POST /api/v1/playbooks/search (the space's skills + custom prompts)

    Matching is substring per phrasing, so a multi-word phrasing that finds
    nothing is retried once with its single words (`broadened: true`).
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        queries = parse_queries(tool_parameters.get("queries"))
        kind = choice_param(text_param(tool_parameters, "kind"), "kind", ("all", "skill", "prompt"), "all")
        limit = int_param(tool_parameters, "limit", default=10, minimum=1, maximum=50)
        body: dict[str, Any] = {"queries": queries, "limit": limit}
        if kind != "all":
            body["kinds"] = [kind]
        near = text_param(tool_parameters, "near_node")
        if near:
            body["nearNodeId"] = node_of(resolve_node(client, near, None, "near_node"))["id"]
        locale = text_param(tool_parameters, "locale")
        if locale:
            body["locale"] = locale

        result = client.search_playbooks(body)
        broadened = False
        if not result.get("items") and queries:
            words = broaden_queries(queries)
            if words:
                result = client.search_playbooks({**body, "queries": words})
                broadened = bool(result.get("items"))
                if broadened:
                    queries = words
        items = [playbook_vo(i) for i in result.get("items") or []]
        if items:
            lines = [
                f"{n}. {playbook_title(i)} — node id {i['nodeId']}"
                + (f": {i['description']}" if i.get("description") else "")
                for n, i in enumerate(items, 1)
            ]
            text = (
                f"{len(items)} playbook(s) of {result.get('total', len(items))} for {queries or 'browse'}:\n"
                + "\n".join(lines)
                + "\nOpen the best fit with get_playbook and follow it; name it in your reply."
            )
        else:
            text = "No playbook in this space fits. Do the work yourself, the usual way."
        yield from emit(
            self,
            {
                "queries": queries,
                "items": items,
                "count": len(items),
                "total": result.get("total", len(items)),
                "truncated": bool(result.get("truncated")),
                "broadened": broadened,
            },
            text,
        )
