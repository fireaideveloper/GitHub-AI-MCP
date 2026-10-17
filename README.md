# GitHub-AI-MCP

Desktop-oriented GitHub MCP project for controlled repository changes, task-based branches, local review, and pull requests.

> **Work in progress — staged publication.** This repository currently contains the initial project metadata and foundational and security source modules. The application is **not yet runnable** from this repository; remaining source, tests, and build scripts will follow in reviewed changes.

## Planned capabilities

- MCP tools for reviewing repository changes and publishing pull requests.
- Separate branches per task, with one changed file per commit.
- Desktop controls, background services, and OS-vault-protected credentials.
- A Windows single-executable distribution after native validation.

## Published so far

- `pyproject.toml` — package metadata and pinned dependencies.
- `.gitignore` — exclusions for local environments, sensitive configuration, and builds.
- `.env.example` — empty placeholder, with no credentials or comment-only configuration.
- `LICENSE` — MIT license.
- `src/github_ai_mcp/__init__.py` — Python package initialization.
- `src/github_ai_mcp/exceptions.py` — stable application error codes.
- `src/github_ai_mcp/config.py` — validated local application configuration.
- `src/github_ai_mcp/core/locking.py` — cross-process operation locks.
- `src/github_ai_mcp/desktop/streams.py` — inherited standard streams in the Windows executable.
- `src/github_ai_mcp/security/paths.py` — canonical path validation and symlink protection.
- `src/github_ai_mcp/security/secret_scan.py` — detection and redaction of credential-like content.
- `src/github_ai_mcp/security/auth_github.py` — GitHub credential storage through the OS vault.
- `src/github_ai_mcp/security/auth_mcp.py` — localhost MCP authorization and rate limiting.
- `src/github_ai_mcp/security/policy.py` — repository authorization and publishing policy.

## Next stages

Next publish job persistence and orchestration, Git operations and GitHub API support, the MCP server and CLI, desktop GUI and tunnel supervision, tests, and packaging tools.

## Security and development status

Python 3.12+ is required. Do not commit real tokens, private configuration, databases, vendor binaries, or build outputs. The published source subset cannot run a complete CLI, MCP server, or desktop application; some newly published modules depend on components not yet available in this repository. Native Windows compilation and end-to-end validation remain outstanding.
