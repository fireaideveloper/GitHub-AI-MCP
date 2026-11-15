"""Native Windows one-file build. No downloads, installers, ZIPs or release reports."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def validate_vendor(root):
    """Vendor artifacts are explicit developer inputs, never downloaded at launch."""
    required = ['git/cmd/git.exe', 'git/mingw64/bin/git.exe',
                'git/usr/bin/sh.exe', 'gh.exe', 'tunnel-client.exe', 'LICENSES.txt']
    for name in required:
        path = root / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('Missing build input: ' + str(path))
        if name.endswith('.exe') and path.read_bytes()[:2] != b'MZ':
            raise ValueError('Not a Windows executable: ' + str(path))
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Vendor tree must not contain symlinks')
        if path.is_file() and (path.name.lower() in {'.env', 'config.json'} or
                              path.suffix.lower() in {'.key', '.pfx', '.sqlite3'}):
            raise ValueError('Private state in vendor tree: ' + str(path))
    return root.resolve()


def validate_output(directory):
    files = list(directory.iterdir())
    if len(files) != 1 or files[0].name != 'GitHub-AI-MCP.exe' or not files[0].is_file():
        raise ValueError('Distribution must contain exactly GitHub-AI-MCP.exe')
    if files[0].read_bytes()[:2] != b'MZ':
        raise ValueError('Missing Windows PE executable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, default=ROOT / 'vendor')
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Build on Windows with the development dependencies installed.')
    vendor = validate_vendor(args.runtime_dir)
    destination = args.dist.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if any(p.name != 'GitHub-AI-MCP.exe' for p in destination.iterdir()):
        parser.error('Output directory contains other files. Select an empty --dist; nothing was deleted.')
    env = {**os.environ, 'GITHUB_AI_BUILD_VENDOR': str(vendor)}
    # Work products, generated license inventory and staged output disappear even on failure.
    with tempfile.TemporaryDirectory(prefix='github-ai-mcp-build-') as temporary:
        stage = Path(temporary) / 'dist'
        env['GITHUB_AI_BUILD_WORK'] = temporary
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                        '--workpath', str(Path(temporary) / 'work'), '--distpath', str(stage),
                        str(ROOT / 'launcher/GitHub-AI-MCP.spec')], cwd=ROOT, env=env, check=True)
        validate_output(stage)
        target = destination / 'GitHub-AI-MCP.exe'
        pending = destination / '.GitHub-AI-MCP.pending'
        try:
            shutil.copyfile(stage / target.name, pending)
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)
    validate_output(destination)
    print(destination / 'GitHub-AI-MCP.exe')


if __name__ == '__main__':
    main()
