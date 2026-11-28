"""MCP tool descriptions and parameter metadata; no authorization logic."""

TOOL_DEFINITIONS = {
    "health_check": [
        "Report local runtime versions, operating mode, transport capabilities and Git availability. Call first to diagnose startup; does not verify GitHub connectivity or change configuration.",
        {}
    ],
    "list_repositories": [
        "List the repository identifiers allowed by local policy. Call before selecting a repository; an empty list means no repositories are configured. Returns repositories, not all repositories accessible to the GitHub account.",
        {}
    ],
    "get_repository_info": [
        "Inspect an allowlisted repository's metadata, default branch and available GitHub information. Use before creating a job; remote sources may require vault credentials. Returns metadata, not file contents.",
        {
            "repository": "Allowlisted owner/repo identifier from list_repositories."
        }
    ],
    "list_branches": [
        "List up to 200 local and remote refs with commit SHAs for an allowlisted repository. Refreshes the local read cache from the source; does not publish changes. Use to identify a base branch.",
        {
            "repository": "Allowlisted owner/repo identifier."
        }
    ],
    "list_tree": [
        "Browse safe tracked entries in the default-branch snapshot. Returns entries, total and next_offset; use next_offset for subsequent pages. Refreshes the local read cache and excludes unsafe paths.",
        {
            "repository": "Allowlisted owner/repo identifier.",
            "offset": "Zero-based entry offset; default 0.",
            "limit": "Page size, 1–200 entries; default 100."
        }
    ],
    "read_file": [
        "Read a safe file from the default-branch snapshot or an existing job workspace. Returns content, encoding, byte count and SHA-256 checksum for subsequent edits; text reads also return snapshot SHA. Secret scanning and file-size limits apply.",
        {
            "repository": "Allowlisted owner/repo identifier; must match the job if supplied.",
            "path": "Repository-relative file path, not an absolute path.",
            "job_id": "Optional existing job ID to read its workspace instead of the default branch.",
            "binary": "Allow base64 output for non-UTF-8 content; default false."
        }
    ],
    "read_files_batch": [
        "Read 1–20 safe UTF-8 files from the same refreshed default-branch snapshot. Returns a files array with content and checksums; total content is limited to 2 MB. Use read_file for job workspace or binary reads.",
        {
            "repository": "Allowlisted owner/repo identifier.",
            "paths": "List of 1–20 repository-relative file paths."
        }
    ],
    "get_diff": [
        "Inspect the existing job's Git diff against its base commit without modifying the workspace. Returns redacted diff text capped at 100,000 characters and a truncation flag. Use preview_job for approval fingerprints and per-file previews.",
        {
            "job_id": "Existing job identifier returned by create_job."
        }
    ],
    "get_git_status": [
        "Inspect the isolated job workspace's short Git status and recorded job state. Use before preview or recovery to identify outstanding changes; does not edit or publish files.",
        {
            "job_id": "Existing job identifier returned by create_job."
        }
    ],
    "list_recent_commits": [
        "List recent commits from the refreshed default-branch snapshot. Returns redacted tab-separated lines containing SHA, author name, author email and subject; does not alter history.",
        {
            "repository": "Allowlisted owner/repo identifier.",
            "limit": "Number of commits, 1–100; default 20."
        }
    ],
    "check_contribution_eligibility": [
        "Estimate whether commits on a branch may qualify for GitHub contribution attribution based on repository and verified identity metadata. Returns eligibility and reasons; never guarantees or measures profile contributions. Local sources return unknown.",
        {
            "repository": "Allowlisted owner/repo identifier.",
            "branch": "Branch name to evaluate, e.g. main."
        }
    ],
    "get_job_status": [
        "Read the recorded state and summary of an existing job, including branch, commits, checks and PR URL when available. Use to inspect progress before choosing the next action; does not refresh remote status.",
        {
            "job_id": "Existing job identifier returned by create_job."
        }
    ],
    "get_remote_status": [
        "Compare a job's target branch with its recorded current SHA and retrieve available GitHub CI/check-run information. Returns remote_sha, matches, ci and PR URL; network access and credentials may be needed. Does not push or retry publication.",
        {
            "job_id": "Existing job identifier returned by create_job."
        }
    ],
    "get_job_report": [
        "Retrieve a job summary and its audit history, including recorded commits, checks, warnings and PR URL. Use for final reporting or troubleshooting; contribution attribution is not guaranteed. Does not change the job.",
        {
            "job_id": "Existing job identifier returned by create_job."
        }
    ],
    "create_job": [
        "Create an isolated local Git workspace and task branch from an allowlisted repository. Requires write-enabled local policy. Supply a short English task name for automatic branch naming; protected base/default branches cannot be targets. Returns job metadata including id, base SHA and state; use id for subsequent tools. Does not push.",
        {
            "repository": "Allowlisted owner/repo identifier.",
            "idempotency_key": "Stable unique request key, 1–100 characters; reuse for retries of the same job.",
            "target_branch": "Optional explicit safe task branch; omit for automatic naming.",
            "expected_base_sha": "Optional expected base commit SHA; mismatches stop creation.",
            "base_ref": "Optional simple source branch name; defaults to configured default branch.",
            "task_name": "Optional short English task title, e.g. fix tunnel startup; used to generate a unique branch."
        }
    ],
    "plan_changes": [
        "Declare or update intended file changes for an editable job before writing, patching or deleting files. Maps each path to its conventional commit subject. Returns job ID and sorted planned paths. Invalidates preview fingerprint and check results; does not edit files or create commits.",
        {
            "job_id": "Existing editable job identifier returned by create_job.",
            "messages": "Object mapping repository-relative paths to conventional commit subjects, e.g. {\"src/app.py\":\"fix: handle timeout\"}. Subjects must use a supported type and 3–120 character message."
        }
    ],
    "write_file": [
        "Create or replace a planned file in an editable job workspace. For existing files, first read_file with the job ID and supply its checksum; for new files use null. Returns path, SHA-256 checksum and byte count. Invalidates preview and checks; does not commit or push.",
        {
            "job_id": "Existing editable job identifier.",
            "path": "Planned repository-relative file path.",
            "content": "Complete replacement content, UTF-8 text or base64 according to encoding.",
            "expected_checksum": "Current SHA-256 checksum for an existing file; null for a new file.",
            "encoding": "utf-8 (default) or base64; binary writes require trusted policy.",
            "executable": "Optional executable-bit setting; null preserves existing behavior."
        }
    ],
    "apply_patch": [
        "Replace an exact, uniquely occurring UTF-8 text fragment in a planned job file. Read the file first and supply its checksum. Rejects missing or ambiguous context instead of fuzzy matching. Returns path, new checksum and byte count; invalidates preview and checks without committing.",
        {
            "job_id": "Existing editable job identifier.",
            "path": "Planned repository-relative file path.",
            "old_text": "Nonempty exact text that occurs once in the current file.",
            "new_text": "Replacement text; may be empty to remove the fragment.",
            "expected_checksum": "Current SHA-256 checksum from read_file for this job workspace."
        }
    ],
    "delete_file": [
        "Remove a planned existing file from the isolated job workspace after verifying its checksum. Returns path and deleted status; invalidates preview and checks. Destructive locally, but does not commit or remove a remote file until separately authorized publication.",
        {
            "job_id": "Existing editable job identifier.",
            "path": "Planned repository-relative file path to delete.",
            "expected_checksum": "Current SHA-256 checksum from read_file for this job workspace."
        }
    ],
    "preview_job": [
        "Inspect and, when needed, prepare a review snapshot of a job's changes. May update local job state and fingerprint under write policy. Returns paginated per-file diffs, fingerprint, final tree and warnings; review every page before requesting trusted local approval. Does not grant approval or publish.",
        {
            "job_id": "Existing job identifier.",
            "offset": "Zero-based change offset; default 0.",
            "limit": "Page size, 1–50 changes; default 20."
        }
    ],
    "run_checks": [
        "Run locally configured checks against a prepared job snapshot and record results. Requires preview first; configured host commands run only with trusted local authorization and are not OS-sandboxed. Returns passed, check results and isolation information; does not grant approval or publish.",
        {
            "job_id": "Existing job identifier with a prepared final tree."
        }
    ],
    "create_file_commits": [
        "Create one real local commit per changed path from the reviewed job snapshot, then verify the final tree. Requires applicable local approval and policy; may reconcile an already completed commit chain. Returns job report with commit SHAs and checks. Does not push.",
        {
            "job_id": "Existing job identifier with reviewed snapshot and applicable local commit approval."
        }
    ],
    "cancel_job": [
        "Mark an existing job CANCELLED while retaining its workspace. Requires write policy. Returns job ID, state and workspace_retained. Does not undo existing commits, pushes or pull requests.",
        {
            "job_id": "Existing job identifier to cancel."
        }
    ],
    "resume_job": [
        "Recover an interrupted job by inspecting recorded state, local commits and remote branch where applicable. May resume authorized local commits, verify checks or reconcile publication; refuses divergent remotes. Returns current job report. Does not grant approval or blindly retry pushes.",
        {
            "job_id": "Existing interrupted job identifier."
        }
    ],
    "publish_branch": [
        "Publish a verified job's task branch to its configured remote after applicable local push approval, policy and checks. Revalidates final tree and remote expectations; refuses divergence and protected branches. Returns job report; changes remote state and does not create a PR.",
        {
            "job_id": "Existing verified job identifier with applicable push approval."
        }
    ],
    "create_pull_request": [
        "Create or reconcile a GitHub pull request for a published job branch into the configured default branch. Requires applicable local PR approval and matching remote SHA. Returns URL and existing flag; does not merge. GitHub credentials and permissions are required.",
        {
            "job_id": "Existing published job identifier with applicable PR approval.",
            "title": "Nonempty PR title, at most 200 characters.",
            "description": "PR summary/body text, at most 10,000 characters; server adds commit and test details."
        }
    ]
}
