import time

import pytest

from github_ai_mcp.config import Config, Grant, Repository
from github_ai_mcp.core.git_engine import Git
from github_ai_mcp.core.job_engine import Service


@pytest.fixture
def factory(tmp_path):
    serial = 0
    def build(mode="AUTO_APPROVED", preapprove=True, files=None):
        nonlocal serial
        serial += 1
        root = tmp_path / str(serial)
        root.mkdir()
        source, remote = root / "source", root / "remote.git"
        source.mkdir()
        git = Git()
        git.run(source, "init", "-b", "main")
        git.run(source, "config", "user.name", "Test Author")
        git.run(source, "config", "user.email", "test@example.invalid")
        for name, content in (files or {"README.md": "original\n"}).items():
            p = source / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content if isinstance(content, bytes) else content.encode())
            git.run(source, "add", "--", name)
        git.run(source, "commit", "-m", "test: initial fixture")
        git.run(root, "init", "--bare", "--initial-branch=main", str(remote))
        git.run(source, "remote", "add", "origin", str(remote))
        git.run(source, "push", "origin", "main")
        grants = [Grant(repository="test/repo", branch_prefix="", actions=["commit", "push", "pr"], expires_at=time.time()+3600)] if preapprove else []
        config = Config(data_dir=root / "state", mode=mode,
                        repositories={"test/repo": Repository(source=str(remote), author_name="Test Author",
                                                              author_email="test@example.invalid", identity_authorized=True)},
                        grants=grants)
        return Service(config), source, remote
    return build


def modify(service, job, path, content):
    ident = job["id"]
    service.plan_changes(ident, {path: "fix: update " + path})
    try:
        checksum = service.read_file("test/repo", path, ident)["checksum"]
    except Exception as e:
        if getattr(e, "code", "") != "NOT_FOUND":
            raise
        checksum = None
    return service.write_file(ident, path, content, checksum)
