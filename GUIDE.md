# Developing the Busabase Dify plugin

This guide is for contributors and is not shipped in the `.difypkg`. Users should read [README.md](README.md).

## Layout

```
manifest.yaml            plugin manifest (version, author, runner)
main.py                  entrypoint — dify_plugin.Plugin
provider/busabase.yaml   credentials (base_url, api_key, space_id) + tool list
provider/busabase.py     credential check: lists Bases
tools/<name>.yaml|py     one Dify tool per file (each .py holds exactly ONE Tool subclass)
busabase_dify/client.py  REST client: auth + space headers, errors, one method per endpoint
busabase_dify/core.py    Base/field resolution, output shaping, merged vs in_review mapping;
                         its docstring lists every server quirk the plugin guards against
busabase_dify/nodes.py   node resolution (id / slug / name), slugs, trees, node CR results, playbook helpers
tests/                   pytest: mocked-HTTP unit tests + real-server integration test
```

Do not put a shared `Tool` base class in an importable module. Dify loads each tool by taking the single `Tool` subclass in its file, so importing a base class makes every tool ambiguous. Shared code goes in `busabase_dify/` as plain functions.

Request and response shapes come from the Busabase contract, not from guesses. Print any endpoint's exact schema offline with `npx busabase-cli schema <id> --io input|output`. The ids used here are `bases.list`, `bases.get`, `records.list`, `records.search`, `records.get`, `bases.createChangeRequest`, `records.changeRequest`, `records.listChangeRequests`, `grep`, `nodes.list`, `nodes.searchByName`, `nodes.get`, `nodes.readLines`, `nodes.createChangeRequest`, `nodes.updateContent`, `docs.create`, `changeRequests.list`, `fileTrees.listFiles`, `fileTrees.readFile`, `fileTrees.createChangeRequest`, `playbooks.search` and `playbooks.get`.

Two output rules for new tools. Dify gives an Agent's LLM both the text message and the JSON message (concatenated; the workflow Agent node does not even de-duplicate), and SDK 0.10 has no way to hide the JSON. So long content such as a doc body, a file or a playbook goes in the JSON only, and the text stays a short summary. And never trust that a slug, a key or a parent is accepted just because the call succeeded: check the core.py list first.

## Test

```bash
uv venv -p 3.12 && uv pip install -r requirements.txt pytest
uv run pytest                       # unit tests, mocked HTTP

# Integration: every tool against a real, throwaway local server
npx busabase server --port 15419 --data /tmp/busabase-dify-test
BUSABASE_TEST_BASE_URL=http://127.0.0.1:15419 uv run pytest -m integration -s
```

The integration test creates its own Base, folders, docs, a skill and a custom prompt, all with a per-run timestamp, so it can be re-run against the same server. It refuses to run against a non-local host unless you set `BUSABASE_TEST_ALLOW_REMOTE=1`, so never point it at a real workspace.

## Debug inside Dify

Copy `.env.example` to `.env` and fill in the remote-debug URL and key from Dify (**Plugins → Debug**). Then run `uv run python -m main`. The plugin appears in Dify marked "debugging".

## Package and publish

```bash
dify plugin package . -o busabase-0.1.0.difypkg     # dify = langgenius/dify-plugin-daemon CLI
```

To publish on the Marketplace, open a PR to [langgenius/dify-plugins](https://github.com/langgenius/dify-plugins) that adds exactly one file, `busabase/busabase/busabase-<version>.difypkg` (CI rejects any other file). Fill in the repo's PR template in English: CI checks the five "Plugin information" fields, exactly one "Submission type" and one "Risk level" box, non-empty "What changed", "Security and privacy notes" and "Local validation", and no CJK anywhere in the body. Run their validator first: `python3 validator/validate-difypkg.py busabase-<version>.difypkg --pr-body-file body.md` from [langgenius/dify-marketplace-toolkit](https://github.com/langgenius/dify-marketplace-toolkit). The README must stay English-only outside code blocks and must link the public source repo; `manifest.yaml` must keep `repo`, `contact` and `privacy`. Before you open it, bump `version` in `manifest.yaml`, in `pyproject.toml`, and `PLUGIN_VERSION` in `busabase_dify/client.py`. Keep `requirements.txt` and `pyproject.toml` dependencies identical; a test checks this.
