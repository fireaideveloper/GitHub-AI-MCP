"""Portable, fail-closed repository path validation."""
import re
from pathlib import Path, PurePosixPath

from github_ai_mcp.exceptions import AppError

RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
SENSITIVE = {".git", ".ssh", ".aws", ".gnupg", ".netrc", ".npmrc", ".pypirc",
             "id_rsa", "id_ed25519", "credentials", "credentials.json"}


def safe_path(root: Path, path: str) -> Path:
    if not path or len(path) > 220 or "\\" in path or ":" in path or "\x00" in path:
        raise AppError("UNSAFE_PATH", "Invalid or nonportable path")
    p = PurePosixPath(path)
    parts = path.split("/")
    if p.is_absolute() or any(x in {"", ".", ".."} for x in parts):
        raise AppError("UNSAFE_PATH", "Path must be a canonical repository-relative path")
    for part in parts:
        low = part.casefold()
        if (low in SENSITIVE or (low.startswith(".env") and low != ".env.example")
                or low.endswith((".pem", ".key", ".p12", ".pfx"))
                or part.endswith((" ", ".")) or RESERVED.match(part)
                or any(ord(c) < 32 for c in part)):
            raise AppError("SENSITIVE_PATH", "Sensitive or reserved path denied")
    dest = root.joinpath(*parts)
    for ancestor in [dest, *dest.parents]:
        if ancestor == root.parent:
            break
        if ancestor.is_symlink():
            raise AppError("UNSAFE_PATH", "Symlink traversal denied")
    if not dest.resolve().is_relative_to(root.resolve()):
        raise AppError("UNSAFE_PATH", "Workspace escape denied")
    return dest
