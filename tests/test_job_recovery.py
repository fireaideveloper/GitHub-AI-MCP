"""Recovery regression cases based on a real CHECK_FAILED job with completed commits."""
import sys

import pytest

from conftest import modify
from github_ai_mcp.exceptions import AppError


def prepared_job(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "checked-job")
    modify(svc, job, "README.md", "ready for recovery\n")
    gate = svc.root.parent / "release-gate.txt"
    gate.write_text("enabled", encoding="utf-8")
    repo = svc.config.repositories["test/repo"]
    repo.required_checks = ["release_gate"]
    repo.checks = {
        "release_gate": [
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; "
            f"sys.exit(0 if Path({str(gate)!r}).exists() else 1)",
        ]
    }
    repo.trusted_execution = True
    svc.preview_job(job["id"])
    first = svc.create_file_commits(job["id"])
    assert first["state"] == "VERIFIED"
    assert first["created_commits"] == 1
    gate.unlink()
    failed = svc.run_checks(job["id"])
    assert not failed["passed"]
    assert svc.get_job_status(job["id"])["state"] == "CHECK_FAILED"
    return svc, job, gate, first


def test_recheck_recovers_existing_commit_chain_without_rewriting(factory):
    svc, job, gate, first = prepared_job(factory)
    gate.write_text("enabled", encoding="utf-8")
    result = svc.run_checks(job["id"])
    assert result["passed"] is True
    recovered = svc.get_job_status(job["id"])
    assert recovered["state"] == "VERIFIED"
    assert recovered["final_sha"] == first["final_sha"]
    assert recovered["final_tree"] == first["final_tree"]
    assert [c["sha"] for c in recovered["commits"]] == [c["sha"] for c in first["commits"]]
    assert svc.create_file_commits(job["id"])["created_commits"] == 1


def test_resume_recovers_after_previously_failed_checks(factory):
    svc, job, gate, first = prepared_job(factory)
    with pytest.raises(AppError) as error:
        svc.resume_job(job["id"])
    assert error.value.code == "CHECK_FAILED"
    gate.write_text("enabled", encoding="utf-8")
    recovered = svc.resume_job(job["id"])
    assert recovered["state"] == "VERIFIED"
    assert recovered["final_sha"] == first["final_sha"]
    assert recovered["created_commits"] == 1


def test_injected_commit_not_accepted_as_verified(factory):
    svc, job, gate, first = prepared_job(factory)
    work = svc._work(job)
    svc.git.run(work, "commit", "--allow-empty", "-m", "test: unexpected extra commit")
    gate.write_text("enabled", encoding="utf-8")
    with pytest.raises(AppError) as error:
        svc.resume_job(job["id"])
    assert error.value.code in {"RECOVERY_REQUIRED", "INVARIANT_FAILED"}
    assert svc.get_job_status(job["id"])["state"] == "CHECK_FAILED"


def test_retry_commit_button_rechecks_without_snapshot_recreation(factory):
    svc, job, gate, first = prepared_job(factory)
    gate.write_text("enabled", encoding="utf-8")
    result = svc.create_file_commits(job["id"])
    assert result["state"] == "VERIFIED"
    assert result["final_sha"] == first["final_sha"]


def test_thirteen_commits_recover_and_publish_without_rewriting(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "thirteen")
    for i in range(13):
        modify(svc, job, f"file-{i}.txt", f"value {i}\n")
    svc.preview_job(job["id"])
    first = svc.create_file_commits(job["id"])
    stored = svc.db.get(job["id"])
    stored["state"] = "CHECK_FAILED"
    svc.db.save(stored, "TEST_FAILURE")
    recovered = svc.resume_job(job["id"])
    assert recovered["state"] == "VERIFIED"
    assert recovered["commits"] == first["commits"]
    assert svc.publish_branch(job["id"])["pushed_commits"] == 13


@pytest.mark.parametrize("field", ["message", "entry", "identity"])
def test_snapshot_record_tampering_rejected(factory, field):
    svc, job, gate, _ = prepared_job(factory)
    record = svc.db.get(job["id"])
    if field == "message":
        record["changes"][0]["message"] = "fix: tampered"
    elif field == "entry":
        record["changes"][0]["entry"]["mode"] = "100755"
    else:
        record["commit_identity"]["name"] = "Other Author"
    svc.db.save(record, "TEST_TAMPERING")
    gate.write_text("enabled", encoding="utf-8")
    with pytest.raises(AppError) as error:
        svc.resume_job(job["id"])
    assert error.value.code == "INVARIANT_FAILED"


def test_delete_final_tracked_file_removes_only_empty_parents(factory):
    svc, source, _ = factory(files={"desktop/src-tauri/binares/.gitkeep": "", "README.md": "original\n"})
    job = svc.create_job("test/repo", "empty-directory")
    path = "desktop/src-tauri/binares/.gitkeep"
    checksum = svc.read_file("test/repo", path, job["id"])["checksum"]
    svc.plan_changes(job["id"], {path: "chore: remove obsolete directory marker"})
    svc.delete_file(job["id"], path, checksum)
    assert not (svc._work(job) / "desktop/src-tauri/binares").exists()
    assert (source / path).exists()  # The live source is never modified.
    svc.preview_job(job["id"])
    result = svc.create_file_commits(job["id"])
    assert result["created_commits"] == 1


def test_check_creating_untracked_file_is_rejected(factory):
    svc, _, _ = factory()
    repo = svc.config.repositories["test/repo"]
    repo.required_checks = ["artifact"]
    repo.trusted_execution = True
    repo.checks = {"artifact": [sys.executable, "-c", "from pathlib import Path; Path('unapproved.txt').write_text('unexpected')"]}
    job = svc.create_job("test/repo", "untracked")
    modify(svc, job, "README.md", "changed\n")
    svc.preview_job(job["id"])
    with pytest.raises(AppError) as error:
        svc.create_file_commits(job["id"])
    assert error.value.code == "CHECK_FAILED"


def test_failed_checks_after_commits_cannot_reopen_snapshot_for_editing(factory):
    svc, job, _, first = prepared_job(factory)
    with pytest.raises(AppError) as error:
        svc.plan_changes(job["id"], {"README.md": "fix: rewrite frozen snapshot"})
    assert error.value.code == "INVALID_STATE"
    assert svc.get_job_status(job["id"])["final_sha"] == first["final_sha"]
