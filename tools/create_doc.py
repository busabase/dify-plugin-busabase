from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import text_param
from busabase_dify.messages import client_for, emit
from busabase_dify.nodes import change_result, node_ref, pick_slug, resolve_parent_folder, status_text


class CreateDocTool(Tool):
    """docs.create — POST /api/v1/docs

    Merges immediately with write access on the parent folder; otherwise it is
    proposed as a Change Request. The slug is checked first: with a slug that
    already exists in the same folder the server returns the EXISTING doc,
    unchanged, as if it had been created.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        name = text_param(tool_parameters, "name")
        if not name:
            raise BusabaseError("`name` is required: the doc's title.")
        body = str(tool_parameters.get("body") or "")
        parent = resolve_parent_folder(client, text_param(tool_parameters, "parent"))
        slug = pick_slug(client, "doc", name, text_param(tool_parameters, "slug"))
        response = client.create_doc(
            slug=slug,
            name=name,
            body=body,
            parent_node_id=parent["id"] if parent else None,
            description=text_param(tool_parameters, "description"),
        )
        returned = response.get("node") if response.get("materialized") is True else None
        if isinstance(returned, dict) and (returned.get("name") != name or str(response.get("body") or "") != body):
            raise BusabaseError(
                f"Busabase returned an existing doc for slug {slug!r} ({returned.get('id')}) instead of creating "
                "one; nothing was written. Use update_doc to change it, or choose another slug."
            )
        result = change_result(client, response)
        where = f"folder {parent['name']!r}" if parent else "the workspace root"
        text = status_text(
            result,
            f"Created doc {name!r} (slug: {slug}, id: {result['nodeId']}) in {where}",
            f"a new doc {name!r} in {where}",
        )
        yield from emit(
            self,
            {**result, "slug": slug, "name": name, "parent": node_ref(parent) if parent else None},
            text,
        )
