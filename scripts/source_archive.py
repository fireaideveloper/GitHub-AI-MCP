"""Complete source archive; no environment, state, build output or credentials."""
import argparse
import zipfile
from pathlib import Path

EXCLUDED = {'.git', '.venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
            'dist', 'build', 'vendor', 'node_modules', '.idea'}


def write_archive(root: Path, output: Path):
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.resolve() == output:
            continue
        relative = path.relative_to(root)
        if any(p in EXCLUDED or p.endswith('.egg-info') or p.startswith(('dist-', 'build-')) for p in relative.parts):
            continue
        if path.name in {'.env', 'config.json'} or path.suffix.lower() in {'.pyc', '.pfx', '.key', '.sqlite3', '.db', '.zip', '.exe', '.dll'}:
            continue
        files.append(path)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            # Fixed timestamp/order removes machine-specific filesystem timestamps.
            info = zipfile.ZipInfo('GitHub-AI-MCP/' + path.relative_to(root).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return files


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    write_archive(Path(__file__).resolve().parents[1], args.output)
