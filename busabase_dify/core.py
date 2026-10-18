"""Tool-independent logic: resolving Base / field references and shaping outputs.

Two behaviours of the REST API make a thin pass-through unsafe for LLM tool
calling, so they are handled here:

* `records.list` / `records.search` accept only a Base **id** in `baseId`. A slug
  there is not an error — it silently returns no rows. Every tool therefore
  resolves the Base first via `bases.get` (whose path accepts an id or a slug)
  and falls back to a case-insensitive display-name match.
* A write keyed by a field's display name ("Name") instead of its slug ("name")
  is accepted and silently dropped. Field keys are mapped to slugs (accepting a
  slug, a field id, or a display name) and unknown keys are rejected with the
  list of valid slugs, before anything is sent.

The node endpoints have more of the same kind (found against a real 0.95.x
server; `tests/test_integration.py::test_server_quirks_the_node_tools_guard_against`
re-checks each one). The guards live in `nodes.py` and the tools:

* `nodes.list` with a `parentId` that is a slug, an unknown id, or a non-folder
  returns `[]`, not an error — and with `types` set it ignores `parentId`
  entirely. List Nodes resolves the parent to a folder id, and filters a
  type-within-folder listing itself from the subtree.
* `nodes.get` takes an id or a slug, but `nodes.updateContent`,
  `playbooks.get` and `docs.create`'s `parentNodeId` take an id only (a slug is
  a 404). Every node reference is resolved to an id first (`resolve_node`: id,
  slug, then exact name via `nodes.searchByName`).
* `docs.create` with a slug that already exists IN THE SAME FOLDER returns the
  existing doc, unchanged, as `materialized: true` — the new name and body are
  dropped (elsewhere it is a proper "slug already used" error). Create Doc
  checks the slug first and verifies the returned doc is the one it sent.
* A merged `docs.create` returns the node, not its Change Request; the CR is
  looked up with `changeRequests.list?affectsNodeId=`.
* A file-tree `update` of a path that does not exist silently CREATES it.
  Write File reads first and picks create/update itself (sending
  `baseContentHash` on update), and `mode: update` refuses a missing path.
* `nodes.readLines` answers a skill / drive / airapp with a misleading "Node not
  found"; Read Lines cuts the range from `fileTrees.readFile` instead.
* `playbooks.search` ignores an unknown key (e.g. `query` for `queries`) and
  falls back to browsing everything; a multi-word phrasing that is not a
  literal substring finds nothing. The tool always sends `queries` and retries
  once with single words.
* Input validation errors carry their reasons in `data.issues` (zod), which the
  client now spells out.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .client import BusabaseClient, BusabaseError


# ── Parameter parsing ───────────────────────────────────────────────────────


def text_param(params: Mapping[str, Any], name: str) -> str:
    value = params.get(name)
    if value is None:
        return ""
    return str(value).strip()


def int_param(
    params: Mapping[str, Any], name: str, default: int, minimum: int, maximum: int
) -> int:
    value = params.get(name)
    if value is None or value == "":
        return default
    try:
        number = int(float(value))
    except (TypeError, ValueError) as exc:
        raise BusabaseError(f"`{name}` must be a number (got {value!r}).") from exc
    return max(minimum, min(maximum, number))


def parse_fields(value: Any) -> dict[str, Any]:
    """`fields` arrives as a JSON object string (Dify string parameter) or an already-parsed dict."""
    if isinstance(value, Mapping):
        fields = dict(value)
    elif isinstance(value, str) and value.strip():
        try:
            fields = json.loads(value)
        except json.JSONDecodeError as exc:
            raise BusabaseError(
                f'`fields` must be a JSON object such as {{"name": "Acme Corp", "score": 8}} — {exc}'
            ) from exc
        if not isinstance(fields, dict):
            raise BusabaseError("`fields` must be a JSON object keyed by field slug.")
    else:
        raise BusabaseError("`fields` is required: a JSON object keyed by field slug.")
    if not fields:
        raise BusabaseError("`fields` is empty — give at least one field value.")
    return fields


# ── Bases and fields ────────────────────────────────────────────────────────


def field_display_name(field: Mapping[str, Any]) -> str:
    """Field names are either a string or a locale map ({"en": ..., "zh-CN": ...})."""
    name = field.get("name")
    if isinstance(name, Mapping):
        return str(name.get("en") or next(iter(name.values()), "") or field.get("slug", ""))
    return str(name or field.get("slug", ""))


def _field_names(field: Mapping[str, Any]) -> list[str]:
    name = field.get("name")
    if isinstance(name, Mapping):
        return [str(v) for v in name.values() if v]
    return [str(name)] if name else []


def resolve_base(client: BusabaseClient, ref: str) -> dict[str, Any]:
    """A Base by id, slug, or (case-insensitive) display name."""
    ref = (ref or "").strip()
    if not ref:
        raise BusabaseError("`base` is required: a Base id, slug, or name (use List Bases to see them).")
    try:
        return client.get_base(ref)
    except BusabaseError as exc:
        if exc.status_code not in (400, 404):
            raise
    bases = client.list_bases()
    wanted = ref.casefold()
    matches = [b for b in bases if str(b.get("name", "")).casefold() == wanted]
    if len(matches) == 1:
        return client.get_base(matches[0]["id"])
    available = ", ".join(f"{b.get('name')} ({b.get('slug')})" for b in bases) or "none"
    if len(matches) > 1:
        raise BusabaseError(f"More than one Base is named {ref!r}; pass its slug or id. Bases: {available}")
    raise BusabaseError(f"No Base matches {ref!r}. Available Bases: {available}")


def resolve_field_slug(base: Mapping[str, Any], ref: str) -> str:
    """A field of `base` by slug, id, or (case-insensitive) display name → its slug."""
    ref = (ref or "").strip()
    fields = base.get("fields") or []
    for field in fields:
        if ref in (field.get("slug"), field.get("id")):
            return str(field["slug"])
    wanted = ref.casefold()
    for field in fields:
        if wanted in (n.casefold() for n in _field_names(field)):
            return str(field["slug"])
    valid = ", ".join(f"{f.get('slug')} ({field_display_name(f)})" for f in fields) or "none"
    raise BusabaseError(f"Base {base.get('slug')!r} has no field {ref!r}. Fields: {valid}")


def map_field_keys(base: Mapping[str, Any], fields: Mapping[str, Any]) -> dict[str, Any]:
    """Rewrite every key to its field slug; reject unknown keys instead of letting them vanish."""
    mapped: dict[str, Any] = {}
    for key, value in fields.items():
        slug = resolve_field_slug(base, str(key))
        if slug in mapped:
            raise BusabaseError(f"Field {slug!r} is given twice in `fields` (as a slug and as a name).")
        mapped[slug] = value
    return mapped


# ── Output shaping (PO-ish API objects → compact, LLM-friendly views) ────────


def field_vo(field: Mapping[str, Any]) -> dict[str, Any]:
    vo: dict[str, Any] = {
        "slug": field.get("slug"),
        "name": field_display_name(field),
        "type": field.get("type"),
        "required": bool(field.get("required")),
    }
    choices = (field.get("options") or {}).get("choices")
    if choices:
        vo["choices"] = [c.get("name") for c in choices if isinstance(c, Mapping)]
    return vo


def base_ref(base: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": base.get("id"), "slug": base.get("slug"), "name": base.get("name")}


def base_vo(base: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **base_ref(base),
        "description": base.get("description") or "",
        "fields": [field_vo(f) for f in base.get("fields") or []],
    }


def user_name(user: Any) -> str | None:
    if isinstance(user, Mapping):
        return user.get("name") or user.get("email") or user.get("id")
    return None


def record_vo(record: Mapping[str, Any]) -> dict[str, Any]:
    head = record.get("headCommit") or {}
    return {
        "id": record.get("id"),
        "baseId": record.get("baseId"),
        "status": record.get("status"),
        "fields": head.get("payload") or {},
        "createdAt": record.get("createdAt"),
        "updatedAt": record.get("updatedAt"),
        "createdBy": user_name(record.get("createdByUser")) or record.get("createdBy"),
        "lastMessage": head.get("message"),
    }


def primary_value(base: Mapping[str, Any], fields: Mapping[str, Any]) -> str | None:
    """The Base's first field is the record's display title."""
    base_fields = base.get("fields") or []
    if not base_fields:
        return None
    value = fields.get(base_fields[0].get("slug"))
    return None if value in (None, "") else str(value)


def record_title(base: Mapping[str, Any], record: Mapping[str, Any]) -> str:
    return primary_value(base, (record.get("headCommit") or {}).get("payload") or {}) or str(
        record.get("id")
    )


# ── Write results ───────────────────────────────────────────────────────────


def _find_merged_change_request(
    client: BusabaseClient, record_id: str, head_commit_id: str | None
) -> dict[str, Any] | None:
    """A merged write returns the record, not its Change Request; look the CR up by head commit."""
    if not head_commit_id:
        return None
    try:
        history = client.list_record_change_requests(record_id)
    except BusabaseError:
        return None
    for cr in history:
        for op in cr.get("operations") or []:
            if op.get("headCommitId") == head_commit_id:
                return cr
    return None


def write_result(
    client: BusabaseClient,
    response: Mapping[str, Any],
    base: Mapping[str, Any],
    action: str,
) -> tuple[dict[str, Any], str]:
    """Normalize both write outcomes into one shape.

    The write endpoints return EITHER the materialized record (`materialized:
    true` — merged in the same call) OR a pending Change Request
    (`materialized: false` — waiting for a reviewer). Callers need to tell
    these apart, so `status` / `merged` are always present.
    """
    base_label = base.get("name") or base.get("slug")
    if response.get("materialized") is not False and "headCommit" in response:
        record = record_vo(response)
        cr = _find_merged_change_request(client, str(response["id"]), response.get("headCommitId"))
        result = {
            "status": "merged",
            "merged": True,
            "changeRequestId": cr.get("id") if cr else None,
            "recordId": response.get("id"),
            "base": base_ref(base),
            "record": record,
        }
        verb = "Created" if action == "create" else "Updated"
        title = record_title(base, response)
        cr_text = f" (change request {result['changeRequestId']})" if result["changeRequestId"] else ""
        text = f"Merged. {verb} record {title!r} ({response.get('id')}) in Base {base_label!r}{cr_text}."
        return result, text

    op = response.get("primaryOperation") or {}
    proposed = (op.get("headCommit") or {}).get("payload") or {}
    record_id = op.get("targetRecordId") or op.get("mergedRecordId")
    status = response.get("status") or "in_review"
    result = {
        "status": status,
        "merged": status == "merged",
        "changeRequestId": response.get("id"),
        "recordId": record_id,
        "base": base_ref(base),
        "proposedFields": proposed,
        "submittedBy": user_name(response.get("submittedByUser")) or response.get("submittedBy"),
    }
    if action == "create":
        what = "a new record" + (f" {primary_value(base, proposed)!r}" if primary_value(base, proposed) else "")
        tail = "The record is created once a reviewer approves it."
    else:
        what = f"an update to record {record_id}"
        tail = "The record changes once a reviewer approves it."
    text = (
        f"Submitted for review. Change request {response.get('id')} proposing {what} in Base "
        f"{base_label!r} is {status}. {tail}"
    )
    return result, text
