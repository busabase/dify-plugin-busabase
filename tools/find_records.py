from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import (
    base_ref,
    int_param,
    record_title,
    record_vo,
    resolve_base,
    resolve_field_slug,
    text_param,
)
from busabase_dify.messages import client_for, emit


class FindRecordsTool(Tool):
    """records.search — GET /api/v1/records/search (EXACT field value match)"""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        base = resolve_base(client, text_param(tool_parameters, "base"))
        field = resolve_field_slug(base, text_param(tool_parameters, "field"))
        value = text_param(tool_parameters, "value")
        if not value:
            raise BusabaseError("`value` is required: the exact text to match.")
        limit = int_param(tool_parameters, "limit", default=20, minimum=1, maximum=100)
        raw = client.search_records(base["id"], field, value, limit)
        records = [record_vo(r) for r in raw]
        if raw:
            titles = ", ".join(f"{record_title(base, r)} ({r.get('id')})" for r in raw[:10])
            text = f"{len(raw)} record(s) in {base.get('name')!r} where {field} = {value!r}: {titles}"
        else:
            text = (
                f"No record in {base.get('name')!r} has {field} exactly equal to {value!r}. "
                "This is an exact match; use Search Workspace for partial or full-text matches."
            )
        yield from emit(
            self,
            {"base": base_ref(base), "field": field, "value": value, "records": records, "count": len(records)},
            text,
        )
