import os
import subprocess
import sys
from pathlib import Path
from github_ai_mcp.exceptions import AppError

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "GitHub-AI-MCP"


def command(config_path):
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        args = [str(executable)]
    else:
        windowed = executable.with_name("pythonw.exe")
        if windowed.is_file():
            executable = windowed
        args = [str(executable), "-m", "github_ai_mcp.desktop.entry"]
    if not executable.is_file() or not Path(config_path).is_file():
        raise AppError("STARTUP_INVALID", "Restore executable/configuration before enabling startup / Восстановите программу и конфигурацию")
    return subprocess.list2cmdline([*args, "--config", str(Path(config_path).resolve()), "--logon"])


def registry():
    if os.name != "nt":
        raise AppError("WINDOWS_ONLY", "Windows startup is available on Windows / Автозапуск доступен в Windows")
    import winreg
    return winreg


def status(config_path):
    try:
        reg = registry()
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
            actual, kind = reg.QueryValueEx(key, VALUE)
        return {"registered": True, "valid": kind == reg.REG_SZ and actual == command(config_path),
                "mechanism": "HKCU Run", "error": ""}
    except FileNotFoundError:
        return {"registered": False, "valid": False, "mechanism": "HKCU Run", "error": ""}
    except (AppError, OSError) as error:
        return {"registered": False, "valid": False, "mechanism": "HKCU Run", "error": str(error)}


def enable(config_path):
    reg = registry()

    legacy = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/GitHub-AI-MCP.lnk"
    if legacy.is_file():
        raise AppError("STARTUP_CONFLICT", "Remove the old GitHub-AI-MCP startup shortcut first / Удалите старый ярлык GitHub-AI-MCP из автозагрузки")
    value = command(config_path)
    with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
        reg.SetValueEx(key, VALUE, 0, reg.REG_SZ, value)
    return status(config_path)


def disable():
    reg = registry()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
            reg.DeleteValue(key, VALUE)
    except FileNotFoundError:
        pass
