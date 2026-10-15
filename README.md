# GitHub-AI-MCP

Desktop-oriented GitHub MCP tools for controlled file changes, task-based branches, local review, and pull requests.

> **Work in progress — staged publication.** The source code is being uploaded in small, reviewed batches. This initial stage includes project metadata and safe configuration examples only. The application is **not yet runnable** from this repository.

## Planned capabilities

- GitHub MCP tools for inspecting, checking, and publishing repository changes.
- Separate branches for individual tasks and changes.
- Local desktop controls, diagnostics, and protected credentials.
- Windows single-executable packaging, subject to native Windows testing.

## What's available now

- `pyproject.toml` — Python package configuration and dependencies.
- `.gitignore` — excludes local environments, build artifacts, secrets, and runtime data.
- `.env.example` — credential handling notes without real secrets.
- `LICENSE` — MIT license.

Source modules, tests, documentation, and build scripts will follow in later updates.

## Security

Never commit authentication tokens, local configuration with credentials, or private runtime data. The project is intended to store secrets in the operating system credential vault.

## Status

The supplied source has **not** been certified as a working Windows build; native Windows validation is still required.
