"""HTTP client for the Busabase REST API (`/api/v1`).

Every tool and the credential check go through `BusabaseClient`, so auth
headers, the space header, timeouts and error messages are built in exactly
one place. It takes an optional `httpx.Client` so tests can inject a
`MockTransport` and exercise this same request-building code.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

PLUGIN_VERSION = "0.1.0"
DEFAULT_BASE_URL = "https://busabase.com"
DEFAULT_TIMEOUT = 30.0


def _default_http(timeout: float) -> httpx.Client:
    """The transport every client uses unless one is passed in — the seam tests replace."""
    return httpx.Client(timeout=timeout, follow_redirects=True)


class BusabaseError(Exception):
    """A Busabase request failed. The message is meant to be read by a human or an LLM."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _seg(value: str) -> str:
    """One URL path segment — ids and slugs are user/LLM input, never trusted as a path."""
    return quote(value.strip(), safe="")


def normalize_base_url(base_url: str | None) -> str:
    """Root URL of the server, without a trailing slash or a pasted `/api/v1` suffix."""
    url = (base_url or "").strip() or DEFAULT_BASE_URL
    url = url.rstrip("/")
    for suffix in ("/api/v1", "/api"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    if not url.startswith(("http://", "https://")):
        raise BusabaseError(f"Base URL must start with http:// or https:// (got {url!r}).")
    return url


def _issue_text(issue: Mapping[str, Any]) -> str:
    """One zod issue (`data.issues[]`) as `path: message`."""
    path = ".".join(str(p) for p in issue.get("path") or [])
    message = str(issue.get("message") or issue.get("code") or issue)
    return f"{path}: {message}" if path else message


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = None
    detail = ""
    if isinstance(body, Mapping):
        detail = str(body.get("error") or body.get("message") or "")
        data = body.get("data") if isinstance(body.get("data"), Mapping) else {}
        parts: list[str] = []
        errors = data.get("errors")
        if isinstance(errors, list):
            parts += [str(e.get("message") or e) for e in errors if isinstance(e, Mapping)]
        # Input validation failures (400 "Input validation failed") carry zod issues.
        issues = data.get("issues")
        if isinstance(issues, list):
            parts += [_issue_text(i) for i in issues[:5] if isinstance(i, Mapping)]
        allowed = data.get("allowedParentTypes")
        if isinstance(allowed, list) and allowed:
            parts.append(f"allowed parent types: {', '.join(map(str, allowed))}")
        if parts:
            detail = f"{detail} ({'; '.join(parts)})" if detail else "; ".join(parts)
    if not detail:
        detail = response.text[:300].strip() or response.reason_phrase

    status = response.status_code
    if status == 401:
        hint = "The API key is missing or invalid. Create one in Busabase under Settings → API Keys."
    elif status == 403:
        hint = "The API key does not have access to this resource or space."
    elif status == 404:
        hint = "Not found."
    elif status == 429:
        hint = "Rate limited by Busabase — retry later."
    else:
        hint = ""
    return f"Busabase API error {status}: {detail}" + (f" — {hint}" if hint and hint not in detail else "")


class BusabaseClient:
    def __init__(
        self,
        base_url: str | None,
        api_key: str | None = None,
        space_id: str | None = None,
        *,
        http: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        headers = {
            "Accept": "application/json",
            "User-Agent": f"dify-plugin-busabase/{PLUGIN_VERSION}",
        }
        if api_key and api_key.strip():
            headers["Authorization"] = f"Bearer {api_key.strip()}"
        if space_id and space_id.strip():
            headers["x-busabase-space"] = space_id.strip()
        self.headers = headers
        self._http = http or _default_http(timeout)

    @classmethod
    def from_credentials(cls, credentials: Mapping[str, Any], **kwargs: Any) -> BusabaseClient:
        return cls(
            credentials.get("base_url"),
            credentials.get("api_key"),
            credentials.get("space_id"),
            **kwargs,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        url = f"{self.base_url}/api/v1{path}"
        query = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            response = self._http.request(
                method, url, params=query or None, json=json, headers=self.headers
            )
        except httpx.HTTPError as exc:
            raise BusabaseError(f"Could not reach Busabase at {self.base_url}: {exc}") from exc
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise BusabaseError(_error_message(response), response.status_code, body)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise BusabaseError(
                f"Busabase at {self.base_url} returned a non-JSON response — is the Base URL right?"
            ) from exc

    # ── Endpoints (shapes from `busabase-cli schema <id>`) ──────────────────

    def list_bases(self, status: str = "active") -> list[dict[str, Any]]:
        """bases.list — GET /api/v1/bases"""
        return self.request("GET", "/bases", params={"status": status}) or []

    def get_base(self, base_id_or_slug: str) -> dict[str, Any]:
        """bases.get — GET /api/v1/bases/{baseId}; the path accepts an id or a slug."""
        return self.request("GET", f"/bases/{_seg(base_id_or_slug)}")

    def list_records(
        self, base_id: str, limit: int, cursor: str | None = None, status: str = "active"
    ) -> dict[str, Any]:
        """records.list — GET /api/v1/records"""
        return self.request(
            "GET",
            "/records",
            params={"baseId": base_id, "limit": limit, "cursor": cursor, "status": status},
        )

    def search_records(
        self, base_id: str, field_slug: str, value_text: str, limit: int
    ) -> list[dict[str, Any]]:
        """records.search — GET /api/v1/records/search (exact field value match)"""
        return (
            self.request(
                "GET",
                "/records/search",
                params={
                    "baseId": base_id,
                    "fieldSlug": field_slug,
                    "valueText": value_text,
                    "limit": limit,
                },
            )
            or []
        )

    def get_record(
        self,
        record_id: str | None = None,
        *,
        base_id: str | None = None,
        field_slug: str | None = None,
        value_text: str | None = None,
    ) -> dict[str, Any]:
        """records.get — GET /api/v1/records/get (by id, or by exact field value)"""
        if record_id:
            params: dict[str, Any] = {"recordId": record_id}
        else:
            params = {"baseId": base_id, "fieldSlug": field_slug, "valueText": value_text}
        return self.request("GET", "/records/get", params=params)

    def create_record_change_request(
        self,
        base_id: str,
        fields: Mapping[str, Any],
        message: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """bases.createChangeRequest — POST /api/v1/bases/{baseId}/change-requests

        `autoMerge` is deliberately omitted: the server merges immediately when
        the key has write access on the Base, and keeps a pending Change Request
        for a reviewer otherwise.
        """
        body: dict[str, Any] = {"fields": dict(fields), "message": message}
        if idempotency_key:
            body["idempotencyKey"] = idempotency_key
        return self.request("POST", f"/bases/{_seg(base_id)}/change-requests", json=body)

    def update_record_change_request(
        self, record_id: str, fields: Mapping[str, Any], message: str
    ) -> dict[str, Any]:
        """records.changeRequest (operation=update) — POST /api/v1/records/{recordId}/change-requests"""
        return self.request(
            "POST",
            f"/records/{_seg(record_id)}/change-requests",
            json={"operation": "update", "fields": dict(fields), "message": message},
        )

    def list_record_change_requests(self, record_id: str) -> list[dict[str, Any]]:
        """records.listChangeRequests — GET /api/v1/records/{recordId}/change-requests"""
        return self.request("GET", f"/records/{_seg(record_id)}/change-requests") or []

    def grep(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """grep — POST /api/v1/grep"""
        return self.request("POST", "/grep", json=dict(body))

    # ── Nodes ────────────────────────────────────────────────────────────────

    def list_nodes(
        self,
        *,
        parent_id: str | None = None,
        depth: int | None = None,
        types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """nodes.list — GET /api/v1/nodes (a tree, or a flat list when `types` is given)

        `parentId` must be a node id; see core.py for why it is resolved first.
        """
        return (
            self.request(
                "GET",
                "/nodes",
                params={"parentId": parent_id, "depth": depth, "types": types or None},
            )
            or []
        )

    def search_nodes_by_name(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """nodes.searchByName — GET /api/v1/nodes/search (name/slug substring, max 50)"""
        return self.request("GET", "/nodes/search", params={"query": query, "limit": limit}) or []

    def get_node(self, node_id_or_slug: str, node_type: str | None = None) -> dict[str, Any]:
        """nodes.get — GET /api/v1/nodes/{nodeId}; accepts an id or a slug (+ `type` to disambiguate)."""
        return self.request("GET", f"/nodes/{_seg(node_id_or_slug)}", params={"type": node_type})

    def read_node_lines(self, node_id: str, start_line: int, end_line: int) -> dict[str, Any]:
        """nodes.readLines — GET /api/v1/nodes/{nodeId}/lines (doc, html, whiteboard, workflow)"""
        return self.request(
            "GET",
            f"/nodes/{_seg(node_id)}/lines",
            params={"startLine": start_line, "endLine": end_line},
        )

    def create_doc(
        self,
        *,
        slug: str,
        name: str,
        body: str,
        parent_node_id: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """docs.create — POST /api/v1/docs (no `autoMerge`: the server decides merge vs review)"""
        payload: dict[str, Any] = {"slug": slug, "name": name, "body": body, "description": description}
        if parent_node_id:
            payload["parentNodeId"] = parent_node_id
        return self.request("POST", "/docs", json=payload)

    def node_change_request(self, operations: list[dict[str, Any]], message: str) -> dict[str, Any]:
        """nodes.createChangeRequest — POST /api/v1/nodes/change-requests (no `autoMerge`)"""
        return self.request(
            "POST", "/nodes/change-requests", json={"operations": operations, "message": message}
        )

    def update_node_content(
        self, node_id: str, content: Mapping[str, Any], message: str
    ) -> dict[str, Any]:
        """nodes.updateContent — PUT /api/v1/nodes/{nodeId}/content (id only — a slug 404s)"""
        return self.request(
            "PUT",
            f"/nodes/{_seg(node_id)}/content",
            json={"content": dict(content), "message": message},
        )

    def list_change_requests(self, affects_node_id: str, limit: int = 1) -> list[dict[str, Any]]:
        """changeRequests.list — GET /api/v1/change-requests?affectsNodeId=… (newest first)"""
        page = self.request(
            "GET", "/change-requests", params={"affectsNodeId": affects_node_id, "limit": limit}
        )
        return (page or {}).get("changeRequests") or []

    # ── File trees (skill / drive / airapp) ─────────────────────────────────

    def list_files(self, node_id: str) -> list[dict[str, Any]]:
        """fileTrees.listFiles — GET /api/v1/file-trees/{nodeId}/files"""
        return self.request("GET", f"/file-trees/{_seg(node_id)}/files") or []

    def read_file(self, node_id: str, path: str) -> dict[str, Any]:
        """fileTrees.readFile — GET /api/v1/file-trees/{nodeId}/files/{+filePath}"""
        file_path = quote(path.strip().lstrip("/"), safe="/")
        return self.request("GET", f"/file-trees/{_seg(node_id)}/files/{file_path}")

    def file_change_request(
        self, node_id: str, operations: list[dict[str, Any]], message: str
    ) -> dict[str, Any]:
        """fileTrees.createChangeRequest — POST /api/v1/file-trees/{nodeId}/change-requests (no `autoMerge`)"""
        return self.request(
            "POST",
            f"/file-trees/{_seg(node_id)}/change-requests",
            json={"operations": operations, "message": message},
        )

    # ── Playbooks (skills + custom prompts) ─────────────────────────────────

    def search_playbooks(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """playbooks.search — POST /api/v1/playbooks/search"""
        return self.request("POST", "/playbooks/search", json=dict(body))

    def get_playbook(
        self, kind: str, node_id: str, key: str | None = None, locale: str | None = None
    ) -> dict[str, Any]:
        """playbooks.get — GET /api/v1/playbooks/{kind}/{nodeId} (id only — a slug 404s)"""
        return self.request(
            "GET",
            f"/playbooks/{_seg(kind)}/{_seg(node_id)}",
            params={"key": key, "locale": locale},
        )
