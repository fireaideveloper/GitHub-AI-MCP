"""Trusted local JSON configuration. MCP never exposes configuration mutations."""
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Repository(StrictModel):
    source: str
    default_branch: str = "main"
    author_name: str
    author_email: str = ""
    identity_authorized: bool = False
    allow_binary: bool = False
    required_checks: list[str] = Field(default_factory=list)
    # Commands are trusted local administration, never MCP inputs.
    @field_validator("author_name", "author_email")
    @classmethod
    def real_identity_text(cls, value: str, info):
        # Legacy configurations may omit email. Preserve read-only access, but
        # require an explicit identity before any commit/publication.
        if info.field_name == "author_email" and value == "":
            return value
        if not value or len(value) > 200 or any(ord(c) < 32 for c in value) or "<" in value or ">" in value:
            raise ValueError("Identity must be nonempty single-line real author text")
        return value

    checks: dict[str, list[str]] = Field(default_factory=dict)
    trusted_execution: bool = False


class Grant(StrictModel):
    repository: str
    # Empty string explicitly opts into all safe non-default task branches.
    # Existing ai/* grants are never widened automatically.
    branch_prefix: str = "ai/"
    actions: list[Literal["commit", "push", "pr"]]
    expires_at: float
    max_files: int = Field(default=100, ge=1, le=1000)
    max_bytes: int = Field(default=10_000_000, ge=1)


class Config(StrictModel):
    data_dir: Path = Field(default_factory=lambda: Path(
        os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "GitHub-AI-MCP")
    mode: Literal["READ_ONLY", "LOCAL_REVIEW", "AUTO_APPROVED"] = "READ_ONLY"
    locale: Literal["ru", "en"] = "ru"
    port: int = Field(default=8766, ge=1024, le=65535)
    tunnel_client: str = ""
    tunnel_profile: str = "github-ai-local"
    autostart_services: bool = True
    start_mcp: bool = True
    start_tunnel: bool = True
    minimize_on_startup: bool = False
    restart_services: bool = True
    critical_notifications: bool = True
    tunnel_profile_file: str = ""
    # Explicit local administrator override; empty follows the current executable.
    tunnel_stdio_command: str = ""
    background_on_close: bool = True
    setup_complete: bool = False
    repositories: dict[str, Repository] = Field(default_factory=dict)
    grants: list[Grant] = Field(default_factory=list)
    max_files: int = Field(default=100, ge=1, le=1000)
    max_file_bytes: int = Field(default=1_000_000, ge=1, le=10_000_000)
    max_job_bytes: int = Field(default=10_000_000, ge=1)
    git_timeout: int = Field(default=120, ge=1, le=600)
    retention_days: int = Field(default=14, ge=1)

    @model_validator(mode="after")
    def validate_sources(self):
        import re
        for name, repo in self.repositories.items():
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
                raise ValueError("Repository identifier must be owner/repo")
            if not repo.source.startswith("https://github.com/"):
                if not Path(repo.source).is_absolute():
                    raise ValueError("Source must be absolute local path or canonical GitHub HTTPS URL")
            elif repo.source != f"https://github.com/{name}.git":
                raise ValueError("GitHub source must match the allowlisted owner/repo")
        return self


def load_config(path: Path) -> Config:
    config = Config.model_validate_json(path.read_text(encoding="utf-8"))
    if not config.data_dir.is_absolute():
        config.data_dir = (path.resolve().parent / config.data_dir).resolve()
    return config


def save_config(path: Path, config: Config) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)


def resolve_config(path: Path | None = None) -> Path:
    """Explicit paths, environment, then per-user state; never write beside the EXE."""
    if path is not None:
        return path.expanduser().resolve()
    if os.environ.get("GITHUB_AI_CONFIG"):
        return Path(os.environ["GITHUB_AI_CONFIG"]).expanduser().resolve()
    return Config().data_dir / "config.json"
