import time

import pytest

from github_ai_mcp.core.locking import lock
from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.paths import safe_path
from github_ai_mcp.security.secret_scan import redact
from conftest import modify


@pytest.mark.parametrize("path", ["../escape", "/tmp/file", "C:/x", "\\\\server\\x", ".git/config", ".GIT/config",
                                ".env", "a/.env.local", "id_rsa", "secret.pem", "NUL.txt", "LPT1", "a//b", "a/./b", "a/../b", "x.", "x "])
def test_path_denial(tmp_path, path):
    with pytest.raises(AppError):
        safe_path(tmp_path, path)


def test_symlink_escape(tmp_path):
    try:
        (tmp_path / "escape").symlink_to(tmp_path.parent, target_is_directory=True)
    except OSError:
        pytest.skip("OS user lacks symlink creation privilege")
    with pytest.raises(AppError):
        safe_path(tmp_path, "escape/secret.txt")


def test_env_example_allowed(tmp_path):
    assert safe_path(tmp_path, ".env.example") == tmp_path / ".env.example"


def test_secret_blocked_and_redacted(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "secret")
    secret = "ghp_" + "a" * 36
    with pytest.raises(AppError) as e:
        modify(svc, job, "code.txt", secret)
    assert e.value.code == "SECRET_DETECTED"
    assert secret not in str(e.value)
    assert secret not in redact(secret)
    assert not (svc._work(job) / "code.txt").exists()


def test_readonly_all_mutations(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "read-only")
    svc.config.mode = "READ_ONLY"
    calls = [lambda: svc.create_job("test/repo", "other"),
             lambda: svc.plan_changes(job["id"], {"file": "feat: file content"}),
             lambda: svc.write_file(job["id"], "file", "content"),
             lambda: svc.delete_file(job["id"], "README.md", "checksum"),
             lambda: svc.create_file_commits(job["id"]), lambda: svc.publish_branch(job["id"]),
             lambda: svc.create_pull_request(job["id"], "Title", "Summary"),
             lambda: svc.cancel_job(job["id"]), lambda: svc.resume_job(job["id"]),
             lambda: svc.run_checks(job["id"])]
    for fn in calls:
        with pytest.raises(AppError) as e:
            fn()
        assert e.value.code == "PERMISSION_DENIED"
    assert svc.read_file("test/repo", "README.md")["content"] == "original\n"


def test_exact_approval_and_invalidation(factory):
    svc, _, _ = factory(mode="LOCAL_REVIEW", preapprove=False)
    job = svc.create_job("test/repo", "approval")
    modify(svc, job, "README.md", "first\n")
    preview = svc.preview_job(job["id"])
    with pytest.raises(AppError) as e:
        svc.create_file_commits(job["id"])
    assert e.value.code == "APPROVAL_REQUIRED"
    svc.approve_local(job["id"], preview["fingerprint"], ["commit"])
    modify(svc, job, "README.md", "second\n")
    svc.preview_job(job["id"])
    with pytest.raises(AppError) as e:
        svc.create_file_commits(job["id"])
    assert e.value.code == "APPROVAL_REQUIRED"


def test_expired_grant(factory):
    svc, _, _ = factory()
    svc.config.grants[0].expires_at = time.time() - 1
    job = svc.create_job("test/repo", "expired")
    modify(svc, job, "new", "content\n")
    svc.preview_job(job["id"])
    with pytest.raises(AppError) as e:
        svc.create_file_commits(job["id"])
    assert e.value.code == "APPROVAL_REQUIRED"


def test_unallowlisted_denied(factory):
    svc, _, _ = factory()
    with pytest.raises(AppError) as e:
        svc.get_repository_info("evil/repo")
    assert e.value.code == "PERMISSION_DENIED"


def test_unplanned_denied(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "unplanned")
    with pytest.raises(AppError) as e:
        svc.write_file(job["id"], "new", "content")
    assert e.value.code == "UNPLANNED_PATH"


def test_kernel_lock(tmp_path):
    with lock(tmp_path, "key"):
        with pytest.raises(AppError) as e:
            with lock(tmp_path, "key"):
                pass
        assert e.value.code == "BUSY"
    with lock(tmp_path, "key"):
        pass


def test_hooks_do_not_execute(factory):
    svc, source, _ = factory()
    hook = source / ".git/hooks/post-checkout"
    marker = source / "pwned"
    hook.write_text("#!/bin/sh\ntouch " + str(marker) + "\n")
    hook.chmod(0o755)
    svc.config.repositories["test/repo"].source = str(source)
    job = svc.create_job("test/repo", "hook")
    modify(svc, job, "safe", "safe\n")
    svc.preview_job(job["id"])
    svc.create_file_commits(job["id"])
    assert not marker.exists()


def test_case_collision_denied(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "case")
    # Fail before writing: on Windows readme.md aliases tracked README.md.
    with pytest.raises(AppError) as e:
        svc.plan_changes(job["id"], {"readme.md": "fix: reject case alias"})
    assert e.value.code == "CASE_COLLISION"
    assert (svc._work(job) / "README.md").read_bytes() == b"original\n"


def test_case_collision_between_new_paths_denied(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "new-case")
    with pytest.raises(AppError) as e:
        svc.plan_changes(job["id"], {"New.txt": "feat: new upper", "new.txt": "feat: new lower"})
    assert e.value.code == "CASE_COLLISION"


def test_directory_case_collision_denied(factory):
    svc, _, _ = factory(files={"Docs/intro.md": "original\n"})
    job = svc.create_job("test/repo", "directory-case")
    with pytest.raises(AppError) as e:
        svc.plan_changes(job["id"], {"docs/other.md": "feat: add other file"})
    assert e.value.code == "CASE_COLLISION"


def test_unsupported_plaintext_vault_rejected(monkeypatch):
    from github_ai_mcp.security import auth_github
    class Plaintext:
        priority = 10
    Plaintext.__module__ = "keyrings.alt.file"
    monkeypatch.setattr(auth_github.keyring, "get_keyring", lambda: Plaintext())
    with pytest.raises(AppError) as e:
        auth_github.store_token("fixture")
    assert e.value.code == "AUTH_REQUIRED"


def test_grant_file_limit_enforced(factory):
    svc, _, _ = factory()
    svc.config.grants[0].max_files = 1
    job = svc.create_job("test/repo", "limit")
    modify(svc, job, "a", "a\n")
    modify(svc, job, "b", "b\n")
    svc.preview_job(job["id"])
    with pytest.raises(AppError) as e:
        svc.create_file_commits(job["id"])
    assert e.value.code == "APPROVAL_REQUIRED"


def test_approved_identity_change_invalidates_preview(factory):
    svc, _, _ = factory(mode="LOCAL_REVIEW", preapprove=False)
    job = svc.create_job("test/repo", "identity")
    modify(svc, job, "new", "new\n")
    preview = svc.preview_job(job["id"])
    svc.approve_local(job["id"], preview["fingerprint"], ["commit"])
    svc.config.repositories["test/repo"].author_name = "Changed trusted author"
    with pytest.raises(AppError) as e:
        svc.create_file_commits(job["id"])
    assert e.value.code == "STALE_APPROVAL"


def test_legacy_missing_email_has_no_personal_default_and_cannot_commit(factory):
    from github_ai_mcp.config import Config
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "missing-email")
    data = svc.config.model_dump(mode="json")
    data["repositories"]["test/repo"].pop("author_email")
    restored = Config.model_validate(data)
    assert restored.repositories["test/repo"].author_email == ""
    svc.config = restored
    svc.policy.config = restored
    with pytest.raises(AppError) as error:
        svc.policy.authorize(job, "commit")
    assert error.value.code == "IDENTITY_REQUIRED"
    assert svc.read_file("test/repo", "README.md")["content"] == "original\n"
