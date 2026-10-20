from pathlib import Path

import pytest
from pydantic import ValidationError

from github_ai_mcp.config import Config, Repository, load_config, resolve_config, save_config


def test_defaults_are_read_only():
    config = Config()
    assert config.mode == "READ_ONLY"
    assert config.repositories == {}
    assert config.max_file_bytes <= config.max_job_bytes


def test_save_and_load_preserve_configuration(tmp_path: Path):
    path = tmp_path / "settings" / "config.json"
    repository = Repository(
        source="https://github.com/example/project.git",
        author_name="Example Developer",
        author_email="developer@example.com",
        identity_authorized=True,
    )
    original = Config(mode="LOCAL_REVIEW", repositories={"example/project": repository})
    save_config(path, original)
    restored = load_config(path)
    assert restored == original
    assert restored.repositories["example/project"].author_email == "developer@example.com"


@pytest.mark.parametrize(
    "repository_name,source",
    [
        ("invalid", "https://github.com/example/project.git"),
        ("example/project", "https://github.com/elsewhere/project.git"),
        ("example/project", "https://example.com/repository.git"),
        ("example/project", "relative/project"),
    ],
)
def test_repository_allowlist_rejects_invalid_sources(repository_name: str, source: str):
    with pytest.raises(ValidationError):
        Config(repositories={repository_name: Repository(source=source, author_name="Developer")})


@pytest.mark.parametrize("author_name", ["", "Multiple\nLines", "Someone <malicious>"])
def test_author_identity_rejects_invalid_names(author_name: str):
    with pytest.raises(ValidationError):
        Repository(source="https://github.com/example/project.git", author_name=author_name)


def test_explicit_config_path_is_resolved(tmp_path: Path):
    selected = tmp_path / "settings.json"
    assert resolve_config(selected) == selected.resolve()


def test_unrecognized_configuration_keys_are_rejected():
    with pytest.raises(ValidationError):
        Config.model_validate({"unexpected_flag": True})
