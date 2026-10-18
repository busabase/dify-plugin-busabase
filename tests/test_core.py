import pytest

from busabase_dify.client import BusabaseClient, BusabaseError, normalize_base_url
from busabase_dify.core import map_field_keys, parse_fields, resolve_field_slug, write_result
from tests.fixtures import BASE, IN_REVIEW_CREATE, IN_REVIEW_UPDATE, change_request_history, merged_record


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://busabase.com", "https://busabase.com"),
        ("https://busabase.com/", "https://busabase.com"),
        ("https://busabase.com/api/v1/", "https://busabase.com"),
        ("http://localhost:15419/api", "http://localhost:15419"),
        ("", "https://busabase.com"),
        (None, "https://busabase.com"),
    ],
)
def test_normalize_base_url(raw, expected):
    assert normalize_base_url(raw) == expected


def test_normalize_base_url_rejects_missing_scheme():
    with pytest.raises(BusabaseError, match="http"):
        normalize_base_url("busabase.com")


def test_parse_fields_accepts_json_string_and_dict():
    assert parse_fields('{"name": "Acme", "score": 8}') == {"name": "Acme", "score": 8}
    assert parse_fields({"name": "Acme"}) == {"name": "Acme"}


@pytest.mark.parametrize("raw", ["", None, "[1, 2]", "{}", "not json"])
def test_parse_fields_rejects_bad_input(raw):
    with pytest.raises(BusabaseError):
        parse_fields(raw)


def test_resolve_field_slug_by_slug_id_and_localized_name():
    assert resolve_field_slug(BASE, "score") == "score"
    assert resolve_field_slug(BASE, "bsfscore") == "score"
    assert resolve_field_slug(BASE, "Name") == "name"
    assert resolve_field_slug(BASE, "name") == "name"
    assert resolve_field_slug(BASE, "状态") == "status"
    assert resolve_field_slug(BASE, "STATUS") == "status"


def test_map_field_keys_rejects_unknown_field_listing_valid_slugs():
    # The server silently drops unknown keys; the plugin must not.
    with pytest.raises(BusabaseError, match=r"no field 'Company'.*name \(Name\)"):
        map_field_keys(BASE, {"Company": "Acme"})


def test_map_field_keys_rejects_duplicate_after_mapping():
    with pytest.raises(BusabaseError, match="given twice"):
        map_field_keys(BASE, {"name": "a", "Name": "b"})


def test_write_result_merged_looks_up_change_request(fake):
    fake.on("GET", "/api/v1/records/recmve1abzlnki6zwy/change-requests", change_request_history())
    client = BusabaseClient("https://bb.example.com")
    data, text = write_result(client, merged_record(), BASE, "create")
    assert data["status"] == "merged"
    assert data["merged"] is True
    assert data["recordId"] == "recmve1abzlnki6zwy"
    assert data["changeRequestId"] == "crqmve1abyedammlfg"  # matched by headCommitId, not position
    assert data["record"]["fields"] == {"name": "Probe Co", "score": 5}
    assert text.startswith("Merged. Created record 'Probe Co'")


def test_write_result_merged_without_history_still_reports_record(fake):
    fake.on("GET", "/api/v1/records/recmve1abzlnki6zwy/change-requests", {"error": "boom"}, status=500)
    data, _ = write_result(BusabaseClient("https://bb.example.com"), merged_record(), BASE, "update")
    assert data["status"] == "merged"
    assert data["changeRequestId"] is None
    assert data["recordId"] == "recmve1abzlnki6zwy"


def test_write_result_in_review_update():
    data, text = write_result(BusabaseClient("https://bb.example.com"), IN_REVIEW_UPDATE, BASE, "update")
    assert data == {
        "status": "in_review",
        "merged": False,
        "changeRequestId": "crqmve1aub58pq6aps",
        "recordId": "recmve1abzlnki6zwy",
        "base": {"id": BASE["id"], "slug": "dify-leads", "name": "Dify Leads"},
        "proposedFields": {"score": 11},
        "submittedBy": "Local Producer",
    }
    assert "Submitted for review" in text and "in_review" in text


def test_write_result_in_review_create_has_no_record_yet():
    data, text = write_result(BusabaseClient("https://bb.example.com"), IN_REVIEW_CREATE, BASE, "create")
    assert data["status"] == "in_review"
    assert data["recordId"] is None
    assert "a new record 'Acme Corp'" in text


def test_validation_issues_are_spelled_out(fake):
    # 400 "Input validation failed" carries zod issues in data.issues — show them.
    fake.on(
        "POST",
        "/api/v1/docs",
        {
            "error": "Input validation failed",
            "code": "BAD_REQUEST",
            "data": {"issues": [{"code": "invalid_format", "path": ["slug"], "message": "Invalid string: must match pattern /^[a-z0-9-]+$/"}]},
        },
        status=400,
    )
    with pytest.raises(BusabaseError, match=r"400: Input validation failed \(slug: Invalid string: must match pattern"):
        BusabaseClient("https://bb.example.com").create_doc(slug="Bad", name="x", body="")


def test_parent_type_errors_name_the_allowed_types(fake):
    fake.on(
        "POST",
        "/api/v1/docs",
        {"error": "Doc cannot be nested under a Doc; choose a folder or root node.", "code": "INVALID_PARENT_NODE_TYPE", "data": {"allowedParentTypes": ["folder"]}},
        status=400,
    )
    with pytest.raises(BusabaseError, match="allowed parent types: folder"):
        BusabaseClient("https://bb.example.com").create_doc(slug="x", name="x", body="", parent_node_id="nod1")


def test_file_paths_keep_their_slashes(fake):
    fake.on("GET", "/api/v1/file-trees/nod1/files/references/a b.md", {"path": "references/a b.md"})
    BusabaseClient("https://bb.example.com").read_file("nod1", "/references/a b.md")
    assert fake.requests[-1].url.raw_path == b"/api/v1/file-trees/nod1/files/references/a%20b.md"
