import sqlite3
from pathlib import Path

import pytest

from github_ai_mcp.exceptions import AppError
from github_ai_mcp.storage.database import Database


def make_job(state: str = "SNAPSHOT_READY") -> dict:
    return {
        "id": "test-job",
        "idempotency_key": "stable-request",
        "repository": "example/repo",
        "target_branch": "work-branch",
        "fingerprint": "fingerprint-1",
        "state": state,
    }


def test_persist_and_find_job(tmp_path: Path):
    db = Database(tmp_path / "state" / "jobs.sqlite3")
    job = make_job()
    db.save(job, "created")
    assert db.get(job["id"]) == job
    assert db.by_key(job["idempotency_key"]) == job
    assert db.list_jobs() == [job]
    assert [entry["event"] for entry in db.audit(job["id"])] == ["created"]


def test_update_preserves_single_job_record(tmp_path: Path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.save(make_job(), "created")
    updated = make_job("COMPLETED")
    db.save(updated, "completed")
    assert db.get("test-job")["state"] == "COMPLETED"
    assert len(db.list_jobs()) == 1
    assert [event["event"] for event in db.audit("test-job")] == ["created", "completed"]


def test_grants_are_bound_to_exact_fingerprint(tmp_path: Path):
    db = Database(tmp_path / "jobs.sqlite3")
    job = make_job()
    db.save(job, "created")
    assert not db.approved(job, "commit")
    db.grant(job, ["commit"])
    assert db.approved(job, "commit")
    assert not db.approved(job, "push")
    assert not db.approved({**job, "fingerprint": "fingerprint-2"}, "commit")


def test_expired_grants_are_not_accepted(tmp_path: Path):
    db = Database(tmp_path / "jobs.sqlite3")
    job = make_job()
    db.grant(job, ["commit"], hours=-1)
    assert not db.approved(job, "commit")


def test_branch_ownership_excludes_terminal_jobs(tmp_path: Path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.save(make_job(), "created")
    assert db.branch_owned("example/repo", "work-branch")
    assert not db.branch_owned("example/repo", "different-branch")
    db.save(make_job("COMPLETED"), "completed")
    assert not db.branch_owned("example/repo", "work-branch")


def test_pruning_removes_audit_only(tmp_path: Path):
    db = Database(tmp_path / "jobs.sqlite3")
    db.save(make_job(), "created")
    result = db.prune_audit(0)
    assert result["deleted_audit_rows"] == 1
    assert result["jobs_and_workspaces_preserved"]
    assert db.get("test-job")["state"] == "SNAPSHOT_READY"


def test_unknown_job_returns_stable_error(tmp_path: Path):
    db = Database(tmp_path / "jobs.sqlite3")
    with pytest.raises(AppError) as error:
        db.get("missing")
    assert error.value.code == "NOT_FOUND"


def test_newer_schema_is_rejected(tmp_path: Path):
    path = tmp_path / "jobs.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=2")
    with pytest.raises(AppError) as error:
        Database(path)
    assert error.value.code == "SCHEMA_VERSION"
