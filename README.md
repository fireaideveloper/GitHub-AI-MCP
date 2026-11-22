# GitHub-AI-MCP

Desktop GitHub MCP tools with local review, protected credentials, diagnostics,
background service supervision and opt-in Windows logon startup.

The Windows distribution is **one `GitHub-AI-MCP.exe`**. It opens the GUI and
runs MCP workers using the same executable. Internal vendor programs are
extracted automatically into PyInstaller's temporary directory. Configuration,
logs and database live in `%LOCALAPPDATA%\GitHub-AI-MCP`; credentials use the OS vault.

## Build on Windows

Developer tools are needed only to build; users of the EXE need no Python or Git installation.

```powershell
uv sync --frozen --extra gui --extra dev
uv pip install --python .venv/Scripts/python.exe -r launcher/build-requirements.txt
.venv/Scripts/python.exe scripts/build.py
```

First prepare the vendor input described in [RELEASE_BUILD.md](docs/RELEASE_BUILD.md).
It is absent from the supplied source archive. The build deliberately fails if
Git, gh or the official tunnel client is missing; it does not produce a partial
application disguised as standalone. Use `--runtime-dir C:/approved-runtime` for
an input outside the repository. Default output: `dist/GitHub-AI-MCP.exe` only.
No installers, ZIPs, checksum/signature reports or permanent build tree are generated.

Run by double-clicking the EXE. Enable/disable logon startup in Setup; it uses
one HKCU Run value pointing to this same EXE. After moving the EXE, re-enable
startup and repair the tunnel's MCP command in Setup. Existing user data stays in place.
Closing the window can leave the application in the tray; use Exit to stop its services.

Source development: `.venv/Scripts/python.exe -m github_ai_mcp.desktop.entry`.
Source tests: `uv run --frozen --extra gui --extra dev pytest -q`.
Packaged CLI: `GitHub-AI-MCP.exe --cli --config <path> doctor` with output redirected
or captured by a caller; the EXE never allocates a console.

See [task-based branch naming](docs/BRANCH_NAMING.md),
[Russian guide](docs/USER_GUIDE_RU.md), [English guide](docs/USER_GUIDE_EN.md),
[MCP connection](docs/MCP_CONNECTION.md), [security model](docs/SECURITY_MODEL.md),
[licensing](docs/LICENSE_COMPLIANCE.md), and [Windows acceptance](docs/WINDOWS_SMOKE_TEST.md).

This delivery was verified on Linux. Native Windows compilation, inherited stdio
handles, tray behavior, vendor binaries, live GitHub/tunnel and clean-machine
portability still require native testing. A successful source test suite is not
Windows certification.
