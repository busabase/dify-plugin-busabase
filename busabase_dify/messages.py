"""Glue between the Busabase client and a Dify `Tool` instance.

Deliberately plain functions, not a shared `Tool` base class: Dify loads each
tool by taking the single `Tool` subclass found in its module, so importing a
base class into every tool file would make each of them ambiguous.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from typing import Any

from .client import BusabaseClient


def client_for(tool: Any) -> BusabaseClient:
    return BusabaseClient.from_credentials(tool.runtime.credentials)


def emit(tool: Any, data: Mapping[str, Any], text: str) -> Generator[Any, None, None]:
    """A one-line summary for chat / Agent use, and the structured JSON for workflows."""
    yield tool.create_text_message(text)
    yield tool.create_json_message(dict(data))
