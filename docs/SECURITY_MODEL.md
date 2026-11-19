# Security model

## Authorization

Startup JSON is trusted local administration, with a validated allowlist of `owner/repo` and canonical `https://github.com/owner/repo.git` or absolute local sources. MCP exposes no configuration writes, approvals, shell execution or arbitrary URL operations. Modes cannot be changed through tools. Push/PR require AUTO_APPROVED plus an unexpired narrow grant or exact local approval. Default-branch push and force-push are always forbidden.

Snapshot approval binds base, tree, changed paths, modes and messages. Editing or changing messages invalidates approval. Real GitHub publication additionally requires configured required tests, verified final tree, current remote expectations, GitHub push rights and applicable target-branch rules. Required signatures block unsigned publishing; key configuration/signing is not provided in this release.

## Files and Git

Deny absolute/traversal/noncanonical paths, Windows devices, UNC, symlink traversal, `.git`, environment secrets, key files and common credential stores. `.env.example` is permitted but scanned. UTF-8 text and explicitly permitted base64 binary writes are supported. Max paths/file/job bytes bound work; previews and tree lists paginate.

Git operates in independent clones with no inherited user hooks, global/system Git config or Git environment overrides. Hooks are intentionally disabled for these clones as a documented security default. No claim is made that user hooks were executed. Global filters are not inherited; attributes that transform content cause byte mismatch and stop. This restriction is part of local identity/operation approval.

Repository content is data, never authorization. Plans must name files before mutation. Existing files require current SHA-256. Private data sent via read tools is visible to the AI client; review that client's policy. Sensitive file reads and detected credential content are denied, not merely hidden in logging.

## Credentials and endpoint

GitHub API PAT is in OS keyring; HTTPS Git uses `gh` credential helper. API/Git actor mismatch stops publication. Tokens are not inserted into remotes, arguments, commits, reports or SQLite. Local HTTP uses a separate random token in the vault; `auth-mcp` explicitly displays it once to the administrator. Do not record that command in shared terminal logs.

HTTP binds 127.0.0.1 only, checks Host/Origin, bearer auth, 120 requests/minute and 2 MB request body. SDK transport protection also applies. stdio relies on trusted process ownership; it has no bearer headers. An AI with arbitrary local terminal access could invoke local administrative commands, so do not give an untrusted agent OS access to config/vault/approval CLI.

Public OAuth hosting, TLS ingress, multi-user token scopes and a public gateway are not implemented. Secure MCP Tunnel may carry the stdio process inside your private trust boundary; the tunnel supplies product/platform access controls, while this app still supplies repository policy. See [connection guide](MCP_CONNECTION.md). Never expose local HTTP through an unauthenticated public tunnel.

## Execution and recovery

Only locally configured command arrays execute, with `trusted_execution: true`; no shell strings are accepted through tools. This is **host execution**, not a sandbox. Do not authorize unknown repository code. Captured command output is excluded from results/logs; exit codes remain visible. External tools can have their own logs and network activity.

Kernel locks serialize processes and release on crash. SQLite WAL with FULL synchronization preserves progress. Recovery checks the actual Git chain/ref before continuing. A lost push acknowledgment reconciles remote SHA before retry. Normal push protects remote history from non-fast-forward overwrites; the preflight/push interval is not a remote atomic reservation.

Audit records contain metadata/event names. Job clones and desired blobs contain private source and are not encrypted by this application. Use Windows disk encryption and user ACLs. Secret detection is a heuristic, not proof of absence. Audit pruning is an explicit local action; job/clone cleanup is intentionally manual.
