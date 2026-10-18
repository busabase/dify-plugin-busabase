"""Response shapes trimmed from a real local `busabase server` (0.95.x).

Only fields the plugin reads are kept, plus a few neighbours so the shapes
stay recognisable next to `busabase-cli schema <id> --io output`.
"""

BASE = {
    "id": "bsemve1a8qqyg3l2qj",
    "nodeId": "nodmve1a8qqlzkmlfv",
    "slug": "dify-leads",
    "name": "Dify Leads",
    "description": "Scratch base",
    "reviewPolicy": {"kind": "single", "requiredApprovals": 1},
    "createdAt": "2026-10-18T16:22:26.498Z",
    "fields": [
        {"id": "bsfname", "baseId": "bsemve1a8qqyg3l2qj", "slug": "name", "name": "Name", "type": "text", "required": False, "position": 0, "options": {}},
        {"id": "bsfstatus", "baseId": "bsemve1a8qqyg3l2qj", "slug": "status", "name": {"en": "Status", "zh-CN": "状态"}, "type": "select", "required": False, "position": 1, "options": {"choices": [{"id": "New", "name": "New"}, {"id": "Won", "name": "Won"}]}},
        {"id": "bsfscore", "baseId": "bsemve1a8qqyg3l2qj", "slug": "score", "name": "Score", "type": "number", "required": False, "position": 2, "options": {}},
    ],
}


def record(record_id="recmve1abzlnki6zwy", head="cmtmve1abyewlwzxxd", payload=None, message="Add Probe Co"):
    return {
        "id": record_id,
        "baseId": BASE["id"],
        "headCommitId": head,
        "parentRecordId": None,
        "parentCommitId": None,
        "status": "active",
        "createdBy": "local-admin",
        "createdByUser": {"id": "local-admin", "name": "Owner", "email": None, "image": None, "role": "owner"},
        "fieldUsers": {},
        "archivedAt": None,
        "createdAt": "2026-10-18T16:22:30.700Z",
        "updatedAt": "2026-10-18T16:22:30.700Z",
        "base": BASE,
        "headCommit": {
            "id": head,
            "baseId": BASE["id"],
            "targetType": "base",
            "operationId": "oprmve1abye93a2qyp",
            "payload": payload if payload is not None else {"name": "Probe Co", "score": 5},
            "operation": "record_create",
            "message": message,
            "author": "producer",
        },
    }


def merged_record(**kwargs):
    return {**record(**kwargs), "materialized": True}


def change_request_history(record_id="recmve1abzlnki6zwy", head="cmtmve1abyewlwzxxd", cr_id="crqmve1abyedammlfg"):
    return [
        {
            "id": cr_id,
            "baseId": BASE["id"],
            "status": "merged",
            "mergeSummary": {"viewIds": [], "recordIds": [record_id], "operationCount": 1},
            "operations": [{"id": "opr1", "changeRequestId": cr_id, "operation": "record_create", "status": "merged", "headCommitId": head}],
        },
        {
            "id": "crqolder",
            "baseId": BASE["id"],
            "status": "merged",
            "operations": [{"id": "opr0", "changeRequestId": "crqolder", "operation": "record_create", "status": "merged", "headCommitId": "cmtolder"}],
        },
    ]


IN_REVIEW_UPDATE = {
    "id": "crqmve1aub58pq6aps",
    "baseId": BASE["id"],
    "targetType": "base",
    "nodeId": None,
    "status": "in_review",
    "submittedBy": "local-producer",
    "submittedByUser": {"id": "local-producer", "name": "Local Producer", "email": None, "image": None, "role": "producer"},
    "mergedAt": None,
    "primaryOperation": {
        "id": "oprmve1aub5ykm3o0f",
        "changeRequestId": "crqmve1aub58pq6aps",
        "operation": "record_update",
        "status": "pending",
        "targetRecordId": "recmve1abzlnki6zwy",
        "mergedRecordId": None,
        "baseCommitId": "cmtmve1au6paz06v72",
        "headCommitId": "cmtmve1aub5hktkr66",
        "headCommit": {"id": "cmtmve1aub5hktkr66", "payload": {"score": 11}},  # update payload is partial
    },
    "operationCount": 1,
    "reviews": [],
    "materialized": False,
}

IN_REVIEW_CREATE = {
    **IN_REVIEW_UPDATE,
    "id": "crqcreate",
    "primaryOperation": {
        **IN_REVIEW_UPDATE["primaryOperation"],
        "operation": "record_create",
        "targetRecordId": None,
        "headCommit": {"id": "cmtnew", "payload": {"name": "Acme Corp", "score": 8}},
    },
}
