# MCP API reference

Prefix every tool with `github_mcp.`. SDK `tools/list` is the authoritative machine-readable JSON schema. Successful envelopes are `{ok:true,data:{...},error_code:null,message:null}`; safe business failures are `{ok:false,data:null,error_code:CODE,message:...}`. SDK protocol validation failures use MCP errors. Output schemas use a typed envelope with tool-specific data dictionaries; payload schemas are not fully specialized by tool in this release.

| Tool | Inputs / behavior |
|---|---|
| health_check | No inputs; versions/mode/endpoint, no token |
| list_repositories | No inputs; trusted allowlist only |
| get_repository_info | repository; local metadata or REST default/fork/rights/rules |
| list_branches | repository; bounded local cache refs/SHAs |
| list_tree | repository, offset=0, limit=100 (1–200); filtered/paginated paths |
| read_file | repository, path, optional job_id, binary=false; content and SHA-256 |
| read_files_batch | repository, paths (1–20); UTF-8, bounded total |
| list_recent_commits | repository, limit=20 (1–100) |
| check_contribution_eligibility | repository, branch; no activity guarantees |
| create_job | repository, idempotency_key, target_branch?, expected_base_sha?, base_ref?, task_name?; English task name auto-generates a flat kebab-case branch, with -2/-3 suffix on collisions |
| plan_changes | job_id, messages map path → conventional subject |
| write_file | job_id, path, content, expected_checksum?, encoding=utf-8/base64, executable? |
| apply_patch | job_id, path, old_text, new_text, expected_checksum; exact unique context |
| delete_file | job_id, path, expected_checksum |
| preview_job | job_id, offset=0, limit=20 (1–50); diffs/fingerprint/tree, 20k chars per diff |
| run_checks | job_id; configured required tests only |
| create_file_commits | job_id; freezes/verifies strict sequence, resumable |
| get_job_status | job_id; stages, real local/pushed SHAs |
| get_git_status | job_id; owned workspace only |
| get_diff | job_id; base to work diff, maximum 100k chars |
| cancel_job | job_id; retains workspace, no remote undo |
| resume_job | job_id; validates refs, recovers interrupted commits/push |
| publish_branch | job_id; normal push, checks/policy/expected remote |
| create_pull_request | job_id, title, description; verified published head |
| get_remote_status | job_id; actual SHA and REST statuses/check-runs |
| get_job_report | job_id; metadata audit, JSON-ready report |

`github-ai://policy` and `github-ai://jobs` resources expose non-secret policy summaries and job reports. No approval or configuration mutation resource/tool exists.

## Edit concurrency

For existing content, pass the latest read_file `checksum`. For file creation, pass null (the path must not exist). Deletion also requires the current checksum. UTF-8 byte preservation uses binary I/O; `apply_patch` is an exact single-context replacement, not unified-diff syntax. Binary content is base64 and requires local repository `allow_binary` for writes. Git mode changes use `executable`.

## Example tool sequence (illustrative inputs)

1. `create_job({repository:"owner/repo",idempotency_key:"localization-1",task_name:"fix localization"})` creates `fix-localization` (or `fix-localization-2` if already used). AI clients should translate non-English task descriptions into short English titles. The tool does **not** call a translation model itself.
2. `plan_changes({job_id:ID,messages:{"src/es.json":"fix(i18n): repair Spanish punctuation"}})`.
3. `read_file({repository:"owner/repo",job_id:ID,path:"src/es.json"})`.
4. `write_file({job_id:ID,path:"src/es.json",content:FINAL_TEXT,expected_checksum:READ_CHECKSUM})`.
5. `preview_job({job_id:ID})`, local human approval, `create_file_commits({job_id:ID})`.
6. If authorized: `publish_branch`, `create_pull_request`, `get_remote_status`, `get_job_report`.

These are illustrative requests; they do not claim changes to owner/repo. Actual job ID/SHA/URL must come from real results.

## Important errors

`PERMISSION_DENIED`, `APPROVAL_REQUIRED`, `STALE_APPROVAL`, `STALE_FILE`, `UNSAFE_PATH`, `SENSITIVE_PATH`, `SECRET_DETECTED`, `UNPLANNED_PATH`, `CHECK_FAILED`, `CHECKS_REQUIRED`, `EXECUTION_DENIED`, `REMOTE_DIVERGED`, `INVARIANT_FAILED`, `SIGNING_REQUIRED`, `AUTH_REQUIRED`, `IDENTITY_MISMATCH`, `RATE_LIMITED`, `BUSY`, `RECOVERY_REQUIRED`.

No-change jobs return NO_CHANGE with zero commits. After an error inspect status before retrying. Check failures after commits cannot be edited in the frozen job; create a new job with corrected final content. Creation failures are retained for diagnostics; automatic reconstruction of an incomplete clone is not implemented.
