# One genuinely changed path per commit

Final path set is obtained from a NUL-delimited, rename-disabled diff of the recorded base tree and frozen desired tree. Paths sort deterministically. Multiple edits of one path collapse into its final blob. A deletion is a separate nonempty commit. Strict renames are two commits; atomic two-path rename exceptions are unsupported and cannot be enabled.

Every commit must have exactly one parent, one changed path and the approved content/mode at that path. The entire chain ends at the approved tree. No `--allow-empty`, fabricated timestamps, force-push, broad staging or user-worktree reset is used. Conventional subjects and an `AI-assisted: GitHub-AI-MCP` trailer are required.

The engine uses `git add -A -- <declared-path>` to capture the desired snapshot. Commit building installs only that path's frozen index entry, checks the staged diff and whitespace, creates the tree/commit through plumbing and atomically advances the branch. Only the owned clone's index is reset with `read-tree`; the user's index is never opened.

## Inspect a completed offline job

Use the `fixture_root` from `examples/local_demo.py`, then the UUID and target branch from its report. The work directory is `<fixture_root>/state/jobs/<UUID>/work`.

```powershell
git -C WORK_DIR log --format="%H %s" BASE_SHA..HEAD
git -C WORK_DIR diff-tree --no-commit-id --name-only --no-renames -r PARENT_SHA COMMIT_SHA
git -C WORK_DIR rev-parse 'HEAD^{tree}'
git -C WORK_DIR diff --name-only --no-renames BASE_SHA HEAD
git -C WORK_DIR ls-remote origin refs/heads/ai/BRANCH
```

Each `diff-tree` output has precisely the report's path; HEAD tree equals report `final_tree`; remote SHA equals report `final_sha` after a verified local push. The demo emits real local evidence, not GitHub commit links.

Whitespace validation treats CR at EOL as a line terminator; LF and CRLF bytes remain distinct in Git objects. Executable mode can be specified explicitly. Git-attribute normalization that changes submitted bytes stops with `FILTER_TRANSFORM`. Symlinks/gitlinks and LFS pointer writes stop. Windows case-colliding trees stop. A case-only rename on Windows needs a separate dedicated workflow and is not claimed as supported.

Intermediate commits may be temporarily inconsistent; only the approved final state is checked before publication. Required tests must be explicitly configured by a trusted human; no repository-discovered commands run automatically.
