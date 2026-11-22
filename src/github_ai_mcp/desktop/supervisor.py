"""Serialized, ownership-verified lifecycle with bounded recovery and redacted logs."""
import json
import hashlib
import os
import secrets
import random
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import psutil

from github_ai_mcp.config import load_config
from github_ai_mcp.desktop.processes import ProcessTree, background_options
from github_ai_mcp.desktop.runtime import service_command, bundled_tool
from github_ai_mcp.desktop.tunnel import preflight, external_processes, health_observation
from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.auth_github import get_secret
from github_ai_mcp.security.secret_scan import redact


def port_open(port):
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


class Supervisor:
    def __init__(self, config_path: Path):
        self.path = config_path.resolve()
        self.config = load_config(self.path)
        self.mutex = threading.RLock()
        self.children: dict = {}
        self.desired = {"mcp": False, "tunnel": False}
        self.errors = {"mcp": "", "tunnel": ""}
        self.error_codes = {"mcp": "", "tunnel": ""}
        self.retries = {"mcp": 0, "tunnel": 0}
        self.retry_at = {"mcp": 0.0, "tunnel": 0.0}
        self.log_path = self.config.data_dir / "services.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_mutex = threading.Lock()
        self.permanent = {"mcp": False, "tunnel": False}
        self.last_output = {"mcp": "", "tunnel": ""}
        self.control = secrets.token_urlsafe(32)
        self.hidden = [self.control]

    def log(self, name, event):
        message = str(event)
        for secret in self.hidden:
            message = message.replace(secret, "[REDACTED]")
        message = redact(message)
        with self.log_mutex:
            if self.log_path.exists() and self.log_path.stat().st_size > 2_000_000:
                self.log_path.replace(self.log_path.with_suffix(".previous.jsonl"))
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"time": time.time(), "service": name,
                                         "event": redact(message[:8000])}, ensure_ascii=False) + "\n")

    def logs(self):
        if not self.log_path.exists():
            return ""
        with self.log_path.open("rb") as stream:
            stream.seek(max(0, self.log_path.stat().st_size - 100_000))
            return stream.read().decode("utf-8", "replace")

    def _drain(self, name, process):
        for line in iter(process.stdout.readline, b""):
            message = line.decode("utf-8", "replace").rstrip()
            for secret in self.hidden:
                message = message.replace(secret, "[REDACTED]")
            safe = redact(message)
            self.last_output[name] = safe[:2000]
            if name == "tunnel" and any(term in safe.lower() for term in
                    ("unauthorized", "authentication rejected", "invalid api key", "status 401", "status 403", "exit status 2", "yaml:", "not set")):
                self.permanent[name] = True
            self.log(name, safe)
        process.stdout.close()

    def _health(self):
        token = get_secret("mcp-http")
        if token not in self.hidden:
            self.hidden.append(token)
        with httpx.Client(timeout=0.8, trust_env=False) as client:
            r = client.get(f"http://127.0.0.1:{self.config.port}/_local/health",
                           headers={"Authorization": "Bearer " + token})
            r.raise_for_status()
            data = r.json()
        return data

    def _health_pid_is_owned(self, pid):
        child = self.children.get("mcp")
        if not child or child[0].poll() is not None or type(pid) is not int:
            return False
        root_pid = child[0].pid
        if pid == root_pid:
            return True
        try:
            return any(process.pid == pid for process in
                       psutil.Process(root_pid).children(recursive=True))
        except (psutil.Error, OSError):
            return False

    def start(self, name, retry=False):
        with self.mutex:
            if name not in self.desired:
                raise ValueError("Unknown service")
            child = self.children.get(name)
            if child and child[0].poll() is None:
                return self.status()
            if not retry:
                self.retries[name] = 0
                self.permanent[name] = False
                self.retry_at[name] = 0
                self.last_output[name] = ""
            self.desired[name] = True
            self.errors[name] = ""
            self.error_codes[name] = ""
            process = None
            tree = None
            try:
                if child:
                    child[1].close()
                    self.children.pop(name, None)
                candidate = load_config(self.path)
                mcp = self.children.get("mcp")
                if mcp and mcp[0].poll() is None and candidate.port != self.config.port:
                    raise AppError("CONFIG_CHANGED", "Restart the application before changing the live MCP port")
                self.config = candidate
                env = os.environ.copy()
                if name == "mcp":
                    if port_open(self.config.port):
                        # Even a compatible server is never adopted without ownership proof.
                        raise AppError("PORT_CONFLICT", "Port is occupied by another instance. Stop it in its owning application or change the configured port.")
                    get_secret("mcp-http")
                    env["GITHUB_AI_CONTROL"] = self.control
                    args = service_command(self.path)
                else:
                    external, inaccessible = external_processes(self.config)
                    if external:
                        raise AppError("EXTERNAL_TUNNEL", "External tunnel client detected; stop it in its owning application / Найден внешний клиент: остановите его в исходном приложении")
                    if inaccessible:
                        raise AppError("EXTERNAL_UNKNOWN", "Process inspection denied; duplicate safety cannot be verified / Доступ к процессам запрещён: нельзя исключить дубликат")
                    args, env, _ = preflight(self.config, self.path)
                    key = env["CONTROL_PLANE_API_KEY"]
                    if key not in self.hidden:
                        self.hidden.append(key)
                process = subprocess.Popen(args, cwd=self.path.parent, env=env, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **background_options(suspended=True))
                tree = ProcessTree(process, suspended=True)
                self.children[name] = (process, tree, time.monotonic())
                threading.Thread(target=self._drain, args=(name, process), daemon=True).start()
                self.log(name, "started owned process " + str(process.pid))
            except Exception as error:
                if tree is not None:
                    tree.close()
                elif process is not None and process.poll() is None:
                    process.kill()
                if process is not None:
                    process.wait(timeout=5)
                    if process.stdout:
                        process.stdout.close()
                    self.children.pop(name, None)
                self.error_codes[name] = error.code if isinstance(error, AppError) else "START_FAILED"
                self.permanent[name] = isinstance(error, AppError) and error.code not in {"DOCTOR_TIMEOUT"}
                self.errors[name] = str(error) if isinstance(error, AppError) else "Service start failed; check selected executable and configuration"
                self.log(name, self.errors[name])
                if not retry:
                    self.desired[name] = not self.permanent[name]
                raise AppError("START_FAILED", self.errors[name]) from None
            return self.status()

    def stop(self, name):
        with self.mutex:
            self.desired[name] = False
            self.errors[name] = ""
            self.error_codes[name] = ""
            child = self.children.get(name)
            if child:
                process, tree, _ = child
                if process.poll() is None:
                    if name == "mcp":
                        try:
                            data = self._health()
                            if data.get("instance") != hashlib.sha256(self.control.encode()).hexdigest() or not self._health_pid_is_owned(data.get("pid")):
                                raise AppError("OWNERSHIP_FAILED", "Server identity mismatch")
                            with httpx.Client(timeout=2, trust_env=False) as client:
                                response = client.post(f"http://127.0.0.1:{self.config.port}/_local/shutdown",
                                    headers={"Authorization": "Bearer " + get_secret("mcp-http"),
                                             "X-Local-Control": self.control})
                                response.raise_for_status()
                            process.wait(timeout=6)
                        except (httpx.HTTPError, ValueError, AppError, subprocess.TimeoutExpired):
                            self.log(name, "graceful shutdown unavailable; terminating owned process tree")
                            tree.kill()
                    else:
                        # No undocumented tunnel shutdown API is assumed.
                        process.terminate()
                        try:
                            process.wait(timeout=4)
                        except subprocess.TimeoutExpired:
                            tree.kill()
                tree.close()
                process.wait(timeout=5)
                self.children.pop(name, None)
                self.log(name, "owned process tree stopped")
                if name == "mcp":
                    deadline = time.monotonic() + 3
                    while port_open(self.config.port) and time.monotonic() < deadline:
                        time.sleep(0.1)
                    if port_open(self.config.port):
                        self.errors[name] = "Owned process exited but port is occupied; unrelated listener left untouched"
                        raise AppError("PORT_CONFLICT", self.errors[name])
            return self.status()

    def reload_config(self):
        with self.mutex:
            candidate = load_config(self.path)
            child = self.children.get("mcp")
            if child and child[0].poll() is None and candidate.port != self.config.port:
                raise AppError("CONFIG_CHANGED", "Restart MCP before changing its live port")
            self.config = candidate
            return self.status()

    def restart(self, name):
        with self.mutex:
            self.stop(name)
            return self.start(name)

    def stop_all(self):
        errors = []
        for name in ("tunnel", "mcp"):
            try:
                self.stop(name)
            except Exception as error:
                errors.append(str(error))
        if errors:
            raise AppError("STOP_FAILED", "; ".join(errors))
        return self.status()

    def poll(self):
        with self.mutex:
            for name, desired in self.desired.items():
                child = self.children.get(name)
                if name == "tunnel" and child and child[0].poll() is None and self.permanent[name]:
                    child[0].terminate()
                    try:
                        child[0].wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        child[1].kill()
                        child[0].wait(timeout=5)
                if child and child[0].poll() is None and time.monotonic() - child[2] > 60:
                    if name == "mcp":
                        try:
                            if self._health().get("instance") == hashlib.sha256(self.control.encode()).hexdigest():
                                self.retries[name] = 0
                        except (AppError, httpx.HTTPError, ValueError):
                            pass
                    # Tunnel retry count is not reset solely on process liveness.
                if desired and name == "mcp" and child and child[0].poll() is None and time.monotonic() - child[2] > 15:
                    try:
                        health = self._health()
                        healthy = health.get("instance") == hashlib.sha256(self.control.encode()).hexdigest() and self._health_pid_is_owned(health.get("pid"))
                    except (AppError, httpx.HTTPError, ValueError):
                        healthy = False
                    if not healthy:
                        self.last_output[name] = "MCP readiness timeout / Превышено время готовности MCP"
                        child[1].kill()
                        child[0].wait(timeout=5)
                if not desired or (child and child[0].poll() is None):
                    continue
                if child:
                    child[1].close()
                    if name == "mcp":
                        # The Windows Job has been closed, but its descendants may
                        # release the listening socket slightly later.
                        deadline = time.monotonic() + 5
                        while port_open(self.config.port) and time.monotonic() < deadline:
                            time.sleep(0.1)
                    self.errors[name] = ("Service exited unexpectedly (exit " + str(child[0].returncode) + "). "
                                         + (self.last_output[name] or "Open service logs / Откройте журнал служб"))
                    self.error_codes[name] = "PROCESS_EXITED"
                    if child[0].returncode == 2:
                        self.permanent[name] = True
                now = time.monotonic()
                if not self.retry_at[name]:
                    self.retry_at[name] = now + 2 ** (self.retries[name] + 1) + random.uniform(0, 1)
                if self.config.restart_services and not self.permanent[name] and self.retries[name] < 3 and now >= self.retry_at[name]:
                    self.retries[name] += 1
                    self.retry_at[name] = 0
                    self.log(name, "bounded crash recovery " + str(self.retries[name]))
                    try:
                        self.start(name, retry=True)
                    except AppError:
                        pass
            return self.status()

    def status(self):
        with self.mutex:
            result = {}
            for name in self.desired:
                child = self.children.get(name)
                running = bool(child and child[0].poll() is None)
                result[name] = {"state": "Running" if running else "Failed" if self.errors[name] else "Stopped",
                                "process_alive": running, "owned": bool(child),
                                "pid": child[0].pid if child and running else None, "error": self.errors[name],
                                "error_code": self.error_codes[name],
                                "exit_code": child[0].returncode if child and not running else None,
                                "retries": self.retries[name]}
            result["mcp"]["port_open"] = port_open(self.config.port)
            result["mcp"]["endpoint"] = f"http://127.0.0.1:{self.config.port}/mcp"
            result["mcp"]["healthy"] = False
            if not result["mcp"]["process_alive"] and result["mcp"]["port_open"]:
                result["mcp"]["state"] = "Failed"
                result["mcp"]["error"] = "Port occupied by an external instance; this controller does not own it"
                result["mcp"]["error_code"] = "PORT_CONFLICT"
            if result["mcp"]["process_alive"]:
                try:
                    data = self._health()
                    result["mcp"]["healthy"] = (data.get("instance") == hashlib.sha256(self.control.encode()).hexdigest() and
                                                  self._health_pid_is_owned(data.get("pid")))
                except (AppError, httpx.HTTPError, ValueError):
                    pass
                if not result["mcp"]["healthy"]:
                    result["mcp"]["state"] = "Starting" if time.monotonic() - self.children.get("mcp", (None, None, time.monotonic()))[2] < 15 else "Failed"
            if not result["tunnel"]["process_alive"] and not self.errors["tunnel"] and not self.config.tunnel_client and not bundled_tool("tunnel-client") and not shutil.which("tunnel-client.exe") and not shutil.which("tunnel-client"):
                result["tunnel"]["state"] = "Not configured"
            if result["mcp"]["process_alive"] and not result["mcp"]["healthy"] and result["mcp"]["state"] == "Failed":
                result["mcp"]["error"] = "Owned process is alive but authenticated health verification failed; check service logs"
                result["mcp"]["error_code"] = "HEALTH_FAILED"
            if result["tunnel"]["process_alive"]:
                result["tunnel"]["state"] = "Running, connection unverified"
                evidence = health_observation(self.config, result["tunnel"]["pid"])
                result["tunnel"]["observations"] = evidence
                if evidence.get("degraded"):
                    result["tunnel"]["state"] = "Degraded"
                elif evidence.get("mcp") == evidence.get("control-plane") == "Recent successful observation":
                    if time.monotonic() - self.children["tunnel"][2] > 60:
                        self.retries["tunnel"] = 0
            else:
                external, inaccessible = external_processes(self.config)
                if external:
                    result["tunnel"]["state"] = "External process detected, ownership unverified"
                    result["tunnel"]["external_pids"] = external
                    result["tunnel"]["owned"] = False
                    if len(external) == 1:
                        result["tunnel"]["observations"] = health_observation(self.config, external[0])
                elif inaccessible:
                    result["tunnel"]["inspection"] = "Access denied; external detection incomplete"
                elif self.desired["tunnel"] and self.retry_at["tunnel"] and self.retries["tunnel"] < 3 and not self.permanent["tunnel"] and self.config.restart_services:
                    result["tunnel"]["state"] = "Reconnecting"
            result["tunnel"]["remote_availability"] = "Unverified"
            result["tunnel"]["profile"] = self.config.tunnel_profile
            result["tunnel"]["connection"] = "Unverified" if result["tunnel"]["process_alive"] else "Disconnected"
            return result
