import argparse
import getpass
import json
import secrets
import sys
from pathlib import Path
from typing import Any

from github_ai_mcp.config import Config, load_config, resolve_config, save_config
from github_ai_mcp.core.job_engine import Service
from github_ai_mcp.exceptions import AppError


def parser():
    p = argparse.ArgumentParser(prog="github-ai-mcp")
    p.add_argument("--config", type=Path, default=None)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("doctor")
    sub.add_parser("prune-audit")
    sub.add_parser("gui")
    sub.add_parser("login")
    sub.add_parser("logout")
    sub.add_parser("auth-mcp")
    srv = sub.add_parser("serve")
    srv.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    repo = sub.add_parser("repo")
    repo.add_argument("action", choices=["list", "info"])
    repo.add_argument("repository", nargs="?")
    job = sub.add_parser("job")
    job.add_argument("action", choices=["list", "status", "preview", "resume", "cancel", "commit", "publish", "report", "approve"])
    job.add_argument("job_id", nargs="?")
    job.add_argument("--fingerprint")
    job.add_argument("--actions", nargs="+", choices=["commit", "push", "pr"], default=["commit"])
    job.add_argument("--output", type=Path)
    return p


def main():
    args = parser().parse_args()
    args.config = resolve_config(args.config)
    try:
        result: dict[str, Any] | list[Any]
        if args.command == "init":
            if args.config.exists():
                raise AppError("ALREADY_EXISTS", "Configuration already exists")
            save_config(args.config, Config())
            result = {"config": str(args.config), "mode": "READ_ONLY"}
        elif args.command in {"login", "logout", "auth-mcp"}:
            from github_ai_mcp.security.auth_github import logout, store_token
            if args.command == "login":
                store_token(getpass.getpass("GitHub fine-grained PAT (hidden): "))
                result = {"stored": True, "note": "Install GitHub CLI for private Git clone/push; the vault credential is reused"}
            elif args.command == "logout":
                logout()
                result = {"deleted_from_vault": True, "revoke": "https://github.com/settings/tokens"}
            else:
                from github_ai_mcp.security.auth_github import store_secret
                token = secrets.token_urlsafe(32)
                store_secret("mcp-http", token)

                print("MCP HTTP authentication token; save in your client's secure credentials (never Git):")
                print(token)
                return
        else:
            config = load_config(args.config)
            service = Service(config)
            if args.command == "serve":
                from github_ai_mcp.server import serve
                serve(service, args.transport)
                return
            if args.command == "gui":
                from github_ai_mcp.gui.app import run
                run(service, args.config)
                return
            if args.command == "prune-audit":
                result = service.db.prune_audit(config.retention_days)
            elif args.command == "doctor":
                import shutil
                doctor_result = service.health_check()
                doctor_result["executables"] = {n: shutil.which(n) for n in ["python", "git", "gh"]}
                import socket
                with socket.socket() as probe:
                    probe.settimeout(1)
                    doctor_result["loopback_port_open"] = probe.connect_ex(("127.0.0.1", config.port)) == 0
                try:
                    doctor_result["github"] = service.github.request("GET", "/user")["login"]
                except AppError as e:
                    doctor_result["github"] = e.code
                result = doctor_result
            elif args.command == "repo":
                result = service.list_repositories() if args.action == "list" else service.get_repository_info(args.repository)
            elif args.command == "job":
                if args.action == "list":
                    result = [service._report(j) for j in service.db.list_jobs() if j["repository"] in config.repositories]
                else:
                    if not args.job_id:
                        raise AppError("INVALID_INPUT", "job_id required")
                    if args.action == "approve":
                        preview = service.preview_job(args.job_id)
                        if args.fingerprint != preview["fingerprint"]:
                            raise AppError("STALE_APPROVAL", "Supply --fingerprint from the reviewed preview")
                        print(json.dumps(preview, ensure_ascii=False, indent=2))
                        if input(f"Approve {args.actions} for this exact diff? Type APPROVE: ") != "APPROVE":
                            raise AppError("CANCELLED", "Approval cancelled")
                        result = service.approve_local(args.job_id, args.fingerprint, args.actions)
                    else:
                        method = {"status": "get_job_status", "preview": "preview_job", "resume": "resume_job",
                                  "cancel": "cancel_job", "commit": "create_file_commits", "publish": "publish_branch",
                                  "report": "get_job_report"}[args.action]
                        result = getattr(service, method)(args.job_id)
                    if args.output:
                        data = json.dumps(result, ensure_ascii=False, indent=2)
                        if args.output.suffix.lower() == ".md":
                            data = "# GitHub-AI-MCP Job Report\n\n```json\n" + data + "\n```\n"
                        args.output.write_text(data, encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except AppError as e:
        print(json.dumps({"ok": False, "error_code": e.code, "message": str(e)}), file=sys.stderr)
        raise SystemExit(2)
    except (ValueError, OSError):
        print("Configuration/file error; check the path and validated config schema", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
