# Busabase for Dify

A [Dify](https://dify.ai) tool plugin for [Busabase](https://busabase.com), the open-source database & workspace for AI agents. A Busabase workspace is a tree of **nodes**: folders, Bases (tables), docs, skills (your company's written procedures), drives and AirApps with their files, and more. This plugin lets any Dify workflow, chatflow or Agent read all of it, follow the company's own **playbooks**, and write back as **reviewed, versioned changes**. Every write is a Change Request with a commit message. It merges right away when your API key has write access, and waits in the review inbox for a human when it does not.

**Author:** busabase · **Version:** 0.1.1 · **Type:** tool · **Source:** [github.com/busabase/dify-plugin-busabase](https://github.com/busabase/dify-plugin-busabase)

## Tools

### Records (Bases)

| Tool | What it does | Busabase API |
| --- | --- | --- |
| **List Bases** | Every Base (table) in the space, with its fields: slug, name, type, select choices. | `GET /api/v1/bases` |
| **List Records** | One page of a Base's records (up to 100), plus a `nextCursor` for the next page. Can list the archived ones instead. | `GET /api/v1/records` |
| **Find Records by Field Value** | Records whose field is *exactly* equal to a value. Use it to check for a duplicate before you create one. | `GET /api/v1/records/search` |
| **Get Record** | One record, by its id or by an exact field value. | `GET /api/v1/records/get` |
| **Create Record** | Adds a record as a Change Request. | `POST /api/v1/bases/{baseId}/change-requests` |
| **Update Record** | Changes only the fields you pass, as a Change Request. The record's history keeps every version. | `POST /api/v1/records/{recordId}/change-requests` |

### Nodes & Docs

| Tool | What it does | Busabase API |
| --- | --- | --- |
| **List Nodes** | The workspace tree (1 to 5 levels deep), every node of one type (all docs, all skills…), or what is inside one folder. Returns compact id / type / slug / name / parentId. | `GET /api/v1/nodes` |
| **Search Nodes by Name** | Nodes whose name or slug contains some text, optionally of one type. | `GET /api/v1/nodes/search` |
| **Get Node** | One node's detail: a doc's markdown body, a folder's children, a skill's / drive's / AirApp's file list, a Base's fields. Long doc bodies are truncated with a pointer to Read Lines. | `GET /api/v1/nodes/{nodeId}` (+ `GET /api/v1/bases/{baseId}` for a Base) |
| **Read Lines** | An exact line range of a doc, HTML page, whiteboard or workflow, or of a file inside a skill / drive / AirApp. | `GET /api/v1/nodes/{nodeId}/lines` |
| **Create Folder** | A folder, at the root or inside another folder, as a Change Request. | `POST /api/v1/nodes/change-requests` |
| **Create Doc** | A markdown doc in a folder (or at the root). The slug is derived from the title if you leave it empty. | `POST /api/v1/docs` |
| **Update Doc** | Appends to a doc, or replaces its whole body, as a Change Request. | `PUT /api/v1/nodes/{nodeId}/content` |

### Files (skills, drives, AirApps)

| Tool | What it does | Busabase API |
| --- | --- | --- |
| **List Files** | The files inside a skill, drive or AirApp, optionally under a path prefix. | `GET /api/v1/file-trees/{nodeId}/files` |
| **Read File** | One file's text, e.g. a skill's `SKILL.md`, with its content hash. Binary files return a download URL. | `GET /api/v1/file-trees/{nodeId}/files/{path}` |
| **Write File** | Creates or replaces one file as a Change Request. An existing file is sent with its content hash, so a concurrent edit fails instead of being overwritten. | `POST /api/v1/file-trees/{nodeId}/change-requests` |

### Playbooks

| Tool | What it does | Busabase API |
| --- | --- | --- |
| **Search Playbooks** | Finds the skills and custom prompts your team wrote for a job ("how we qualify a lead", "how we write the weekly report"). The tool description tells the Agent to call it first on every new task. | `POST /api/v1/playbooks/search` |
| **Get Playbook** | Opens one: a skill's `SKILL.md` plus its other files, or a custom prompt rendered for the node it lives on. The Agent follows it as the company's procedure. | `GET /api/v1/playbooks/{kind}/{nodeId}` |

### Search

| Tool | What it does | Busabase API |
| --- | --- | --- |
| **Search Workspace** | Every occurrence of a word or regex across Base records, docs, Drive and skill files, and agent prompts. Returns the location of each hit. | `POST /api/v1/grep` |

Every tool returns a short text summary plus structured JSON (for workflow variables). Long content (a doc body, a file, a playbook) is sent once, in the JSON, because Dify shows an Agent both messages.

**References are forgiving.** Bases, folders, docs, skills and other nodes can be given by id, slug or exact name. Fields can be given by slug or display name. The plugin resolves them before it sends anything, and when something does not exist the call fails and lists the valid options. It never lets a value be dropped silently.

### Writes are reviewed, not blind

No write tool ever forces a merge. They let Busabase decide:

- **`status: "merged"`**: the key has write access, so the change is applied now. The output has the new or changed object's id (`recordId` or `nodeId`) and the `changeRequestId` it was merged as.
- **`status: "in_review"`**: the key can only propose changes. The output has the `changeRequestId`, and nothing changes until someone approves it in Busabase.
- **`status: "unchanged"`** (Update Doc, Write File): the content was already exactly that, so nothing was sent.

The write tools take a **Commit Message**, which reviewers see and the history keeps. If you leave it empty, the plugin writes a short one for you (`Add Acme Corp via Dify`). A message that says *why* reads much better in the history.

## Setup

1. Install **Busabase** from the Dify Marketplace (or upload the `.difypkg` under **Plugins → Install from local file**).
2. Open **Tools → Busabase → Authorize** and fill in:

| Credential | Required | Value |
| --- | --- | --- |
| **Base URL** | yes | `https://busabase.com` for Busabase Cloud. For a self-hosted or local open-source server, use its URL: `npx busabase server` listens on `http://localhost:15419`. If Dify runs in Docker, `localhost` means the container itself. Start the server with `--host 0.0.0.0` and use `http://host.docker.internal:15419` on Docker Desktop (macOS/Windows), or the Docker bridge gateway IP on Linux (for example `http://172.17.0.1:15419`). |
| **API Key** | Cloud: yes | Create one in Busabase under **Settings → API Keys**. Give it write access if you want writes to merge immediately; give it change-request access if you want every write reviewed by a human. Leave empty for a local server without auth. |
| **Space ID** | no | Only if your Cloud account has more than one space. It is sent as the `x-busabase-space` header. |

Dify checks the credentials by listing your Bases.

## Examples

**Agent: follow the company's procedure.** Add *Search Playbooks*, *Get Playbook*, *Read File* and the record tools to an Agent, then ask it:

> A new inbound lead just came in from acme.com. Qualify it.

The Agent first calls *Search Playbooks* with `queries = ["qualify inbound lead", "lead qualification", "qualify"]`, finds your **Lead Qualification** skill, opens it with *Get Playbook* and works through its steps (say: check company size, check budget, score 1 to 10), then files the result with *Create Record*. Its reply names the playbook it followed. If nothing fits, it does the work its own way.

**Agent: research a lead, then file it for review.** With *List Bases*, *Find Records by Field Value* and *Create Record*:

> Research acme.com and add it to our Leads base with a one-line summary and a score from 1 to 10.

The Agent lists your Bases to learn the field slugs and checks that Acme isn't already there. Then it calls *Create Record*:

```json
{
  "base": "leads",
  "fields": "{\"company\": \"Acme Corp\", \"website\": \"https://acme.com\", \"score\": 8, \"summary\": \"Mid-market logistics, hiring 3 data engineers\"}",
  "message": "Add Acme Corp — logistics lead researched from acme.com"
}
```

and gets back:

```json
{
  "status": "in_review",
  "merged": false,
  "changeRequestId": "crq…",
  "recordId": null,
  "base": { "id": "bse…", "slug": "leads", "name": "Leads" },
  "proposedFields": { "company": "Acme Corp", "score": 8 },
  "message": "Add Acme Corp — logistics lead researched from acme.com"
}
```

A teammate approves it in Busabase, and it becomes a record with full history.

**Workflow: write the weekly report into a doc.** An LLM node drafts the report, then *Create Doc* saves it:

```json
{ "name": "Weekly report 2026-W42", "parent": "Reports", "body": "{{llm.text}}" }
```

The output's `nodeId` and `status` tell the next node where the doc is and whether it is live or waiting for review. Later runs can add to it with *Update Doc* (`mode = append`, `text = "## Follow-ups\n- …"`).

**Agent: keep a skill up to date.** "Add a budget check to our lead qualification skill." The Agent opens the skill with *Read File* (`node = "lead-qualify"`, `path = "SKILL.md"`), edits the text, and sends the full new file with *Write File* and a commit message. If a teammate edited `SKILL.md` in the meantime, the write fails with a conflict and the Agent reads the file again.

**Workflow: answer from your docs.** *Search Workspace* with `pattern = {{query}}` and `source = nodes` returns each hit's node and line number. *Read Lines* with that node and a range around the line gives the LLM node just the passage it needs.

**Workflow: keep a status field in sync.** Use *Get Record* (by `email` = the form's email) and then *Update Record* with `{"stage": "Demo booked"}`. Branch on `status` to send a different message for `merged` and `in_review`.

## Limits (v1)

- No delete, archive, move or rename, for records or nodes. In Busabase, each of these is itself a reviewed Change Request, and v1 leaves them out rather than ship them with surprising behaviour.
- No bulk writes and no Base schema changes. Create Bases and fields in Busabase itself.
- Docs and files are written whole: *Update Doc* appends or replaces the body, *Write File* replaces the file. There is no in-place patch.
- *Create Doc* and *Create Folder* only. Skills, drives, AirApps, Bases and other node types are created in Busabase; the plugin reads them and edits their files.
- *Find Records* matches the whole value exactly, so `Acme` does not find `Acme Corp`. Use *Search Workspace* for partial matches.
- Authentication is by API key only. OAuth is not supported yet.

## Privacy

The plugin sends your requests to the Busabase server you configure and stores nothing itself. See [PRIVACY.md](PRIVACY.md).

## Support

Report issues at [github.com/busabase/dify-plugin-busabase/issues](https://github.com/busabase/dify-plugin-busabase/issues) or email support@busabase.com. Busabase docs: [busabase.com/docs](https://busabase.com/docs).
