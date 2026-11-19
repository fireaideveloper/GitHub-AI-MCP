# MASTER IMPLEMENTATION SPECIFICATION
## GitHub-AI-MCP: Secure MCP Server for AI-Assisted GitHub Development

**Target:** Windows 10/11 x64 (portable architecture for Linux/macOS) | **Product UI and end-user docs:** Russian by default, English localization included.  
**User:** A developer delegating repository analysis, code changes, commits, and publication to ChatGPT or another MCP-compatible AI client.  
**Deliverable:** A complete, installable, tested application and source archive—not an architectural proposal or mockup.

**Preferred Git commit author email: `author@example.invalid`.** Configure `user.email` per authorized working repository, never globally without consent. Check, where technically possible, whether the email is verified on the authenticated GitHub account; otherwise report `unverified`. An email is **not** an authentication credential. Do not impersonate other authors.

---

# 0. ROLE AND REQUIRED DELIVERABLES

Act as a senior Python architect, Git/GitHub engineer, Model Context Protocol (MCP) specialist, DevSecOps engineer, Windows deployment engineer, and UX developer. **DESIGN AND IMPLEMENT the complete, functional `GitHub-AI-MCP` project.** Create actual code, tests, examples, installation scripts, documentation, and configuration. When the environment supports files, package everything into a ZIP. Never claim that a file was created, a test passed, or GitHub was updated unless you actually verified it.

Deliver:

1. Architecture explaining boundaries between the AI client, MCP server, local Git engine, and GitHub.
2. Complete source tree with actual implementations—not placeholders.
3. A Python MCP server using the current stable MCP specification and official SDK; pin validated compatible versions.
4. A local Git engine enforcing **one genuinely changed file path per separate nonempty commit**.
5. Repository reading, permissions, branches, fast-forward push, Pull Requests, and verified commit links.
6. Working Windows one-click launcher, desktop GUI, and CLI.
7. Access modes, explicit approvals, dry runs, audit logs, crash recovery.
8. Correct commit identity and honest diagnostics for GitHub Contributions (without guarantees).
9. Automated unit, integration, security, and E2E tests; offline demo requiring no real GitHub token.
10. English `README.md` linking to full `README_RU.md`, plus architecture, security, setup, API, troubleshooting, and example AI prompts.
11. An accurate report of executed checks and untested scenarios.
12. If ZIP generation is impossible, provide a reproducible complete set of files instead of generic advice.

Do not ask optional clarification questions. Choose secure, documented defaults and make them configurable.

**Nonnegotiable principles:** User code and Git history take priority over commit counts; never create empty, misleading, repeated, artificially dated, or fabricated activity. Local commits are not the same as remote publication. No network writes without policy authorization. Never bypass branch protection, rulesets, reviews, or CI. GitHub need not be open in a browser; the local MCP service runs only while its process is active. The MCP server does not expose or capture a model's private internal reasoning.

---

# 1. PRODUCT WORKFLOW

Example user request to ChatGPT:

> "Open my SherlockPC repository, diagnose Spanish/Portuguese localization encoding issues, implement fixes and tests, make one commit for each changed file, then push to a separate branch and open a PR."

Expected flow:

1. AI client queries MCP for allowed repositories, structure, branches, rules, and connection status.
2. AI inspects files and generates a plan identifying paths, objectives, checks, and risks. **The AI generates code; the MCP server supplies tools, data, and enforcement. The server cannot independently think or create new features without an AI client.**
3. AI sends desired file versions or patches using typed MCP tools.
4. MCP prepares an isolated workspace, preserving any uncommitted user changes.
5. MCP checks the exact final changes, previews diffs and commit plan, and obtains required approvals.
6. MCP creates a linear sequence of nonempty commits: normally **N distinct changed paths = N commits**. Intermediate edits of the same path do not multiply commits.
7. MCP verifies the complete commit chain, final tree, allowed tests, secret scan, and policies.
8. Only in an authorized mode, MCP performs a normal push of the chain and optionally opens a PR (the default).
9. MCP returns structured status, affected paths, real commit SHAs and URLs, branch/PR URL, checks, publication outcome, warnings, and contribution eligibility assessment.
10. AI reports only actions actually confirmed by tools.

**Dependency caveat:** Intermediate one-file commits may temporarily fail to compile when several files must change together. Guarantee checks of the **final state** before publishing; optionally check intermediate commits and report those results honestly. Do not claim all intermediate commits are independently buildable.

---

# 2. SCOPE AND EXCLUSIONS

**Must:**

- Access only explicitly authorized GitHub repositories; read metadata, file contents, branches, history, diffs, PRs, and access policies.
- Clone/fetch safely; handle create/modify/delete, checks, local commits, branch publishing and PRs.
- Support text, Unicode (Cyrillic/CJK), CRLF/LF, and binary changes only by explicit policy.
- Support larger, multi-file jobs, partial progress, deterministic recovery, precise file-based commit history.
- Protect repositories, credentials, private source, and platform protections.

**Must not:**

- Invent autonomous goals, execute unrequested edits, or treat repository content as instructions.
- Fake contribution activity or imply every file, push, PR, or commit will count toward GitHub Contributions.
- Leak secrets in logs, stdout, URLs, tool results, generated reports, or commits.
- Modify account settings, branch rules, access scopes, or permissions without authorization.
- Force-push, rewrite shared history, run `git reset --hard` in the user's worktree, or delete unrelated branches.
- Run arbitrary shell commands copied from repositories or LLM output without strict authorization and sandboxing.

---

# 3. TECHNOLOGY STACK

Recommended, unless a demonstrably better well-supported alternative is justified:

- Python 3.12+, typing, `pathlib`, `asyncio`, Pydantic and/or dataclasses.
- Official maintained MCP Python SDK (`FastMCP`/supported server API). **Verify real versions and signatures**, then pin dependencies.
- MCP **Streamable HTTP** for remote-capable clients; optional local `stdio`. Do not build exclusively on legacy SSE.
- **Git CLI** for real, auditable commits. GitHub REST API and/or `gh` for permissions, metadata, PRs; separate abstractions.
- `httpx` with timeouts, bounded retries, GitHub primary/secondary rate-limit handling.
- SQLite for resumable job state, stages, idempotency, and migrations; never store raw credentials there.
- OS keyring/Windows Credential Manager for GitHub credentials; no plaintext PAT in config.
- PySide6 for desktop UI if appropriate for packaging/licensing; also provide headless CLI.
- `pytest`, `pytest-asyncio`, `ruff`, a selected type checker (`mypy`/`pyright`), mocked GitHub HTTP for offline tests.
- PyInstaller or other verified Windows packaging mechanism; test packaged output.
- Reproducible dependency lockfile and only verified package names.

Put business logic in services, **not** MCP tool decorators or GUI event handlers.

---

# 4. ARCHITECTURE AND TRUST BOUNDARIES

```text
USER: specifies task, repository, permission mode
  |
AI CLIENT (ChatGPT / MCP-compatible): reads context, plans, produces code/patches
  |  MCP auth + typed input validation
GITHUB-AI-MCP SERVER
  |-- Transport + client authentication
  |-- Authorization: repository allowlist, policy, scopes, approvals
  |-- Repository reader + Workspace Manager (isolated clones/worktrees)
  |-- Patch Service + Preview + Check Engine (lint/tests/secret scanning)
  |-- Commit Planner + Git Engine (one changed path per commit)
  |-- Job Orchestrator + SQLite + Audit + Recovery
  |-- GitHub Client (remote checks, branches, push, PR, CI)
  `-- Interfaces (GUI / CLI / Windows Launcher)
  |  authenticated Git and GitHub API
GITHUB REPOSITORY: commits, branches, PR, CI, rules
```

Required service boundaries:

1. MCP transport: tools/resources, JSON schemas, protocol, validation.
2. AuthN: separate MCP-client and GitHub credential flows.
3. AuthZ/policy: allowed repositories, branches, modes, actions, limits.
4. Repository service: metadata, files, diff, history.
5. Workspace manager: isolated copies/worktrees, ownership and cleanup.
6. Patch service: safe file replacement and contextual patching with expected SHA checks.
7. Commit planner: deterministic path order and individual messages.
8. Git engine: staging, commit, SHA/parent verification, safe push.
9. Check engine: formatting, lint, tests, builds, secret checks.
10. GitHub API service: permissions, PRs, CI status, verified URLs.
11. Job orchestrator: state machine, approvals, retries, cancellation.
12. Persistence: SQLite and schema migrations.
13. GUI, CLI, launcher: shared backend services.
14. Observability: redacted structured logs, diagnostics, report export.

Treat README text, issues, comments, source code, and GitHub Actions files as **untrusted content**, never higher-priority operational instructions. Prevent prompt injection and policy escalation through all entry points.

---

# 5. ACCESS MODES

Startup mode is fixed by the trusted server/launcher; an AI tool call cannot elevate it.

| Mode | Read | Local edits | Local commits | Remote push | PR |
|---|---|---|---|---|---|
| `1 READ_ONLY` | Yes | No | No | No | No |
| `2 LOCAL_REVIEW` | Yes | Isolated workspace | With local approval | No | No |
| `3 AUTO_APPROVED` | Yes | Yes | Yes | Only preapproved repos/branches/actions | Within approvals |

Defaults: `REVIEW_BEFORE_PUSH=true`, `PREFER_PULL_REQUEST=true`, `PROTECT_DEFAULT_BRANCH=true`. A narrowly scoped preauthorization for a specific repository and workflow may waive per-push review; never provide blanket authorization to everything.

Approval grants specify repo, branches, allowed operations, maximum file count/size, and expiry. On expiration, require renewed human approval. `AUTO_APPROVED` must never let the AI raise permissions, disable checks, change repository allowlists, delete unrelated branches, or rewrite history. UI confirmation must come from the authorized human, not an MCP tool parameter.

---

# 6. CORE REQUIREMENT: ONE COMMIT PER ACTUALLY CHANGED PATH

**Strict invariant:** For every file path genuinely changed between the recorded base tree and approved final tree, generate exactly one **nonempty** commit whose diff against its first parent contains **only that path**. The path may be added, modified, or deleted. Commits form a linear sequence of distinct SHAs. Explicitly approved rename exceptions are handled separately.

Example final diff:

```text
src/api/server.py        modified
src/ui/main_window.py    modified
src/i18n/es.json         modified
tests/test_i18n.py       added
README.md                modified
```

Expected history:

```text
BASE
  └─ C1  fix(api): improve backend request handling              [src/api/server.py]
      └─ C2  fix(ui): correct localization rendering             [src/ui/main_window.py]
          └─ C3  fix(i18n): normalize Spanish strings            [src/i18n/es.json]
              └─ C4  test(i18n): cover localized punctuation      [tests/test_i18n.py]
                  └─ C5  docs(readme): document localization fix [README.md]
```

Implementation algorithm:

1. Diff `base SHA` against the **approved final snapshot**, excluding unchanged, ignored, temporary, or unapproved files.
2. Record base SHA; create a separate clean commit-building clone/worktree with verified clean index/HEAD. **Never stage user-worktree changes.**
3. Compute and freeze the full desired final tree; sort changed paths deterministically for understandable history. Keep the final desired snapshot separate from the commit worktree as needed.
4. For each path, apply that path's approved final content or deletion to current HEAD; stage **only that path** using safe argument-array subprocess (`git add -- <path>` or `git add -A -- <path>` for deletion). Never use unscoped `git add .`/`git add -A` to produce these commits.
5. Check `git diff --cached --name-only -z`, `git diff --cached --check`, exactly one staged path, and after committing verify the parent-to-commit diff via `git diff-tree`. Use NUL-delimited paths to handle whitespace, Cyrillic, special characters, and Unicode correctly.
6. Create one actual nonempty commit per path with a meaningful Conventional-Commits-style subject; never use `--allow-empty` to inflate activity.
7. Persist verified SHA, path, parent, and progress after every commit.
8. Require `HEAD^{tree}` to match the **approved final tree** byte-for-byte (Git tree semantics). On mismatch, stop; never push.
9. Execute approved lint/tests/build and secret/policy checks against the final tree. Block publication if required checks fail pending a new approved decision/fix.
10. Verify upstream branch/ref, expected remote SHA, and permissions; use normal **fast-forward push** only—never force by default.

Edge cases:

- No actual diff: `NO_CHANGE`, zero commits.
- Multiple revisions of the same file within one job: **one final commit**, not one commit per tool call.
- File deletion: separate nonempty deletion commit.
- Rename `old -> new`: Strict mode produces two path commits (old deletion, new addition), documenting temporary inconsistency. Optional `PRESERVE_RENAMES`, with human approval, may create one atomic two-path commit, **explicitly marked as an exception**; never claim it meets strict one-path invariant.
- Symlinks, gitlinks/submodules: block write by default; require dedicated opt-in and safety handling.
- Git LFS: detect pointers, size constraints, client availability and credentials; honor GitHub limits.
- File mode changes (100644/100755) count as a changed path.
- Case-only rename on Windows: correctly distinguish and handle both paths.
- Equal basenames in separate folders are separate paths.
- Hooks/filters modifying staged files: recheck staged content and post-commit diff; never silently accept extra paths or disable hooks without informed approval.
- Production file + test file: two commits; validate combined final code.
- Large jobs: configurable per-job file count, bytes, duration, approval thresholds; safe batch recovery without duplicate commits.

**Critical acceptance test:** Given 17 ordinary distinct paths changed in the approved snapshot, create exactly 17 nonempty commits, each changing exactly one corresponding path, and make `BASE..HEAD` match the approved final diff. Given no changes, create zero commits.

---

# 7. HONEST AUTHORSHIP AND GITHUB CONTRIBUTIONS

Separate Git commits from GitHub profile Contributions; platform rules can change and must be checked against official documentation.

1. Configure `user.name` / preferred `user.email=author@example.invalid` **locally per working repository**, only when that identity is authorized. Optionally support a real account-linked GitHub `noreply` email. Do not alter global Git config without permission.
2. Verify association/verification of the author email with the authenticated GitHub user when permissions and APIs allow; otherwise return `unknown` or `unverified`, not a guess.
3. Distinguish **Git author**, **Git committer**, **GitHub API actor**, and **AI assistance**. Do not present bot-authored changes as manually written by somebody else. Support configurable transparent `AI-assisted` attribution/trailer where appropriate.
4. Present `contribution_eligibility: likely | not_eligible | unknown`, with diagnostic reasons and explicit non-guarantee.
5. Consider email attribution, non-fork repository requirement, default branch or `gh-pages`, account/repository participation rules, private contribution visibility, and processing delays. **Do not promise any numeric contribution count.**
6. Feature-branch commits usually are not yet counted as default-branch commits. Squash merging typically does not preserve every original SHA on default branch; warn users and prefer a history-preserving merge only if permitted by repository rules.
7. No backdating, fabricated activity, empty commit shells, or misleading attribution.
8. Report `created_commits`, `pushed_commits`, `PR_created`, and `observed_profile_contributions` **separately**; only populate the last field with genuinely verified information.

Official references:
- https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference
- https://docs.github.com/en/account-and-profile/how-tos/contribution-settings/troubleshooting-missing-contributions
- https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address

---
# 8. REQUIRED MCP API: TOOLS AND RESOURCES

Implement a compact, coherent, documented tool set with typed **input/output JSON Schemas**, strict validation, bounded response sizes, standard error codes, repository/job identifiers, and explicit policy context. Prefer the following consistent names (adjust grouping only when demonstrably safer):

### Read and diagnostics

- `github_mcp.health_check`: server/SDK/Git versions, GitHub connectivity, active mode, transport security, supported capabilities; no secrets.
- `github_mcp.list_repositories`: only authorized/allowlisted repositories.
- `github_mcp.get_repository_info`: default branch, fork, visibility, access rights, protection/rulesets.
- `github_mcp.list_branches`: branches and head SHAs.
- `github_mcp.list_tree`: bounded, paginated tree; skip dangerous/oversized content by policy.
- `github_mcp.read_file`: content, encoding, hash, size; explicit binary handling.
- `github_mcp.read_files_batch`: constrained total payload, secure batch reads.
- `github_mcp.get_diff`: diff between refs, branches, or job snapshots.
- `github_mcp.get_git_status`: **job workspace**, not a user's unrelated worktree.
- `github_mcp.list_recent_commits`: history and identity.
- `github_mcp.check_contribution_eligibility`: honest eligibility diagnostics.

### Planning and mutations

- `github_mcp.create_job`: repo, base ref/SHA, target branch, policy, idempotency key.
- `github_mcp.plan_changes`: paths, intent, operation types, planned checks, commit messages.
- `github_mcp.write_file`: create/replace one sandbox file with expected base SHA/checksum.
- `github_mcp.apply_patch`: contextual validation and preview, only for declared paths.
- `github_mcp.delete_file`: delete a precisely validated path.
- `github_mcp.preview_job`: reviewed diffs, redactions, commits, risks.
- `github_mcp.run_checks`: allowlisted checks in an isolated environment; never arbitrary shell.
- `github_mcp.create_file_commits`: freeze snapshot, verify invariants, create path-only local commits.
- `github_mcp.get_job_status`: state, warnings, progress, existing SHAs and activity.
- `github_mcp.cancel_job`: safe cancellation and recoverable state.
- `github_mcp.resume_job`: idempotent restart recovery.

### Publication

- `github_mcp.publish_branch`: authorized fast-forward push or new branch publication.
- `github_mcp.create_pull_request`: title, description, changes and test results.
- `github_mcp.get_remote_status`: upstream SHA, URLs, PR, remote CI.
- `github_mcp.get_job_report`: precise machine-readable and readable final report.

State-changing operations must return actual outcomes and IDs, never generic success messages. No tool may accept arbitrary out-of-workspace filesystem paths, arbitrary subprocess commands, or unvalidated hosts/URLs receiving GitHub tokens. Do not expose secrets through tool responses.

Example `create_job` input:

```json
{
  "repository": "owner/repo",
  "base_ref": "main",
  "target_branch": "ai/localization-fix",
  "commit_mode": "one_path_per_commit",
  "publish_strategy": "pull_request",
  "idempotency_key": "client-generated-unique-operation-id",
  "expected_base_sha": "verified-base-commit-sha"
}
```

Illustrative report (NOT a claim of a real GitHub action):

```json
{
  "job_id": "job-example",
  "status": "PUBLISHED",
  "base_sha": "example-base-sha",
  "final_sha": "example-final-sha",
  "files_changed": 3,
  "commits_created": 3,
  "commits_pushed": 3,
  "commits": [
    {"path": "src/a.py", "sha": "example-1", "status": "pushed"},
    {"path": "src/b.py", "sha": "example-2", "status": "pushed"},
    {"path": "tests/test_a.py", "sha": "example-3", "status": "pushed"}
  ],
  "checks": {"lint": "passed", "tests": "passed", "secrets": "passed"},
  "pull_request_url": "https://github.com/owner/repo/pull/42",
  "contribution_eligibility": "unknown",
  "warnings": ["Feature branch commits may not count until merged"]
}
```

---

# 9. JOB STATE MACHINE AND RESILIENCE

Implement explicit states:

```text
CREATED → SNAPSHOT_READY → PATCHING → PREVIEW_READY → APPROVED
        → PRECHECKED → COMMITTING → COMMITTED → VERIFIED
        → PUBLISHING → PUBLISHED → COMPLETED

CHECK_FAILED | AUTH_REQUIRED | PERMISSION_DENIED | REMOTE_DIVERGED
RETRYABLE_ERROR | CANCELLED | RECOVERY_REQUIRED
```

Persist `job_id`, `request_id`, timestamps, state, base/current SHA, changeset fingerprint, last successful commit, and outcome after each critical step. Logs must never include secrets or private source contents by default.

- `resume_job` must validate state and avoid duplicate commits/pushes.
- Lock by repository/target branch across parallel jobs (SQLite/file locks), with stale-lock recovery.
- If remote advances unexpectedly, **stop**; offer safe new task/rebase/PR options, never force-push.
- If the network dies **after** a successful push but before local acknowledgment, inspect the remote SHA before retrying.
- If 8 of 10 commits were created when the process crashed, continue from commit 9, preserving validated existing SHAs.
- Cleanup only owned job workspaces, honoring retention/TTL and cancellation; never delete arbitrary user paths.
- Enforce file count, total bytes, duration, paginated previews, and skipped-file reporting.
- Keep a local, secure audit record with explicit retention controls.

---

# 10. GITHUB AUTHENTICATION, MCP SECURITY, FILE SAFETY

**There are two independent trust/auth layers:** (1) MCP client → local/remote MCP server, and (2) MCP server → GitHub API/Git transport. A GitHub PAT does **not** protect an internet-exposed MCP endpoint.

### GitHub auth

- Personal Windows setup: optionally fine-grained PAT limited to specific repos and minimal privileges, stored in Windows Credential Manager.
- Scalable deployment: prefer a GitHub App with scoped permissions and short-lived installation tokens; accurately reflect app vs human commit attribution.
- GUI must support setup/login, scopes, token expiry, accessible repositories, logout and revoke instructions.
- `git push` uses a secure credential helper/GitHub CLI/short-lived credentials. Never embed tokens in Git remote URLs, CLI arguments, stdout, or tracked files.
- Request `Contents` read/write and `Pull requests` write only where necessary; no gratuitous `Administration` permission.

### MCP endpoint

- Local: bind **only** to `127.0.0.1`, e.g. `http://127.0.0.1:8766/mcp`.
- Remote ChatGPT: require HTTPS and **MCP-compatible client authorization** (relevant OAuth discovery/token validation or a correctly configured auth gateway). Verify actual capabilities against the **current published** protocol and client documentation; do not invent setup steps.
- Enforce `Host`/`Origin`, DNS-rebinding protections, authenticated mutating tools, request limits, rate limits and scopes.
- Never expose an unauthenticated localhost server through a public tunnel. HTTPS reverse proxies/tunnels are allowed only with a complete verified trust model, TLS, AuthN/AuthZ, client allowlists and rate limits.
- If secure client compatibility cannot be implemented, state the limitation and provide working local alternatives rather than claiming any tunnel works with ChatGPT.
- Warn about private repository content sent to third-party AI clients; never make a repository public merely for integration.

### Files, secrets and execution

- Deny `.git/`, `.env` (allow explicitly reviewed `.env.example`), secrets, SSH keys, token stores, credential dumps, system paths, and other configured sensitive files.
- Normalize and resolve paths; reject `../`, absolute paths, symlink escapes, UNC/device paths outside the workspace; account for case-insensitive Windows filesystems, reserved device names, and long paths.
- Scan changes for secrets **before push**. Report safe file/type indicators without disclosing the detected credential.
- Running repository tests/build scripts is potential **untrusted code execution**. Prefer containers/sandboxed runners; otherwise use a narrow command allowlist and explicit approval for untrusted scripts. Warn about isolation limitations.
- Apply payload bounds, careful encoding, structured redaction, safe exceptions, and protected local ports.
- `READ_ONLY` must prohibit **every** write, including branch/PR creation.

---

# 11. BRANCHES, PUSH, PR, CI, RULESETS

- Default: new `ai/<slug>-<job-short-id>` branch → normal push → PR → CI/review.
- Direct default-branch pushes require a separately enabled owner policy; **disabled by default**.
- Detect branch protection, rulesets, mandatory checks, reviews, signed-commit requirements, blocked direct pushes, and GitHub App restrictions.
- If signing is required, configure legitimate GPG/SSH signing using the user's permitted key or stop with precise guidance. Never forge verified signatures.
- PR description sections: `Summary`, `Files Changed`, `Testing`, `Commit Breakdown`, `Security/Compatibility Notes`, and job-report link.
- Warn that squash merge changes the resulting commit history; never bypass repository rules for metrics.
- Distinguish local test success, remote CI pending, remote CI passed/failed.
- Return typed errors and safe recovery advice on authentication failures, GitHub API limits, conflicts, network errors, and protection denials.

---

# 12. WINDOWS ONE-CLICK LAUNCHER AND GUI

A user who unzips the project on Windows must be able to run it without guessing directories or editing hard-coded paths.

Required launcher files:

```text
dist/GitHub-AI-MCP.exe
src/github_ai_mcp/desktop/entry.py
launcher/install.ps1
launcher/check_environment.ps1
launcher/README_RU.md
```

**Launcher requirements:**

- Derive project paths using `$PSScriptRoot` / script location, never fixed `C:\Users\...` paths or archive folder names.
- Check Python, Git, virtual environment, pinned packages, available port, and GitHub login; offer venv/install with consent.
- Russian-language startup menu (English language option may be added):

```text
=== GitHub-AI-MCP — One Click Launcher ===
1 — Read Only (READ_ONLY)
2 — Local Changes and Commits (LOCAL_REVIEW)
3 — Approved Automation and Publishing (AUTO_APPROVED)
4 — Diagnostics: Git / Python / GitHub / MCP
5 — Settings
0 — Exit
Select mode [1]:
```

- Mode 3 must display approved repos/branches/actions and request **local human** privilege confirmation; an AI-invoked flag or tool parameter must not bypass it.
- On errors, preserve console visibility and show actionable diagnostics: Python/Git versions, missing script/package, port issues, log path.
- Gracefully handle Ctrl+C, GUI close, service shutdown; preserve resumable jobs.
- Show the MCP endpoint **without credentials**, auth status, and accurate client-specific connection instructions.

**Functional, polished GUI**, ideally light/dark themes:

1. Dashboard: GitHub login, MCP status, active mode, allowed repository count.
2. Repositories: allowlist, default branch, protection status, last sync.
3. Jobs: state, per-file progress, retries, warnings.
4. Change Review: real diff viewer, paths, per-file commit previews, risk indicators.
5. Commit History: path → commit SHA → GitHub link, push and CI state.
6. Contributions Diagnostics: emails, fork status, branch eligibility, truthful caveats.
7. Settings: port, transport, default mode, author, allowlists, limits, scanning, exceptions.
8. Logs/Support: redacted logs, diagnostics export, README links.

All buttons must perform actual operations. Visually distinguish `created locally`, `pushed`, `PR opened`, and `CI passed`.

---

# 13. RECOMMENDED REPOSITORY STRUCTURE

You may improve file names, but preserve layers and documentation links. Do not create empty ornamental files; every module must have a purpose and valid implementation.

```text
GitHub-AI-MCP/
├── README.md
├── README_RU.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── pyproject.toml
├── uv.lock                       # or lockfile from chosen package manager
├── .gitignore
├── .env.example                 # no real credentials
├── config/
│   ├── config.example.yaml
│   └── policy.example.yaml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SECURITY_MODEL.md
│   ├── MCP_CONNECTION.md
│   ├── GITHUB_AUTH.md
│   ├── COMMIT_SEMANTICS.md
│   ├── CONTRIBUTIONS.md
│   ├── TROUBLESHOOTING_RU.md
│   └── API_REFERENCE.md
├── src/github_ai_mcp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── server.py
│   ├── config.py
│   ├── exceptions.py
│   ├── models.py
│   ├── mcp/
│   │   ├── tools_read.py
│   │   ├── tools_write.py
│   │   ├── tools_publish.py
│   │   └── resources.py
│   ├── security/
│   │   ├── auth_mcp.py
│   │   ├── auth_github.py
│   │   ├── policy.py
│   │   ├── paths.py
│   │   ├── secret_scan.py
│   │   └── redaction.py
│   ├── core/
│   │   ├── repositories.py
│   │   ├── workspaces.py
│   │   ├── patching.py
│   │   ├── commit_planner.py
│   │   ├── git_engine.py
│   │   ├── github_api.py
│   │   ├── job_engine.py
│   │   ├── checks.py
│   │   ├── contributions.py
│   │   └── reports.py
│   ├── storage/
│   │   ├── database.py
│   │   └── migrations/
│   ├── gui/
│   │   ├── app.py
│   │   ├── main_window.py
│   │   └── views/
│   └── cli/
│       └── app.py
├── launcher/
│   ├── GitHub-AI-MCP.spec
│   ├── start.ps1
│   ├── install.ps1
│   ├── check_environment.ps1
│   └── README_RU.md
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   ├── e2e/
│   └── fixtures/
├── examples/
│   ├── local_demo.py
│   ├── mcp_client_example.py
│   ├── request_examples_ru.md
│   └── sample_repository/
└── .github/
    └── workflows/
        ├── test.yml
        └── security.yml
```

If you reorganize paths, update every reference in installation scripts and docs.

---
# 14. CONFIGURATION AND POLICY

Example configuration (adapt to the implemented validated schema; **no secrets in YAML**):

```yaml
app:
  name: GitHub-AI-MCP
  locale: ru
  data_dir: auto_user_data_dir

mcp:
  transport: streamable_http
  host: 127.0.0.1
  port: 8766
  require_auth_for_remote: true
  remote_enabled: false

permissions:
  mode: READ_ONLY
  allowed_repositories: []
  protect_default_branch: true
  default_publish_strategy: pull_request
  approval_before_push: true
  allow_force_push: false
  allow_repo_admin_actions: false

commits:
  strategy: one_path_per_commit
  preserve_renames: false
  allow_empty_commits: false
  use_current_timestamp: true
  conventional_messages: true
  annotate_ai_assistance: true
  require_final_tree_match: true
  max_files_per_job: 100

git:
  isolated_workspace: true
  reject_dirty_user_workspace: false
  no_user_worktree_mutation: true
  author_email: author@example.invalid  # preferred; verify before use

checks:
  verify_diff: true
  detect_secrets: true
  run_repo_commands_only_when_trusted: true
  require_tests_before_push: true
  test_commands_allowlist: []

logging:
  redact_secrets: true
  retention_days: 14
```

`reject_dirty_user_workspace: false` **does not permit modifying or capturing dirty user changes**. It means dirty user workspaces need not block jobs because all operations occur in independent clean copies. AI-written repository files and tool arguments cannot change server-wide authorization or escalate privileges. Configuration changes require trusted local administration.

---

# 15. AUTOMATED TEST MATRIX

Run the main test suite **offline** using local `git init` and bare Git remotes. Run live network/GitHub E2E tests only after explicit opt-in, with a dedicated test repository.

### Git and commit invariants

- 1 added file → exactly 1 nonempty commit.
- 5 modified paths → exactly 5 nonempty commits, each affecting only its path.
- 12 modified + 5 added → exactly **17 commits** with matching final diff.
- 1 deleted file → exactly 1 deletion commit.
- 3 AI patches to one file before finalization → exactly 1 final commit for that path.
- Unchanged content → 0 commits.
- Foreign staged changes in a user's repo never enter the job's commits.
- Final committed tree equals approved preview/snapshot.
- Strict rename vs explicitly authorized `PRESERVE_RENAMES` exception.
- Paths with Cyrillic, spaces, parentheses, emoji, nested paths; Windows case-only rename.
- CRLF/LF, executable-bit changes, and allowed binary payloads.
- Hooks/filters must not silently stage a second path or alter approved final content.

### Security

- Reject `../escape`, absolute paths, symlink escapes, `.git/config`, Windows devices, unauthorized paths.
- A secret in a patch blocks push and is redacted from diagnostic output.
- `READ_ONLY` blocks all mutating tools, including branch/PR creation.
- AI cannot upgrade authorization through any MCP call.
- Missing/expired GitHub credentials and unapproved repositories return typed denials.
- Invalid remote MCP client authentication fails closed.
- Reports/logs never expose raw credentials or protected private content.
- Untrusted repository test commands do not execute without sandbox/approval.

### Reliability and concurrency

- Network failure before, during, and after actually successful push (acknowledgment lost).
- Remote branch advanced, conflicts, protected default branch, failed CI.
- Crash during commit 7 of 10, resume without duplicate commits.
- Two simultaneous jobs targeting one branch, lock correctness and stale-lock recovery.
- API rate limits, oversized files, unavailable Git LFS.
- Cancellation before/after commit, server shutdown, duplicate client request/idempotency key.

### End-to-end

1. Initialize a local bare remote and a sample repository, perform an MCP job changing 3–5 paths, inspect individual commit diffs and final tree.
2. Read a public repository without write rights.
3. Demonstrate that `READ_ONLY` cannot push.
4. Publish to a **fully local** test remote and compare SHAs.
5. Test Windows launcher startup and understandable missing Python/Git errors.
6. Verify PR creation against a **mock** GitHub API; use a real test repo only with user-granted test credentials.

Clearly distinguish mock results, offline integration, and authenticated real-GitHub E2E results. Never label a mocked outcome as verified real GitHub behavior.

---

# 16. PERFORMANCE, UX, AND DIAGNOSTICS

- Large repositories: paginated trees, path search, context/output limits. Never dump hundreds of files into one MCP response.
- Safely cache by SHA/ETag with correct invalidation.
- Use bounded retries with jitter/backoff for GitHub rate limits; no infinite loops.
- Preserve UTF-8 and correct Cyrillic display on Windows and in PowerShell (avoid console-codepage mojibake).
- Display actionable status messages (e.g. `Publishing blocked: 2 tests failed`) rather than only stack traces.
- CLI minimum: `doctor`, `serve`, `gui`, `repo list`, `job list`, `job status`, `job resume`, `job cancel`.
- `github-ai-mcp doctor`: Python/Git versions/paths, GitHub connectivity and permissions, endpoint accessibility, operating mode/policy, safe redacted output.
- Export job reports as static JSON and Markdown for precise summaries by AI clients.

---

# 17. README AND END-USER INSTRUCTIONS

**`README.md` is the primary English entry point.** Include the value proposition, features, Mermaid architecture diagram, **only authentic screenshots** of an actual implemented GUI, quick start, permissions matrix, link to complete `README_RU.md`, API/documentation links, and troubleshooting.

**`README_RU.md` is a full Russian-language Windows setup guide**, with:

1. Download and extract ZIP.
2. Start `dist/GitHub-AI-MCP.exe`.
3. Select mode.
4. Authenticate securely using supported GitHub PAT/App workflow.
5. Select allowed repositories.
6. Run `doctor`, confirm endpoint and protection.
7. Connect ChatGPT or another MCP-compatible client using a **verified supported** method.
8. Test a read-only command.
9. Run a local sample repository commit job (**never start in a production repository**).
10. Preview and check an approved real-repo change, then publish according to permissions.

Explain that **one path per Git commit does not mean one contribution per file or one green square per commit**. Provide accurate FAQ for private repositories, unmerged PR branches, email attribution, signed commits, branch eligibility, and profile-graph delays.

Include at least 10 ready-to-use prompts for ChatGPT, in English and/or Russian versions:

1. "Show the project tree and explain its architecture; do not modify anything."
2. "Locate a bug and propose a plan, but do not publish."
3. "Fix four files, create one separate commit per changed file, and show the diffs."
4. "Add localization tests and publish a PR after verification."
5. "Compare base SHA with remote and stop if it diverged."
6. "Show the report with commit SHAs, GitHub links, and CI outcomes."
7. "Why have my commits not appeared in GitHub Contributions?"
8. "Resume the interrupted job without duplicating commits."
9. "Cancel publication and keep the local audit report."
10. "Run authorized security checks before publishing."

---

# 18. IMPLEMENTATION PHASES (DO NOT STOP AFTER PLANNING)

- **A — Core:** typed models/policies, Git/workspaces, patches, path-only commits, SQLite, Git invariant tests.
- **B — MCP:** transport, auth, schemas, tools, client examples, offline integration tests.
- **C — GitHub:** API, credential handling, remote links, safe push, PRs, divergence, branch permissions.
- **D — Product UX:** Windows one-click launcher, CLI, GUI, Russian localization, light/dark UI.
- **E — Hardening:** secret scanning, filesystem traversal defenses, concurrency, crash recovery, signing requirements, CI statuses, docs.
- **F — Delivery:** lint, type-check, tests, fresh-extract Windows setup verification, full ZIP, evidence-based final report.

Implementation may be incremental internally, but the **deliverable must be the most complete runnable application achievable**, not promises of later stages. Classify every feature as implemented, partially implemented, or not implemented, and indicate actual test coverage.

---

# 19. STRICT ACCEPTANCE CRITERIA

The work is complete only when:

1. A clean extracted archive installs without manual fixes to imports/paths.
2. Windows launcher discovers project files relative to itself, never hard-coding user profiles.
3. MCP `tools/list` exposes real tools and `health_check` works.
4. `READ_ONLY` can read approved repositories but cannot create files, commits, branches, PRs, or push.
5. Offline example changing 5 paths produces 5 distinct nonempty commits.
6. Each commit diff affects its expected single path; authorized rename exceptions are explicit and tested.
7. Final Git tree equals approved changes and excludes unrelated staged edits.
8. Failed required checks block push.
9. `.git/`, secrets, and workspace escapes cannot be modified through tools.
10. GUI and CLI call the same functional backend and show accurate state.
11. MCP-client and GitHub authentication are separate; remote exposure requires real client auth.
12. Divergent remote cannot be overwritten by force.
13. Idempotency and interruption recovery have been tested.
14. Contributions are explained accurately, without false guarantees.
15. English/Russian READMEs, API docs, launcher docs, and sample prompts exist.
16. `pytest` and lint pass in available environment, **or** exact blockers and redacted logs are provided.
17. A fully offline, token-free local demo works.
18. Remote success claims carry genuine confirmed SHAs/URLs, never fabricated evidence.
19. Existing user work is preserved; no unscoped `git add .`, user-worktree `git reset --hard`, or force-push.
20. Complete source is supplied as a ZIP or fully reproducible file set.

---

# 20. REQUIREMENT CONFLICT PRIORITY

1. **Security and preservation of Git history/user work.**
2. Correctness of the final published project.
3. Functional MCP integration and reproducible installation.
4. One commit per genuinely changed path.
5. Windows one-click workflow and functional GUI.
6. Optional visual polish.

If path-only commits conflict with mandatory atomic changes or protected branch rules, **do not break Git or violate rules**. Explain the exception and obtain a safe user-approved choice.

---

# 21. OFFICIAL REFERENCES TO VERIFY DURING IMPLEMENTATION

- MCP specification: https://modelcontextprotocol.io/specification
- Official MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- GitHub REST API: https://docs.github.com/en/rest
- Git commit API: https://docs.github.com/en/rest/git/commits
- Git tree API: https://docs.github.com/en/rest/git/trees
- Repository rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- Protected branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- Contributions: https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference
- Missing contributions: https://docs.github.com/en/account-and-profile/how-tos/contribution-settings/troubleshooting-missing-contributions
- GitHub Apps: https://docs.github.com/en/apps/overview

Recheck current stable SDK, protocol, and GitHub docs at development time. If internet access is unavailable, explicitly identify unverifiable assumptions and avoid inventing API features.

---

# 22. REQUIRED FINAL RESPONSE FROM THE IMPLEMENTING MODEL

Provide:

1. Brief architecture rationale (maximum 1–2 pages).
2. Actual project tree and responsibility of each layer.
3. Complete runnable source code, preferably as a **downloadable ZIP**.
4. Safe Windows 10/11 install and first-launch instructions.
5. Accurate MCP-client/ChatGPT connection steps, including client-specific limitations.
6. Verifiable demo of path-only commits, with inspection commands; explicitly mark illustrative examples vs real remote changes.
7. Tests executed: commands, counts, passed/failed/skipped, redacted error details.
8. Crash-recovery and credential-protection explanation.
9. Remaining risks and incomplete features, if any.
10. Sample user request demonstrating authorized end-to-end automation.

**START IMPLEMENTING NOW.** Do not stop at design, replace code with mockups, or ask permission for noncritical engineering decisions. Require separate actual authorization before interacting with the user's real GitHub account, changing live repositories, or publishing remotely.
