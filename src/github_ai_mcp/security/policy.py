import time

from github_ai_mcp.config import Config
from github_ai_mcp.exceptions import AppError
from github_ai_mcp.storage.database import Database


class Policy:
    def __init__(self, config: Config, db: Database):
        self.config, self.db = config, db

    def repo(self, name: str):
        if name not in self.config.repositories:
            raise AppError("PERMISSION_DENIED", "Repository not allowlisted")
        return self.config.repositories[name]

    def write(self):
        if self.config.mode == "READ_ONLY":
            raise AppError("PERMISSION_DENIED", "READ_ONLY prohibits mutations")

    def authorize(self, job: dict, action: str):
        self.write()
        repo = self.repo(job["repository"])
        if not repo.identity_authorized or not repo.author_email:
            raise AppError("IDENTITY_REQUIRED", "Authorize your real commit identity in local settings")
        if action in {"push", "pr"} and self.config.mode != "AUTO_APPROVED":
            raise AppError("PERMISSION_DENIED", "Remote writes require AUTO_APPROVED")
        if self.db.approved(job, action):
            return
        if self.config.mode == "AUTO_APPROVED":
            for grant in self.config.grants:
                if (grant.repository == job["repository"] and grant.expires_at > time.time()
                        and ((grant.branch_prefix == "" and job["target_branch"] != repo.default_branch)
                             or (grant.branch_prefix.startswith("ai/")
                                 and job["target_branch"].startswith(grant.branch_prefix)))
                        and action in grant.actions
                        and len(job.get("changes", [])) <= grant.max_files
                        and job.get("total_bytes", 0) <= grant.max_bytes):
                    return
        raise AppError("APPROVAL_REQUIRED", "Approve this exact preview using the local GUI or CLI")
