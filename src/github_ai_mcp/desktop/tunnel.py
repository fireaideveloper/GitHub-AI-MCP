"""Profile preflight and lossless, backed-up edits. Vendor doctor owns exact schema."""
import io
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from ruamel.yaml import YAML
from github_ai_mcp.desktop.processes import background_options
from github_ai_mcp.desktop.runtime import service_command, bundled_tool
from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.auth_github import get_secret

SECRET = "tunnel-control-plane"


def profile_path(config):
    if config.tunnel_profile_file:
        return Path(config.tunnel_profile_file).expanduser().resolve()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", config.tunnel_profile) or config.tunnel_profile in {".", ".."}:
        raise AppError("PROFILE_INVALID", "Invalid profile name / Неверное имя профиля")
    directories = [os.environ.get("TUNNEL_CLIENT_PROFILE_DIR"),
                   str(Path(os.environ["APPDATA"]) / "tunnel-client") if os.environ.get("APPDATA") else None,
                   str(Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "tunnel-client")]
    for directory in filter(None, directories):
        candidate = Path(directory) / (config.tunnel_profile + ".yaml")
        if candidate.is_file():
            return candidate.resolve()
    raise AppError("PROFILE_MISSING", "Select existing tunnel YAML in Setup / Выберите существующий YAML профиля")


def read_profile(path):
    try:
        data = YAML(typ="rt").load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("control_plane"), dict):
            raise ValueError()
        if data["control_plane"].get("api_key") != "env:CONTROL_PLANE_API_KEY":
            raise AppError("PROFILE_SECRET", "Use api_key: env:CONTROL_PLANE_API_KEY; no plaintext key migration / Используйте ссылку env:CONTROL_PLANE_API_KEY")
        check_references(data)
        return data
    except AppError:
        raise
    except Exception:
        # Parser exceptions can contain YAML source, including credentials.
        raise AppError("PROFILE_INVALID", "Invalid YAML structure; repair profile in editor / Неверная структура YAML: исправьте профиль в редакторе") from None


def command_text(config_path):
    args = service_command(config_path, "stdio")
    if sys.platform == "win32":
        # Forward slashes survive vendor shell-word parsing as well as Windows argv.
        args = [argument.replace("\\", "/") for argument in args]
        return subprocess.list2cmdline(args)
    return shlex.join(args)


def expected_command(config, config_path):
    command = config.tunnel_stdio_command.strip() or command_text(config_path)
    if not command or any(ord(c) < 32 for c in command):
        raise AppError("MCP_COMMAND", "Use a single-line stdio command / Укажите однострочную команду stdio")
    from github_ai_mcp.security.secret_scan import scan
    scan(command.encode())
    return command


def local_profile(config, config_path, path=None):
    """Validate local structure/command without credentials, vendor or network."""
    data = read_profile(path or profile_path(config))
    main = main_command(data)
    if main["command"].strip() != expected_command(config, config_path):
        raise AppError("MCP_COMMAND", "Repair the MCP command in Setup (stale path or arguments) / Исправьте команду MCP в настройке запуска")
    if not Path(config_path).is_file():
        raise AppError("CONFIG_MISSING", "Application configuration missing / Конфигурация приложения отсутствует")
    return data


def main_command(data):
    mcp = data.get("mcp")
    commands = mcp.get("commands") if isinstance(mcp, dict) else None
    if not isinstance(commands, list):
        raise AppError("MCP_COMMAND", "mcp.commands must be a list / mcp.commands должен быть списком")
    main = [item for item in commands if isinstance(item, dict) and item.get("channel", "main") == "main"]
    if len(main) != 1 or not isinstance(main[0].get("command"), str):
        raise AppError("MCP_COMMAND", "This integration requires one main stdio command / Требуется одна команда stdio канала main")
    return main[0]


def child_environment(runtime_key=None):
    env = os.environ.copy()
    # Credential selected explicitly; never persist/import a shell key automatically.
    for name in ("TUNNEL_CLIENT_CONFIG", "TUNNEL_CLIENT_PROFILE", "TUNNEL_CLIENT_PROFILE_FILE", "MCP_COMMAND", "MCP_SERVER_URL", "CONTROL_PLANE_BASE_URL", "CONTROL_PLANE_TUNNEL_ID", "CONTROL_PLANE_API_KEY"):
        env.pop(name, None)
    try:
        env["CONTROL_PLANE_API_KEY"] = runtime_key or get_secret(SECRET)
    except AppError:
        raise AppError("TUNNEL_KEY_MISSING", "Save the tunnel runtime key in Setup / Сохраните ключ туннеля в настройке запуска") from None
    return env


def preflight(config, config_path, doctor=True, path=None, runtime_key=None):
    client = config.tunnel_client or bundled_tool("tunnel-client") or shutil.which("tunnel-client.exe") or shutil.which("tunnel-client")
    if not client or not Path(client).is_file():
        raise AppError("TUNNEL_MISSING", "Select official tunnel executable / Выберите официальный клиент туннеля")
    path = path or profile_path(config)
    data = local_profile(config, config_path, path)
    env = child_environment(runtime_key)
    if doctor:
        try:
            result = subprocess.run([str(Path(client).resolve()), "doctor", "--profile-file", str(path)],
                                    env=env, capture_output=True, timeout=25, **background_options())
        except subprocess.TimeoutExpired:
            raise AppError("DOCTOR_TIMEOUT", "Client doctor timed out; check network/profile / Проверка клиента превысила время: проверьте сеть и профиль") from None
        except OSError:
            raise AppError("TUNNEL_EXECUTABLE", "Cannot execute tunnel client / Не удалось запустить файл клиента туннеля") from None
        if result.returncode:
            # Vendor output can contain arbitrary secrets: do not export it.
            raise AppError("DOCTOR_FAILED", "Client doctor rejected the profile or credentials; open official client diagnostics / Клиент отклонил профиль или ключ: откройте его диагностику")
    return [str(Path(client).resolve()), "run", "--profile-file", str(path)], env, data


def repair_profile(config, config_path):
    path = profile_path(config)
    before = path.read_bytes()
    data = read_profile(path)
    main = main_command(data)
    main["command"] = expected_command(config, config_path)
    output = io.StringIO()
    YAML(typ="rt").dump(data, output)
    fd, name = tempfile.mkstemp(prefix=".github-ai-", suffix=".yaml", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(output.getvalue())
            stream.flush()
            os.fsync(stream.fileno())
        local_profile(config, config_path, path=temp)
        if path.read_bytes() != before:
            raise AppError("PROFILE_CHANGED", "Profile changed during validation; retry / Профиль изменился: повторите")
        backup = path.with_name(path.name + ".github-ai-backup-" + secrets.token_hex(6))
        backup.write_bytes(before)
        os.chmod(backup, 0o600)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return str(backup)


def external_processes(config):
    import psutil
    matches: list[int] = []
    inaccessible = False
    target = config.tunnel_client or bundled_tool("tunnel-client") or shutil.which("tunnel-client.exe") or shutil.which("tunnel-client")
    if not target:
        return matches, inaccessible
    for process in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            info = process.info
            if not info["exe"] and info.get("name", "").lower() == Path(target).name.lower():
                inaccessible = True
            if not info["exe"] or Path(info["exe"]).resolve() != Path(target).resolve():
                continue
            # Exact executable match only; no inference from an occupied port.
            matches.append(info["pid"])
        except psutil.AccessDenied:
            inaccessible = True
        except (psutil.NoSuchProcess, OSError):
            pass
    return matches, inaccessible


def health_observation(config, pid):
    """Only read a loopback listener belonging to the selected process; no adoption."""
    import psutil
    import httpx
    from datetime import datetime, timezone
    try:
        data = read_profile(profile_path(config))
        address = data.get("health", {}).get("listen_addr", "127.0.0.1:8080")
        host, port = address.rsplit(":", 1)
        if host not in {"127.0.0.1", "localhost"} or not 0 < int(port) < 65536:
            return {"health": "Unverified"}
        connections = psutil.Process(pid).net_connections(kind="tcp")
        if not any(c.status == psutil.CONN_LISTEN and c.laddr.port == int(port) for c in connections):
            return {"health": "Unverified"}
        with httpx.Client(timeout=0.5, trust_env=False) as client:
            response = client.get(f"http://127.0.0.1:{int(port)}/health?details=true")
            response.raise_for_status()
            if len(response.content) > 65536:
                return {"health": "Unverified"}
            snapshot = response.json()
        if snapshot.get("schema_version") != 1:
            return {"health": "Unverified"}
        observations = {"health": "Observed", "ready": snapshot.get("ready") is True}
        for name in ("mcp", "control-plane"):
            item = snapshot.get("components", {}).get(name, {})
            observed = item.get("observed_at")
            fresh = False
            if isinstance(observed, str):
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(observed.replace("Z", "+00:00"))).total_seconds()
                fresh = 0 <= age <= 60
            observations[name] = "Recent successful observation" if item.get("status") == "ok" and fresh else "Unverified"
        observations["degraded"] = any(snapshot.get("components", {}).get(name, {}).get("status") == "degraded" for name in ("mcp", "control-plane"))
        return observations
    except (AppError, OSError, ValueError, KeyError, TypeError, AttributeError, psutil.Error, httpx.HTTPError):
        return {"health": "Unverified"}


def check_references(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if re.search(r"(?i)(api[_-]?key|password|secret|token|authorization|cookie)", str(key)) and isinstance(value, str):
                if not value.startswith(("env:", "file:")):
                    raise AppError("PROFILE_SECRET", "Literal secret field blocked; use env:/file: references / Замените секрет на ссылку env:/file:")
            check_references(value)
    elif isinstance(data, list):
        for value in data:
            check_references(value)


def safe_editor_text(text):
    from github_ai_mcp.security.secret_scan import redact
    references: dict[str, str] = {}
    lines = []
    for line in text.splitlines(keepends=True):
        match = re.match(r"(\s*(?:api[_-]?key|password|secret|token|authorization|cookie)\s*:\s*)(.*)", line, re.I)
        if match and not match[2].strip().strip("\"'").startswith(("env:", "file:")):
            line = match[1] + "env:REPLACE_WITH_SECRET_REFERENCE\n"
        lines.append(line)
    text = "".join(lines)
    def hold(match):
        placeholder = "REF" + str(len(references))
        references[placeholder] = match.group(0)
        return placeholder
    text = re.sub(r"(?:env:|file:)[^\s\"']+", hold, text)
    text = redact(text)
    for placeholder, reference in references.items():
        text = text.replace(placeholder, reference)
    return text
