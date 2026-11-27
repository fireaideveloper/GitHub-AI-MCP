# Single-executable Windows build

New to the project? Start with [Windows quickstart (EN)](QUICKSTART_EN.md) or [быстрый старт (RU)](QUICKSTART_RU.md) for installation, official downloads, profile configuration and first-run checks.

Build on native Windows x64 with Python 3.12 and the locked environment.
PyInstaller cannot cross-compile a Windows executable from this Linux delivery.

## Explicit build inputs

The archive contains application sources, not vendor executables. Prepare a
reviewed `vendor/` directory (or pass `--runtime-dir <absolute directory>`):

```text
vendor/
  git/                  complete x64 PortableGit distribution, original layout
    cmd/git.exe
    mingw64/bin/git.exe
    usr/bin/sh.exe
    ...                 all original DLLs, helpers, certificates and licenses
  gh.exe                official x64 GitHub CLI executable
  tunnel-client.exe     this project's official provider client, not cloudflared
  LICENSES.txt           vendor versions, SHA256, upstream origins, license texts,
                         corresponding source/source offers where applicable
  ...                   vendor notices and required companion resources
```

Use a clean extracted PortableGit archive, not an installed Git directory. Do not copy uninstall artifacts (`unins000.*`) or record absolute personal paths in `LICENSES.txt`; use relative paths. Do not copy installed application profiles, YAML credentials, PATs, user data,
private signing material or your entire development environment. The required
file check validates presence and PE signatures; it cannot prove completeness,
trustworthiness or licensing of a vendor distribution. Preserve the full
PortableGit tree. Obtain the tunnel client and its redistribution rights from
its provider; this source project supplies neither its binary nor its license.
The provider account, existing YAML profile and runtime control-plane key remain
required. No cloudflared download or replacement protocol is invented.

## One build command

```powershell
uv sync --frozen --extra gui --extra dev
uv pip install --python .venv/Scripts/python.exe -r launcher/build-requirements.txt
.venv/Scripts/python.exe scripts/build.py
```

The last command is the production build. Use `--runtime-dir C:/approved-runtime`
if inputs live elsewhere. It validates inputs, invokes the single onefile/windowed
spec, stages output in an OS temporary directory and atomically replaces only
`dist/GitHub-AI-MCP.exe`. A nonempty output directory containing other files is
refused without deletion. Old release folders should be removed by the developer
or a fresh `--dist` selected. Work directories and generated license inventory
are removed on build completion/failure. Runtime license texts are embedded in
the EXE and available through About / Legal. No release archive, installer,
checksum, signature report or evidence JSON is produced by default.

Run `dist/GitHub-AI-MCP.exe`; no installation or admin privileges are requested.
The spec embeds Python, Qt, application code and the prepared vendor tree.
MCP HTTP and stdio use this same EXE with `--internal-server`. Stdout is protocol
only in stdio mode; inherited Windows pipes are reopened before MCP imports.
Worker subprocesses share the GUI's extraction directory and are owned through
Windows Job Objects. The EXE must stay available at its path while running.
Temporary extraction is a PyInstaller requirement; an abnormal machine shutdown
can leave temporary OS files, never a permanent runtime beside the EXE.

## Verification

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src
.venv/Scripts/python.exe scripts/windows_smoke.py --bundle dist --output "$env:TEMP/GitHub-AI-MCP-smoke.json"
```

Smoke tests are an explicit optional command, on a disposable Windows account
with no existing app credentials. They capture the actual packaged stdio,
HTTP ownership/recovery/shutdown and offscreen GUI startup. The smoke report
lives outside dist. Test the EXE separately on a clean Windows VM without
Python, source, Git or gh, with PATH cleared of developer tools; test private
Git operations and your authorized provider tunnel. Verify native tray exit,
logon enable/disable, moved paths, Unicode paths and no orphaned descendants.
GitHub/provider credentials and external account authorization cannot be tested
without a real session. Neither this source archive nor CI compilation alone
proves these requirements.

Optional developer tools `source_archive.py`, `release_tools.py hash` and
`launcher/sign_windows.ps1` remain available explicitly and are never called by
the production build. Signing requires your own certificate; no identity is invented.
