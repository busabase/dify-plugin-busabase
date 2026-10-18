from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.core import base_ref, int_param, record_title, record_vo, resolve_base, text_param
from busabase_dify.messages import client_for, emit


class ListRecordsTool(Tool):
    """records.list — GET /api/v1/records (one page, with a cursor for the next)"""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        base = resolve_base(client, text_param(tool_parameters, "base"))
        limit = int_param(tool_parameters, "limit", default=20, minimum=1, maximum=100)
        status = text_param(tool_parameters, "status") or "active"
        page = client.list_records(
            base["id"], limit, cursor=text_param(tool_parameters, "cursor") or None, status=status
        )
        raw = page.get("records") or []
        records = [record_vo(r) for r in raw]
        next_cursor = page.get("nextCursor")
        titles = ", ".join(f"{record_title(base, r)} ({r.get('id')})" for r in raw[:10])
        text = f"{len(records)} {status} record(s) from Base {base.get('name')!r}"
        text += f": {titles}" if titles else "."
        if len(raw) > 10:
            text += f" … and {len(raw) - 10} more"
        if next_cursor:
            text += " More records exist — call again with the returned `nextCursor` as `cursor`."
        yield from emit(
            self,
            {"base": base_ref(base), "records": records, "count": len(records), "nextCursor": next_cursor},
            text,
        )
