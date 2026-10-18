from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import map_field_keys, parse_fields, record_title, text_param, write_result
from busabase_dify.messages import client_for, emit


class UpdateRecordTool(Tool):
    """records.changeRequest (operation=update) — POST /api/v1/records/{recordId}/change-requests

    Only the given fields change. Merges immediately with write access on the
    Base; otherwise it becomes a pending Change Request for a reviewer.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        record_id = text_param(tool_parameters, "record_id")
        if not record_id:
            raise BusabaseError("`record_id` is required (find it with List Records or Find Records).")
        # Read first: it confirms the record exists and carries its Base's field
        # list, which is what lets display-name keys be mapped to slugs.
        current = client.get_record(record_id)
        base = current.get("base") or {}
        fields = map_field_keys(base, parse_fields(tool_parameters.get("fields")))
        message = text_param(tool_parameters, "message") or (
            f"Update {record_title(base, current)} via Dify"
        )
        response = client.update_record_change_request(record_id, fields, message)
        data, text = write_result(client, response, base, "update")
        yield from emit(self, {**data, "message": message}, text)
