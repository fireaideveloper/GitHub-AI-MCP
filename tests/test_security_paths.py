from pathlib import Path

import pytest

from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.paths import safe_path


def test_safe_path_accepts_nested_repository_file(tmp_path: Path):
    expected = tmp_path / "src" / "package" / "module.py"
    assert safe_path(tmp_path, "src/package/module.py") == expected


@pytest.mark.parametrize(
    "candidate",
    [
        "",
        "/absolute.txt",
        "../outside.txt",
        "folder/../../outside.txt",
        "folder//file.txt",
        "./file.txt",
        "folder/./file.txt",
        "folder\\file.txt",
        "C:/windows/file.txt",
        "folder/file.txt ",
        "folder/CON.txt",
        ".git/config",
        ".env",
        ".env.production",
        "secrets/private.key",
        "keys/id_rsa",
        "credentials.json",
        "dir/aux",
        "folder/evil\x00name",
    ],
)
def test_unsafe_paths_are_rejected(tmp_path: Path, candidate: str):
    with pytest.raises(AppError) as error:
        safe_path(tmp_path, candidate)
    assert error.value.code in {"UNSAFE_PATH", "SENSITIVE_PATH"}


def test_env_example_is_allowed(tmp_path: Path):
    assert safe_path(tmp_path, ".env.example") == tmp_path / ".env.example"


def test_symlink_escape_is_rejected(tmp_path: Path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    link = workspace / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks are unavailable on this platform")
    with pytest.raises(AppError) as error:
        safe_path(workspace, "linked/secret.txt")
    assert error.value.code == "UNSAFE_PATH"


def test_overlong_path_is_rejected(tmp_path: Path):
    with pytest.raises(AppError):
        safe_path(tmp_path, "a" * 221)
