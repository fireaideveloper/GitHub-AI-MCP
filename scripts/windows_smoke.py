"""Real packaged Windows acceptance. Never substitutes Python for the EXE.

Run only on a disposable Windows account with no existing MCP vault credential.
No GitHub requests, repositories, PATs, provider session, or release publication.
"""
import argparse
import hashlib
import json
import os
import platform
import queue
import secrets
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from github_ai_mcp.config import Config, save_config
from github_ai_mcp.desktop import supervisor as supervisor_module
from github_ai_mcp.desktop.supervisor import Supervisor, port_open
from github_ai_mcp.exceptions import AppError
from github_ai_mcp.security.auth_github import SERVICE, store_secret, vault


def stdio_exchange(command, config, cwd):
    """Raw wire assertions: all stdout lines must be JSON-RPC protocol messages."""
    process = subprocess.Popen([*command, '--config', str(config), 'serve'], cwd=cwd,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    lines = queue.Queue()
    errors = []
    def read_output():
        for line in process.stdout:
            lines.put(line)
        lines.put(None)
    def read_errors():
        for line in process.stderr:
            errors.append(line)
    threading.Thread(target=read_output, daemon=True).start()
    error_thread = threading.Thread(target=read_errors, daemon=True)
    error_thread.start()
    wire = []
    def send(message):
        process.stdin.write(json.dumps(message).encode() + b'\n')
        process.stdin.flush()
    def response(identifier):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            line = lines.get(timeout=max(0.01, deadline-time.monotonic()))
            if line is None:
                raise AssertionError('Worker closed stdout before response')
            message = json.loads(line)
            assert message.get('jsonrpc') == '2.0', 'Non-protocol stdout'
            wire.append(message)
            if message.get('id') == identifier:
                assert 'error' not in message, message
                return message['result']
        raise TimeoutError('MCP response deadline')
    try:
        send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-11-25', 'capabilities': {},
            'clientInfo': {'name': 'packaged-acceptance', 'version': '1'}}})
        initialized = response(1)
        assert initialized['protocolVersion']
        send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
        tools = response(2)['tools']
        assert len(tools) == 26
        send({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {
            'name': 'github_mcp.health_check', 'arguments': {}}})
        health = response(3)['structuredContent']
        assert health['ok'] and health['data']['mode'] == 'READ_ONLY'
        process.stdin.close()
        process.wait(timeout=15)
        assert process.returncode == 0
        # Drain any extra output and reject banners, prompts and invalid JSON.
        while True:
            line = lines.get(timeout=5)
            if line is None:
                break
            message = json.loads(line)
            assert message.get('jsonrpc') == '2.0'
            wire.append(message)
        error_thread.join(timeout=3)
        return {'tools': len(tools), 'protocol': initialized['protocolVersion'],
                'stdout_protocol_messages': len(wire), 'exit_code': process.returncode}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream and not stream.closed:
                stream.close()


def wait_health(manager):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        state = manager.status()['mcp']
        if state['healthy']:
            return state
        if manager.children['mcp'][0].poll() is not None:
            raise AssertionError('Packaged HTTP process exited; inspect redacted services log')
        time.sleep(0.1)
    raise TimeoutError('Packaged HTTP health deadline')


def packaged_http(bundle, config):
    manager = Supervisor(config)
    original = supervisor_module.service_command
    # Exercise production Supervisor/JobObject against the exact packaged executable.
    supervisor_module.service_command = lambda path: [str(bundle/'GitHub-AI-MCP.exe'), '--internal-server',
        '--config', str(path), 'serve', '--transport', 'streamable-http']
    try:
        manager.start('mcp')
        first = wait_health(manager)
        with httpx.Client(trust_env=False, timeout=3) as client:
            url = f'http://127.0.0.1:{manager.config.port}'
            assert client.get(url+'/_local/health').status_code == 401
            assert client.post(url+'/_local/shutdown').status_code == 401
            token = vault().get_password(SERVICE, 'mcp-http')
            headers = {'Authorization': 'Bearer '+token}
            identity = client.get(url+'/_local/health', headers=headers).json()
            assert identity['pid'] == first['pid']
            assert identity['instance'] == hashlib.sha256(manager.control.encode()).hexdigest()
            assert client.post(url+'/_local/shutdown', headers=headers).status_code == 403
        manager.restart('mcp')
        second = wait_health(manager)
        assert second['pid'] != first['pid']
        owned = manager.children['mcp'][0]
        owned.kill()
        owned.wait(timeout=5)
        # Poll through the actual production backoff rather than changing policy.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            manager.poll()
            if manager.retries['mcp']:
                break
            time.sleep(0.2)
        recovered = wait_health(manager)
        assert recovered['pid'] != owned.pid and manager.retries['mcp'] == 1
        manager.stop('mcp')
        assert not port_open(manager.config.port)
        time.sleep(2.2)
        manager.poll()
        assert not manager.children and not manager.desired['mcp']
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', manager.config.port))
            listener.listen()
            try:
                manager.start('mcp')
                raise AssertionError('External listener was adopted')
            except AppError:
                assert port_open(manager.config.port) and not manager.children
        logs = manager.logs()
        assert token not in logs and manager.control not in logs
        return {'unauthenticated': 401, 'owned_pid_verified': True, 'restart': True,
                'crash_recovery': True, 'manual_stop_stays_stopped': True,
                'unrelated_listener_untouched': True, 'logs_redacted': True}
    finally:
        manager.stop_all()
        supervisor_module.service_command = original


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = {'os': platform.platform(), 'status': 'FAIL', 'checks': {},
                'manual_not_run': ['Clean Windows without Python', 'Moved EXE, logon autostart, and data retention',
                                   'UAC, tray, keyboard, DPI and themes', 'Vendor tunnel and real GitHub',
                                   'Authenticode when no certificate supplied']}
    if os.name != 'nt':
        evidence.update(status='NOT_RUN', reason='Native Windows required')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        raise SystemExit('NOT RUN: packaged smoke requires native Windows')
    backend = vault()
    if any(backend.get_password(SERVICE, name) is not None for name in ('mcp-http', 'github')):
        evidence.update(status='BLOCKED', reason='Existing production credential protected; use a disposable Windows account')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        raise SystemExit('Refusing to replace existing credential; compilation is unaffected. Use a disposable Windows account, or build with -SkipSmoke (unverified).')
    token = secrets.token_urlsafe(32)
    try:
        store_secret('mcp-http', token)
        with TemporaryDirectory(prefix='GitHub-AI-MCP acceptance ') as temporary:
            root = Path(temporary)/'Проверка с пробелами'
            bundle = root/'Приложение'
            shutil.copytree(args.bundle.resolve(), bundle)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            config = root/'настройки'/'config.json'
            save_config(config, Config(data_dir=root/'данные', port=port, setup_complete=True,
                                      autostart_services=False, background_on_close=False))
            evidence['checks']['stdio'] = stdio_exchange([str(bundle/'GitHub-AI-MCP.exe')], config, root)
            doctor = subprocess.run([str(bundle/'GitHub-AI-MCP.exe'), '--cli', '--config', str(config), 'doctor'],
                                    cwd=root, capture_output=True, timeout=30, check=True)
            assert json.loads(doctor.stdout)['mode'] == 'READ_ONLY'
            evidence['checks']['doctor'] = {'json': True, 'exit_code': doctor.returncode}
            evidence['checks']['http'] = packaged_http(bundle, config)
            env = os.environ.copy()
            env['QT_QPA_PLATFORM'] = 'offscreen'
            gui = subprocess.Popen([str(bundle/'GitHub-AI-MCP.exe'), '--config', str(config)], cwd=root, env=env)
            try:
                time.sleep(3)
                assert gui.poll() is None, 'GUI startup failed'
                evidence['checks']['gui'] = {'alive_after_seconds': 3, 'mode': 'Windows offscreen startup only'}
            finally:
                if gui.poll() is None:
                    gui.terminate()  # Only this isolated acceptance-owned GUI; autostart disabled.
                gui.wait(timeout=10)
            evidence['status'] = 'PASS'
    except Exception as error:
        evidence['failure_type'] = type(error).__name__  # No credential-bearing exception dump.
        raise
    finally:
        if backend.get_password(SERVICE, 'mcp-http') == token:
            backend.delete_password(SERVICE, 'mcp-http')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
