"""Every tool through `Tool.invoke` (the runtime's entry point) against a faked Busabase."""

import pytest

from busabase_dify.client import BusabaseError
from tests.fixtures import BASE, IN_REVIEW_UPDATE, change_request_history, merged_record, record
from tests.helpers import run_tool
from tools.create_record import CreateRecordTool
from tools.find_records import FindRecordsTool
from tools.get_record import GetRecordTool
from tools.list_bases import ListBasesTool
from tools.list_records import ListRecordsTool
from tools.search_workspace import SearchWorkspaceTool
from tools.update_record import UpdateRecordTool

BASE_PATH = f"/api/v1/bases/{BASE['id']}"


def test_auth_and_space_headers(fake):
    fake.on("GET", "/api/v1/bases", [BASE])
    run_tool(ListBasesTool, {})
    request = fake.last("GET", "/api/v1/bases")
    assert str(request.url) == "https://bb.example.com/api/v1/bases?status=active"
    assert request.headers["authorization"] == "Bearer bb_test_key"
    assert request.headers["x-busabase-space"] == "spc_1"
    assert request.headers["user-agent"].startswith("dify-plugin-busabase/")


def test_open_local_server_sends_no_auth_headers(fake):
    fake.on("GET", "/api/v1/bases", [])
    text, data = run_tool(ListBasesTool, {}, {"base_url": "http://localhost:15419"})
    request = fake.last("GET", "/api/v1/bases")
    assert "authorization" not in request.headers
    assert "x-busabase-space" not in request.headers
    assert data == {"bases": [], "count": 0}
    assert text == "No Bases in this space yet."


def test_list_bases_shapes_fields(fake):
    fake.on("GET", "/api/v1/bases", [BASE])
    text, data = run_tool(ListBasesTool, {})
    assert data["count"] == 1
    status = data["bases"][0]["fields"][1]
    assert status == {"slug": "status", "name": "Status", "type": "select", "required": False, "choices": ["New", "Won"]}
    assert "Dify Leads (slug: dify-leads" in text


def test_list_records_resolves_slug_to_id(fake):
    # records.list silently returns nothing for a slug — the tool must send the id.
    fake.on("GET", "/api/v1/bases/dify-leads", BASE)
    fake.on("GET", "/api/v1/records", {"records": [record()], "nextCursor": "cur_2"})
    text, data = run_tool(ListRecordsTool, {"base": "dify-leads", "limit": 5.0, "cursor": "cur_1"})
    params = fake.last("GET", "/api/v1/records").url.params
    assert params["baseId"] == BASE["id"]
    assert params["limit"] == "5"
    assert params["cursor"] == "cur_1"
    assert params["status"] == "active"
    assert data["nextCursor"] == "cur_2"
    assert data["records"][0]["fields"] == {"name": "Probe Co", "score": 5}
    assert "More records exist" in text


def test_list_records_falls_back_to_base_name(fake):
    fake.on("GET", "/api/v1/bases", [BASE])
    fake.on("GET", BASE_PATH, BASE)
    fake.on("GET", "/api/v1/records", {"records": [], "nextCursor": None})
    _, data = run_tool(ListRecordsTool, {"base": "dify leads"})
    assert data["base"]["id"] == BASE["id"]


def test_unknown_base_lists_available(fake):
    fake.on("GET", "/api/v1/bases", [BASE])
    with pytest.raises(BusabaseError, match=r"No Base matches 'Nope'.*Dify Leads \(dify-leads\)"):
        run_tool(ListRecordsTool, {"base": "Nope"})


def test_find_records_exact_match(fake):
    fake.on("GET", "/api/v1/bases/dify-leads", BASE)
    fake.on("GET", "/api/v1/records/search", [record()])
    text, data = run_tool(FindRecordsTool, {"base": "dify-leads", "field": "Name", "value": "Probe Co"})
    params = fake.last("GET", "/api/v1/records/search").url.params
    assert dict(params) == {"baseId": BASE["id"], "fieldSlug": "name", "valueText": "Probe Co", "limit": "20"}
    assert data["count"] == 1
    assert "where name = 'Probe Co'" in text


def test_get_record_by_id(fake):
    fake.on("GET", "/api/v1/records/get", record())
    text, data = run_tool(GetRecordTool, {"record_id": "recmve1abzlnki6zwy"})
    assert dict(fake.last("GET", "/api/v1/records/get").url.params) == {"recordId": "recmve1abzlnki6zwy"}
    assert data["record"]["id"] == "recmve1abzlnki6zwy"
    assert "score: 5" in text


def test_get_record_by_field_value(fake):
    fake.on("GET", "/api/v1/bases/dify-leads", BASE)
    fake.on("GET", "/api/v1/records/get", record())
    run_tool(GetRecordTool, {"base": "dify-leads", "field": "name", "value": "Probe Co"})
    params = dict(fake.last("GET", "/api/v1/records/get").url.params)
    assert params == {"baseId": BASE["id"], "fieldSlug": "name", "valueText": "Probe Co"}


def test_get_record_requires_a_selector(fake):
    with pytest.raises(BusabaseError, match="record_id"):
        run_tool(GetRecordTool, {"base": "dify-leads"})


def test_get_record_not_found_message(fake):
    fake.on("GET", "/api/v1/records/get", {"error": "Record not found: nope", "code": "NOT_FOUND"}, status=404)
    with pytest.raises(BusabaseError, match="Busabase API error 404: Record not found: nope"):
        run_tool(GetRecordTool, {"record_id": "nope"})


def test_create_record_omits_auto_merge_and_maps_names(fake):
    fake.on("GET", "/api/v1/bases/dify-leads", BASE)
    fake.on("POST", f"{BASE_PATH}/change-requests", merged_record())
    fake.on("GET", "/api/v1/records/recmve1abzlnki6zwy/change-requests", change_request_history())
    text, data = run_tool(
        CreateRecordTool,
        {"base": "dify-leads", "fields": '{"Name": "Probe Co", "score": 5}', "message": "Add Probe Co — test"},
    )
    body = fake.body(fake.last("POST", f"{BASE_PATH}/change-requests"))
    assert body == {"fields": {"name": "Probe Co", "score": 5}, "message": "Add Probe Co — test"}
    assert "autoMerge" not in body
    assert data["status"] == "merged"
    assert data["changeRequestId"] == "crqmve1abyedammlfg"
    assert data["message"] == "Add Probe Co — test"
    assert text.startswith("Merged.")


def test_create_record_default_message_and_idempotency_key(fake):
    fake.on("GET", "/api/v1/bases/dify-leads", BASE)
    fake.on("POST", f"{BASE_PATH}/change-requests", merged_record())
    fake.on("GET", "/api/v1/records/recmve1abzlnki6zwy/change-requests", change_request_history())
    run_tool(CreateRecordTool, {"base": "dify-leads", "fields": {"name": "Acme"}, "idempotency_key": "k1"})
    body = fake.body(fake.last("POST", f"{BASE_PATH}/change-requests"))
    assert body["message"] == "Add Acme via Dify"
    assert body["idempotencyKey"] == "k1"


def test_create_record_rejects_unknown_field_before_writing(fake):
    fake.on("GET", "/api/v1/bases/dify-leads", BASE)
    with pytest.raises(BusabaseError, match="no field 'Company'"):
        run_tool(CreateRecordTool, {"base": "dify-leads", "fields": '{"Company": "Acme"}'})
    assert not [r for r in fake.requests if r.method == "POST"]


def test_create_record_surfaces_validation_errors(fake):
    fake.on("GET", "/api/v1/bases/dify-leads", BASE)
    fake.on(
        "POST",
        f"{BASE_PATH}/change-requests",
        {
            "error": "Invalid field value: Score must be a number",
            "code": "BAD_REQUEST",
            "data": {"errors": [{"slug": "score", "type": "number", "message": "Score must be a number"}]},
        },
        status=400,
    )
    with pytest.raises(BusabaseError, match="400: Invalid field value: Score must be a number"):
        run_tool(CreateRecordTool, {"base": "dify-leads", "fields": '{"score": "abc"}'})


def test_update_record_in_review(fake):
    fake.on("GET", "/api/v1/records/get", record())
    fake.on("POST", "/api/v1/records/recmve1abzlnki6zwy/change-requests", IN_REVIEW_UPDATE)
    text, data = run_tool(
        UpdateRecordTool, {"record_id": "recmve1abzlnki6zwy", "fields": '{"Score": 11}', "message": "Bump score"}
    )
    body = fake.body(fake.last("POST", "/api/v1/records/recmve1abzlnki6zwy/change-requests"))
    assert body == {"operation": "update", "fields": {"score": 11}, "message": "Bump score"}
    assert data["status"] == "in_review"
    assert data["merged"] is False
    assert data["changeRequestId"] == "crqmve1aub58pq6aps"
    assert data["recordId"] == "recmve1abzlnki6zwy"
    assert "Submitted for review" in text


def test_update_record_default_message(fake):
    fake.on("GET", "/api/v1/records/get", record())
    fake.on("POST", "/api/v1/records/recmve1abzlnki6zwy/change-requests", merged_record(head="cmt2"))
    fake.on(
        "GET",
        "/api/v1/records/recmve1abzlnki6zwy/change-requests",
        change_request_history(head="cmt2", cr_id="crq2"),
    )
    _, data = run_tool(UpdateRecordTool, {"record_id": "recmve1abzlnki6zwy", "fields": '{"score": 7}'})
    body = fake.body(fake.last("POST", "/api/v1/records/recmve1abzlnki6zwy/change-requests"))
    assert body["message"] == "Update Probe Co via Dify"
    assert data["changeRequestId"] == "crq2"


def test_search_workspace_body(fake):
    fake.on("GET", "/api/v1/bases/dify-leads", BASE)
    fake.on(
        "POST",
        "/api/v1/grep",
        {
            "matches": [
                {"source": "records", "baseId": BASE["id"], "baseSlug": "dify-leads", "recordId": "rec1", "fieldSlug": "name", "line": 1, "column": 1, "text": "Probe Co", "before": [], "after": []}
            ],
            "coverage": {"records": {"scanned": 2, "errored": [], "notReached": 0}},
            "truncated": False,
        },
    )
    text, data = run_tool(
        SearchWorkspaceTool, {"pattern": "probe", "base": "dify-leads", "case_insensitive": True, "max_matches": 10}
    )
    body = fake.body(fake.last("POST", "/api/v1/grep"))
    assert body == {
        "pattern": "probe",
        "maxMatches": 10,
        "flags": "i",
        "sources": ["records"],
        "scope": {"records": {"baseIds": [BASE["id"]]}},
    }
    assert data["count"] == 1
    assert "record rec1 in dify-leads · name" in text


def test_search_workspace_source_filter(fake):
    fake.on("POST", "/api/v1/grep", {"matches": [], "coverage": {}, "truncated": True})
    text, data = run_tool(SearchWorkspaceTool, {"pattern": "x", "source": "files"})
    body = fake.body(fake.last("POST", "/api/v1/grep"))
    assert body == {"pattern": "x", "maxMatches": 50, "sources": ["files"]}
    assert data["truncated"] is True
    assert "truncated" in text
