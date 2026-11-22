"""Real loopback processes; fake vault only in isolated fixtures, never production."""
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import httpx
import pytest

from github_ai_mcp.config import Config, resolve_config, save_config
from github_ai_mcp.desktop.control import ControlRoutes
from github_ai_mcp.desktop.supervisor import Supervisor, port_open
from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.auth_mcp import LocalAuth


def wait_health(controller):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        # Recovery is driven by poll(); a child may be temporarily absent
        # while the previous owned process tree is being replaced.
        state = controller.poll()
        if state["mcp"]["healthy"]:
            return state
        if controller.permanent["mcp"] or not controller.desired["mcp"]:
            pytest.fail(controller.logs())
        time.sleep(0.05)
    pytest.fail(controller.logs())


@pytest.fixture
def controller(tmp_path, monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    config = Config(data_dir=tmp_path / "state", port=port)
    path = tmp_path / "config.json"
    save_config(path, config)
    token = "fixture-loopback-credential"
    monkeypatch.setattr("github_ai_mcp.desktop.supervisor.get_secret", lambda _: token)
    original = subprocess.Popen
    def spawn(args, **kwargs):
        if "github_ai_mcp" in args:
            # Substitute a test-only vault in the child interpreter; production has no env-secret path.
            code = ("import runpy,sys; import github_ai_mcp.security.auth_github as auth; "
                    f"auth.get_secret=lambda name: {token!r}; "
                    "sys.argv=['github-ai-mcp',*sys.argv[1:]]; "
                    "runpy.run_module('github_ai_mcp',run_name='__main__')")
            args = [sys.executable, "-c", code, *args[3:]]
        return original(args, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    manager = Supervisor(path)
    yield manager
    manager.stop_all()


def test_start_stop_restart_confirms_port_and_owned_pid(controller):
    controller.start("mcp")
    first = wait_health(controller)
    pid = first["mcp"]["pid"]
    controller.start("mcp")
    assert controller.status()["mcp"]["pid"] == pid
    stopped = controller.stop("mcp")
    assert stopped["mcp"]["state"] == "Stopped"
    assert not port_open(controller.config.port)
    assert controller.poll()["mcp"]["state"] == "Stopped"
    controller.start("mcp")
    wait_health(controller)
    controller.restart("mcp")
    assert wait_health(controller)["mcp"]["pid"] != pid
    controller.stop_all()
    assert not controller.children


def test_port_conflict_leaves_unrelated_listener_alive(controller):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", controller.config.port))
        listener.listen()
        with pytest.raises(AppError, match="occupied"):
            controller.start("mcp")
        assert port_open(controller.config.port)
        assert not controller.children
        controller.stop("mcp")
        assert port_open(controller.config.port)


def test_crash_recovery_is_bounded_and_manual_stop_disables_it(controller):
    controller.start("mcp")
    wait_health(controller)
    process = controller.children["mcp"][0]
    process.kill()
    process.wait(timeout=5)
    controller.retry_at["mcp"] = time.monotonic() - 1
    controller.poll()
    assert wait_health(controller)["mcp"]["pid"] != process.pid
    assert controller.retries["mcp"] == 1
    controller.stop("mcp")
    controller.retry_at["mcp"] = time.monotonic() - 1
    controller.poll()
    assert not controller.desired["mcp"]
    assert not controller.children


def test_recovery_exhaustion_does_not_spawn_fourth_retry(controller):
    controller.start("mcp")
    wait_health(controller)
    process = controller.children["mcp"][0]
    process.kill()
    process.wait(timeout=5)
    controller.retries["mcp"] = 3
    controller.retry_at["mcp"] = time.monotonic() - 1
    state = controller.poll()
    assert state["mcp"]["state"] == "Failed"
    assert controller.children["mcp"][0] is process


def test_log_redacts_nonce_and_bearer(controller):
    controller.log("test", controller.control + " Authorization: Bearer private-fixture-value")
    logs = controller.logs()
    assert controller.control not in logs
    assert "private-fixture-value" not in logs


async def test_shutdown_requires_both_bearer_and_private_nonce():
    runner = SimpleNamespace(should_exit=False)
    async def fallback(scope, receive, send):
        raise AssertionError("unexpected fallback")
    routes = ControlRoutes(fallback, "private-controller", runner)
    app = LocalAuth(routes, "fixture", 8766)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8766") as client:
        assert (await client.post("/_local/shutdown")).status_code == 401
        assert (await client.post("/_local/shutdown", headers={"Authorization": "Bearer fixture"})).status_code == 403
        assert not runner.should_exit
        headers = {"Authorization": "Bearer fixture", "X-Local-Control": "private-controller"}
        assert (await client.get("/_local/shutdown", headers=headers)).status_code == 403
        assert (await client.post("/_local/shutdown", headers=headers)).status_code == 200
        assert runner.should_exit


def test_config_resolution_ignores_current_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_AI_CONFIG", raising=False)
    before = resolve_config()
    monkeypatch.chdir(tmp_path)
    assert resolve_config() == before
    explicit = tmp_path / "папка с пробелами" / "config.json"
    monkeypatch.setenv("GITHUB_AI_CONFIG", str(explicit))
    assert resolve_config() == explicit


def test_lock_released_after_crashed_owner(tmp_path):
    from github_ai_mcp.core.locking import lock
    script = ("import sys,time; from pathlib import Path; from github_ai_mcp.core.locking import lock; "
              "context=lock(Path(sys.argv[1]),'fixture'); context.__enter__(); print('ready',flush=True); time.sleep(30)")
    child = subprocess.Popen([sys.executable, "-c", script, str(tmp_path)], stdout=subprocess.PIPE)
    try:
        assert child.stdout.readline().strip() == b"ready"
        with pytest.raises(AppError) as error:
            with lock(tmp_path, "fixture"):
                pass
        assert error.value.code == "BUSY"
        import psutil
        descendants = psutil.Process(child.pid).children(recursive=True)
        for descendant in reversed(descendants):
            try:
                descendant.kill()
            except psutil.NoSuchProcess:
                pass
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        _, still_running = psutil.wait_procs(descendants, timeout=5)
        assert not still_running, "A descendant still owns the test lock"
        with lock(tmp_path, "fixture"):
            pass
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        child.stdout.close()


def test_tunnel_process_not_mislabeled_connected_and_stops_tree(controller, tmp_path, monkeypatch):
    dummy = tmp_path / "official-client-fixture.exe"
    dummy.touch()
    config = controller.config.model_copy(update={"tunnel_client": str(dummy)})
    save_config(controller.path, config)
    monkeypatch.setattr("github_ai_mcp.desktop.supervisor.preflight", lambda c, p:
                        ([str(dummy), "run"], {"CONTROL_PLANE_API_KEY": "test-only-key"}, {}))
    original = subprocess.Popen
    def spawn(args, **kwargs):
        if args[0] == str(dummy):
            args = [sys.executable, "-c", "import time; time.sleep(30)"]
        return original(args, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    state = controller.start("tunnel")
    assert state["tunnel"]["process_alive"]
    assert state["tunnel"]["connection"] == "Unverified"
    process = controller.children["tunnel"][0]
    assert controller.stop("tunnel")["tunnel"]["state"] == "Stopped"
    assert process.poll() is not None


def test_health_never_discloses_shutdown_nonce():
    import hashlib
    import asyncio
    async def check():
        async def fallback(scope, receive, send):
            pass
        routes = ControlRoutes(fallback, "private-controller", SimpleNamespace(should_exit=False))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=routes), base_url="http://fixture") as client:
            data = (await client.get("/_local/health")).json()
            assert data["instance"] == hashlib.sha256(b"private-controller").hexdigest()
            assert "private-controller" not in str(data)
    asyncio.run(check())


def test_failed_process_containment_reaps_spawned_child(controller, monkeypatch):
    spawned = []
    original = subprocess.Popen
    def spawn(*args, **kwargs):
        process = original(*args, **kwargs)
        spawned.append(process)
        return process
    def failure(*args, **kwargs):
        raise OSError('job assignment fixture failure')
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    monkeypatch.setattr('github_ai_mcp.desktop.supervisor.ProcessTree', failure)
    with pytest.raises(AppError):
        controller.start('mcp')
    assert len(spawned) == 1
    assert spawned[0].poll() is not None
    assert spawned[0].stdout.closed
    assert not controller.children
    assert controller.status()['mcp']['error_code'] == 'START_FAILED'


def test_saved_tunnel_selection_reloaded_without_restart(controller, tmp_path):
    new_client = tmp_path / 'selected-client.exe'
    config = controller.config.model_copy(update={'tunnel_client': str(new_client), 'tunnel_profile': 'new-profile'})
    save_config(controller.path, config)
    result = controller.reload_config()
    assert controller.config.tunnel_client == str(new_client)
    assert result['tunnel']['profile'] == 'new-profile'
