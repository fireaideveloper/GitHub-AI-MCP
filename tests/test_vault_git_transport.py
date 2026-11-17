"""Credentials are ephemeral subprocess environment, never files or argv."""
from types import SimpleNamespace

import pytest

from github_ai_mcp.core.git_engine import Git
from github_ai_mcp.exceptions import AppError


def test_network_git_receives_vault_pat_but_local_commands_do_not(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("github_ai_mcp.core.git_engine.get_token", lambda: "private-fixture-value")
    def run(args, **kwargs):
        calls.append((args, kwargs["env"]))
        return SimpleNamespace(returncode=0, stdout=b"ok")
    monkeypatch.setattr("github_ai_mcp.core.git_engine.run_background", run)
    git = Git()
    git.run(tmp_path, "clone", "https://github.com/test/repo.git", str(tmp_path / "clone"))
    assert calls[-1][1]["GH_TOKEN"] == "private-fixture-value"
    assert all("private-fixture-value" not in arg for arg in calls[-1][0])
    git.run(tmp_path, "status")
    assert "GH_TOKEN" not in calls[-1][1]
    assert not list(tmp_path.iterdir())


def test_github_transport_actor_mismatch_cannot_push(factory, monkeypatch):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "actor-check")
    record = svc.db.get(job["id"])
    calls = []
    monkeypatch.setattr("github_ai_mcp.security.auth_github.get_token", lambda: "fixture-vault-value")
    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["env"]["GH_TOKEN"] == "fixture-vault-value"
        return SimpleNamespace(returncode=0, stdout=b"other-actor\n")
    monkeypatch.setattr("github_ai_mcp.core.job_engine.run_background", run)
    monkeypatch.setattr(svc.github, "request", lambda *args: {"login": "approved-actor"})
    with pytest.raises(AppError) as error:
        svc._push_via_gh(record, svc._work(job))
    assert error.value.code == "IDENTITY_MISMATCH"
    assert all(args[0] != "git" for args in calls)
