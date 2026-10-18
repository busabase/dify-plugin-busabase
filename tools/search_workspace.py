from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from busabase_dify.client import BusabaseError
from busabase_dify.core import int_param, resolve_base, text_param
from busabase_dify.messages import client_for, emit

SOURCES = ("files", "nodes", "records", "prompts")


def _location(match: dict[str, Any]) -> str:
    source = match.get("source")
    if source == "records":
        return f"record {match.get('recordId')} in {match.get('baseSlug')} · {match.get('fieldSlug')}"
    if source == "files":
        return f"file {match.get('drivePath') or match.get('fileName')}"
    if source == "nodes":
        return f"{match.get('type')} {match.get('name') or match.get('slug')}"
    if source == "prompts":
        return f"prompt {match.get('label') or match.get('key')} on {match.get('nodeName')}"
    return str(source)


class SearchWorkspaceTool(Tool):
    """grep — POST /api/v1/grep (unified search over files, docs, records and prompts)"""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        client = client_for(self)
        pattern = text_param(tool_parameters, "pattern")
        if not pattern:
            raise BusabaseError("`pattern` is required: the text or regular expression to look for.")
        body: dict[str, Any] = {
            "pattern": pattern,
            "maxMatches": int_param(tool_parameters, "max_matches", default=50, minimum=1, maximum=1000),
        }
        if tool_parameters.get("case_insensitive") in (True, "true", "True", 1):
            body["flags"] = "i"
        source = text_param(tool_parameters, "source") or "all"
        if source != "all":
            if source not in SOURCES:
                raise BusabaseError(f"`source` must be one of: all, {', '.join(SOURCES)}.")
            body["sources"] = [source]
        base_text = text_param(tool_parameters, "base")
        if base_text:
            base = resolve_base(client, base_text)
            body["sources"] = ["records"]
            body["scope"] = {"records": {"baseIds": [base["id"]]}}

        result = client.grep(body)
        matches = result.get("matches") or []
        truncated = bool(result.get("truncated"))
        if matches:
            lines = [f"- {_location(m)} (line {m.get('line')}): {m.get('text')}" for m in matches[:20]]
            text = f"{len(matches)} match(es) for {pattern!r}:\n" + "\n".join(lines)
            if len(matches) > 20:
                text += f"\n… and {len(matches) - 20} more in the JSON output"
        else:
            text = f"No matches for {pattern!r}."
        if truncated:
            text += "\nResults were truncated — narrow the search with `source` or `base`."
        yield from emit(
            self,
            {
                "pattern": pattern,
                "matches": matches,
                "count": len(matches),
                "truncated": truncated,
                "coverage": result.get("coverage") or {},
            },
            text,
        )
