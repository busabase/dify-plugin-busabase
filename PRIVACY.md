# Privacy Policy

This policy covers the Busabase tool plugin for Dify ("the plugin"), published by Busabase.

## Data the plugin handles

- **Credentials.** The Base URL, the API key and the optional Space ID you enter when you authorize the plugin. Dify stores them encrypted, as it does for every tool credential. The plugin itself does not store them anywhere.
- **Tool inputs.** The parameters a workflow or Agent passes to a tool: Base, field, folder, doc, skill and file names or ids, record field values, doc bodies and file contents to write, commit messages, search patterns, and playbook search phrasings.
- **Busabase data.** What Busabase returns: Bases and records, the node tree, doc bodies, file contents, playbooks (skills and custom prompts), and search matches. The plugin passes them back to your Dify app.

The plugin does not collect anything beyond what a tool call needs. It has no analytics or telemetry, and it does not track anyone.

## Where the data goes

Every request goes to **one** place: the Busabase server at the Base URL you configured. That is either Busabase Cloud (`https://busabase.com`) or a server you host yourself. Requests use HTTPS whenever the Base URL does. The plugin sends nothing to Busabase-the-company or to any third party unless that is the server you chose. Your Dify instance and any LLM it uses also see tool inputs and outputs, under their own policies.

- Busabase Cloud privacy policy: <https://busabase.com/privacy-policy>
- A self-hosted Busabase server: data stays on the infrastructure you run.

## Retention

The plugin keeps nothing between calls. It caches no data, writes no files, and logs no request contents. What you write through the plugin is kept in your Busabase workspace like any other change, with its version history and Change Request record. You manage and delete it there, under your workspace's settings and Busabase's terms.

## Your control

- To revoke the plugin's access, delete or rotate its API key in Busabase under **Settings → API Keys**. You can also remove the credential in Dify.
- To keep every write reviewed by a human first, give the plugin a key that can only propose changes. Its writes will then wait in the review inbox.

## Contact

Privacy questions: support@busabase.com, or open an issue at <https://github.com/busabase/dify-plugin-busabase/issues>.
