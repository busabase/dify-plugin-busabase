"""Nodes, docs, file trees and playbooks: reference resolution, guards and output shaping.

Several node endpoints accept a slug in one place and only an id in the next,
and some answer a mistake with an empty result instead of an error — see the
list in core.py's docstring. Every tool therefore resolves a node reference to
its id here (`resolve_node`) before calling anything else.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections.abc import Mapping
from typing import Any

from .client import BusabaseClient, BusabaseError

NODE_TYPES = (
    "folder",
    "doc",
    "base",
    "skill",
    "drive",
    "airapp",
    "file",
    "form",
    "html",
    "whiteboard",
    "workflow",
)
FILE_TREE_TYPES = ("skill", "drive", "airapp")
LINE_TYPES = ("doc", "html", "whiteboard", "workflow")
ROOT_REFS = ("", "/", "root")
SLUG_RE = re.compile(r"^[a-z0-9-]+$")
MAX_LINE_RANGE = 2000


# ── Small helpers ───────────────────────────────────────────────────────────


def node_of(detail: Mapping[str, Any]) -> dict[str, Any]:
    """`nodes.get` wraps the node (`{type, node, …}`); list endpoints return it bare."""
    inner = detail.get("node")
    return dict(inner) if isinstance(inner, Mapping) else dict(detail)


def node_ref(node: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": node.get("id"), "type": node.get("type"), "slug": node.get("slug"), "name": node.get("name")}


def node_vo(node: Mapping[str, Any]) -> dict[str, Any]:
    return {**node_ref(node), "parentId": node.get("parentId")}


def node_label(node: Mapping[str, Any]) -> str:
    return f"{node.get('type')} {node.get('name')!r} (slug: {node.get('slug')}, id: {node.get('id')})"


def file_vo(file: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": file.get("path"),
        "size": file.get("size"),
        "mimeType": file.get("mimeType"),
        "updatedAt": file.get("updatedAt"),
    }


def truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def line_count(text: str) -> int:
    return len(text.splitlines()) if text else 0


def choice_param(value: str, name: str, choices: tuple[str, ...], default: str) -> str:
    value = (value or "").strip().lower() or default
    if value not in choices:
        raise BusabaseError(f"`{name}` must be one of: {', '.join(choices)} (got {value!r}).")
    return value


# ── Resolving node references ───────────────────────────────────────────────


def _type_text(types: tuple[str, ...] | None) -> str:
    return " or ".join(types) if types else "node"


def _by_name(client: BusabaseClient, ref: str, types: tuple[str, ...] | None) -> dict[str, Any]:
    hits = client.search_nodes_by_name(ref, 50)
    if types:
        hits = [h for h in hits if h.get("type") in types]
    wanted = ref.casefold()
    exact = [h for h in hits if str(h.get("name", "")).casefold() == wanted]
    if len(exact) == 1:
        return client.get_node(str(exact[0]["id"]))
    what = _type_text(types)
    if len(exact) > 1:
        listed = "; ".join(node_label(h) for h in exact[:10])
        raise BusabaseError(f"More than one {what} is named {ref!r}; pass its id. Matches: {listed}")
    if hits:
        listed = "; ".join(node_label(h) for h in hits[:10])
        raise BusabaseError(f"No {what} is named exactly {ref!r}. Similar: {listed}")
    raise BusabaseError(
        f"No {what} matches {ref!r} (tried it as an id, a slug and a name). "
        "Use list_nodes or search_nodes to find it."
    )


def resolve_node(
    client: BusabaseClient, ref: str, types: tuple[str, ...] | None = None, param: str = "node"
) -> dict[str, Any]:
    """A node's `nodes.get` detail, from an id, a slug or an exact (case-insensitive) name.

    `types` restricts what is accepted; a node of another type is rejected with
    a message naming what it actually is.
    """
    ref = (ref or "").strip()
    if not ref:
        raise BusabaseError(f"`{param}` is required: a {_type_text(types)} id, slug, or name.")
    detail: dict[str, Any] | None = None
    try:
        detail = client.get_node(ref)
    except BusabaseError as exc:
        if exc.status_code not in (400, 404):
            raise
        # A slug used by two node types (a doc and a folder both called "notes")
        # is a 400 asking for `type`: retry with each type the caller accepts.
        if exc.status_code == 400 and "type" in str(exc):
            for node_type in types or ():
                try:
                    detail = client.get_node(ref, node_type)
                    break
                except BusabaseError as inner:
                    if inner.status_code not in (400, 404):
                        raise
            if detail is None and not types:
                raise BusabaseError(f"{exc} Pass `type` to choose one.", exc.status_code, exc.body) from exc
    if detail is None:
        detail = _by_name(client, ref, types)
    node = node_of(detail)
    node_type = detail.get("type") or node.get("type")
    if types and node_type not in types:
        hint = ""
        if node_type in FILE_TREE_TYPES:
            hint = " Use list_files / read_file / write_file for its files."
        elif node_type == "base":
            hint = " Use the record tools (list_records, create_record…) for Base data."
        raise BusabaseError(f"{ref!r} is a {node_type} ({node_label(node)}), not a {_type_text(types)}.{hint}")
    return detail


def resolve_parent_folder(client: BusabaseClient, ref: str) -> dict[str, Any] | None:
    """A folder to put something in, or None for the space root."""
    ref = (ref or "").strip()
    if ref.lower() in ROOT_REFS:
        return None
    return node_of(resolve_node(client, ref, ("folder",), "parent"))


# ── Slugs ───────────────────────────────────────────────────────────────────


def slugify(name: str, max_length: int = 60) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug[:max_length].strip("-")


def _slug_taken(client: BusabaseClient, slug: str, node_type: str) -> dict[str, Any] | None:
    try:
        return node_of(client.get_node(slug, node_type))
    except BusabaseError as exc:
        if exc.status_code in (400, 404):
            return None
        raise


def pick_slug(client: BusabaseClient, node_type: str, name: str, explicit: str) -> str:
    """The slug to create a node with.

    Slugs are unique per type across the whole space. An explicit slug that is
    taken is an error (for docs the server would otherwise hand back the
    existing doc — see core.py); a derived one gets a numeric suffix.
    """
    if explicit:
        if not SLUG_RE.match(explicit):
            raise BusabaseError(
                f"`slug` may only contain lowercase letters, digits and hyphens (got {explicit!r}). "
                "Leave it empty to derive one from the name."
            )
        existing = _slug_taken(client, explicit, node_type)
        if existing:
            hint = " Use update_doc to change it" if node_type == "doc" else " Use it as the parent"
            raise BusabaseError(
                f"A {node_type} with slug {explicit!r} already exists: {node_label(existing)}.{hint}, "
                "or choose another slug."
            )
        return explicit
    base = slugify(name) or f"{node_type}-{int(time.time() * 1000) % 36**6:x}"
    for n in range(1, 50):
        candidate = base if n == 1 else f"{base}-{n}"
        if not _slug_taken(client, candidate, node_type):
            return candidate
    raise BusabaseError(f"Could not find a free slug for {name!r}; pass `slug` explicitly.")


# ── Trees ───────────────────────────────────────────────────────────────────


def flatten_tree(nodes: list[Mapping[str, Any]], depth: int = 0) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for node in nodes:
        vo = {**node_vo(node), "depth": depth}
        children = node.get("children") or []
        if node.get("hasChildren") and not children:
            vo["hasMoreChildren"] = True  # beyond the depth limit — list it as `parent` to expand
        flat.append(vo)
        flat.extend(flatten_tree(children, depth + 1))
    return flat


def outline(nodes: list[Mapping[str, Any]], indent: bool = True) -> str:
    lines = []
    for n in nodes:
        pad = "  " * n.get("depth", 0) if indent else ""
        more = " (+ more inside)" if n.get("hasMoreChildren") else ""
        lines.append(f"{pad}- [{n['type']}] {n['name']} (slug: {n['slug']}, id: {n['id']}){more}")
    return "\n".join(lines)


# ── Change Request results ──────────────────────────────────────────────────


def _merged_change_request_id(client: BusabaseClient, node_id: str) -> str | None:
    """`docs.create` returns the merged node, not its CR: take the newest CR touching the node."""
    try:
        for cr in client.list_change_requests(node_id, limit=5):
            merged = (cr.get("mergeSummary") or {}).get("mergedNodeIds") or []
            if cr.get("status") == "merged" and (not merged or node_id in merged):
                return cr.get("id")
    except BusabaseError:
        return None
    return None


def change_result(client: BusabaseClient, response: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize every node write response to `status` / `merged` / `changeRequestId` / `nodeId`.

    Two shapes come back: the materialized node (`docs.create` when merged:
    `{node, body, materialized: true}`) or a Change Request (`{id: "crq…",
    status, primaryOperation, mergeSummary}`) — node CRs, `nodes.updateContent`
    and file-tree CRs always answer with the CR, merged or not.
    """
    if response.get("materialized") is True and isinstance(response.get("node"), Mapping) and "status" not in response:
        node = response["node"]
        return {
            "status": "merged",
            "merged": True,
            "changeRequestId": _merged_change_request_id(client, str(node.get("id"))),
            "nodeId": node.get("id"),
            "node": node_vo(node),
        }
    status = str(response.get("status") or "in_review")
    op = response.get("primaryOperation") or {}
    merged_ids = (response.get("mergeSummary") or {}).get("mergedNodeIds") or []
    return {
        "status": status,
        "merged": status == "merged",
        "changeRequestId": response.get("id"),
        "nodeId": response.get("nodeId") or op.get("nodeId") or (merged_ids[0] if merged_ids else None),
    }


def status_text(result: Mapping[str, Any], done: str, pending: str) -> str:
    """`done` reads after "Merged."; `pending` names what the review is about."""
    cr = result.get("changeRequestId")
    if result.get("status") == "merged":
        return f"Merged. {done}" + (f" (change request {cr})." if cr else ".")
    return (
        f"Submitted for review. Change request {cr} proposing {pending} is {result.get('status')}. "
        "It takes effect once a reviewer approves it in Busabase."
    )


# ── Playbooks ───────────────────────────────────────────────────────────────


def parse_queries(value: Any) -> list[str]:
    """2–5 phrasings, as a JSON array string, a list, or one per line / separated by | ; , ，；"""
    if isinstance(value, list):
        items = value
    else:
        text = str(value or "").strip()
        items = []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                items = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                items = []
        if not items:
            items = re.split(r"[\n|;,，；]+", text)
    queries: list[str] = []
    for item in items:
        q = str(item).strip()
        if q and q not in queries:
            queries.append(q[:200])
    return queries[:8]


def broaden_queries(queries: list[str]) -> list[str]:
    """Single words of multi-word phrasings — matching is substring, so "qualify lead" misses "Lead qualification"."""
    words: list[str] = []
    for q in queries:
        for word in re.split(r"\s+", q):
            w = word.strip(".,:;!?\"'()").lower()
            if len(w) >= 3 and w not in words and w not in (x.lower() for x in queries):
                words.append(w)
    return words[:8]


def playbook_vo(item: Mapping[str, Any]) -> dict[str, Any]:
    vo: dict[str, Any] = {
        "kind": item.get("kind"),
        "nodeId": item.get("nodeId"),
        "nodeType": item.get("nodeType"),
        "nodeName": item.get("nodeName"),
        "nodeSlug": item.get("nodeSlug"),
        "path": " / ".join(item.get("path") or []),
    }
    for key in ("key", "label", "intent", "name", "description", "matchedOn"):
        if item.get(key) not in (None, "", []):
            vo[key] = item.get(key)
    return vo


def playbook_title(item: Mapping[str, Any]) -> str:
    if item.get("kind") == "prompt":
        return f"prompt {item.get('label') or item.get('key')!r} (key: {item.get('key')}) on {item.get('nodeType')} {item.get('nodeName')!r}"
    return f"skill {item.get('name') or item.get('nodeName')!r}"
