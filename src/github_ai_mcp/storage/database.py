import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from github_ai_mcp.exceptions import AppError


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connection() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] not in {0, 1}:
                raise AppError("SCHEMA_VERSION", "Database schema is newer than this application")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, idem TEXT UNIQUE, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY, at REAL, job TEXT, event TEXT);
            CREATE TABLE IF NOT EXISTS grants(job TEXT, fingerprint TEXT, action TEXT, expires REAL,
                                             PRIMARY KEY(job, fingerprint, action));
            PRAGMA user_version=1;
            """)
        path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, job: dict, event: str):
        with self.connection() as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                       (job["id"], job["idempotency_key"], json.dumps(job)))
            db.execute("INSERT INTO audit(at,job,event) VALUES(?,?,?)", (time.time(), job["id"], event))

    def get(self, job_id: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise AppError("NOT_FOUND", "Job does not exist")
        return json.loads(row[0])

    def by_key(self, key: str):
        with self.connection() as db:
            row = db.execute("SELECT data FROM jobs WHERE idem=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_jobs(self) -> list[dict]:
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM jobs ORDER BY rowid DESC LIMIT 200")]

    def grant(self, job: dict, actions: list[str], hours: float = 1):
        with self.connection() as db:
            for action in actions:
                db.execute("INSERT OR REPLACE INTO grants VALUES(?,?,?,?)",
                           (job["id"], job["fingerprint"], action, time.time() + hours * 3600))

    def approved(self, job: dict, action: str) -> bool:
        with self.connection() as db:
            return db.execute("SELECT 1 FROM grants WHERE job=? AND fingerprint=? AND action=? AND expires>?",
                              (job["id"], job.get("fingerprint", ""), action, time.time())).fetchone() is not None

    def audit(self, job_id: str):
        with self.connection() as db:
            return [dict(at=r[0], event=r[1]) for r in db.execute(
                "SELECT at,event FROM audit WHERE job=? ORDER BY seq", (job_id,))]

    def prune_audit(self, retention_days: int):
        with self.connection() as db:
            cursor = db.execute("DELETE FROM audit WHERE at<?", (time.time() - retention_days * 86400,))
            return {"deleted_audit_rows": cursor.rowcount, "jobs_and_workspaces_preserved": True}

    def branch_owned(self, repository: str, branch: str) -> bool:
        with self.connection() as db:
            row = db.execute("""SELECT 1 FROM jobs
                WHERE json_extract(data,'$.repository')=?
                AND json_extract(data,'$.target_branch')=?
                AND json_extract(data,'$.state') NOT IN ('COMPLETED','CANCELLED','NO_CHANGE')
                LIMIT 1""", (repository, branch)).fetchone()
        return row is not None
