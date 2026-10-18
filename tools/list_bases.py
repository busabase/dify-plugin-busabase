from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.core import base_vo
from busabase_dify.messages import client_for, emit


class ListBasesTool(Tool):
    """bases.list — GET /api/v1/bases"""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        bases = [base_vo(b) for b in client_for(self).list_bases()]
        if bases:
            lines = [
                f"- {b['name']} (slug: {b['slug']}, id: {b['id']}) — fields: "
                + (", ".join(f"{f['slug']} ({f['type']})" for f in b["fields"]) or "none")
                for b in bases
            ]
            text = f"{len(bases)} Base(s):\n" + "\n".join(lines)
        else:
            text = "No Bases in this space yet."
        yield from emit(self, {"bases": bases, "count": len(bases)}, text)
