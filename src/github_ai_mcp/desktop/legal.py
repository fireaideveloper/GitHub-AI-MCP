"""Offline discovery of installed legal files. Nothing opens user-selected URLs."""
from github_ai_mcp.desktop.runtime import program_root


def legal_files():
    root = program_root()
    paths = [root/"LICENSE", root/"docs/THIRD_PARTY.md", root/"docs/LICENSE_COMPLIANCE.md"]
    paths += sorted(p for p in (root/"legal").rglob("*") if p.is_file()) if (root/"legal").exists() else []
    return [p for p in paths if p.is_file()]
