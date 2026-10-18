"""Every tool against a REAL Busabase server, through the same `Tool.invoke` path Dify uses.

Skipped unless BUSABASE_TEST_BASE_URL is set. It creates a throwaway Base, so
it refuses to run against anything but a local server unless
BUSABASE_TEST_ALLOW_REMOTE=1 — never point it at a real workspace.

    npx busabase server --port 15419 --data /tmp/busabase-dify-test
    BUSABASE_TEST_BASE_URL=http://127.0.0.1:15419 pytest -m integration -s

The node tests also create a scratch folder, docs, a skill and a custom prompt.
"""

from __future__ import annotations

import json
import os
import time
from urllib.parse import urlparse

import pytest

from busabase_dify.client import BusabaseClient
from tests.helpers import run_tool
from tools.create_doc import CreateDocTool
from tools.create_folder import CreateFolderTool
from tools.create_record import CreateRecordTool
from tools.find_records import FindRecordsTool
from tools.get_node import GetNodeTool
from tools.get_playbook import GetPlaybookTool
from tools.get_record import GetRecordTool
from tools.list_bases import ListBasesTool
from tools.list_files import ListFilesTool
from tools.list_nodes import ListNodesTool
from tools.list_records import ListRecordsTool
from tools.read_file import ReadFileTool
from tools.read_node_lines import ReadNodeLinesTool
from tools.search_nodes import SearchNodesTool
from tools.search_playbooks import SearchPlaybooksTool
from tools.search_workspace import SearchWorkspaceTool
from tools.update_doc import UpdateDocTool
from tools.update_record import UpdateRecordTool
from tools.write_file import WriteFileTool

BASE_URL = os.environ.get("BUSABASE_TEST_BASE_URL", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not BASE_URL, reason="set BUSABASE_TEST_BASE_URL to run against a real server"),
]


@pytest.fixture(scope="module")
def credentials():
    host = urlparse(BASE_URL).hostname
    if host not in ("localhost", "127.0.0.1", "::1") and os.environ.get("BUSABASE_TEST_ALLOW_REMOTE") != "1":
        pytest.skip(f"refusing to create test data on {host}; set BUSABASE_TEST_ALLOW_REMOTE=1 to override")
    return {
        "base_url": BASE_URL,
        "api_key": os.environ.get("BUSABASE_TEST_API_KEY", ""),
        "space_id": os.environ.get("BUSABASE_TEST_SPACE_ID", ""),
    }


@pytest.fixture(scope="module")
def scratch_base(credentials):
    """A fresh Base (bases.create — POST /api/v1/bases) so runs never collide."""
    slug = f"dify-it-{int(time.time())}"
    client = BusabaseClient.from_credentials(credentials)
    base = client.request(
        "POST",
        "/bases",
        json={
            "slug": slug,
            "name": f"Dify IT {slug[-6:]}",
            "description": "Created by the Dify plugin integration test",
            "message": "Create scratch Base for the Dify plugin integration test",
            "fields": [
                {"slug": "company", "name": "Company", "type": "text"},
                {"slug": "stage", "name": "Stage", "type": "text"},
                {"slug": "score", "name": "Score", "type": "number"},
            ],
        },
    )
    assert base.get("materialized") is not False, "scratch Base needs write access to be created"
    return base


def show(name, text, data):
    print(f"\n=== {name}\n{text}\n{json.dumps(data, ensure_ascii=False, indent=1)[:1500]}")


def test_all_tools_round_trip(credentials, scratch_base):
    slug = scratch_base["slug"]

    text, data = run_tool(ListBasesTool, {}, credentials)
    show("list_bases", text, data)
    assert slug in [b["slug"] for b in data["bases"]]

    # Display names ("Company") on purpose: the plugin maps them to slugs.
    text, data = run_tool(
        CreateRecordTool,
        {
            "base": slug,
            "fields": json.dumps({"Company": "Acme Corp", "stage": "Lead", "score": 6}),
            "message": "Add Acme Corp — lead from the Dify integration test",
        },
        credentials,
    )
    show("create_record", text, data)
    assert data["status"] == "merged"
    assert data["changeRequestId"]
    record_id = data["recordId"]
    assert data["record"]["fields"] == {"company": "Acme Corp", "stage": "Lead", "score": 6}

    text, data = run_tool(
        UpdateRecordTool,
        {"record_id": record_id, "fields": '{"stage": "Qualified", "Score": 9}', "message": "Qualify Acme Corp — demo booked"},
        credentials,
    )
    show("update_record", text, data)
    assert data["status"] == "merged"
    assert data["recordId"] == record_id
    update_cr = data["changeRequestId"]
    assert update_cr

    text, data = run_tool(GetRecordTool, {"record_id": record_id}, credentials)
    show("get_record (id)", text, data)
    assert data["record"]["fields"] == {"company": "Acme Corp", "stage": "Qualified", "score": 9}
    assert data["record"]["lastMessage"] == "Qualify Acme Corp — demo booked"

    text, data = run_tool(GetRecordTool, {"base": slug, "field": "Company", "value": "Acme Corp"}, credentials)
    show("get_record (field value)", text, data)
    assert data["record"]["id"] == record_id

    text, data = run_tool(ListRecordsTool, {"base": slug, "limit": 10}, credentials)
    show("list_records", text, data)
    assert [r["id"] for r in data["records"]] == [record_id]

    text, data = run_tool(FindRecordsTool, {"base": slug, "field": "company", "value": "Acme Corp"}, credentials)
    show("find_records", text, data)
    assert [r["id"] for r in data["records"]] == [record_id]

    text, data = run_tool(FindRecordsTool, {"base": slug, "field": "company", "value": "Acme"}, credentials)
    assert data["count"] == 0  # exact match only

    text, data = run_tool(
        SearchWorkspaceTool, {"pattern": "acme", "base": slug, "case_insensitive": True}, credentials
    )
    show("search_workspace", text, data)
    assert {m["recordId"] for m in data["matches"]} == {record_id}

    with pytest.raises(Exception, match="no field 'Website'"):
        run_tool(CreateRecordTool, {"base": slug, "fields": '{"Website": "x"}'}, credentials)


# ── Nodes, docs, files and playbooks ────────────────────────────────────────


@pytest.fixture(scope="module")
def stamp():
    return str(int(time.time()))


@pytest.fixture(scope="module")
def scratch_skill(credentials, stamp):
    """A skill with a SKILL.md (fileTrees.create — POST /api/v1/file-trees); the plugin has no create-skill tool."""
    client = BusabaseClient.from_credentials(credentials)
    skill = client.request(
        "POST",
        "/file-trees",
        json={
            "type": "skill",
            "slug": f"dify-it-qualify-{stamp}",
            "name": f"Dify IT Lead Qualification {stamp}",
            "description": "How we qualify inbound leads (Dify integration test)",
            "files": [
                {
                    "path": "SKILL.md",
                    "content": f"---\nname: dify-it-qualify-{stamp}\ndescription: How we qualify inbound leads\n---\n\n"
                    "# Lead qualification\n\n1. Check company size\n2. Score 1-10\n",
                }
            ],
        },
    )
    assert skill.get("materialized") is True, "scratch skill needs write access to be created"
    return skill["node"]


def test_node_tools_round_trip(credentials, stamp, scratch_skill):
    client = BusabaseClient.from_credentials(credentials)
    folder_name = f"Dify IT Folder {stamp}"

    text, data = run_tool(CreateFolderTool, {"name": folder_name, "message": "Create scratch folder for the Dify plugin test"}, credentials)
    show("create_folder", text, data)
    assert data["status"] == "merged" and data["changeRequestId"] and data["nodeId"]
    folder_id, folder_slug = data["nodeId"], data["slug"]
    assert folder_slug == f"dify-it-folder-{stamp}"

    # Custom prompt on the folder, so search/get playbooks has a prompt to find (setup only).
    client.request(
        "PUT",
        f"/nodes/{folder_id}/agent-prompts",
        json={"agentPrompts": [{"key": f"weekly-{stamp}", "intent": "read-only", "label": {"en": f"Write weekly report {stamp}", "zh-CN": "写周报"}, "body": {"en": "Summarize this folder into a weekly report.", "zh-CN": "把这个文件夹总结成周报。"}}]},
    )

    # Parent by NAME (resolved client-side; docs.create only takes an id).
    text, data = run_tool(CreateDocTool, {"name": f"Launch Plan {stamp}", "body": "# Launch plan\n\nGoal: ship v1", "parent": folder_name}, credentials)
    show("create_doc", text, data)
    assert data["status"] == "merged" and data["changeRequestId"] and data["parent"]["id"] == folder_id
    doc_id, doc_slug = data["nodeId"], data["slug"]

    # Same name again: the derived slug is taken, so it gets a suffix instead of returning the old doc.
    text, data = run_tool(CreateDocTool, {"name": f"Launch Plan {stamp}", "body": "second", "parent": folder_id}, credentials)
    show("create_doc (same name)", text, data)
    assert data["slug"] == f"{doc_slug}-2" and data["nodeId"] != doc_id

    with pytest.raises(Exception, match="already exists"):
        run_tool(CreateDocTool, {"name": "Dup", "slug": doc_slug, "parent": folder_id}, credentials)

    # Append via SLUG (nodes.updateContent itself 404s for a slug).
    text, data = run_tool(UpdateDocTool, {"doc": doc_slug, "text": "Owner: Ops team", "message": "Add owner to launch plan"}, credentials)
    show("update_doc append", text, data)
    assert data["status"] == "merged" and data["changeRequestId"]
    _, data = run_tool(GetNodeTool, {"node": doc_id}, credentials)
    assert data["body"] == "# Launch plan\n\nGoal: ship v1\nOwner: Ops team"

    text, data = run_tool(UpdateDocTool, {"doc": doc_id, "mode": "replace", "text": "# Launch plan\n\n1. Beta\n2. GA\n3. Retro", "message": "Rewrite launch plan as steps"}, credentials)
    show("update_doc replace", text, data)
    assert data["status"] == "merged"
    _, data = run_tool(UpdateDocTool, {"doc": doc_id, "mode": "replace", "text": "# Launch plan\n\n1. Beta\n2. GA\n3. Retro"}, credentials)
    assert data["status"] == "unchanged"

    text, data = run_tool(ReadNodeLinesTool, {"node": doc_id, "start_line": 3, "end_line": 4}, credentials)
    show("read_node_lines (doc)", text, data)
    assert data["lines"] == ["1. Beta", "2. GA"] and data["totalLines"] == 5 and data["hasMore"] is True

    text, data = run_tool(GetNodeTool, {"node": doc_slug, "max_chars": 500}, credentials)
    show("get_node (doc)", text, data)
    assert data["type"] == "doc" and data["body"].startswith("# Launch plan") and data["bodyTruncated"] is False

    text, data = run_tool(GetNodeTool, {"node": folder_slug}, credentials)
    show("get_node (folder)", text, data)
    assert {c["id"] for c in data["children"]} >= {doc_id}

    # Files in a skill.
    skill_id, skill_slug = scratch_skill["id"], scratch_skill["slug"]
    text, data = run_tool(ListFilesTool, {"node": skill_slug}, credentials)
    show("list_files", text, data)
    assert "SKILL.md" in [f["path"] for f in data["files"]]

    text, data = run_tool(ReadFileTool, {"node": skill_id, "path": "SKILL.md"}, credentials)
    show("read_file", text, data)
    assert "# Lead qualification" in data["content"] and data["contentHash"].startswith("sha256:")

    new_skill_md = data["content"] + "3. Check budget\n"
    text, data = run_tool(WriteFileTool, {"node": skill_slug, "path": "SKILL.md", "content": new_skill_md, "message": "Add budget check to qualification"}, credentials)
    show("write_file update", text, data)
    assert data["status"] == "merged" and data["operation"] == "updated" and data["changeRequestId"]

    text, data = run_tool(WriteFileTool, {"node": skill_id, "path": "references/checklist.md", "content": "- size\n- budget\n"}, credentials)
    show("write_file create", text, data)
    assert data["operation"] == "created" and data["status"] == "merged"

    with pytest.raises(Exception, match="to update"):
        run_tool(WriteFileTool, {"node": skill_id, "path": "references/checklst.md", "content": "typo", "mode": "update"}, credentials)
    paths = [f["path"] for f in client.list_files(skill_id)]
    assert "references/checklst.md" not in paths and "references/checklist.md" in paths

    text, data = run_tool(ReadNodeLinesTool, {"node": skill_id, "path": "SKILL.md", "start_line": 6, "end_line": 9}, credentials)
    show("read_node_lines (skill file)", text, data)
    assert data["lines"] == ["# Lead qualification", "", "1. Check company size", "2. Score 1-10"]

    text, data = run_tool(GetNodeTool, {"node": skill_slug, "type": "skill"}, credentials)
    show("get_node (skill)", text, data)
    assert {"SKILL.md", "references/checklist.md"} <= {f["path"] for f in data["files"]}

    # Tree, type filter, parent filter, name search.
    text, data = run_tool(ListNodesTool, {"parent": folder_slug}, credentials)
    show("list_nodes (parent slug)", text, data)
    assert doc_id in [n["id"] for n in data["nodes"]]
    text, data = run_tool(ListNodesTool, {"parent": folder_id, "type": "doc"}, credentials)
    show("list_nodes (parent + type)", text, data)
    assert {n["type"] for n in data["nodes"]} == {"doc"} and all(n["parentId"] == folder_id for n in data["nodes"])
    assert data["count"] == 2
    text, data = run_tool(ListNodesTool, {"type": "skill"}, credentials)
    show("list_nodes (type skill)", text, data)
    assert skill_id in [n["id"] for n in data["nodes"]]
    text, data = run_tool(ListNodesTool, {"depth": 1}, credentials)
    show("list_nodes (tree depth 1)", text, data)
    assert folder_id in [n["id"] for n in data["nodes"]]

    text, data = run_tool(SearchNodesTool, {"query": stamp, "type": "doc"}, credentials)
    show("search_nodes", text, data)
    assert {n["id"] for n in data["nodes"]} >= {doc_id}
    text, data = run_tool(SearchNodesTool, {"query": f"Folder {stamp}"}, credentials)
    assert [n["id"] for n in data["nodes"]] == [folder_id]

    # Playbooks: skill + custom prompt.
    text, data = run_tool(SearchPlaybooksTool, {"queries": f'["qualify lead {stamp}", "线索"]', "kind": "skill"}, credentials)
    show("search_playbooks (broadened)", text, data)
    assert skill_id in [i["nodeId"] for i in data["items"]] and data["broadened"] is True
    text, data = run_tool(SearchPlaybooksTool, {"queries": f"weekly report {stamp}\n写周报", "near_node": folder_slug, "locale": "zh-CN"}, credentials)
    show("search_playbooks (prompt)", text, data)
    prompt = next(i for i in data["items"] if i["kind"] == "prompt" and i["nodeId"] == folder_id)
    assert prompt["key"] == f"weekly-{stamp}"

    text, data = run_tool(GetPlaybookTool, {"node": skill_slug}, credentials)
    show("get_playbook (skill by slug)", text, data)
    assert data["kind"] == "skill" and "3. Check budget" in data["content"]
    text, data = run_tool(GetPlaybookTool, {"node": folder_id, "key": prompt["key"], "locale": "zh-CN"}, credentials)
    show("get_playbook (prompt)", text, data)
    assert "把这个文件夹总结成周报" in data["content"]
    with pytest.raises(Exception, match=f"Prompt keys there: weekly-{stamp}"):
        run_tool(GetPlaybookTool, {"node": folder_id, "key": "nope"}, credentials)


def test_server_quirks_the_node_tools_guard_against(credentials, stamp, scratch_skill):
    """Raw API behaviour the guards exist for. If one of these starts failing, the
    server fixed it and the matching workaround (see core.py) can be revisited."""
    client = BusabaseClient.from_credentials(credentials)
    folder = client.node_change_request(
        [{"kind": "create", "nodeType": "folder", "slug": f"dify-it-quirks-{stamp}", "name": f"Dify IT Quirks {stamp}"}],
        "Create folder for the server-quirk checks",
    )
    folder_id = folder["primaryOperation"]["nodeId"]
    doc = client.create_doc(slug=f"dify-it-quirk-doc-{stamp}", name="Quirk Doc", body="original", parent_node_id=folder_id)
    doc_id = doc["node"]["id"]

    # 1. nodes.list: a parentId slug is not an error — it returns nothing.
    assert client.list_nodes(parent_id=f"dify-it-quirks-{stamp}", depth=1) == []
    assert [n["id"] for n in client.list_nodes(parent_id=folder_id, depth=1)] == [doc_id]
    # 2. nodes.list: with `types`, `parentId` is ignored (nodes outside the folder come back).
    outside = client.list_nodes(parent_id=folder_id, types=["skill"])
    assert scratch_skill["id"] in [n["id"] for n in outside]
    # 3. docs.create: a slug already used in the SAME folder returns the existing doc, unchanged.
    again = client.create_doc(slug=f"dify-it-quirk-doc-{stamp}", name="Other", body="new", parent_node_id=folder_id)
    assert again.get("materialized") is True and again["node"]["id"] == doc_id and again["body"] == "original"
    # 4. nodes.updateContent / playbooks.get take an id only; nodes.readLines answers a skill with 404.
    for call in (
        lambda: client.update_node_content(f"dify-it-quirk-doc-{stamp}", {"kind": "doc", "body": "x"}, "slug"),
        lambda: client.get_playbook("skill", scratch_skill["slug"]),
        lambda: client.read_node_lines(scratch_skill["id"], 1, 5),
    ):
        with pytest.raises(Exception, match="404"):
            call()
    # 5. fileTrees `update` of a path that does not exist silently creates it.
    response = client.file_change_request(
        scratch_skill["id"], [{"kind": "update", "path": f"ghost-{stamp}.md", "content": "boo"}], "Quirk check: update a missing path"
    )
    assert response["status"] == "merged"
    assert f"ghost-{stamp}.md" in [f["path"] for f in client.list_files(scratch_skill["id"])]
    # 6. playbooks.search: a misspelled `query` key is ignored and the call browses everything.
    browse = client.search_playbooks({"query": "zzz-no-such-playbook"})
    assert browse["items"], "an unknown key fell back to browse mode"
