import sys

import httpx
import pytest

from github_ai_mcp.core.github_api import GitHub
from github_ai_mcp.core.job_engine import Service
from github_ai_mcp.exceptions import AppError
from conftest import modify


def verified(svc):
    job = svc.create_job("test/repo", "publish", "ai/publish")
    modify(svc, job, "new", "new\n")
    svc.preview_job(job["id"])
    svc.create_file_commits(job["id"])
    return job


def test_failed_check_blocks_publication(factory):
    svc, _, _ = factory()
    job = verified(svc)
    repo = svc.config.repositories["test/repo"]
    repo.required_checks = ["tests"]
    repo.trusted_execution = True
    repo.checks = {"tests": [sys.executable, "-c", "raise SystemExit(1)"]}
    with pytest.raises(AppError) as e:
        svc.publish_branch(job["id"])
    assert e.value.code == "CHECK_FAILED"
    assert svc.git.remote_sha(svc._work(job), "ai/publish") is None


def test_untrusted_commands_not_executed(factory):
    svc, _, _ = factory()
    job = verified(svc)
    svc.config.repositories["test/repo"].required_checks = ["tests"]
    with pytest.raises(AppError) as e:
        svc.run_checks(job["id"])
    assert e.value.code == "EXECUTION_DENIED"


def test_remote_divergence_no_force(factory):
    svc, source, _ = factory()
    job = verified(svc)
    svc.git.run(source, "checkout", "-b", "ai/publish")
    (source / "foreign").write_text("foreign\n")
    svc.git.run(source, "add", "--", "foreign")
    svc.git.run(source, "commit", "-m", "feat: foreign update")
    svc.git.run(source, "push", "origin", "ai/publish")
    before = svc.git.remote_sha(svc._work(job), "ai/publish")
    with pytest.raises(AppError) as e:
        svc.publish_branch(job["id"])
    assert e.value.code == "REMOTE_DIVERGED"
    assert svc.git.remote_sha(svc._work(job), "ai/publish") == before


def test_lost_push_acknowledgment_reconciled(factory, monkeypatch):
    svc, _, _ = factory()
    job = verified(svc)
    original = svc.git.run
    def lost(cwd, *args, **kwargs):
        value = original(cwd, *args, **kwargs)
        if args[0] == "push":
            raise AppError("RETRYABLE_ERROR", "lost ack")
        return value
    monkeypatch.setattr(svc.git, "run", lost)
    with pytest.raises(AppError):
        svc.publish_branch(job["id"])
    fresh = Service(svc.config)
    result = fresh.resume_job(job["id"])
    assert result["state"] == "PUBLISHED"
    assert result["pushed_commits"] == 1


def test_github_identity_mock_and_safe_auth_errors():
    def handler(r):
        assert r.url.host == "api.github.com"
        if r.url.path == "/user":
            return httpx.Response(200, json={"login": "fixture"})
        return httpx.Response(200, json=[{"email": "author@example.invalid", "verified": True}])
    api = GitHub(token="mock-token", transport=httpx.MockTransport(handler))
    assert api.identity("author@example.invalid")["email_association"] == "verified"
    failed = GitHub(token="mock-token", transport=httpx.MockTransport(lambda _: httpx.Response(401)))
    with pytest.raises(AppError) as e:
        failed.request("GET", "/user")
    assert e.value.code == "AUTH_REQUIRED"
    assert "mock-token" not in str(e.value)


def test_pr_mock_actual_service(factory, monkeypatch):
    svc, _, _ = factory()
    job = verified(svc)
    svc.publish_branch(job["id"])
    svc.config.repositories["test/repo"].source = "https://github.com/test/repo.git"
    requests = []
    def handler(r):
        requests.append(r.method)
        if r.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(201, json={"html_url": "https://github.com/test/repo/pull/1"})
    svc.github = GitHub(token="mock-token", transport=httpx.MockTransport(handler))
    result = svc.create_pull_request(job["id"], "Test PR", "Offline mocked PR")
    assert result["url"].endswith("/pull/1")
    assert svc.create_pull_request(job["id"], "Again", "Again")["existing"]
    assert requests == ["GET", "POST"]


def test_base_branch_advancement_stops_publication(factory):
    svc, source, _ = factory()
    job = verified(svc)
    (source / "README.md").write_text("new upstream\n")
    svc.git.run(source, "add", "--", "README.md")
    svc.git.run(source, "commit", "-m", "docs: update upstream")
    svc.git.run(source, "push", "origin", "main")
    with pytest.raises(AppError) as e:
        svc.publish_branch(job["id"])
    assert e.value.code == "REMOTE_DIVERGED"


def test_check_modifies_snapshot_blocks_commit(factory):
    svc, _, _ = factory()
    repo = svc.config.repositories["test/repo"]
    repo.required_checks = ["mutating"]
    repo.trusted_execution = True
    repo.checks = {"mutating": [sys.executable, "-c", "from pathlib import Path; Path('README.md').write_text('unexpected')"]}
    job = svc.create_job("test/repo", "mutating")
    modify(svc, job, "new", "new\n")
    svc.preview_job(job["id"])
    with pytest.raises(AppError) as e:
        svc.create_file_commits(job["id"])
    assert e.value.code == "CHECK_FAILED"
    assert not svc.get_job_status(job["id"])["commits"]


def test_github_free_private_branch_rules_403_detected_precisely():
    plan_error = {"message": "Upgrade to GitHub Pro or make this repository public to enable this feature."}
    api = GitHub(token="mock-token", transport=httpx.MockTransport(
        lambda _: httpx.Response(403, json=plan_error)))
    with pytest.raises(AppError) as caught:
        api.request("GET", "/repos/test/repo/rules/branches/staged-files")
    assert caught.value.code == "RULESETS_UNAVAILABLE"
    # A similar 403 from unrelated endpoints must stay permission denied.
    with pytest.raises(AppError) as caught:
        api.request("GET", "/repos/test/repo/issues")
    assert caught.value.code == "PERMISSION_DENIED"


def test_other_branch_rules_denials_fail_closed():
    for status, message in [(403, "Resource not accessible by integration"),
                            (404, "Not Found")]:
        api = GitHub(token="mock-token", transport=httpx.MockTransport(
            lambda _, code=status, text=message: httpx.Response(code, json={"message": text})))
        with pytest.raises(AppError) as caught:
            api.request("GET", "/repos/test/repo/rules/branches/staged-files")
        assert caught.value.code == "PERMISSION_DENIED"


def test_publish_private_free_repo_preserves_checks_and_commits(factory, monkeypatch):
    svc, _, _ = factory()
    job = verified(svc)
    repo = svc.config.repositories["test/repo"]
    repo.source = "https://github.com/test/repo.git"
    repo.required_checks = ["metadata"]
    repo.trusted_execution = True
    repo.checks = {"metadata": [sys.executable, "-c", "pass"]}
    monkeypatch.setattr(svc.github, "info", lambda _: {"private": True, "permissions": {"push": True}})
    def limited(method, path):
        assert method == "GET" and "/rules/branches/" in path
        raise AppError("RULESETS_UNAVAILABLE", "GitHub plan does not provide branch rulesets")
    monkeypatch.setattr(svc.github, "request", limited)
    monkeypatch.setattr(svc, "_push_via_gh", lambda job, work: svc.git.run(
        work, "push", "origin", "HEAD:refs/heads/" + job["target_branch"]))
    result = svc.publish_branch(job["id"])
    assert result["state"] == "PUBLISHED"
    assert result["pushed_commits"] == 1


def test_public_repo_rules_unavailable_does_not_allow_push(factory, monkeypatch):
    svc, _, _ = factory()
    job = verified(svc)
    repo = svc.config.repositories["test/repo"]
    repo.source = "https://github.com/test/repo.git"
    repo.required_checks = ["metadata"]
    repo.trusted_execution = True
    repo.checks = {"metadata": [sys.executable, "-c", "pass"]}
    monkeypatch.setattr(svc.github, "info", lambda _: {"private": False, "permissions": {"push": True}})
    def unavailable(method, path):
        raise AppError("RULESETS_UNAVAILABLE", "GitHub plan does not provide branch rulesets")
    monkeypatch.setattr(svc.github, "request", unavailable)
    with pytest.raises(AppError) as caught:
        svc.publish_branch(job["id"])
    assert caught.value.code == "RULESETS_UNAVAILABLE"
    assert svc.git.remote_sha(svc._work(job), job["target_branch"]) is None
