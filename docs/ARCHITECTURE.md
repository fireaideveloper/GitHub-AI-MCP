# Architecture and source map

The official SDK is the transport boundary. CLI and GUI use the same `Service`; tool wrappers contain no Git business logic. Local human administration is intentionally absent from the MCP registry. All operations serialize through a kernel-owned interprocess lock: correctness is preferred over parallel throughput.

| Path | Responsibility |
|---|---|
| `src/github_ai_mcp/config.py` | Strict trusted JSON policy, source allowlist, grants, repository identity |
| `server.py` | SDK registration, schemas, safe envelopes, stdio/HTTP |
| `security/auth_mcp.py` | Loopback bearer/Host/Origin/rate/size checks |
| `security/auth_github.py` | OS credential vault; no plaintext persistence |
| `security/paths.py` | Portable relative path validation, sensitive files, symlinks |
| `security/policy.py` | Immutable startup mode, grants, fingerprint approval |
| `security/secret_scan.py` | Credential indicators and redaction |
| `core/git_engine.py` | Real Git CLI, fixed arguments/environment, hardened isolated operations |
| `core/job_engine.py` | Repository reader, plans, edits, snapshot, checks, commit chain, recovery, push, PR |
| `core/github_api.py` | Canonical REST API, bounded retries and safe failures |
| `core/locking.py` | Cross-process lock, automatically released on process death |
| `storage/database.py` | WAL/FULL SQLite, schema guard, jobs, grants, metadata audit |
| `gui/app.py` | PySide6 local control with background workers, reviewed approvals |
| `cli/app.py` | Administration, doctor, server, jobs, report export |
| `launcher/` | Relative-path PowerShell install/diagnostics/menu |
| `tests/`, `examples/` | Local bare remotes, mock REST, real MCP protocol and runnable demo |

## Job boundaries

`CREATED → SNAPSHOT_READY → PATCHING → PREVIEW_READY → COMMITTING → COMMITTED → VERIFIED → PUBLISHING → PUBLISHED → COMPLETED`.

`NO_CHANGE`, `CHECK_FAILED`, `CANCELLED`, `RECOVERY_REQUIRED` are persisted outcomes. Other errors have typed codes and preserve the last durable stage rather than pretending that every specification state is implemented. Approval is a grant tied to a fingerprint, not a mutable tool argument. Check results contain exit codes, not stdout/source/secret values.

## Frozen Git objects

Approved desired blobs are stored in the owned clone's Git object database. The full final tree and plan are persisted before commit creation. For each path, reset only the isolated index to the last verified parent, install one approved blob/deletion, verify its staged diff, and call `git commit-tree`. Update the job branch atomically with `git update-ref <new> <expected-old>`. Reconcile the actual chain against the frozen plan after every update. This plumbing-based implementation produces real normal commits and intentionally does not execute hooks, filters from global config, or repository scripts as part of committing.

An interruption between object creation and ref update leaves an unreachable object; no duplicate branch commit results. Between ref update and DB save, recovery discovers the actual ref chain. Final HEAD tree must exactly match the frozen approved tree. This is independent of hash-based file checksums used for edit concurrency.

## Trust and limitations

The local OS user owns the config, vault and DB. A process able to edit these can act as an administrator. This is not protection against a compromised same-user OS account. Clones preserve committed content, not dirty user edits. Repository reads fetch the allowlisted origin and detach the owned cache at the current default branch. Jobs always use a new clone and fresh base. ETag caching, parallel jobs and container runners are not implemented. See [coverage](REQUIREMENTS.md).

## Windows distribution entrypoints

One windowed EXE dispatches GUI, internal HTTP/stdio workers and explicit CLI
modes before importing Qt. Workers run in isolated processes using the same EXE,
with inherited pipes restored, bounded restart and authenticated ownership checks.
Bundled resources and vendor tools resolve inside `_MEIPASS`; writable state stays
in the per-user data directory. Prepared vendor tools retain their original layout.
The single build stages intermediates outside dist and publishes one EXE.
See RELEASE_BUILD.md and LICENSE_COMPLIANCE.md.
