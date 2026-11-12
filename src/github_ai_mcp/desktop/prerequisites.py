"""Read-only dependency diagnostics; no installs, network access or vendor commands."""
import shutil
import subprocess

from github_ai_mcp.desktop.processes import run_background
from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.auth_github import vault

LINKS = {"git": "https://git-scm.com/download/win", "gh": "https://cli.github.com/",
         "vault": "https://support.microsoft.com/windows"}


def check_prerequisites() -> dict:
    result = {}
    for tool in ("git", "gh"):
        path = shutil.which(tool)
        status = "Missing"
        if path:
            try:
                probe = run_background([path, "--version"], capture_output=True, timeout=5)
                status = "Installed" if probe.returncode == 0 else "Unusable"
            except (OSError, subprocess.TimeoutExpired):
                status = "Unusable"
        result[tool] = {"status": status, "path": path, "url": LINKS[tool]}
    try:
        vault()
        status = "Available"
    except AppError:
        status = "Unavailable"
    result["vault"] = {"status": status, "url": LINKS["vault"]}
    return result
