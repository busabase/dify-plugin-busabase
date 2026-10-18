"""The node / doc / file / playbook tools through `Tool.invoke` against a faked Busabase."""

import httpx
import pytest

from busabase_dify.client import BusabaseError
from tests.fixtures import BASE
from tests.helpers import run_tool
from tests.node_fixtures import (
    BASE_DETAIL,
    CR_LIST_FOR_NEW_DOC,
    DOC,
    DOC_CREATE_IN_REVIEW,
    DOC_CREATE_MERGED,
    DOC_DETAIL,
    DOC_ID,
    EMPTY_PLAYBOOKS,
    FILES,
    FOLDER_DETAIL,
    FOLDER_ID,
    HASH,
    PLAYBOOK_SEARCH,
    PROMPT_PLAYBOOK,
    READ_FILE,
    SKILL,
    SKILL_DETAIL,
    SKILL_ID,
    SKILL_MD,
    SKILL_PLAYBOOK,
    TREE,
    by_type,
    change_request,
    node,
    not_found,
)
from tools.create_doc import CreateDocTool
from tools.create_folder import CreateFolderTool
from tools.get_node import GetNodeTool
from tools.get_playbook import GetPlaybookTool
from tools.list_files import ListFilesTool
from tools.list_nodes import ListNodesTool
from tools.read_file import ReadFileTool
from tools.read_node_lines import ReadNodeLinesTool
from tools.search_nodes import SearchNodesTool
from tools.search_playbooks import SearchPlaybooksTool
from tools.update_doc import UpdateDocTool
from tools.write_file import WriteFileTool

V1 = "/api/v1"


def posts(fake):
    return [r for r in fake.requests if r.method in ("POST", "PUT")]


# ── list_nodes / search_nodes ──────────────────────────────────────────────


def test_list_nodes_tree_unwraps_root_and_flags_deeper_folders(fake):
    fake.on("GET", f"{V1}/nodes", TREE)
    text, data = run_tool(ListNodesTool, {})
    assert dict(fake.last("GET", f"{V1}/nodes").url.params) == {"depth": "2"}
    assert [(n["slug"], n["depth"]) for n in data["nodes"]] == [("probe-folder", 0), ("probe-doc", 1), ("sub", 1), ("d-root", 0)]
    assert data["nodes"][2]["hasMoreChildren"] is True
    assert "  - [doc] Probe Doc (slug: probe-doc" in text
    assert "(+ more inside)" in text


def test_list_nodes_by_type_is_flat(fake):
    fake.on("GET", f"{V1}/nodes", [DOC, node("nodrootdoc", "doc", "d-root", "Root Doc")])
    text, data = run_tool(ListNodesTool, {"type": "doc"})
    assert fake.last("GET", f"{V1}/nodes").url.params.get_list("types") == ["doc"]
    assert data["count"] == 2
    assert text.startswith("2 doc node(s) in the workspace")


def test_list_nodes_parent_slug_is_resolved_to_an_id(fake):
    # nodes.list returns [] for a parentId slug — the tool must send the id.
    fake.on("GET", f"{V1}/nodes/probe-folder", FOLDER_DETAIL)
    fake.on("GET", f"{V1}/nodes", [DOC, SKILL])
    _, data = run_tool(ListNodesTool, {"parent": "probe-folder", "depth": 1})
    assert dict(fake.last("GET", f"{V1}/nodes").url.params) == {"parentId": FOLDER_ID, "depth": "1"}
    assert data["parent"]["id"] == FOLDER_ID
    assert data["count"] == 2


def test_list_nodes_type_and_parent_filters_client_side(fake):
    # With `types` set the server ignores `parentId`, so the tool walks the subtree instead.
    fake.on("GET", f"{V1}/nodes/{FOLDER_ID}", FOLDER_DETAIL)
    fake.on("GET", f"{V1}/nodes", [DOC, {**node("nodsub", "folder", "sub", "Sub"), "children": [node("nodd2", "doc", "deep", "Deep Doc", parent="nodsub")]}, SKILL])
    _, data = run_tool(ListNodesTool, {"parent": FOLDER_ID, "type": "doc"})
    params = fake.last("GET", f"{V1}/nodes").url.params
    assert "types" not in params
    assert dict(params) == {"parentId": FOLDER_ID, "depth": "5"}
    assert [n["slug"] for n in data["nodes"]] == ["probe-doc", "deep"]


def test_list_nodes_parent_must_be_a_folder(fake):
    fake.on("GET", f"{V1}/nodes/probe-doc", DOC_DETAIL)
    with pytest.raises(BusabaseError, match="'probe-doc' is a doc .*not a folder"):
        run_tool(ListNodesTool, {"parent": "probe-doc"})


def test_list_nodes_rejects_unknown_type(fake):
    with pytest.raises(BusabaseError, match="`type` must be one of: all, folder, doc"):
        run_tool(ListNodesTool, {"type": "docs"})


def test_list_nodes_caps_output(fake):
    fake.on("GET", f"{V1}/nodes", [node(f"nod{i}", "doc", f"d{i}", f"D{i}") for i in range(30)])
    text, data = run_tool(ListNodesTool, {"type": "doc", "limit": 5})
    assert data["count"] == 5 and data["total"] == 30 and data["truncated"] is True
    assert "25 more not shown" in text


def test_search_nodes_filters_type_after_fetching_the_max(fake):
    fake.on(
        "GET",
        f"{V1}/nodes/search",
        [
            {"id": "nodf", "type": "folder", "name": "Probe Folder", "slug": "probe-folder", "path": "/folder/probe-folder", "updatedAt": "x", "icon": None},
            {"id": DOC_ID, "type": "doc", "name": "Probe Doc", "slug": "probe-doc", "path": "/doc/probe-doc", "updatedAt": "x", "icon": None},
        ],
    )
    text, data = run_tool(SearchNodesTool, {"query": "probe", "type": "doc", "limit": 5})
    assert dict(fake.last("GET", f"{V1}/nodes/search").url.params) == {"query": "probe", "limit": "50"}
    assert [n["id"] for n in data["nodes"]] == [DOC_ID]
    assert "[doc] Probe Doc" in text


def test_search_nodes_no_hit_points_to_content_search(fake):
    fake.on("GET", f"{V1}/nodes/search", [])
    text, _ = run_tool(SearchNodesTool, {"query": "zzz"})
    assert "search_workspace" in text
    text, _ = run_tool(SearchNodesTool, {"query": "zzz", "type": "skill"})
    assert text.startswith("No skill node name")


# ── get_node / resolution ──────────────────────────────────────────────────


def test_get_node_doc_truncates_long_bodies(fake):
    long_body = "\n".join(f"line {i}" for i in range(1, 2001))
    fake.on("GET", f"{V1}/nodes/probe-doc", {**DOC_DETAIL, "body": long_body})
    text, data = run_tool(GetNodeTool, {"node": "probe-doc", "max_chars": 500})
    assert data["type"] == "doc"
    assert data["bodyTruncated"] is True
    assert len(data["body"]) == 500
    assert data["totalLines"] == 2000
    assert "read_node_lines" in text and f"node {DOC_ID}" in text
    assert "line 1" not in text  # the body is only in the JSON — Dify shows an Agent both messages


def test_get_node_ambiguous_slug_uses_the_type_hint(fake):
    ambiguous = httpx.Response(400, json={"error": 'Slug "probe-doc" exists as doc and folder; pass `type` to choose one.', "code": "BAD_REQUEST"})
    fake.on("GET", f"{V1}/nodes/probe-doc", by_type(**{"": ambiguous, "doc": DOC_DETAIL}))
    _, data = run_tool(GetNodeTool, {"node": "probe-doc", "type": "doc"})
    assert data["node"]["id"] == DOC_ID


def test_get_node_ambiguous_slug_without_type_explains(fake):
    ambiguous = httpx.Response(400, json={"error": 'Slug "probe-doc" exists as doc and folder; pass `type` to choose one.', "code": "BAD_REQUEST"})
    fake.on("GET", f"{V1}/nodes/probe-doc", by_type(**{"": ambiguous}))
    with pytest.raises(BusabaseError, match="exists as doc and folder"):
        run_tool(GetNodeTool, {"node": "probe-doc"})


def test_get_node_by_exact_name(fake):
    fake.on("GET", f"{V1}/nodes/Lead qualification", not_found())
    fake.on("GET", f"{V1}/nodes/search", [{"id": SKILL_ID, "type": "skill", "name": "Lead Qualification", "slug": "lead-qualify", "path": "/skill/lead-qualify", "updatedAt": "x"}])
    fake.on("GET", f"{V1}/nodes/{SKILL_ID}", SKILL_DETAIL)
    text, data = run_tool(GetNodeTool, {"node": "Lead qualification"})
    assert data["fileCount"] == 3
    assert [f["path"] for f in data["files"]] == ["SKILL.md", "references/checklist.md", "skill.json"]
    assert "Open one with read_file" in text


def test_get_node_unknown_lists_similar(fake):
    fake.on("GET", f"{V1}/nodes/Lead", not_found())
    fake.on("GET", f"{V1}/nodes/search", [{"id": SKILL_ID, "type": "skill", "name": "Lead Qualification", "slug": "lead-qualify", "path": "/skill/lead-qualify", "updatedAt": "x"}])
    with pytest.raises(BusabaseError, match=r"No node is named exactly 'Lead'\. Similar: skill 'Lead Qualification'"):
        run_tool(GetNodeTool, {"node": "Lead"})


def test_get_node_folder_and_base(fake):
    fake.on("GET", f"{V1}/nodes/{FOLDER_ID}", FOLDER_DETAIL)
    text, data = run_tool(GetNodeTool, {"node": FOLDER_ID})
    assert data["childCount"] == 2 and data["children"][0]["id"] == DOC_ID
    assert "- [skill] Lead Qualification" in text

    fake.on("GET", f"{V1}/nodes/dify-leads", BASE_DETAIL)
    fake.on("GET", f"{V1}/bases/{BASE['id']}", BASE)
    text, data = run_tool(GetNodeTool, {"node": "dify-leads"})
    assert [f["slug"] for f in data["base"]["fields"]] == ["name", "status", "score"]
    assert "list_records" in text


# ── read_node_lines ────────────────────────────────────────────────────────


def test_read_node_lines_doc(fake):
    fake.on("GET", f"{V1}/nodes/probe-doc", DOC_DETAIL)
    fake.on("GET", f"{V1}/nodes/{DOC_ID}/lines", {"lines": ["", "line two"], "startLine": 2, "endLine": 3, "totalLines": 5, "truncated": False})
    text, data = run_tool(ReadNodeLinesTool, {"node": "probe-doc", "start_line": 2, "end_line": 3})
    assert dict(fake.last("GET", f"{V1}/nodes/{DOC_ID}/lines").url.params) == {"startLine": "2", "endLine": "3"}
    assert data["lines"] == ["", "line two"] and data["hasMore"] is True
    assert "Lines 2–3 of 5" in text and "Lines 4–5 remain" in text and "line two" not in text


def test_read_node_lines_caps_range_and_checks_order(fake):
    fake.on("GET", f"{V1}/nodes/{DOC_ID}", DOC_DETAIL)
    fake.on("GET", f"{V1}/nodes/{DOC_ID}/lines", {"lines": [], "startLine": 1, "endLine": 1, "totalLines": 0, "truncated": False})
    run_tool(ReadNodeLinesTool, {"node": DOC_ID, "start_line": 1, "end_line": 99999})
    assert fake.last("GET", f"{V1}/nodes/{DOC_ID}/lines").url.params["endLine"] == "2000"
    with pytest.raises(BusabaseError, match="end_line"):
        run_tool(ReadNodeLinesTool, {"node": DOC_ID, "start_line": 5, "end_line": 2})


def test_read_node_lines_file_in_a_skill(fake):
    # nodes.readLines 404s ("Node not found") for a skill; the tool slices the file instead.
    fake.on("GET", f"{V1}/nodes/{SKILL_ID}", SKILL_DETAIL)
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files/SKILL.md", READ_FILE)
    text, data = run_tool(ReadNodeLinesTool, {"node": SKILL_ID, "path": "SKILL.md", "start_line": 6, "end_line": 6})
    assert data["lines"] == ["# Lead qualification"] and data["totalLines"] == len(SKILL_MD.splitlines())
    assert "lines[0] is line 6" in text
    with pytest.raises(BusabaseError, match="give `path`.*SKILL.md, references/checklist.md"):
        run_tool(ReadNodeLinesTool, {"node": SKILL_ID})


def test_read_node_lines_rejects_types_without_lines(fake):
    fake.on("GET", f"{V1}/nodes/{FOLDER_ID}", FOLDER_DETAIL)
    with pytest.raises(BusabaseError, match="is a folder"):
        run_tool(ReadNodeLinesTool, {"node": FOLDER_ID})


# ── create_doc / create_folder ─────────────────────────────────────────────


def test_create_doc_resolves_parent_derives_slug_and_omits_auto_merge(fake):
    fake.on("GET", f"{V1}/nodes/probe-folder", FOLDER_DETAIL)
    fake.on("GET", f"{V1}/nodes/launch-plan", not_found())  # slug is free
    fake.on("POST", f"{V1}/docs", DOC_CREATE_MERGED)
    fake.on("GET", f"{V1}/change-requests", CR_LIST_FOR_NEW_DOC)
    text, data = run_tool(CreateDocTool, {"name": "Launch Plan", "body": "# Plan", "parent": "probe-folder"})
    assert fake.last("GET", f"{V1}/nodes/launch-plan").url.params["type"] == "doc"
    body = fake.body(fake.last("POST", f"{V1}/docs"))
    assert body == {"slug": "launch-plan", "name": "Launch Plan", "body": "# Plan", "description": "", "parentNodeId": FOLDER_ID}
    assert "autoMerge" not in body
    assert fake.last("GET", f"{V1}/change-requests").url.params["affectsNodeId"] == "nodnewdoc"
    assert data["status"] == "merged" and data["merged"] is True
    assert data["nodeId"] == "nodnewdoc" and data["changeRequestId"] == "crqnewdoc"
    assert text.startswith("Merged. Created doc 'Launch Plan' (slug: launch-plan")


def test_create_doc_at_root_with_cjk_name_gets_a_generated_slug(fake):
    fake.on("POST", f"{V1}/docs", lambda r: {**DOC_CREATE_MERGED, "node": {**DOC_CREATE_MERGED["node"], "name": "周报"}, "body": ""})
    fake.on("GET", f"{V1}/change-requests", CR_LIST_FOR_NEW_DOC)
    _, data = run_tool(CreateDocTool, {"name": "周报"})
    body = fake.body(fake.last("POST", f"{V1}/docs"))
    assert "parentNodeId" not in body
    assert body["slug"].startswith("doc-")
    assert data["parent"] is None


def test_create_doc_explicit_slug_taken_fails_before_writing(fake):
    fake.on("GET", f"{V1}/nodes/probe-doc", DOC_DETAIL)
    with pytest.raises(BusabaseError, match="A doc with slug 'probe-doc' already exists.*update_doc"):
        run_tool(CreateDocTool, {"name": "Probe Doc", "slug": "probe-doc"})
    assert not posts(fake)


def test_create_doc_derived_slug_gets_a_suffix(fake):
    fake.on("GET", f"{V1}/nodes/probe-doc", DOC_DETAIL)
    fake.on("GET", f"{V1}/nodes/probe-doc-2", not_found())
    fake.on("POST", f"{V1}/docs", {**DOC_CREATE_MERGED, "node": {**DOC_CREATE_MERGED["node"], "name": "Probe Doc"}, "body": "x"})
    fake.on("GET", f"{V1}/change-requests", CR_LIST_FOR_NEW_DOC)
    _, data = run_tool(CreateDocTool, {"name": "Probe Doc", "body": "x"})
    assert fake.body(fake.last("POST", f"{V1}/docs"))["slug"] == "probe-doc-2"
    assert data["slug"] == "probe-doc-2"


def test_create_doc_rejects_bad_slug(fake):
    with pytest.raises(BusabaseError, match="lowercase letters, digits and hyphens"):
        run_tool(CreateDocTool, {"name": "X", "slug": "Bad Slug"})


def test_create_doc_detects_the_server_returning_an_existing_doc(fake):
    # Same-folder duplicate slug: the server answers materialized:true with the OLD doc.
    fake.on("GET", f"{V1}/nodes/launch-plan", not_found())
    fake.on("POST", f"{V1}/docs", {**DOC_CREATE_MERGED, "body": "old body"})
    with pytest.raises(BusabaseError, match="returned an existing doc.*nothing was written"):
        run_tool(CreateDocTool, {"name": "Launch Plan", "body": "new body"})


def test_create_doc_in_review(fake):
    fake.on("GET", f"{V1}/nodes/launch-plan", not_found())
    fake.on("POST", f"{V1}/docs", DOC_CREATE_IN_REVIEW)
    text, data = run_tool(CreateDocTool, {"name": "Launch Plan", "body": "# Plan"})
    assert data["status"] == "in_review" and data["merged"] is False
    assert data["changeRequestId"] == "crqreviewdoc" and data["nodeId"] is None
    assert text.startswith("Submitted for review. Change request crqreviewdoc proposing a new doc 'Launch Plan'")


def test_create_folder(fake):
    fake.on("GET", f"{V1}/nodes/research", not_found())
    fake.on("POST", f"{V1}/nodes/change-requests", change_request("crqfolder", "merged", "node_create", "nodnewfolder"))
    text, data = run_tool(CreateFolderTool, {"name": "Research", "message": "Create Research folder for notes"})
    body = fake.body(fake.last("POST", f"{V1}/nodes/change-requests"))
    assert body == {
        "operations": [{"kind": "create", "nodeType": "folder", "slug": "research", "name": "Research", "description": ""}],
        "message": "Create Research folder for notes",
    }
    assert data["status"] == "merged" and data["nodeId"] == "nodnewfolder" and data["changeRequestId"] == "crqfolder"
    assert "Created folder 'Research'" in text


def test_create_folder_in_review_and_default_message(fake):
    fake.on("GET", f"{V1}/nodes/{FOLDER_ID}", FOLDER_DETAIL)
    fake.on("GET", f"{V1}/nodes/research", not_found())
    fake.on("POST", f"{V1}/nodes/change-requests", change_request("crqf2", "in_review", "node_create", None))
    _, data = run_tool(CreateFolderTool, {"name": "Research", "parent": FOLDER_ID})
    body = fake.body(fake.last("POST", f"{V1}/nodes/change-requests"))
    assert body["operations"][0]["parentNodeId"] == FOLDER_ID
    assert body["message"] == "Create folder Research via Dify"
    assert data["status"] == "in_review" and data["nodeId"] is None


# ── update_doc ─────────────────────────────────────────────────────────────


def test_update_doc_append_reads_then_writes_by_id(fake):
    # nodes.updateContent 404s for a slug — the PUT must use the id.
    fake.on("GET", f"{V1}/nodes/probe-doc", DOC_DETAIL)
    fake.on("PUT", f"{V1}/nodes/{DOC_ID}/content", change_request())
    text, data = run_tool(UpdateDocTool, {"doc": "probe-doc", "text": "line three"})
    body = fake.body(fake.last("PUT", f"{V1}/nodes/{DOC_ID}/content"))
    assert body == {"content": {"kind": "doc", "body": "# Probe\n\nline two\nline three"}, "message": "Append to Probe Doc via Dify"}
    assert "autoMerge" not in body
    assert data["status"] == "merged" and data["changeRequestId"] == "crqmveg8puygo1oza0" and data["mode"] == "append"
    assert text.startswith("Merged. Appended to doc 'Probe Doc'")


def test_update_doc_replace_in_review(fake):
    fake.on("GET", f"{V1}/nodes/{DOC_ID}", DOC_DETAIL)
    fake.on("PUT", f"{V1}/nodes/{DOC_ID}/content", change_request("crqrev", "in_review"))
    text, data = run_tool(UpdateDocTool, {"doc": DOC_ID, "text": "# New", "mode": "replace", "message": "Rewrite intro"})
    assert fake.body(fake.last("PUT", f"{V1}/nodes/{DOC_ID}/content"))["content"]["body"] == "# New"
    assert data["status"] == "in_review" and data["nodeId"] == DOC_ID
    assert "Submitted for review" in text


def test_update_doc_unchanged_sends_nothing(fake):
    fake.on("GET", f"{V1}/nodes/{DOC_ID}", DOC_DETAIL)
    _, data = run_tool(UpdateDocTool, {"doc": DOC_ID, "text": DOC_DETAIL["body"], "mode": "replace"})
    assert data["status"] == "unchanged"
    assert not posts(fake)


def test_update_doc_rejects_a_skill(fake):
    fake.on("GET", f"{V1}/nodes/lead-qualify", SKILL_DETAIL)
    with pytest.raises(BusabaseError, match="is a skill.*write_file"):
        run_tool(UpdateDocTool, {"doc": "lead-qualify", "text": "x"})


# ── list_files / read_file / write_file ────────────────────────────────────


def test_list_files_with_prefix(fake):
    fake.on("GET", f"{V1}/nodes/lead-qualify", SKILL_DETAIL)
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files", FILES)
    text, data = run_tool(ListFilesTool, {"node": "lead-qualify", "prefix": "references/"})
    assert [f["path"] for f in data["files"]] == ["references/checklist.md"]
    assert data["node"]["id"] == SKILL_ID
    assert "- references/checklist.md (27 bytes)" in text


def test_list_files_rejects_a_doc(fake):
    fake.on("GET", f"{V1}/nodes/{DOC_ID}", DOC_DETAIL)
    with pytest.raises(BusabaseError, match="is a doc .*not a skill or drive or airapp"):
        run_tool(ListFilesTool, {"node": DOC_ID})


def test_read_file(fake):
    fake.on("GET", f"{V1}/nodes/{SKILL_ID}", SKILL_DETAIL)
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files/references/checklist.md", {**READ_FILE, "path": "references/checklist.md", "content": "- size\n"})
    text, data = run_tool(ReadFileTool, {"node": SKILL_ID, "path": "/references/checklist.md"})
    assert data["content"] == "- size\n" and data["contentHash"] == HASH
    assert "references/checklist.md in skill 'Lead Qualification'" in text and "- size" not in text


def test_read_file_missing_lists_files(fake):
    fake.on("GET", f"{V1}/nodes/{SKILL_ID}", SKILL_DETAIL)
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files/nope.md", not_found("Skill file not found: nope.md"))
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files", FILES)
    with pytest.raises(BusabaseError, match="No file 'nope.md'.*Files: SKILL.md, references/checklist.md, skill.json"):
        run_tool(ReadFileTool, {"node": SKILL_ID, "path": "nope.md"})


def test_read_file_binary_returns_absolute_url(fake):
    fake.on("GET", f"{V1}/nodes/{SKILL_ID}", SKILL_DETAIL)
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files/logo.png", {**READ_FILE, "path": "logo.png", "encoding": "url", "content": "", "mimeType": "image/png"})
    _, data = run_tool(ReadFileTool, {"node": SKILL_ID, "path": "logo.png"})
    assert data["assetUrl"] == "https://bb.example.com/api/storage/attachments/local/blobs/sha256/f3/f3.md"
    assert "content" not in data


def test_write_file_update_sends_base_content_hash(fake):
    fake.on("GET", f"{V1}/nodes/{SKILL_ID}", SKILL_DETAIL)
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files/SKILL.md", READ_FILE)
    fake.on("POST", f"{V1}/file-trees/{SKILL_ID}/change-requests", change_request("crqfile", "merged", "skill_file_update", SKILL_ID, "SKILL.md"))
    text, data = run_tool(WriteFileTool, {"node": SKILL_ID, "path": "SKILL.md", "content": "# v2\n", "message": "Tighten SKILL.md"})
    body = fake.body(fake.last("POST", f"{V1}/file-trees/{SKILL_ID}/change-requests"))
    assert body == {
        "operations": [{"kind": "update", "path": "SKILL.md", "content": "# v2\n", "baseContentHash": HASH}],
        "message": "Tighten SKILL.md",
    }
    assert data["status"] == "merged" and data["operation"] == "updated" and data["changeRequestId"] == "crqfile"
    assert text.startswith("Merged. Updated SKILL.md in skill 'Lead Qualification'")


def test_write_file_creates_a_missing_file(fake):
    fake.on("GET", f"{V1}/nodes/{SKILL_ID}", SKILL_DETAIL)
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files/notes/new.md", not_found("Skill file not found: notes/new.md"))
    fake.on("POST", f"{V1}/file-trees/{SKILL_ID}/change-requests", change_request("crqnew", "in_review", "skill_file_create", SKILL_ID, "notes/new.md"))
    text, data = run_tool(WriteFileTool, {"node": SKILL_ID, "path": "notes/new.md", "content": "hi"})
    body = fake.body(fake.last("POST", f"{V1}/file-trees/{SKILL_ID}/change-requests"))
    assert body == {"operations": [{"kind": "create", "path": "notes/new.md", "content": "hi"}], "message": "Add notes/new.md via Dify"}
    assert data["status"] == "in_review" and data["operation"] == "created"
    assert "Submitted for review" in text


def test_write_file_update_mode_refuses_to_create(fake):
    # The server's `update` of a missing path silently creates it; mode update must not.
    fake.on("GET", f"{V1}/nodes/{SKILL_ID}", SKILL_DETAIL)
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files/SKIL.md", not_found("Skill file not found: SKIL.md"))
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files", FILES)
    with pytest.raises(BusabaseError, match="No file 'SKIL.md'.*to update.*Files: SKILL.md"):
        run_tool(WriteFileTool, {"node": SKILL_ID, "path": "SKIL.md", "content": "x", "mode": "update"})
    assert not posts(fake)


def test_write_file_create_mode_refuses_to_overwrite(fake):
    fake.on("GET", f"{V1}/nodes/{SKILL_ID}", SKILL_DETAIL)
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files/SKILL.md", READ_FILE)
    with pytest.raises(BusabaseError, match="already exists"):
        run_tool(WriteFileTool, {"node": SKILL_ID, "path": "SKILL.md", "content": "x", "mode": "create"})
    assert not posts(fake)


def test_write_file_unchanged_and_conflict(fake):
    fake.on("GET", f"{V1}/nodes/{SKILL_ID}", SKILL_DETAIL)
    fake.on("GET", f"{V1}/file-trees/{SKILL_ID}/files/SKILL.md", READ_FILE)
    _, data = run_tool(WriteFileTool, {"node": SKILL_ID, "path": "SKILL.md", "content": SKILL_MD})
    assert data["status"] == "unchanged" and not posts(fake)

    fake.on("POST", f"{V1}/file-trees/{SKILL_ID}/change-requests", {"error": "Skill file changed before merge: SKILL.md", "code": "CONFLICT"}, status=409)
    with pytest.raises(BusabaseError, match="409.*changed before merge.*Read it again with read_file"):
        run_tool(WriteFileTool, {"node": SKILL_ID, "path": "SKILL.md", "content": "new"})


# ── playbooks ──────────────────────────────────────────────────────────────


def test_search_playbooks_body_and_output(fake):
    fake.on("GET", f"{V1}/nodes/probe-folder", FOLDER_DETAIL)
    fake.on("POST", f"{V1}/playbooks/search", PLAYBOOK_SEARCH)
    text, data = run_tool(
        SearchPlaybooksTool,
        {"queries": '["写周报", "weekly report"]', "kind": "all", "near_node": "probe-folder", "locale": "zh-CN", "limit": 5},
    )
    body = fake.body(fake.last("POST", f"{V1}/playbooks/search"))
    assert body == {"queries": ["写周报", "weekly report"], "limit": 5, "nearNodeId": FOLDER_ID, "locale": "zh-CN"}
    assert [i["kind"] for i in data["items"]] == ["skill", "prompt"]
    assert data["items"][1]["key"] == "weekly-report" and data["items"][0]["path"] == "Probe Folder"
    assert "1. skill 'Lead Qualification'" in text
    assert "2. prompt '写周报' (key: weekly-report)" in text
    assert "get_playbook" in text


def test_search_playbooks_splits_lines_and_broadens_on_no_hit(fake):
    seen = []

    def reply(request):
        body = fake.body(request)
        seen.append(body["queries"])
        return PLAYBOOK_SEARCH if "lead" in body["queries"] else EMPTY_PLAYBOOKS

    fake.on("POST", f"{V1}/playbooks/search", reply)
    _, data = run_tool(SearchPlaybooksTool, {"queries": "qualify lead\n线索评分", "kind": "skill"})
    assert seen == [["qualify lead", "线索评分"], ["qualify", "lead"]]
    assert fake.body(fake.last("POST", f"{V1}/playbooks/search"))["kinds"] == ["skill"]
    assert data["broadened"] is True and data["queries"] == ["qualify", "lead"]


def test_search_playbooks_nothing_fits(fake):
    fake.on("POST", f"{V1}/playbooks/search", EMPTY_PLAYBOOKS)
    text, data = run_tool(SearchPlaybooksTool, {"queries": "invoice"})
    assert data["count"] == 0 and data["broadened"] is False
    assert "Do the work yourself" in text


def test_get_playbook_skill_by_slug(fake):
    # playbooks.get 404s for a slug — the tool resolves it to the id first.
    fake.on("GET", f"{V1}/nodes/lead-qualify", SKILL_DETAIL)
    fake.on("GET", f"{V1}/playbooks/skill/{SKILL_ID}", SKILL_PLAYBOOK)
    text, data = run_tool(GetPlaybookTool, {"node": "lead-qualify"})
    assert data["kind"] == "skill" and data["content"] == SKILL_MD
    assert [f["path"] for f in data["files"]][:2] == ["SKILL.md", "references/checklist.md"]
    assert "never authorises approving or merging" in text and "Check company size" not in text
    assert "Other files in this skill (open with read_file): references/checklist.md, skill.json." in text


def test_get_playbook_prompt_infers_kind_from_key(fake):
    fake.on("GET", f"{V1}/nodes/{FOLDER_ID}", FOLDER_DETAIL)
    fake.on("GET", f"{V1}/playbooks/prompt/{FOLDER_ID}", PROMPT_PLAYBOOK)
    text, data = run_tool(GetPlaybookTool, {"node": FOLDER_ID, "key": "weekly-report", "locale": "zh-CN"})
    assert dict(fake.last("GET", f"{V1}/playbooks/prompt/{FOLDER_ID}").url.params) == {"key": "weekly-report", "locale": "zh-CN"}
    assert data["label"] == "写周报"
    assert text.startswith("Prompt '写周报' on folder 'Probe Folder'")


def test_get_playbook_prompt_unknown_key_lists_keys(fake):
    fake.on("GET", f"{V1}/nodes/{FOLDER_ID}", FOLDER_DETAIL)
    fake.on("GET", f"{V1}/playbooks/prompt/{FOLDER_ID}", not_found('Prompt "nope" not found'))
    fake.on("POST", f"{V1}/playbooks/search", PLAYBOOK_SEARCH)
    with pytest.raises(BusabaseError, match=r"No prompt 'nope'.*Prompt keys there: weekly-report \(写周报\)"):
        run_tool(GetPlaybookTool, {"node": FOLDER_ID, "kind": "prompt", "key": "nope"})
    assert fake.body(fake.last("POST", f"{V1}/playbooks/search"))["inNodeId"] == FOLDER_ID


def test_get_playbook_prompt_needs_a_key(fake):
    with pytest.raises(BusabaseError, match="`key` is required"):
        run_tool(GetPlaybookTool, {"node": FOLDER_ID, "kind": "prompt"})

