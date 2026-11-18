"""Isolated registry/vault/vendor mocks; no real credentials or OS writes."""
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from github_ai_mcp.config import Config, save_config
from github_ai_mcp.desktop import startup, tunnel
from github_ai_mcp.desktop.supervisor import Supervisor
from github_ai_mcp.exceptions import AppError


class Registry:
    HKEY_CURRENT_USER = 1
    REG_SZ = 1
    KEY_SET_VALUE = 2
    def __init__(self):
        self.values = {"Unrelated": "keep"}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def OpenKey(self, *args):
        return self
    CreateKeyEx = OpenKey
    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError()
        return self.values[name], self.REG_SZ
    def SetValueEx(self, key, name, unused, kind, value):
        self.values[name] = value
    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError()
        del self.values[name]


def test_startup_idempotent_repair_disable_spaces(tmp_path, monkeypatch):
    path = tmp_path / "папка с пробелами" / "config.json"
    save_config(path, Config())
    executable = path.parent / "GitHub-AI-MCP.exe"
    executable.touch()
    monkeypatch.setenv("APPDATA", str(tmp_path))
    reg = Registry()
    monkeypatch.setattr(startup, "registry", lambda: reg)
    monkeypatch.setattr(startup.sys, "frozen", True, raising=False)
    monkeypatch.setattr(startup.sys, "executable", str(executable))
    assert not startup.status(path)["registered"]
    assert startup.enable(path)["valid"]
    first = reg.values[startup.VALUE]
    assert '--logon' in first and '"' in first
    assert startup.enable(path)["valid"]
    assert reg.values[startup.VALUE] == first
    reg.values[startup.VALUE] = "stale"
    assert not startup.status(path)["valid"]
    assert startup.enable(path)["valid"]
    startup.disable()
    startup.disable()
    assert reg.values == {"Unrelated": "keep"}


@pytest.fixture
def profile(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    client = tmp_path / "client.exe"
    client.touch()
    yaml = tmp_path / "profile.yaml"
    config = Config(data_dir=tmp_path / "state", tunnel_client=str(client), tunnel_profile_file=str(yaml))
    save_config(path, config)
    yaml.write_text('''# preserve comment
config_version: 1
control_plane:
  tunnel_id: tunnel_fixture
  api_key: "env:CONTROL_PLANE_API_KEY"
health:
  listen_addr: 127.0.0.1:8080
admin_ui:
  open_browser: false
mcp:
  commands:
    - channel: main
      command: stale
''')
    monkeypatch.setattr(tunnel, "get_secret", lambda name: "private-fixture-key")
    monkeypatch.setattr(tunnel.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    return config, path, yaml


def test_repair_preserves_settings_backup_and_exact_command(profile):
    config, path, yaml = profile
    before = yaml.read_bytes()
    backup = tunnel.repair_profile(config, path)
    assert Path(backup).read_bytes() == before
    assert "# preserve comment" in yaml.read_text()
    data = tunnel.read_profile(yaml)
    assert data["admin_ui"]["open_browser"] is False
    args, env, _ = tunnel.preflight(config, path)
    assert args[1:] == ["run", "--profile-file", str(yaml)]
    assert env["CONTROL_PLANE_API_KEY"] == "private-fixture-key"
    assert "private-fixture-key" not in yaml.read_text()
    assert data["mcp"]["commands"][0]["command"] == tunnel.command_text(path)
    assert "stdio" in data["mcp"]["commands"][0]["command"]


def test_offline_repair_does_not_depend_on_doctor_but_launch_still_does(profile, monkeypatch):
    config, path, yaml = profile
    before = yaml.read_bytes()
    monkeypatch.setattr(tunnel.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=2))
    backup = tunnel.repair_profile(config, path)
    assert Path(backup).read_bytes() == before
    assert tunnel.local_profile(config, path)["mcp"]["commands"][0]["command"] == tunnel.command_text(path)
    with pytest.raises(AppError, match="doctor"):
        tunnel.preflight(config, path)


def test_repair_without_client_or_vault(profile, monkeypatch):
    config, path, yaml = profile
    Path(config.tunnel_client).unlink()
    def unavailable(*args, **kwargs):
        raise AssertionError("Offline repair must not inspect vault or run a client")
    monkeypatch.setattr(tunnel, "get_secret", unavailable)
    monkeypatch.setattr(tunnel.subprocess, "run", unavailable)
    tunnel.repair_profile(config, path)
    assert tunnel.local_profile(config, path)


@pytest.mark.parametrize("value", ["null", "[]", "{commands: null}", "{commands: wrong}"])
def test_malformed_command_structure_has_safe_actionable_error(profile, value):
    config, path, yaml = profile
    yaml.write_text('control_plane:\n  api_key: env:CONTROL_PLANE_API_KEY\nmcp: ' + value + '\n')
    with pytest.raises(AppError) as error:
        tunnel.repair_profile(config, path)
    assert error.value.code == "MCP_COMMAND"


def test_explicit_stdio_override_survives_config_and_profile_roundtrip(profile):
    from github_ai_mcp.config import load_config
    config, path, yaml = profile
    config.tunnel_stdio_command = '"C:/Custom MCP/server.exe" --transport stdio'
    save_config(path, config)
    config = load_config(path)
    tunnel.repair_profile(config, path)
    assert tunnel.preflight(config, path)[2]["mcp"]["commands"][0]["command"] == config.tunnel_stdio_command


def test_diagnosis_uses_entered_key_without_persisting_it(profile, monkeypatch):
    config, path, yaml = profile
    tunnel.repair_profile(config, path)
    def unavailable(name):
        raise AppError("AUTH_REQUIRED", "missing")
    monkeypatch.setattr(tunnel, "get_secret", unavailable)
    args, env, data = tunnel.preflight(config, path, runtime_key="new-unsaved-fixture")
    assert env["CONTROL_PLANE_API_KEY"] == "new-unsaved-fixture"
    assert "new-unsaved-fixture" not in yaml.read_text() + path.read_text()


def test_start_failure_retains_machine_readable_cause(profile, monkeypatch):
    config, path, yaml = profile
    manager = Supervisor(path)
    monkeypatch.setattr('github_ai_mcp.desktop.supervisor.external_processes', lambda c: ([], False))
    with pytest.raises(AppError):
        manager.start("tunnel")
    assert manager.status()["tunnel"]["error_code"] == "MCP_COMMAND"
    assert manager.status()["tunnel"]["pid"] is None


def test_invalid_yaml_does_not_expose_secret(profile):
    config, path, yaml = profile
    yaml.write_text('control_plane: [secret-fixture\n')
    with pytest.raises(AppError) as error:
        tunnel.read_profile(yaml)
    assert 'secret-fixture' not in str(error.value)


def test_stale_command_fails_before_spawn(profile):
    config, path, yaml = profile
    with pytest.raises(AppError, match="Repair"):
        tunnel.preflight(config, path)


def test_missing_key_rejects_shell_import(profile, monkeypatch):
    monkeypatch.setenv("CONTROL_PLANE_API_KEY", "shell-fixture")
    def missing(name):
        raise AppError("AUTH_REQUIRED", "missing")
    monkeypatch.setattr(tunnel, "get_secret", missing)
    with pytest.raises(AppError, match="Save"):
        tunnel.child_environment()
    assert os.environ["CONTROL_PLANE_API_KEY"] == "shell-fixture"


def test_environment_scoped_and_conflicting_overrides_removed(profile, monkeypatch):
    monkeypatch.setenv("CONTROL_PLANE_API_KEY", "shell-fixture")
    monkeypatch.setenv("MCP_COMMAND", "stale")
    monkeypatch.setenv("TUNNEL_CLIENT_PROFILE", "other")
    env = tunnel.child_environment()
    assert env["CONTROL_PLANE_API_KEY"] == "private-fixture-key"
    assert "MCP_COMMAND" not in env and "TUNNEL_CLIENT_PROFILE" not in env
    assert os.environ["CONTROL_PLANE_API_KEY"] == "shell-fixture"


def test_editor_masks_short_literals_and_preserves_refs():
    text = 'control_plane:\n  api_key: "env:CONTROL_PLANE_API_KEY"\npassword: abc\ntoken: private-fixture-key\n'
    safe = tunnel.safe_editor_text(text)
    assert 'api_key: "env:CONTROL_PLANE_API_KEY"' in safe
    assert 'abc' not in safe and 'private-fixture-key' not in safe


def test_literal_key_rejected(profile):
    config, path, yaml = profile
    yaml.write_text(yaml.read_text().replace('env:CONTROL_PLANE_API_KEY', 'literal-fixture-key'))
    with pytest.raises(AppError, match="no plaintext"):
        tunnel.read_profile(yaml)


def test_external_process_never_adopted_or_terminated(profile, monkeypatch):
    config, path, yaml = profile
    manager = Supervisor(path)
    monkeypatch.setattr('github_ai_mcp.desktop.supervisor.external_processes', lambda c: ([1234], False))
    monkeypatch.setattr('github_ai_mcp.desktop.supervisor.health_observation', lambda *a: {"health": "Unverified"})
    state = manager.status()["tunnel"]
    assert state["state"] == "External process detected, ownership unverified"
    assert not state["owned"] and state["remote_availability"] == "Unverified"
    with pytest.raises(AppError, match="External"):
        manager.start("tunnel")
    manager.stop("tunnel")
    assert not manager.children


def test_transient_initial_failure_retried_and_permanent_blocked(profile, monkeypatch):
    config, path, yaml = profile
    manager = Supervisor(path)
    monkeypatch.setattr('github_ai_mcp.desktop.supervisor.external_processes', lambda c: ([], False))
    def failure(*args):
        raise AppError('DOCTOR_TIMEOUT', 'network timeout')
    monkeypatch.setattr('github_ai_mcp.desktop.supervisor.preflight', failure)
    with pytest.raises(AppError):
        manager.start('tunnel')
    assert manager.desired['tunnel']
    manager.retry_at['tunnel'] = 1
    manager.poll()
    assert manager.retries['tunnel'] == 1
    def permanent(*args):
        raise AppError('DOCTOR_FAILED', 'bad credentials')
    monkeypatch.setattr('github_ai_mcp.desktop.supervisor.preflight', permanent)
    manager.retry_at['tunnel'] = 1
    manager.poll()
    assert manager.permanent['tunnel']
    retries = manager.retries['tunnel']
    manager.retry_at['tunnel'] = 1
    manager.poll()
    assert manager.retries['tunnel'] == retries


def test_packaged_stdio_uses_internal_worker(profile, monkeypatch):
    from github_ai_mcp.desktop import runtime
    config, path, yaml = profile
    executable = path.parent / 'GitHub-AI-MCP.exe'
    monkeypatch.setattr(runtime.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(runtime.sys, 'executable', str(executable))
    args = runtime.service_command(path, 'stdio')
    assert args[:2] == [str(executable), '--internal-server']
    assert '.venv' not in ' '.join(args)
    assert args[-1] == 'stdio'


def test_health_readiness_alone_never_verifies_connection(profile, monkeypatch):
    import httpx
    import psutil
    config, path, yaml = profile
    monkeypatch.setattr(psutil, 'Process', lambda pid: SimpleNamespace(net_connections=lambda kind:
        [SimpleNamespace(status=psutil.CONN_LISTEN, laddr=SimpleNamespace(port=8080))]))
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            return httpx.Response(200, request=httpx.Request('GET', url),
                                  json={'schema_version': 1, 'ready': True, 'components': {}})
    monkeypatch.setattr(httpx, 'Client', Client)
    observation = tunnel.health_observation(config, 123)
    assert observation['ready']
    assert observation['mcp'] == observation['control-plane'] == 'Unverified'


def test_health_listener_ownership_required(profile, monkeypatch):
    import psutil
    config, path, yaml = profile
    monkeypatch.setattr(psutil, 'Process', lambda pid: SimpleNamespace(net_connections=lambda kind: []))
    assert tunnel.health_observation(config, 123) == {'health': 'Unverified'}


def test_vault_key_survives_new_lookup_and_removes_only_tunnel(monkeypatch):
    from github_ai_mcp.security import auth_github
    class Vault:
        def __init__(self):
            self.values = {('GitHub-AI-MCP', 'github'): 'github-fixture'}
        def get_password(self, service, name):
            return self.values.get((service, name))
        def set_password(self, service, name, value):
            self.values[service, name] = value
        def delete_password(self, service, name):
            del self.values[service, name]
    vault = Vault()
    monkeypatch.setattr(auth_github, 'vault', lambda: vault)
    auth_github.store_secret(tunnel.SECRET, 'runtime-fixture')
    assert auth_github.get_secret(tunnel.SECRET) == 'runtime-fixture'
    auth_github.remove_secret(tunnel.SECRET)
    assert auth_github.get_token() == 'github-fixture'
    with pytest.raises(AppError):
        auth_github.get_secret(tunnel.SECRET)


def test_log_masks_control_plane_key(profile):
    config, path, yaml = profile
    manager = Supervisor(path)
    manager.hidden.append('runtime-fixture')
    manager.log('tunnel', 'auth failed runtime-fixture')
    assert 'runtime-fixture' not in manager.logs()


def test_profile_name_traversal_rejected():
    with pytest.raises(AppError, match='Invalid profile'):
        tunnel.profile_path(Config(tunnel_profile='../escape'))


def test_permanent_auth_error_stops_owned_retry_loop(profile, monkeypatch):
    config, path, yaml = profile
    manager = Supervisor(path)
    class Process:
        pid = 123
        returncode = None
        def poll(self):
            return self.returncode
        def terminate(self):
            self.returncode = 1
        def wait(self, timeout):
            return self.returncode
    closed = []
    process = Process()
    manager.children['tunnel'] = (process, SimpleNamespace(close=lambda: closed.append(True)), 0)
    manager.desired['tunnel'] = True
    manager.permanent['tunnel'] = True
    manager.last_output['tunnel'] = 'Authentication rejected'
    monkeypatch.setattr('github_ai_mcp.desktop.supervisor.external_processes', lambda c: ([], False))
    state = manager.poll()['tunnel']
    assert process.returncode == 1 and closed
    assert state['state'] == 'Failed' and state['retries'] == 0


def test_windows_profile_command_uses_parser_safe_forward_slashes(monkeypatch):
    monkeypatch.setattr(tunnel.sys, 'platform', 'win32')
    monkeypatch.setattr(tunnel, 'service_command', lambda path, transport:
        [r'C:\Program Files\GitHub-AI-MCP\GitHub-AI-MCP-Server.exe', '--config', r'C:\Users\User\config.json', 'serve', '--transport', transport])
    text = tunnel.command_text(Path('unused'))
    assert '\\' not in text
    assert '"C:/Program Files/GitHub-AI-MCP/GitHub-AI-MCP-Server.exe"' in text
    assert 'C:/Users/User/config.json' in text
