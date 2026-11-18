"""Actual offline Git commits and local bare-remote push. Never contacts GitHub."""
import json
import tempfile
from pathlib import Path

from github_ai_mcp.config import Config, Grant, Repository
from github_ai_mcp.core.git_engine import Git
from github_ai_mcp.core.job_engine import Service


def run_demo(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    git = Git()
    source, remote = root / "source", root / "remote.git"
    source.mkdir()
    git.run(source, "init", "-b", "main")
    git.run(source, "config", "user.name", "Offline Demo")
    git.run(source, "config", "user.email", "demo@example.invalid")
    (source / "README.md").write_text("Offline fixture\n")
    git.run(source, "add", "--", "README.md")
    git.run(source, "commit", "-m", "docs: create offline fixture")
    git.run(root, "init", "--bare", "--initial-branch=main", str(remote))
    git.run(source, "remote", "add", "origin", str(remote))
    git.run(source, "push", "origin", "main")
    config = Config(data_dir=root / "state", mode="AUTO_APPROVED",
                    repositories={"demo/local": Repository(source=str(remote), author_name="Offline Demo",
                                                          author_email="demo@example.invalid", identity_authorized=True)},
                    grants=[Grant(repository="demo/local", actions=["commit", "push"], expires_at=4102444800)])
    svc = Service(config)
    job = svc.create_job("demo/local", "demo-five-paths")
    names = ["src/a.txt", "src/b.txt", "tests/test.txt", "документы/привет 🌍.txt", "README.md"]
    svc.plan_changes(job["id"], {p: "feat: update " + p for p in names})
    for path in names:
        expected = svc.read_file("demo/local", path, job["id"])["checksum"] if path == "README.md" else None
        svc.write_file(job["id"], path, "Actual offline change: " + path + "\n", expected)
    preview = svc.preview_job(job["id"])
    report = svc.create_file_commits(job["id"])
    assert report["created_commits"] == 5
    report = svc.publish_branch(job["id"])
    assert report["pushed_commits"] == 5
    assert svc.get_remote_status(job["id"])["matches"]
    return {"preview": preview, "report": report, "fixture_root": str(root)}


if __name__ == "__main__":
    print(json.dumps(run_demo(Path(tempfile.mkdtemp(prefix="github-ai-demo-"))), ensure_ascii=False, indent=2))
