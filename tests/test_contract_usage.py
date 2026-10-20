"""contract-usage.json must list exactly the endpoints busabase_dify/client.py calls.

Busabase checks every key in that file against its API contract in CI, so a
contract change that would break this plugin is caught before release. That only protects us if
the file is complete: this test fails when the client starts calling an endpoint
the file does not list, or the file keeps one the client no longer calls.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Each endpoint method in the client opens its docstring with `<contract id> — METHOD /path`.
ENDPOINT_DOC = re.compile(r'"""([a-zA-Z]+(?:\.[a-zA-Z]+)*)(?: \([^)]*\))? —')


def client_endpoint_ids() -> set[str]:
    return set(ENDPOINT_DOC.findall((ROOT / "busabase_dify" / "client.py").read_text(encoding="utf-8")))


def manifest_endpoint_ids() -> set[str]:
    manifest = json.loads((ROOT / "contract-usage.json").read_text(encoding="utf-8"))
    return {endpoint["id"] for endpoint in manifest["endpoints"]}


def test_client_endpoints_are_found() -> None:
    # Guards the regex itself: an empty set would make the comparison below vacuous.
    assert len(client_endpoint_ids()) >= 20


def test_manifest_lists_exactly_the_endpoints_the_client_calls() -> None:
    client, manifest = client_endpoint_ids(), manifest_endpoint_ids()
    assert client - manifest == set(), f"called by client.py but missing from contract-usage.json: {sorted(client - manifest)}"
    assert manifest - client == set(), f"listed in contract-usage.json but no longer called: {sorted(manifest - client)}"
