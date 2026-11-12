"""Read-only bundle resources and same-executable worker commands."""
import os
import sys
from pathlib import Path



def program_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]


def asset_path(name: str) -> Path:
    return program_root() / "assets" / name


def service_command(config_path: Path, transport="streamable-http") -> list[str]:
    if getattr(sys, "frozen", False):
        command = [str(Path(sys.executable).resolve()), "--internal-server"]
    else:
        command = [sys.executable, "-m", "github_ai_mcp"]
    return [*command, "--config", str(config_path.resolve()), "serve", "--transport", transport]


def bundled_tool(name: str) -> str | None:
    relative = {"git": "git/cmd/git.exe", "gh": "gh.exe", "tunnel-client": "tunnel-client.exe"}
    path = program_root() / "vendor" / relative[name]
    return str(path) if path.is_file() else None


def initialize_runtime():
    """Make bundled Git and its credential helper available to existing tool calls."""
    if getattr(sys, "frozen", False):
        directories = [str(program_root() / "vendor/git/cmd"), str(program_root() / "vendor")]
        os.environ["PATH"] = os.pathsep.join([*directories, os.environ.get("PATH", "")])
