"""Shared application service. No AI inputs can grant permissions or configure checks."""
import base64
import difflib
import functools
import hashlib
import json
import os
import re
import subprocess
import unicodedata

from github_ai_mcp.desktop.processes import run_background
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from github_ai_mcp.config import Config
from github_ai_mcp.core.git_engine import Git
from github_ai_mcp.core.github_api import GitHub
from github_ai_mcp.core.locking import lock
from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.paths import safe_path
from github_ai_mcp.security.policy import Policy
from github_ai_mcp.security.secret_scan import redact, scan
from github_ai_mcp.storage.database import Database


def task_branch_name(title: str) -> str:
    """A flat, English-language Git branch slug derived from a task title.

    MCP clients should translate non-English requests into a short English task
    title before calling create_job. This function does not pretend to translate.
    """
    if not 1 <= len(title) <= 200 or any(ord(ch) < 32 for ch in title):
        raise AppError("INVALID_INPUT", "Task title must be 1–200 characters, single-line")
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    if not normalized.strip() and title.strip():
        raise AppError("INVALID_INPUT", "Provide a short English task title for branch naming")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:100].rstrip("-")
    if not slug or not re.match(r"[a-z]", slug):
        raise AppError("INVALID_INPUT", "Task title must start with an English word")
    return slug


def is_safe_task_branch(name: str) -> bool:
    """New branches have no namespace; older ai/* jobs stay compatible."""
    return bool(re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name)
                or re.fullmatch(r"ai/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", name))


def numbered_task_branch(base: str, index: int) -> str:
    suffix = f"-{index}"
    return base[:120 - len(suffix)].rstrip("-") + suffix


def reject_case_collisions(paths):
    """Reject case-only file or directory aliases before touching a Windows worktree.

    Check every path component, not just complete filenames: Docs/a and docs/b
    would otherwise silently share a physical directory on Windows.
    """
    seen: dict[str, str] = {}
    for path in sorted(set(paths)):
        components = []
        for component in path.split("/"):
            components.append(component)
            prefix = "/".join(components)
            folded = prefix.casefold()
            other = seen.setdefault(folded, prefix)
            if other != prefix:
                raise AppError("CASE_COLLISION", "Case-insensitive path collision denied")


def serialized(function):
    @functools.wraps(function)
    def wrapped(self, *args, **kwargs):
        # Deliberately serialize all operations across GUI, CLI and MCP processes.
        with lock(self.root / "locks", "service"):
            return function(self, *args, **kwargs)
    return wrapped


class Service:
    def __init__(self, config: Config, github: GitHub | None = None):
        self.config = config
        self.root = config.data_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = Database(self.root / "jobs.sqlite3")
        self.policy = Policy(config, self.db)
        self.git = Git(config.git_timeout)
        self.github = github or GitHub()

    def health_check(self) -> dict:
        import importlib.metadata
        import sys
        try:
            git_status = self.git.text(self.root, "--version")
        except AppError:
            git_status = "Unavailable"
        return {"python": sys.version.split()[0], "git": git_status,
                "sdk": importlib.metadata.version("mcp"), "mode": self.config.mode,
                "endpoint": f"http://127.0.0.1:{self.config.port}/mcp",
                "remote_enabled": False, "capabilities": ["stdio", "streamable-http", "strict-path-commits"],
                "github_connectivity": "not_checked", "auth": "local process / HTTP bearer vault"}

    def list_repositories(self) -> dict:
        return {"repositories": list(self.config.repositories)}

    def _work(self, job: dict) -> Path:
        # Paths are always derived from a UUID, never from caller-supplied job fields.
        return self.root / "jobs" / str(uuid.UUID(job["id"])) / "work"

    def _job(self, job_id: str, mutable=False) -> dict:
        job = self.db.get(job_id)
        self.policy.repo(job["repository"])
        if mutable:
            self.policy.write()
            if job["state"] == "CANCELLED":
                raise AppError("CANCELLED", "Job cancelled; create a new job")
        return job

    def _editable(self, job):
        if job.get("commits") or job["state"] not in {"SNAPSHOT_READY", "PATCHING", "PREVIEW_READY", "CHECK_FAILED"}:
            raise AppError("INVALID_STATE", "Frozen or published job cannot be edited")

    def _cached(self, repository: str) -> Path:
        repo = self.policy.repo(repository)
        path = self.root / "read_cache" / hashlib.sha256(repository.encode()).hexdigest()
        if not path.exists():
            self.git.clone(repo.source, path)
        else:
            if self.git.text(path, "remote", "get-url", "origin") != repo.source:
                raise AppError("CACHE_SOURCE_CHANGED", "Configured source changed; remove only the owned read_cache entry locally")
            self.git.run(path, "fetch", "--prune", "origin")
        self.git.run(path, "checkout", "--detach", "refs/remotes/origin/" + repo.default_branch)
        return path

    @serialized
    def get_repository_info(self, repository: str) -> dict:
        repo = self.policy.repo(repository)
        if repo.source.startswith("https://github.com/"):
            return self.github.info(repository)
        path = self._cached(repository)
        return {"repository": repository, "default_branch": repo.default_branch,
                "head": self.git.text(path, "rev-parse", "HEAD"), "github": "local source; unknown"}

    @serialized
    def list_branches(self, repository: str) -> dict:
        path = self._cached(repository)
        return {"refs": self.git.text(path, "for-each-ref", "--format=%(refname) %(objectname)",
                                      "refs/heads", "refs/remotes").splitlines()[:200]}

    @serialized
    def list_tree(self, repository: str, offset: int = 0, limit: int = 100) -> dict:
        if not 0 <= offset or not 1 <= limit <= 200:
            raise AppError("INVALID_INPUT", "Invalid pagination")
        path = self._cached(repository)
        entries = []
        for name, entry in self.git.tree(path).items():
            try:
                safe_path(path, name)
            except AppError:
                continue
            entries.append({"path": name, **entry})
        return {"entries": entries[offset:offset+limit], "total": len(entries),
                "next_offset": offset + limit if offset + limit < len(entries) else None}

    def _read(self, work: Path, path: str, binary: bool = False) -> dict:
        dest = safe_path(work, path)
        if not dest.is_file():
            raise AppError("NOT_FOUND", "File unavailable")
        if dest.stat().st_size > self.config.max_file_bytes:
            raise AppError("LIMIT_EXCEEDED", "File exceeds configured limit")
        content = dest.read_bytes()
        scan(content)
        sha = hashlib.sha256(content).hexdigest()
        try:
            text = content.decode("utf-8")
            if b"\0" in content:
                raise UnicodeDecodeError("utf-8", content, 0, 1, "binary")
            return {"path": path, "content": text, "encoding": "utf-8", "checksum": sha, "bytes": len(content),
                    "snapshot_sha": self.git.text(work, "rev-parse", "HEAD")}
        except UnicodeDecodeError:
            if not binary:
                raise AppError("BINARY_DENIED", "Explicit binary read required") from None
            return {"path": path, "content": base64.b64encode(content).decode(), "encoding": "base64",
                    "checksum": sha, "bytes": len(content)}

    @serialized
    def read_file(self, repository: str, path: str, job_id: str | None = None, binary: bool = False) -> dict:
        self.policy.repo(repository)
        if job_id:
            job = self._job(job_id)
            if job["repository"] != repository:
                raise AppError("PERMISSION_DENIED", "Job belongs to another repository")
            work = self._work(job)
        else:
            work = self._cached(repository)
        return self._read(work, path, binary)

    @serialized
    def read_files_batch(self, repository: str, paths: list[str]) -> dict:
        if not 1 <= len(paths) <= 20:
            raise AppError("LIMIT_EXCEEDED", "Read 1–20 paths per batch")
        work = self._cached(repository)
        items = [self._read(work, p) for p in paths]
        if sum(i["bytes"] for i in items) > 2_000_000:
            raise AppError("LIMIT_EXCEEDED", "Batch too large")
        return {"files": items}

    @serialized
    def list_recent_commits(self, repository: str, limit: int = 20) -> dict:
        if not 1 <= limit <= 100:
            raise AppError("LIMIT_EXCEEDED", "Limit must be 1–100")
        work = self._cached(repository)
        data = self.git.text(work, "log", f"-{limit}", "--format=%H%x09%an%x09%ae%x09%s")
        return {"commits": redact(data).splitlines()}

    @serialized
    def create_job(self, repository: str, idempotency_key: str, target_branch: str | None = None,
                   expected_base_sha: str | None = None, base_ref: str | None = None,
                   task_name: str | None = None) -> dict:
        """Create an isolated job. Supply an English task_name to auto-name its branch.

        Example: task_name='fix tunnel startup' creates fix-tunnel-startup; if
        taken, fix-tunnel-startup-2, etc. An AI client should translate the
        user's task into English before calling this tool. target_branch is
        an optional explicit override. Old ai/* branches remain supported.
        """
        self.policy.write()
        repo = self.policy.repo(repository)
        if not 1 <= len(idempotency_key) <= 100:
            raise AppError("INVALID_INPUT", "Idempotency key must be 1–100 characters")
        previous = self.db.by_key(idempotency_key)
        if previous:
            if (previous["repository"] != repository
                    or (target_branch and previous["target_branch"] != target_branch)
                    or (task_name is not None and previous.get("task_name") != task_name)):
                raise AppError("IDEMPOTENCY_CONFLICT", "Key already used for different job")
            return previous
        base_branch = base_ref or repo.default_branch
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", base_branch):
            raise AppError("INVALID_INPUT", "Base ref must be a simple branch name")
        ident = str(uuid.uuid4())
        automatic = target_branch is None
        base_name = ""
        if automatic:
            if task_name is not None:
                base_name = task_branch_name(task_name)
            else:
                # Legacy clients supply only an idempotency key. A UUID or an
                # opaque key is not a task title: retain a safe fallback.
                try:
                    base_name = task_branch_name(idempotency_key)
                except AppError:
                    base_name = "task-" + ident[:8]
                if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{27,}", idempotency_key.lower()):
                    base_name = "task-" + ident[:8]
        target = base_name if automatic else target_branch
        if not is_safe_task_branch(target) or len(target) > 120:
            raise AppError("PERMISSION_DENIED", "Target must be a safe task branch without a prefix")
        if target in {repo.default_branch, base_branch}:
            raise AppError("PERMISSION_DENIED", "Base/default branch publication forbidden")
        if automatic:
            index = 2
            while self.db.branch_owned(repository, target) or target in {repo.default_branch, base_branch}:
                if index > 1000:
                    raise AppError("BUSY", "No available task branch name")
                target = numbered_task_branch(base_name, index)
                index += 1
        elif self.db.branch_owned(repository, target):
            raise AppError("BUSY", "Existing active job owns branch")
        job: dict = {"id": ident, "repository": repository, "idempotency_key": idempotency_key,
               "target_branch": target, "base_branch": base_branch, "task_name": task_name,
               "state": "CREATED", "created_at": time.time(),
               "commits": [], "checks": {}, "plan": {}, "warnings": [], "pr_url": None}
        self.db.save(job, "CREATED")
        work = self._work(job)
        try:
            self.git.clone(repo.source, work)
            self.git.run(work, "check-ref-format", "--branch", repo.default_branch)
            base = self.git.text(work, "rev-parse", "refs/remotes/origin/" + base_branch)
            if expected_base_sha and expected_base_sha != base:
                raise AppError("BASE_MISMATCH", "Expected base differs from default branch SHA")
            if automatic:
                # Check the remote, not just the local job DB: a real GitHub
                # branch may already exist. No force-push or branch reuse.
                index = 2
                while self.git.remote_sha(work, target) is not None:
                    if index > 1000:
                        raise AppError("BUSY", "No available task branch name")
                    candidate = numbered_task_branch(base_name, index)
                    index += 1
                    if (candidate in {repo.default_branch, base_branch}
                            or self.db.branch_owned(repository, candidate)):
                        continue
                    target = candidate
                if target != job["target_branch"]:
                    job["target_branch"] = target
                    self.db.save(job, "TARGET_BRANCH_SELECTED")
            self.git.run(work, "checkout", "-b", target, base)
            # Identity is configured locally only, after trusted local authorization.
            if repo.identity_authorized:
                self.git.run(work, "config", "--local", "user.name", repo.author_name)
                self.git.run(work, "config", "--local", "user.email", repo.author_email)
            job.update(base_sha=base, current_sha=base, base_tree=self.git.text(work, "rev-parse", "HEAD^{tree}"),
                       expected_remote=self.git.remote_sha(work, target), state="SNAPSHOT_READY")
            self.db.save(job, "SNAPSHOT_READY")
        except AppError:
            job["state"] = "RECOVERY_REQUIRED"
            self.db.save(job, "CREATE_FAILED")
            raise
        return job

    @serialized
    def plan_changes(self, job_id: str, messages: dict[str, str]) -> dict:
        job = self._job(job_id, True)
        self._editable(job)
        if len(set(job["plan"]) | set(messages)) > self.config.max_files:
            raise AppError("LIMIT_EXCEEDED", "Too many planned paths")
        # Check against the tracked base and all planned paths, before any writes.
        reject_case_collisions([*self.git.tree(self._work(job), job["base_sha"]),
                                *job["plan"], *messages])
        for path, message in messages.items():
            safe_path(self._work(job), path)
            if not re.fullmatch(r"(?:feat|fix|docs|test|refactor|chore|style|perf|build|ci)(?:\([\w.-]+\))?: [^\r\n]{3,120}", message):
                raise AppError("INVALID_INPUT", "Meaningful conventional commit subject required")
            scan(message.encode())
        job["plan"].update(messages)
        job["fingerprint"] = ""
        job["checks"] = {}
        self.db.save(job, "PLANNED")
        return {"job_id": job_id, "planned_paths": sorted(job["plan"])}

    def _expected(self, dest: Path, expected_checksum: str | None):
        actual = hashlib.sha256(dest.read_bytes()).hexdigest() if dest.is_file() else None
        if actual != expected_checksum:
            raise AppError("STALE_FILE", "Expected checksum differs from workspace; read the file again")

    def _write(self, job, path: str, data: bytes, expected_checksum: str | None, executable: bool | None):
        self._editable(job)
        if path not in job["plan"]:
            raise AppError("UNPLANNED_PATH", "Declare path and intent before editing")
        work = self._work(job)
        # Protect jobs saved by older versions whose plan was not checked.
        reject_case_collisions([*self.git.tree(work, job["base_sha"]), *job["plan"], path])
        dest = safe_path(work, path)
        self._expected(dest, expected_checksum)
        if len(data) > self.config.max_file_bytes:
            raise AppError("LIMIT_EXCEEDED", "File too large")
        scan(data)
        if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise AppError("LFS_UNSUPPORTED", "LFS writes require a dedicated client workflow")
        tree_entry = self.git.tree(work).get(path)
        if tree_entry and tree_entry["mode"] not in {"100644", "100755"}:
            raise AppError("UNSUPPORTED_MODE", "Symlink and submodule edits forbidden")
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_name(dest.name + ".mcp-tmp-" + uuid.uuid4().hex)
        temp.write_bytes(data)
        if dest.exists():
            temp.chmod(dest.stat().st_mode)
        if executable is not None:
            temp.chmod(0o755 if executable else 0o644)
        os.replace(temp, dest)
        if executable is not None:
            job.setdefault("requested_modes", {})[path] = "100755" if executable else "100644"
        job.update(state="PATCHING", fingerprint="", checks={})
        self.db.save(job, "FILE_WRITTEN")
        return {"path": path, "checksum": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

    @serialized
    def write_file(self, job_id: str, path: str, content: str, expected_checksum: str | None = None,
                   encoding: str = "utf-8", executable: bool | None = None) -> dict:
        job = self._job(job_id, True)
        if encoding == "base64":
            if not self.policy.repo(job["repository"]).allow_binary:
                raise AppError("BINARY_DENIED", "Binary writes disabled in trusted policy")
            try:
                data = base64.b64decode(content, validate=True)
            except ValueError:
                raise AppError("INVALID_INPUT", "Invalid base64") from None
        elif encoding == "utf-8":
            data = content.encode("utf-8")
            if b"\0" in data:
                raise AppError("BINARY_DENIED", "Use explicit binary policy for NUL content")
        else:
            raise AppError("INVALID_INPUT", "Encoding must be utf-8 or base64")
        return self._write(job, path, data, expected_checksum, executable)

    @serialized
    def apply_patch(self, job_id: str, path: str, old_text: str, new_text: str,
                    expected_checksum: str) -> dict:
        """Exact contextual replacement. Context must occur exactly once; never fuzzy apply."""
        job = self._job(job_id, True)
        dest = safe_path(self._work(job), path)
        self._expected(dest, expected_checksum)
        raw = dest.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise AppError("BINARY_DENIED", "Context patch requires UTF-8") from None
        if not old_text or text.count(old_text) != 1:
            raise AppError("PATCH_CONFLICT", "Patch context missing or ambiguous")
        return self._write(job, path, text.replace(old_text, new_text, 1).encode(), expected_checksum, None)

    @serialized
    def delete_file(self, job_id: str, path: str, expected_checksum: str) -> dict:
        job = self._job(job_id, True)
        self._editable(job)
        if path not in job["plan"]:
            raise AppError("UNPLANNED_PATH", "Plan path before deletion")
        dest = safe_path(self._work(job), path)
        self._expected(dest, expected_checksum)
        if not dest.is_file():
            raise AppError("NOT_FOUND", "File does not exist")
        dest.unlink()
        # Remove only empty parents inside this isolated worktree. No recursive deletion.
        parent = dest.parent
        work = self._work(job).resolve()
        while parent != work and parent.is_relative_to(work):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        job.update(state="PATCHING", fingerprint="", checks={})
        self.db.save(job, "FILE_DELETED")
        return {"path": path, "deleted": True}

    def _snapshot(self, job):
        work = self._work(job)
        if self.git.text(work, "rev-parse", "HEAD") != job["base_sha"]:
            raise AppError("INVALID_STATE", "Snapshot can only be made before committing")
        base = self.git.tree(work, job["base_sha"])
        # Validate before Git stages anything, including plans persisted pre-fix.
        reject_case_collisions([*base, *job["plan"]])
        self.git.run(work, "read-tree", "HEAD")
        for path in job["plan"]:
            safe_path(work, path)
            self.git.run(work, "add", "-A", "--", path)
            if path in job.get("requested_modes", {}) and safe_path(work, path).is_file():
                flag = "+x" if job["requested_modes"][path] == "100755" else "-x"
                self.git.run(work, "update-index", "--chmod=" + flag, "--", path)
        paths = self.git.paths(work, "diff", "--cached", "--name-only", "--no-renames", "-z", job["base_sha"])
        if len(paths) > self.config.max_files:
            raise AppError("LIMIT_EXCEEDED", "Too many changes")
        desired = self.git.tree(work, self.git.text(work, "write-tree"))
        reject_case_collisions([*base, *desired, *job["plan"]])
        total = 0
        changes = []
        for path in sorted(paths):
            if path not in job["plan"]:
                raise AppError("UNPLANNED_PATH", "Snapshot contains an undeclared path")
            safe_path(work, path)
            entry = desired.get(path)
            if entry:
                if entry["mode"] not in {"100644", "100755"}:
                    raise AppError("UNSUPPORTED_MODE", "Symlinks and gitlinks blocked")
                data = self.git.blob(work, entry["sha"])
                if len(data) > self.config.max_file_bytes:
                    raise AppError("LIMIT_EXCEEDED", "Blob too large")
                scan(data)
                if data != safe_path(work, path).read_bytes():
                    raise AppError("FILTER_TRANSFORM", "Git attributes transformed approved bytes; review attributes first")
                total += len(data)
            changes.append({"path": path, "entry": entry, "old": base.get(path), "message": job["plan"][path]})
        if total > self.config.max_job_bytes:
            raise AppError("LIMIT_EXCEEDED", "Job too large")
        tree = self.git.text(work, "write-tree")
        repo = self.policy.repo(job["repository"])
        identity = {"name": repo.author_name, "email": repo.author_email}
        fp = hashlib.sha256(json.dumps({"base": job["base_sha"], "tree": tree, "changes": changes, "identity": identity},
                                       sort_keys=True).encode()).hexdigest()
        return changes, tree, fp, total

    def _preview(self, job):
        changes, tree, fp, total = self._snapshot(job)
        repo = self.policy.repo(job["repository"])
        job["commit_identity"] = {"name": repo.author_name, "email": repo.author_email}
        job.update(changes=changes, final_tree=tree, fingerprint=fp, total_bytes=total, state="PREVIEW_READY")
        self.db.save(job, "PREVIEW_READY")
        return job

    @serialized
    def preview_job(self, job_id: str, offset: int = 0, limit: int = 20) -> dict:
        job = self._job(job_id)
        if not 0 <= offset or not 1 <= limit <= 50:
            raise AppError("INVALID_INPUT", "Invalid preview pagination")
        if job["state"] in {"SNAPSHOT_READY", "PATCHING", "PREVIEW_READY", "CHECK_FAILED"}:
            self.policy.write()
            job = self._preview(job)
        diffs = []
        work = self._work(job)
        for change in job.get("changes", [])[offset:offset+limit]:
            old = self.git.blob(work, change["old"]["sha"]) if change["old"] else b""
            new = self.git.blob(work, change["entry"]["sha"]) if change["entry"] else b""
            scan(new)
            lines = difflib.unified_diff(old.decode("utf-8", "replace").splitlines(True),
                                         new.decode("utf-8", "replace").splitlines(True),
                                         fromfile=change["path"], tofile=change["path"])
            diff = redact("".join(lines))
            diffs.append({"path": change["path"], "message": change["message"],
                          "diff": diff[:20000], "truncated": len(diff) > 20000,
                          "old_mode": (change["old"] or {}).get("mode"),
                          "new_mode": (change["entry"] or {}).get("mode")})
        return {"job_id": job_id, "fingerprint": job.get("fingerprint"), "final_tree": job.get("final_tree"),
                "state": job["state"], "count": len(job.get("changes", [])), "diffs": diffs,
                "warnings": ["Intermediate commits may not build", "Independent clone hooks/filters are intentionally disabled"],
                "next_offset": offset+limit if offset+limit < len(job.get("changes", [])) else None}

    @serialized
    def approve_local(self, job_id: str, fingerprint: str, actions: list[str]) -> dict:
        """Trusted local CLI/GUI only. NEVER register this method as an MCP tool."""
        job = self._job(job_id, True)
        if not job.get("fingerprint") or fingerprint != job["fingerprint"]:
            raise AppError("STALE_APPROVAL", "Preview fingerprint changed")
        if not set(actions) <= {"commit", "push", "pr"} or not actions:
            raise AppError("INVALID_INPUT", "Invalid approval actions")
        if job["state"] in {"PREVIEW_READY", "CHECK_FAILED"}:
            _, _, actual, _ = self._snapshot(job)
            if actual != fingerprint:
                raise AppError("STALE_APPROVAL", "Workspace changed since preview")
        if any(a in {"push", "pr"} for a in actions) and self.config.mode != "AUTO_APPROVED":
            raise AppError("PERMISSION_DENIED", "Remote approval requires AUTO_APPROVED")
        self.db.grant(job, actions)
        self.db.save(job, "HUMAN_APPROVAL_" + "_".join(actions))
        return {"approved": actions, "fingerprint": fingerprint, "expires_in_seconds": 3600}

    def _checks(self, job):
        work = self._work(job)
        repo = self.policy.repo(job["repository"])
        results: dict[str, dict[str, Any]] = {"secrets": {"passed": True}, "tree": {"passed": True}}
        for change in job.get("changes", []):
            if change["entry"]:
                scan(self.git.blob(work, change["entry"]["sha"]))
        for name in repo.required_checks:
            if not repo.trusted_execution or name not in repo.checks:
                raise AppError("EXECUTION_DENIED", "Required check needs trusted local command authorization")
            args = repo.checks[name]
            if not args or any("\x00" in a for a in args):
                raise AppError("INVALID_INPUT", "Invalid configured check")
            # No secret environment inherited by repository code. Host execution is explicit opt-in.
            env = {k: v for k, v in os.environ.items() if k in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG"}}
            try:
                p = run_background(args, cwd=work, env=env, capture_output=True, timeout=120)
                results[name] = {"passed": p.returncode == 0, "exit_code": p.returncode}
            except (OSError, subprocess.TimeoutExpired):
                results[name] = {"passed": False, "error": "unavailable or timeout"}
        # Check commands may mutate tracked or untracked files. Re-stage only approved paths and
        # detect tracked differences and untracked artifacts; refuse publication on any change.
        current_tree = self.git.text(work, "write-tree")
        diff = self.git.run(work, "diff", "--name-only", "-z")
        untracked = self.git.paths(work, "ls-files", "--others", "--exclude-standard", "-z")
        if diff or untracked or current_tree != job["final_tree"]:
            results["tree"] = {"passed": False, "error": "Check altered snapshot"}
        passed = all(r["passed"] for r in results.values())
        job["checks"] = results
        job["checked_tree"] = job["final_tree"] if passed else None
        if not passed:
            job["state"] = "CHECK_FAILED"
        elif job["state"] == "CHECK_FAILED" and job.get("commits"):
            # Recovery must not recreate commits or trust a stale database status.
            self._reconcile(job)
            if len(job["commits"]) != len(job.get("changes", [])):
                raise AppError("RECOVERY_REQUIRED", "Incomplete commit chain")
            if self.git.text(work, "rev-parse", "HEAD^{tree}") != job["final_tree"]:
                raise AppError("INVARIANT_FAILED", "Committed tree mismatch")
            job["state"] = "VERIFIED"
        self.db.save(job, "CHECKS_PASSED" if passed else "CHECK_FAILED")
        return {"passed": passed, "checks": results, "execution_isolation": "host opt-in; not an OS sandbox"}

    @serialized
    def run_checks(self, job_id: str) -> dict:
        job = self._job(job_id, True)
        if not job.get("final_tree"):
            raise AppError("INVALID_STATE", "Preview first")
        return self._checks(job)

    def _reconcile(self, job):
        work = self._work(job)
        expected_fingerprint = hashlib.sha256(json.dumps({"base": job["base_sha"],
            "tree": job["final_tree"], "changes": job.get("changes", []),
            "identity": job["commit_identity"]}, sort_keys=True).encode()).hexdigest()
        if expected_fingerprint != job["fingerprint"]:
            raise AppError("INVARIANT_FAILED", "Immutable snapshot fingerprint mismatch")
        head = self.git.text(work, "rev-parse", "HEAD")
        chain = self.git.text(work, "rev-list", "--reverse", job["base_sha"] + ".." + head).splitlines()
        if head != job["base_sha"] and not chain:
            raise AppError("INVARIANT_FAILED", "HEAD is not a descendant of the approved base")
        changes = job.get("changes", [])
        if len(chain) > len(changes):
            raise AppError("RECOVERY_REQUIRED", "Unexpected commit count")
        commits = []
        parent = job["base_sha"]
        for sha, change in zip(chain, changes):
            parents = self.git.text(work, "show", "-s", "--format=%P", sha).split()
            paths = self.git.paths(work, "diff-tree", "--no-commit-id", "--no-renames", "--name-only", "-r", "-z", parent, sha)
            if parents != [parent] or paths != [change["path"]]:
                raise AppError("INVARIANT_FAILED", "Commit parent or path invariant failed")
            identity = job["commit_identity"]
            author = self.git.text(work, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce", sha).split("\0")
            if author != [identity["name"], identity["email"], identity["name"], identity["email"]]:
                raise AppError("INVARIANT_FAILED", "Commit author/committer differs from approved identity")
            subject = self.git.text(work, "show", "-s", "--format=%B", sha)
            if subject != change["message"] + "\n\nAI-assisted: GitHub-AI-MCP":
                raise AppError("INVARIANT_FAILED", "Commit message differs from approved plan")
            entry = self.git.tree(work, sha).get(change["path"])
            if entry != change["entry"]:
                raise AppError("INVARIANT_FAILED", "Commit differs from frozen snapshot")
            commits.append({"path": change["path"], "sha": sha, "parent": parent, "status": "created_locally"})
            parent = sha
        job.update(commits=commits, current_sha=head)
        self.db.save(job, "RECOVERY_RECONCILED")

    def _commit(self, job):
        self.policy.authorize(job, "commit")
        work = self._work(job)
        if job["state"] not in {"COMMITTING", "RECOVERY_REQUIRED"}:
            if job["state"] not in {"PREVIEW_READY", "CHECK_FAILED"}:
                raise AppError("INVALID_STATE", "Preview changes before committing")
            _, tree, fp, _ = self._snapshot(job)
            if tree != job["final_tree"] or fp != job["fingerprint"]:
                raise AppError("STALE_APPROVAL", "Snapshot changed; preview and approve again")
            if not self._checks(job)["passed"]:
                raise AppError("CHECK_FAILED", "Required checks failed")
            job["state"] = "COMMITTING"
            self.db.save(job, "COMMITTING")
        self._reconcile(job)
        identity = job["commit_identity"]
        self.git.run(work, "config", "--local", "user.name", identity["name"])
        self.git.run(work, "config", "--local", "user.email", identity["email"])
        for change in job["changes"][len(job["commits"]):]:
            parent = job["current_sha"]
            self.git.run(work, "read-tree", parent)
            entry = change["entry"]
            if entry:
                self.git.run(work, "update-index", "--add", "--cacheinfo", entry["mode"], entry["sha"], change["path"])
            else:
                self.git.run(work, "update-index", "--force-remove", "--", change["path"])
            staged = self.git.paths(work, "diff", "--cached", "--no-renames", "--name-only", "-z", parent)
            if staged != [change["path"]]:
                raise AppError("INVARIANT_FAILED", "Exactly one nonempty staged path required")
            self.git.run(work, "diff", "--cached", "--check")
            tree = self.git.text(work, "write-tree")
            message = change["message"] + "\n\nAI-assisted: GitHub-AI-MCP\n"
            sha = self.git.run(work, "commit-tree", tree, "-p", parent, input=message.encode()).decode().strip()
            # Atomic compare-and-swap ref. If a crash precedes this, the unreachable object can be GC'd.
            self.git.run(work, "update-ref", "refs/heads/" + job["target_branch"], sha, parent)
            self._reconcile(job)
        if self.git.text(work, "rev-parse", "HEAD^{tree}") != job["final_tree"]:
            raise AppError("INVARIANT_FAILED", "Final tree does not match approved snapshot")
        self.git.run(work, "read-tree", "HEAD")
        job["state"] = "COMMITTED" if job["commits"] else "NO_CHANGE"
        self.db.save(job, job["state"])
        if not self._checks(job)["passed"]:
            raise AppError("CHECK_FAILED", "Final checks failed; publication blocked")
        if job["commits"]:
            job["state"] = "VERIFIED"
        self.db.save(job, "FINAL_TREE_VERIFIED")
        return self._report(job)

    @serialized
    def create_file_commits(self, job_id: str) -> dict:
        job = self._job(job_id, True)
        if job["state"] in {"VERIFIED", "PUBLISHED", "COMPLETED", "NO_CHANGE"}:
            self._reconcile(job)
            return self._report(job)
        if job["state"] == "CHECK_FAILED" and job.get("commits"):
            self._verify_completed(job)
            return self._report(job)
        return self._commit(job)

    def _verify_completed(self, job):
        self._reconcile(job)
        if not job["commits"] or len(job["commits"]) != len(job.get("changes", [])):
            raise AppError("RECOVERY_REQUIRED", "Incomplete commit chain")
        if self.git.text(self._work(job), "rev-parse", "HEAD^{tree}") != job["final_tree"]:
            raise AppError("INVARIANT_FAILED", "Approved final tree mismatch")
        if not self._checks(job)["passed"]:
            raise AppError("CHECK_FAILED", "Final checks failed")
        job["state"] = "VERIFIED"
        self.db.save(job, "FINAL_TREE_VERIFIED")

    @serialized
    def resume_job(self, job_id: str) -> dict:
        job = self._job(job_id, True)
        if job["state"] in {"COMMITTING", "RECOVERY_REQUIRED"} and job.get("final_tree"):
            return self._commit(job)
        if job["state"] == "CHECK_FAILED" and job.get("commits"):
            self._verify_completed(job)
            return self._report(job)
        if job["state"] == "PUBLISHING":
            remote = self.git.remote_sha(self._work(job), job["target_branch"])
            if remote == job["current_sha"]:
                job["state"] = "PUBLISHED"
                self.db.save(job, "PUSH_RECOVERED")
            elif remote != job["expected_remote"]:
                raise AppError("REMOTE_DIVERGED", "Remote changed; no automatic retry")
        return self._report(job)

    @serialized
    def cancel_job(self, job_id: str) -> dict:
        job = self._job(job_id, True)
        job["state"] = "CANCELLED"
        self.db.save(job, "CANCELLED")
        return {"job_id": job_id, "state": "CANCELLED", "workspace_retained": True}

    @serialized
    def get_git_status(self, job_id: str) -> dict:
        job = self._job(job_id)
        return {"status": redact(self.git.text(self._work(job), "status", "--short")), "state": job["state"]}

    @serialized
    def get_diff(self, job_id: str) -> dict:
        job = self._job(job_id)
        out = self.git.run(self._work(job), "diff", "--no-ext-diff", "--no-textconv", job["base_sha"])
        return {"diff": redact(out.decode("utf-8", "replace"))[:100000], "truncated": len(out) > 100000}

    @serialized
    def get_job_status(self, job_id: str) -> dict:
        return self._report(self._job(job_id))

    def _report(self, job):
        remote = job["state"] in {"PUBLISHED", "COMPLETED"}
        source = self.policy.repo(job["repository"]).source
        commits = [dict(c, status="pushed" if remote else "created_locally",
                        url=f"https://github.com/{job['repository']}/commit/{c['sha']}" if remote and source.startswith("https://github.com/") else None)
                   for c in job["commits"]]
        return {"job_id": job["id"], "repository": job["repository"], "state": job["state"],
                "base_sha": job.get("base_sha"), "final_sha": job.get("current_sha"),
                "final_tree": job.get("final_tree"), "fingerprint": job.get("fingerprint"),
                "target_branch": job["target_branch"], "created_commits": len(commits),
                "pushed_commits": len(commits) if remote else 0, "commits": commits,
                "checks": job["checks"], "pull_request_url": job["pr_url"],
                "contribution_eligibility": "unknown", "observed_profile_contributions": None,
                "warnings": job["warnings"] + ["Feature branches may count only after a qualifying merge; squash changes SHAs"]}

    @serialized
    def get_job_report(self, job_id: str) -> dict:
        job = self._job(job_id)
        report = self._report(job)
        report["audit"] = self.db.audit(job_id)
        return report

    @serialized
    def check_contribution_eligibility(self, repository: str, branch: str) -> dict:
        repo = self.policy.repo(repository)
        if not repo.source.startswith("https://github.com/"):
            return {"eligibility": "unknown", "reasons": ["Local source; GitHub attribution not verified"]}
        info = self.github.info(repository)
        identity = self.github.identity(repo.author_email)
        reasons = []
        if info["fork"]:
            reasons.append("Fork commits do not qualify")
        if branch not in {info["default_branch"], "gh-pages"}:
            reasons.append("Feature branch is not yet eligible")
        eligible = "not_eligible" if reasons else "unknown"
        if not reasons and identity["email_association"] == "verified" and info.get("permissions", {}).get("push"):
            eligible = "likely"
        return {"eligibility": eligible, "identity": identity, "reasons": reasons,
                "guaranteed": False, "observed_profile_contributions": None}

    @serialized
    def publish_branch(self, job_id: str) -> dict:
        job = self._job(job_id, True)
        self.policy.authorize(job, "push")
        if job["state"] not in {"VERIFIED", "PUBLISHING", "PUBLISHED", "COMPLETED"}:
            raise AppError("INVALID_STATE", "Verified nonempty final tree required")
        work = self._work(job)
        self._reconcile(job)
        if self.git.text(work, "rev-parse", "HEAD^{tree}") != job["final_tree"]:
            raise AppError("INVARIANT_FAILED", "Approved final tree mismatch")
        if not self._checks(job)["passed"]:
            raise AppError("CHECK_FAILED", "Final checks failed")
        remote = self.git.remote_sha(work, job["target_branch"])
        if remote == job["current_sha"] and job["state"] in {"PUBLISHING", "PUBLISHED", "COMPLETED"}:
            job["state"] = "PUBLISHED" if not job["pr_url"] else "COMPLETED"
            self.db.save(job, "PUSH_CONFIRMED")
            return self._report(job)
        if remote != job["expected_remote"]:
            raise AppError("REMOTE_DIVERGED", "Target branch changed; push stopped")
        repo = self.policy.repo(job["repository"])
        if self.git.remote_sha(work, job.get("base_branch", repo.default_branch)) != job["base_sha"]:
            raise AppError("REMOTE_DIVERGED", "Base branch advanced; create a fresh job")
        if repo.source.startswith("https://github.com/"):
            if not repo.required_checks:
                raise AppError("CHECKS_REQUIRED", "Configure and authorize required tests before GitHub publishing")
            info = self.github.info(job["repository"])
            if not info.get("permissions", {}).get("push"):
                raise AppError("PERMISSION_DENIED", "GitHub actor lacks push rights")
            try:
                rules = self.github.request("GET", f"/repos/{job['repository']}/rules/branches/" + quote(job["target_branch"], safe=""))
            except AppError as error:
                # Only a verified, private-repository GitHub plan limitation may
                # fall back to no available rulesets. All other errors fail closed.
                if error.code != "RULESETS_UNAVAILABLE" or info.get("private") is not True:
                    raise
                rules = []
            if any(r.get("type") == "required_signatures" for r in rules):
                raise AppError("SIGNING_REQUIRED", "Configure a legitimate signing workflow; unsigned publication blocked")
            # gh owns HTTPS credential transport, separately from the REST vault. No PAT arguments.
            self._push_via_gh(job, work)
        else:
            job["state"] = "PUBLISHING"
            self.db.save(job, "PUBLISHING")
            self.git.run(work, "push", "--porcelain", "origin", "HEAD:refs/heads/" + job["target_branch"])
        if self.git.remote_sha(work, job["target_branch"]) != job["current_sha"]:
            raise AppError("RETRYABLE_ERROR", "Push acknowledgment uncertain; resume inspects remote")
        job["state"] = "PUBLISHED"
        self.db.save(job, "PUBLISHED")
        return self._report(job)

    def _push_via_gh(self, job, work):
        # Use the same OS-vault PAT for REST and gh without gh auth login's
        # documented plaintext fallback. Only these trusted network children see it.
        from github_ai_mcp.security.auth_github import get_token
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GH_", "GITHUB_"))}
        env.update(GH_TOKEN=get_token(), GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        try:
            auth = run_background(["gh", "auth", "status", "--hostname", "github.com"],
                                  env=env, capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            raise AppError("AUTH_REQUIRED", "Install GitHub CLI, then sign in using the GUI") from None
        if auth.returncode:
            raise AppError("AUTH_REQUIRED", "Sign in using the GUI for HTTPS Git transport")
        # Verify Git transport actor matches API actor; differing accounts cannot silently publish.
        try:
            actor = run_background(["gh", "api", "user", "--jq", ".login"], env=env, capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            raise AppError("AUTH_REQUIRED", "GitHub CLI actor verification failed") from None
        expected = self.github.request("GET", "/user")["login"]
        if actor.returncode or actor.stdout.decode().strip() != expected:
            raise AppError("IDENTITY_MISMATCH", "GitHub CLI and REST credentials belong to different actors")
        job["state"] = "PUBLISHING"
        self.db.save(job, "PUBLISHING")
        try:
            process = run_background(["git", "-c", "credential.helper=", "-c",
                                      "credential.https://github.com.helper=!gh auth git-credential",
                                      "-c", "core.hooksPath=" + os.devnull,
                                      "push", "--porcelain", "origin", "HEAD:refs/heads/" + job["target_branch"]],
                                     cwd=work, env=env, capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            raise AppError("RETRYABLE_ERROR", "Push interrupted; resume before retry") from None
        if process.returncode:
            raise AppError("PUSH_REJECTED", "GitHub rejected push; inspect permissions, protection or divergence")

    @serialized
    def create_pull_request(self, job_id: str, title: str, description: str) -> dict:
        job = self._job(job_id, True)
        self.policy.authorize(job, "pr")
        if job["state"] not in {"PUBLISHED", "COMPLETED"}:
            raise AppError("INVALID_STATE", "Publish branch before PR")
        if not 1 <= len(title) <= 200 or len(description) > 10000:
            raise AppError("LIMIT_EXCEEDED", "PR title/body too large")
        scan((title + description).encode())
        if not self.policy.repo(job["repository"]).source.startswith("https://github.com/"):
            raise AppError("LOCAL_REMOTE", "Local Git remote has no GitHub PR API")
        if self.git.remote_sha(self._work(job), job["target_branch"]) != job["current_sha"]:
            raise AppError("REMOTE_DIVERGED", "Remote no longer matches job")
        if job["pr_url"]:
            return {"url": job["pr_url"], "existing": True}
        # Reconcile a successful POST with lost acknowledgment before issuing another POST.
        prs = self.github.request("GET", f"/repos/{job['repository']}/pulls")
        existing = next((p for p in prs if p["head"]["ref"] == job["target_branch"]
                         and p["base"]["ref"] == self.policy.repo(job["repository"]).default_branch), None)
        breakdown = "\n".join(f"- `{c['path']}`: `{c['sha']}`" for c in job["commits"])
        body = (f"## Summary\n{description}\n\n## Files Changed\n{breakdown}\n\n## Testing\n"
                f"{json.dumps(job['checks'])}\n\n## Commit Breakdown\n{breakdown}\n\n"
                "## Security/Compatibility Notes\nAI-assisted; final tree verified. Intermediate commits may not build. "
                f"Squash merge changes history. Local report: job {job['id']}.")
        pr = existing or self.github.request("POST", f"/repos/{job['repository']}/pulls",
                                             {"title": title, "body": body, "head": job["target_branch"],
                                              "base": self.policy.repo(job["repository"]).default_branch})
        job.update(pr_url=pr["html_url"], state="COMPLETED")
        self.db.save(job, "PR_CONFIRMED")
        return {"url": job["pr_url"], "existing": existing is not None}

    @serialized
    def get_remote_status(self, job_id: str) -> dict:
        job = self._job(job_id)
        remote = self.git.remote_sha(self._work(job), job["target_branch"])
        result = {"remote_sha": remote, "matches": remote == job.get("current_sha"), "ci": "unknown", "pr_url": job["pr_url"]}
        repo = self.policy.repo(job["repository"])
        if remote and repo.source.startswith("https://github.com/"):
            result["ci"] = self.github.request("GET", f"/repos/{job['repository']}/commits/{remote}/status")["state"]
            result["check_runs"] = self.github.request("GET", f"/repos/{job['repository']}/commits/{remote}/check-runs")
        return result
