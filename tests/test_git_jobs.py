import hashlib

import pytest

from github_ai_mcp.core.job_engine import Service
from github_ai_mcp.exceptions import AppError
from conftest import modify


@pytest.mark.parametrize("count", [1, 5, 17])
def test_exact_path_commits(factory, count):
    initial = {f"file{i}.txt": "old\n" for i in range(12)}
    svc, source, remote = factory(files=initial)
    job = svc.create_job("test/repo", "count")
    for i in range(count):
        modify(svc, job, f"file{i}.txt", f"new {i}\n")
    preview = svc.preview_job(job["id"])
    report = svc.create_file_commits(job["id"])
    assert report["created_commits"] == count
    assert report["final_tree"] == preview["final_tree"]
    work = svc._work(job)
    for commit in report["commits"]:
        paths = svc.git.paths(work, "diff-tree", "--no-commit-id", "--no-renames", "--name-only", "-r", "-z", commit["parent"], commit["sha"])
        assert paths == [commit["path"]]
        assert svc.git.text(work, "show", "-s", "--format=%ae", commit["sha"]) == "test@example.invalid"
    published = svc.publish_branch(job["id"])
    assert published["pushed_commits"] == count
    assert svc.get_remote_status(job["id"])["matches"]
    assert svc.create_file_commits(job["id"])["created_commits"] == count
    assert svc.publish_branch(job["id"])["pushed_commits"] == count


def test_same_path_three_edits_one_commit(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "revisions")
    for i in range(3):
        modify(svc, job, "README.md", str(i) + "\n")
    svc.preview_job(job["id"])
    assert svc.create_file_commits(job["id"])["created_commits"] == 1


def test_no_change_zero_commits(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "no-change")
    modify(svc, job, "README.md", "original\n")
    svc.preview_job(job["id"])
    report = svc.create_file_commits(job["id"])
    assert report["state"] == "NO_CHANGE"
    assert report["created_commits"] == 0


def test_deletion_and_strict_rename(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "rename")
    old = svc.read_file("test/repo", "README.md", job["id"])
    svc.plan_changes(job["id"], {"README.md": "chore: remove old path", "new.md": "docs: restore new path"})
    svc.delete_file(job["id"], "README.md", old["checksum"])
    svc.write_file(job["id"], "new.md", old["content"])
    svc.preview_job(job["id"])
    report = svc.create_file_commits(job["id"])
    assert report["created_commits"] == 2
    assert svc.git.paths(svc._work(job), "diff", "--name-only", "--no-renames", "-z", job["base_sha"], "HEAD") == ["README.md", "new.md"]


@pytest.mark.parametrize("path", ["кириллица/файл.txt", "space (two).txt", "emoji 🌍.txt", "a/name.txt", "b/name.txt"])
def test_unicode_paths(factory, path):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", path)
    modify(svc, job, path, "привет 世界\n")
    svc.preview_job(job["id"])
    assert svc.create_file_commits(job["id"])["commits"][0]["path"] == path


def test_dirty_user_worktree_preserved(factory):
    svc, source, _ = factory()
    (source / "README.md").write_text("uncommitted user change\n")
    svc.git.run(source, "add", "--", "README.md")
    before = svc.git.run(source, "diff", "--cached")
    svc.config.repositories["test/repo"].source = str(source)
    job = svc.create_job("test/repo", "dirty")
    assert svc.read_file("test/repo", "README.md", job["id"])["content"] == "original\n"
    modify(svc, job, "new.txt", "independent\n")
    svc.preview_job(job["id"])
    svc.create_file_commits(job["id"])
    assert svc.git.run(source, "diff", "--cached") == before
    assert (source / "README.md").read_text() == "uncommitted user change\n"


def test_crash_after_ref_before_database_save(factory, monkeypatch):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "crash")
    for i in range(10):
        modify(svc, job, f"p{i}.txt", "new\n")
    svc.preview_job(job["id"])
    original = svc.db.save
    def fail(job, event):
        if event == "RECOVERY_RECONCILED" and len(job["commits"]) == 7:
            raise RuntimeError("simulated sudden termination")
        return original(job, event)
    monkeypatch.setattr(svc.db, "save", fail)
    with pytest.raises(RuntimeError):
        svc.create_file_commits(job["id"])
    fresh = Service(svc.config)
    report = fresh.resume_job(job["id"])
    assert report["created_commits"] == 10
    assert len({c["sha"] for c in report["commits"]}) == 10
    assert report["state"] == "VERIFIED"


def test_idempotency_and_branch_ownership(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "same", "ai/exact")
    assert svc.create_job("test/repo", "same", "ai/exact")["id"] == job["id"]
    with pytest.raises(AppError, match="owns branch"):
        svc.create_job("test/repo", "other", "ai/exact")
    with pytest.raises(AppError) as e:
        svc.create_job("test/repo", "same", "ai/different")
    assert e.value.code == "IDEMPOTENCY_CONFLICT"


def test_binary_and_executable(factory):
    svc, _, _ = factory()
    svc.config.repositories["test/repo"].allow_binary = True
    job = svc.create_job("test/repo", "binary")
    svc.plan_changes(job["id"], {"data.bin": "feat: add binary payload", "script.sh": "feat: add executable script"})
    svc.write_file(job["id"], "data.bin", "AP8BAg==", encoding="base64")
    svc.write_file(job["id"], "script.sh", "#!/bin/sh\nexit 0\n", executable=True)
    svc.preview_job(job["id"])
    svc.create_file_commits(job["id"])
    tree = svc.git.tree(svc._work(job))
    assert tree["script.sh"]["mode"] == "100755"
    assert svc.git.blob(svc._work(job), tree["data.bin"]["sha"]) == b"\0\xff\1\2"


@pytest.mark.parametrize("line", ["line\r\n", "line\n"])
def test_line_endings_preserved(factory, line):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "newline")
    modify(svc, job, "README.md", line)
    svc.preview_job(job["id"])
    svc.create_file_commits(job["id"])
    work = svc._work(job)
    assert svc.git.blob(work, svc.git.tree(work)["README.md"]["sha"]) == line.encode()


def test_exact_context_patch(factory):
    svc, _, _ = factory()
    job = svc.create_job("test/repo", "patch")
    svc.plan_changes(job["id"], {"README.md": "fix: contextual replacement"})
    checksum = hashlib.sha256(b"original\n").hexdigest()
    svc.apply_patch(job["id"], "README.md", "original", "changed", checksum)
    with pytest.raises(AppError) as e:
        svc.apply_patch(job["id"], "README.md", "original", "again", checksum)
    assert e.value.code == "STALE_FILE"


def test_reads_refresh_default_branch_without_user_mutation(factory):
    svc, source, _ = factory(mode="READ_ONLY")
    assert svc.read_file("test/repo", "README.md")["content"] == "original\n"
    # Write exact Git content bytes; write_text() converts LF to CRLF on Windows.
    (source / "README.md").write_bytes(b"upstream new\n")
    svc.git.run(source, "add", "--", "README.md")
    svc.git.run(source, "commit", "-m", "docs: upstream read update")
    svc.git.run(source, "push", "origin", "main")
    updated = svc.read_file("test/repo", "README.md")
    assert updated["content"] == "upstream new\n"
    assert updated["snapshot_sha"] == svc.git.text(source, "rev-parse", "HEAD")
