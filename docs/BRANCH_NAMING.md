# Task-based Git branch names (no prefix)

New jobs use one flat, lowercase English kebab-case branch name (e.g.
`fix-tunnel-startup`, `add-dark-mode`, `update-documentation`) rather than
`ai/..` or `mcp/..`.

## Through ChatGPT / MCP

Pass an English `task_name` to `github_mcp.create_job` even when the user
writes in Russian. The ChatGPT agent selects a short English task title.
Example:

```json
{"repository":"owner/repo","idempotency_key":"unique-operation-123","task_name":"fix tunnel startup"}
```

An explicit `target_branch` is allowed as an override. Old `ai/...` explicit
branches remain accepted so existing jobs and callers are compatible, but new
automatic branches are never given that prefix. If an automatically named
branch already belongs to a job or exists on the Git remote, the program
appends `-2`, `-3`, and so on instead of reusing it. Repeating the same
`idempotency_key` returns the original job, *not* a fresh branch.

## Through the Windows GUI

In **Jobs → Create job**, enter a **unique English-language task title**
(e.g. `fix tunnel startup`). That creates the branch `fix-tunnel-startup`.
The desktop application does not include an offline English translation
model; for Russian input, use ChatGPT/MCP or enter an English task title.

## Approval security (important)

Renaming branches does **not** silently grant additional write permissions.
Old grants with `"branch_prefix": "ai/"` only apply to old `ai/...` jobs.
For a new flat branch in `AUTO_APPROVED` mode, either approve its precise
preview locally (GUI/CLI), or **explicitly** edit the trusted local
`config.json` grants (not through MCP) to set `"branch_prefix": ""` on a
*scoped, time-limited grant for that single allowed repository*. An empty
prefix permits **all safe non-default branches in that repository** while
respecting actions, expiry, file and size limits. Do not enable this unless
you intentionally grant that broader automation scope.

Existing jobs, branch names, GitHub default branches, tokens, and remotes
are not renamed or modified by this update. Rebuild the EXE and restart
MCP and tunnel before using the new tool parameter from ChatGPT.
