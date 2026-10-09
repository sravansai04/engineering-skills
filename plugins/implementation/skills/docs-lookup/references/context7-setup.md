# Optional: connecting a Context7 MCP server

Context7 is a third-party hosted index of library documentation, exposed to agents as an
MCP server. This skill works without it; it is a convenience for frequent lookups. Suggest
it only when the user asks how to get version-matched docs into the agent, or when a
session involves many lookups. Never install or configure it without the user asking.

Commands below were checked against the vendor's docs and the Claude Code plugin docs in
October 2026. Setup flows for hosted services change, so confirm against
<https://context7.com/docs/clients/claude-code> (Claude Code) or
<https://context7.com/docs/resources/all-clients> (other MCP clients) before running them.

## Check whether it is already connected

```bash
claude mcp list        # configured MCP servers and their connection status
claude plugin list     # installed plugins (the server may come from a plugin)
```

Inside a session, `/mcp` shows server status and handles sign-in for servers that need it.

## Setup options for Claude Code (pick one)

**1. Plugin from Anthropic's official marketplace.** Connects to the hosted server; no
local Node.js needed. Works anonymously at shared rate limits.

```bash
claude plugin install context7@claude-plugins-official
```

(Inside a session: `/plugin install context7@claude-plugins-official`.) The vendor also
publishes its own marketplace: `/plugin marketplace add upstash/context7`, then
`/plugin install context7@context7-marketplace`. After installing either plugin, restart
Claude Code and run `/mcp`; for the vendor's plugin, select Context7 there and complete
the browser sign-in it asks for.

**2. The vendor's setup CLI.** Signs in through the browser (device flow on headless
hosts), creates an API key, and configures Claude Code; it asks whether to install an MCP
server or a CLI-plus-skill mode. Requires Node.js.

```bash
npx ctx7 setup --claude
```

Choose the MCP mode if you want this skill to pick Context7 up automatically. The
CLI-plus-skill mode installs the `ctx7` command plus the vendor's own skill, which also
triggers on library-documentation questions. This skill still detects the CLI
(`command -v ctx7`) and uses it, but expect the two skills to compete for the same
prompts.

**3. Manual remote server registration** (as documented by the vendor):

```bash
claude mcp add --scope user --header "Authorization: Bearer YOUR_API_KEY" --transport http context7 https://mcp.context7.com/mcp
```

Create the key in the Context7 dashboard. Anonymous use without the header is possible at
lower rate limits, which is how the official plugin connects by default.

**4. Manual local server over stdio** (runs the npm package `@upstash/context7-mcp`;
needs a recent Node.js, see the package README for the minimum):

```bash
claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp --api-key YOUR_API_KEY
```

`--scope` accepts `user` (all projects on this machine), `project` (written to a
shared `.mcp.json` in the repository), or `local` (this project, this user only).

## Keep keys out of the repository

Never commit an API key. If you register the server at project scope, reference an
environment variable in `.mcp.json` (for example `"Authorization": "Bearer ${CONTEXT7_API_KEY}"`)
and have each developer export the variable in their shell profile.

## Verify it works

1. `claude mcp list` (or `/mcp` in a session) shows the server as connected. Restart the
   session if it was added while one was running. The server name depends on how it was
   installed: `context7` when added with `claude mcp add`, `plugin:context7:context7` when
   it comes from a plugin.
2. The tool list now includes `resolve-library-id` and `query-docs` under the matching
   prefix: `mcp__context7__resolve-library-id` for a server you added, or
   `mcp__plugin_context7_context7__resolve-library-id` for the plugin. Permission
   allowlists, hook matchers and `allowed-tools` lists must use the form actually present;
   a rule written for one form never matches the other.
3. Resolve a library you know, for example a framework already in this project, and check
   that the returned ID's `/owner/repo` matches the package's real repository.

## Tool names and parameters

Current servers expose:

| Tool | Required parameters | Returns |
|---|---|---|
| `resolve-library-id` | `libraryName`, `query` | candidate library IDs such as `/org/project`, with available versions and quality signals |
| `query-docs` | `libraryId`, `query` (optional `language`) | documentation excerpts and code snippets relevant to the query |

A version-pinned ID has the form `/org/project/<version>`, with the version copied exactly as
the resolver listed it (`/vercel/next.js/v15.1.8`), and is only valid when the resolver
listed that version. IDs under `/websites/` or `/llmstxt/` are built from a crawled site or
an llms.txt file rather than a repository, so they carry no release version.

Servers from before the 2.0 release of the package name the second tool `get-library-docs`
and take `context7CompatibleLibraryID` plus optional `topic` and `tokens` instead of
`libraryId` and `query`. Always read the schema of the tool actually present rather than
assuming either shape. Permission allowlists that name only one of the two tool names
will prompt or block on the other.

## Privacy

Queries are sent to the vendor's service. Phrase them generically: library, version,
symbol and task. Do not include secrets, customer data, internal hostnames or proprietary
code. Do not query it for private or internal packages unless your team has deliberately
indexed them there: the public index has nothing on them, and the query leaks the package
name and its symbols.
