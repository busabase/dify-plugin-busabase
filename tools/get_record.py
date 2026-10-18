from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import base_ref, record_title, record_vo, resolve_base, resolve_field_slug, text_param
from busabase_dify.messages import client_for, emit


class GetRecordTool(Tool):
    """records.get — GET /api/v1/records/get (by record id, or by an exact field value)"""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        record_id = text_param(tool_parameters, "record_id")
        if record_id:
            record = client.get_record(record_id)
        else:
            base_text = text_param(tool_parameters, "base")
            field_text = text_param(tool_parameters, "field")
            value = text_param(tool_parameters, "value")
            if not (base_text and field_text and value):
                raise BusabaseError(
                    "Give either `record_id`, or all of `base`, `field` and `value` to select a record "
                    "by an exact field value."
                )
            base = resolve_base(client, base_text)
            record = client.get_record(
                base_id=base["id"], field_slug=resolve_field_slug(base, field_text), value_text=value
            )
        base = record.get("base") or {}
        vo = record_vo(record)
        lines = [f"{k}: {v}" for k, v in vo["fields"].items()]
        text = (
            f"Record {record_title(base, record)!r} ({vo['id']}) in Base {base.get('name')!r}, "
            f"status {vo['status']}:\n" + "\n".join(lines)
        )
        yield from emit(self, {"base": base_ref(base), "record": vo}, text)
