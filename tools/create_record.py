from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.core import map_field_keys, parse_fields, primary_value, resolve_base, text_param, write_result
from busabase_dify.messages import client_for, emit


class CreateRecordTool(Tool):
    """bases.createChangeRequest — POST /api/v1/bases/{baseId}/change-requests

    Merges immediately when the API key has write access on the Base; otherwise
    the record is proposed as a Change Request for a human reviewer.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        base = resolve_base(client, text_param(tool_parameters, "base"))
        fields = map_field_keys(base, parse_fields(tool_parameters.get("fields")))
        title = primary_value(base, fields)
        message = text_param(tool_parameters, "message") or (
            f"Add {title} via Dify" if title else "Add record via Dify"
        )
        response = client.create_record_change_request(
            base["id"], fields, message, text_param(tool_parameters, "idempotency_key") or None
        )
        data, text = write_result(client, response, base, "create")
        yield from emit(self, {**data, "message": message}, text)
