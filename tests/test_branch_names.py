"""Task-based branch names, collision handling, and permission boundaries."""

import time

import pytest

from conftest import modify
from github_ai_mcp.config import Grant
from github_ai_mcp.core.job_engine import task_branch_name
from github_ai_mcp.exceptions import AppError


def test_task_to_branch_and_idempotency(factory):
    service, _, _ = factory()
    job = service.create_job("test/repo", "unique-id", task_name="Fix tunnel startup")
    assert job["target_branch"] == "fix-tunnel-startup"
    assert service.create_job("test/repo", "unique-id", task_name="Fix tunnel startup")["id"] == job["id"]
    with pytest.raises(AppError) as error:
        service.create_job("test/repo", "unique-id", task_name="Add dark mode")
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_new_auto_branches_are_flat_and_unique(factory):
    service, _, _ = factory()
    a = service.create_job("test/repo", "first", task_name="Add dark mode")
    b = service.create_job("test/repo", "second", task_name="Add dark mode")
    assert a["target_branch"] == "add-dark-mode"
    assert b["target_branch"] == "add-dark-mode-2"
    assert "/" not in a["target_branch"]


def test_remote_collision_gets_suffix(factory):
    service, source, _ = factory()
    service.git.run(source, "checkout", "-b", "update-documentation")
    service.git.run(source, "push", "origin", "update-documentation")
    job = service.create_job("test/repo", "new-task", task_name="Update documentation")
    assert job["target_branch"] == "update-documentation-2"


def test_invalid_or_unsafe_names(factory):
    service, _, _ = factory()
    for bad in ("main", "UPPERCASE", "feature/change", "../main", "a..b", "topic lock"):
        with pytest.raises(AppError):
            service.create_job("test/repo", "attempt:" + bad, target_branch=bad)
    with pytest.raises(AppError, match="English"):
        service.create_job("test/repo", "russian", task_name="Исправь ошибку")
    assert task_branch_name("Fix: sign-in / auth") == "fix-sign-in-auth"


def test_legacy_ai_branches_still_supported(factory):
    service, _, _ = factory()
    job = service.create_job("test/repo", "legacy", "ai/legacy")
    assert job["target_branch"] == "ai/legacy"


def test_old_ai_scoped_grant_cannot_silently_approve_flat_branch(factory):
    service, _, _ = factory()
    service.config.grants = [Grant(repository="test/repo", branch_prefix="ai/",
                                   actions=["commit", "push", "pr"], expires_at=time.time()+3600)]
    job = service.create_job("test/repo", "new", task_name="Fix startup")
    modify(service, job, "README.md", "changed\n")
    service.preview_job(job["id"])
    with pytest.raises(AppError) as error:
        service.create_file_commits(job["id"])
    assert error.value.code == "APPROVAL_REQUIRED"
    # Intentional, local trust decision (empty prefix), not an MCP-side mutation.
    service.config.grants[0].branch_prefix = ""
    service.create_file_commits(job["id"])


def test_no_blank_branch_on_bad_task_title(factory):
    service, _, _ = factory()
    with pytest.raises(AppError):
        service.create_job("test/repo", "blank", task_name="!!!")


def test_old_clients_with_opaque_idempotency_keys_get_safe_fallback(factory):
    service, _, _ = factory()
    job = service.create_job("test/repo", "41b0dc65-e91c-49cb-90f7-f63acaab67a3")
    assert job["target_branch"].startswith("task-")
    assert "/" not in job["target_branch"]
    digit = service.create_job("test/repo", "12345678")
    assert digit["target_branch"].startswith("task-")
