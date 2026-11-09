"""Argument-array Git operations; isolated indexes and hardened configuration."""
import os
import subprocess

from github_ai_mcp.desktop.processes import run_background
from pathlib import Path

from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.auth_github import get_token


class Git:
    def __init__(self, timeout: int = 120):
        self.timeout = timeout

    def run(self, cwd: Path, *args: str, input: bytes | None = None) -> bytes:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GH_", "GITHUB_"))}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT="0", GIT_LITERAL_PATHSPECS="1")
        # GitHub CLI reads a transient token from the OS vault for network commands.
        # Nothing is written to gh's configuration, command line, or Git remotes.
        if args and args[0] in {"clone", "fetch", "ls-remote", "push"}:
            github_source = any(a.startswith("https://github.com/") for a in args)
            if not github_source and (cwd / ".git").exists():
                probe = run_background(["git", "config", "--local", "--get", "remote.origin.url"],
                                       cwd=cwd, env=env, capture_output=True, timeout=10)
                github_source = probe.stdout.decode("utf-8", "replace").strip().startswith("https://github.com/")
            if github_source:
                try:
                    env["GH_TOKEN"] = get_token()
                except AppError:
                    pass  # Public cloning may succeed without authentication.
        # Fresh clones have no inherited hooks/filters. Disable template hooks explicitly.
        command = ["git", "-c", "core.hooksPath=" + os.devnull, "-c", "credential.helper=",
                   "-c", "credential.https://github.com.helper=!gh auth git-credential",
                   "-c", "core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol",
                   "-c", "core.autocrlf=false", "-c", "core.quotepath=false",
                   "-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=always", *args]
        try:
            p = run_background(command, cwd=cwd, env=env, input=input,
                               capture_output=True, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise AppError("GIT_UNAVAILABLE", "Git unavailable or command timed out") from None
        if p.returncode:
            # Git stderr can contain credentials or private code: never forward it.
            raise AppError("GIT_ERROR", f"Git operation failed ({args[0]}, exit {p.returncode})")
        return p.stdout

    def text(self, cwd: Path, *args: str) -> str:
        return self.run(cwd, *args).decode("utf-8").strip()

    def paths(self, cwd: Path, *args: str) -> list[str]:
        return [p.decode("utf-8") for p in self.run(cwd, *args).split(b"\0") if p]

    def clone(self, source: str, dest: Path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.run(dest.parent, "clone", "--no-local", "--no-hardlinks", "--template=", "--", source, str(dest))

    def tree(self, cwd: Path, ref: str = "HEAD") -> dict[str, dict]:
        result = {}
        for record in self.run(cwd, "ls-tree", "-rz", ref).split(b"\0"):
            if record:
                meta, path = record.split(b"\t", 1)
                mode, kind, sha = meta.decode().split()
                result[path.decode()] = {"mode": mode, "kind": kind, "sha": sha}
        return result

    def blob(self, cwd: Path, sha: str) -> bytes:
        size = int(self.text(cwd, "cat-file", "-s", sha))
        if size > 10_000_000:
            raise AppError("LIMIT_EXCEEDED", "Git blob exceeds read limit")
        return self.run(cwd, "cat-file", "blob", sha)

    def remote_sha(self, cwd: Path, branch: str) -> str | None:
        out = self.text(cwd, "ls-remote", "--heads", "origin", "refs/heads/" + branch)
        return out.split()[0] if out else None
