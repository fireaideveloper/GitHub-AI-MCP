# GitHub-AI-MCP

Desktop-oriented GitHub MCP project for controlled repository changes, task-based branches, local review, and pull requests.

> **Work in progress — staged publication.** This repository currently contains the initial project metadata and a small set of foundational source modules. The application is **not yet runnable** from this repository; remaining source, tests, and build scripts will follow in reviewed changes.

## Planned capabilities

- MCP tools for reviewing repository changes and publishing pull requests.
- Separate branches per task, with one changed file per commit.
- Desktop controls, background services, and OS-vault-protected credentials.
- A Windows single-executable distribution after native validation.

## Published so far

- `pyproject.toml` — package metadata and pinned dependencies.
- `.gitignore` — exclusions for local environments, sensitive configuration, and builds.
- `.env.example` — configuration notes without real credentials.
- `LICENSE` — MIT license.
- `src/github_ai_mcp/__init__.py` — Python package initialization.
- `src/github_ai_mcp/exceptions.py` — stable application error codes.
- `src/github_ai_mcp/config.py` — validated local application configuration.
- `src/github_ai_mcp/core/locking.py` — cross-process operation locks.
- `src/github_ai_mcp/desktop/streams.py` — inherited standard streams in the Windows executable.

## Next stages

Add secure path and credential checks, job persistence and orchestration, GitHub API support, local review policies, the MCP server and CLI, desktop GUI and tunnel supervision, tests, and packaging tools.

## Security and development status

Python 3.12+ is required. Do not commit real tokens, private configuration, databases, vendor binaries, or build outputs. The published source subset cannot run a complete CLI, MCP server, or desktop application. Native Windows compilation and end-to-end validation remain outstanding.
