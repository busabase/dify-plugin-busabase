"""Node / doc / file-tree / playbook response shapes trimmed from a real local
`busabase server` (0.95.x), captured while building the node tools."""

import httpx

ROOT_ID = "nod_root"
FOLDER_ID = "nodmveg7vfdm4bmzba"
DOC_ID = "nodmveg7z97ch8cs8r"
SKILL_ID = "nodmveg8psg34n5dkv"
BASE_NODE_ID = "nodmvegbnpd815grqu"
HASH = "sha256:" + "f3" * 32


def node(node_id, node_type, slug, name, parent=FOLDER_ID, children=None, has_children=False, **extra):
    return {
        "id": node_id,
        "parentId": parent,
        "type": node_type,
        "slug": slug,
        "name": name,
        "description": "",
        "metadata": {},
        "settings": {},
        "explicitVisibility": None,
        "icon": None,
        "position": 0,
        "createdAt": "2026-10-18T23:20:35.131Z",
        "updatedAt": "2026-10-18T23:20:35.131Z",
        "baseId": None,
        "children": children or [],
        "hasChildren": has_children,
        **extra,
    }


FOLDER = node(FOLDER_ID, "folder", "probe-folder", "Probe Folder", parent=ROOT_ID, has_children=True)
DOC = node(DOC_ID, "doc", "probe-doc", "Probe Doc")
SKILL = node(SKILL_ID, "skill", "lead-qualify", "Lead Qualification", description="How we qualify inbound leads")
BASE_NODE = node(BASE_NODE_ID, "base", "dify-leads", "Dify Leads", baseId="bsemve1a8qqyg3l2qj")

FILES = [
    {"path": "SKILL.md", "name": "SKILL.md", "size": 128, "updatedAt": "2026-10-18T23:21:09.556Z", "mimeType": "text/plain; charset=utf-8", "assetId": "ast1", "displayName": "SKILL.md"},
    {"path": "references/checklist.md", "name": "checklist.md", "size": 27, "updatedAt": "2026-10-18T23:21:09.556Z", "mimeType": "text/plain; charset=utf-8", "assetId": "ast2", "displayName": "checklist.md"},
    {"path": "skill.json", "name": "skill.json", "size": 100, "updatedAt": "2026-10-18T23:21:09.545Z", "mimeType": "application/json", "assetId": "ast3", "displayName": "skill.json"},
]

# nodes.get — typed detail
DOC_DETAIL = {"type": "doc", "node": DOC, "storagePrefix": f"busabase/nodes/{DOC_ID}/doc/", "body": "# Probe\n\nline two"}
FOLDER_DETAIL = {"type": "folder", "node": FOLDER, "children": [DOC, SKILL]}
SKILL_DETAIL = {"type": "skill", "node": SKILL, "entryFile": "SKILL.md", "visibility": "private", "version": "0.1.0", "files": FILES, "skippedGitignorePaths": []}
BASE_DETAIL = {"type": "base", "node": BASE_NODE}

# nodes.list — the legacy/depth-bounded call wraps the root folder
TREE = [
    node(
        ROOT_ID,
        "folder",
        "root",
        "Workspace",
        parent=None,
        has_children=True,
        children=[
            {**FOLDER, "children": [DOC, {**node("nodsub", "folder", "sub", "Sub", has_children=True)}]},
            node("nodrootdoc", "doc", "d-root", "Root Doc", parent=ROOT_ID),
        ],
    )
]

SKILL_MD = "---\nname: lead-qualify\ndescription: How we qualify inbound leads\n---\n\n# Lead qualification\n\n1. Check company size\n2. Score 1-10\n"
READ_FILE = {
    "nodeId": SKILL_ID,
    "path": "SKILL.md",
    "encoding": "utf8",
    "content": SKILL_MD,
    "mimeType": "text/plain; charset=utf-8",
    "assetId": "ast1",
    "displayName": "SKILL.md",
    "assetUrl": "/api/storage/attachments/local/blobs/sha256/f3/f3.md",
    "contentHash": HASH,
}


def change_request(cr_id="crqmveg8puygo1oza0", status="merged", operation="doc_update", node_id=DOC_ID, file_path=None, payload=None):
    """The CR every node write except a merged docs.create answers with."""
    merged = status == "merged"
    return {
        "id": cr_id,
        "baseId": None,
        "targetType": "node",
        "nodeId": node_id if operation != "node_create" else None,
        "status": status,
        "submittedBy": "local-producer",
        "mergeSummary": {"mergedNodeIds": [node_id], "operationCount": 1} if merged else {},
        "primaryOperation": {
            "id": "opr1",
            "changeRequestId": cr_id,
            "nodeId": node_id if (merged or operation != "node_create") else None,
            "operation": operation,
            "status": "merged" if merged else "pending",
            "filePath": file_path,
            "headCommit": {"id": "cmt1", "payload": payload or {}},
        },
    }


DOC_CREATE_MERGED = {"node": node("nodnewdoc", "doc", "launch-plan", "Launch Plan"), "storagePrefix": "x", "body": "# Plan", "materialized": True}
DOC_CREATE_IN_REVIEW = {
    **change_request("crqreviewdoc", "in_review", "node_create", None, payload={"kind": "create", "nodeType": "doc", "slug": "launch-plan", "name": "Launch Plan", "body": "# Plan"}),
    "materialized": False,
}
CR_LIST_FOR_NEW_DOC = {"changeRequests": [{"id": "crqnewdoc", "status": "merged", "mergeSummary": {"mergedNodeIds": ["nodnewdoc"]}}], "nextCursor": None}

PLAYBOOK_SEARCH = {
    "items": [
        {"kind": "skill", "nodeId": SKILL_ID, "nodeType": "skill", "nodeName": "Lead Qualification", "nodeSlug": "lead-qualify", "path": ["Probe Folder"], "name": "Lead Qualification", "description": "How we qualify inbound leads", "matchedOn": ["name"], "score": 4, "updatedAt": "2026-10-18T23:21:09.520Z"},
        {"kind": "prompt", "nodeId": FOLDER_ID, "nodeType": "folder", "nodeName": "Probe Folder", "nodeSlug": "probe-folder", "path": [], "key": "weekly-report", "label": "写周报", "intent": "read-only", "matchedOn": ["label", "body"], "score": 8, "updatedAt": "2026-10-18T23:23:02.386Z"},
    ],
    "total": 2,
    "truncated": False,
    "coverage": {"skillsScanned": 1, "promptNodesScanned": 1},
}
EMPTY_PLAYBOOKS = {"items": [], "total": 0, "truncated": False, "coverage": {"skillsScanned": 1, "promptNodesScanned": 1}}
SKILL_PLAYBOOK = {
    "kind": "skill",
    "nodeId": SKILL_ID,
    "nodeType": "skill",
    "nodeName": "Lead Qualification",
    "nodeSlug": "lead-qualify",
    "path": ["Probe Folder"],
    "content": SKILL_MD,
    "name": "Lead Qualification",
    "description": "How we qualify inbound leads",
    "files": [{"path": f["path"], "size": f["size"], "mimeType": f["mimeType"]} for f in FILES],
}
PROMPT_PLAYBOOK = {
    "kind": "prompt",
    "nodeId": FOLDER_ID,
    "nodeType": "folder",
    "nodeName": "Probe Folder",
    "nodeSlug": "probe-folder",
    "path": [],
    "content": "目标：Busabase 的 Folder「Probe Folder」\n\n把这个文件夹总结成周报。",
    "key": "weekly-report",
    "label": "写周报",
    "intent": "read-only",
    "locale": "zh-CN",
}


def not_found(message="Node not found: x"):
    return httpx.Response(404, json={"error": message, "code": "NOT_FOUND"})


def by_type(**replies):
    """A reply keyed by the `type` query param ('' = none) — nodes.get with and without a type hint."""

    def reply(request: httpx.Request):
        value = replies.get(request.url.params.get("type", ""), None)
        return value if value is not None else not_found()

    return reply
