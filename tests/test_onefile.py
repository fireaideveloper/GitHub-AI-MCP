"""One-file dispatch, resource isolation and fail-closed release inputs."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

from github_ai_mcp.desktop import entry, runtime, streams

ROOT = Path(__file__).resolve().parents[1]


def build_module():
    spec = importlib.util.spec_from_file_location('build_script', ROOT/'scripts/build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_internal_dispatch_does_not_enter_gui(monkeypatch):
    import github_ai_mcp.cli.app
    called = []
    monkeypatch.setattr(sys, 'argv', ['app.exe', '--internal-server', '--config', 'config.json', 'serve', '--transport', 'stdio'])
    monkeypatch.setattr(github_ai_mcp.cli.app, 'main', lambda: called.append(sys.argv[:]))
    entry.main()
    assert called == [['app.exe', '--config', 'config.json', 'serve', '--transport', 'stdio']]


def test_missing_stdio_pipe_fails_without_gui(monkeypatch):
    monkeypatch.setattr(sys, 'stdin', None)
    monkeypatch.setattr(streams, 'inherited_stream', lambda *args: None)
    with pytest.raises(SystemExit, match='pipes'):
        streams.prepare_streams(require_input=True)


def test_bundled_tools_found_after_moving_executable(tmp_path, monkeypatch):
    extracted = tmp_path/'извлечённые файлы'
    (extracted/'vendor/git/cmd').mkdir(parents=True)
    (extracted/'vendor/git/cmd/git.exe').touch()
    (extracted/'vendor/gh.exe').touch()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(extracted), raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path/'moved/app.exe'))
    monkeypatch.setenv('PATH', 'original')
    runtime.initialize_runtime()
    assert runtime.bundled_tool('git') == str(extracted/'vendor/git/cmd/git.exe')
    assert runtime.bundled_tool('gh') == str(extracted/'vendor/gh.exe')
    assert runtime.bundled_tool('tunnel-client') is None


def test_build_refuses_missing_vendor_and_invalid_executable(tmp_path):
    build = build_module()
    with pytest.raises(ValueError, match='Missing build input'):
        build.validate_vendor(tmp_path)
    for name in ['git/cmd/git.exe', 'git/mingw64/bin/git.exe', 'git/usr/bin/sh.exe', 'gh.exe', 'tunnel-client.exe', 'LICENSES.txt']:
        p = tmp_path/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'MZfixture')
    assert build.validate_vendor(tmp_path) == tmp_path
    (tmp_path/'gh.exe').write_bytes(b'not an executable')
    with pytest.raises(ValueError, match='Windows executable'):
        build.validate_vendor(tmp_path)


def test_source_internal_stdio_real_wire(factory, tmp_path):
    from scripts.windows_smoke import stdio_exchange
    from github_ai_mcp.config import save_config
    service, _, _ = factory(mode='READ_ONLY')
    path = tmp_path/'данные с пробелами/config.json'
    save_config(path, service.config)
    result = stdio_exchange([sys.executable, '-m', 'github_ai_mcp.desktop.entry', '--internal-server'], path, ROOT)
    assert result['tools'] == 26 and result['exit_code'] == 0


def test_build_on_linux_creates_no_output(tmp_path):
    if sys.platform == 'win32':
        pytest.skip('Linux-specific platform refusal')
    result = subprocess.run([sys.executable, str(ROOT/'scripts/build.py'), '--dist', str(tmp_path/'dist')], capture_output=True)
    assert result.returncode == 2
    assert not (tmp_path/'dist').exists()


def test_build_stages_one_exe_and_cleans_work(tmp_path, monkeypatch):
    build = build_module()
    work_paths = []
    monkeypatch.setattr(build.sys, 'platform', 'win32')
    monkeypatch.setattr(build, 'validate_vendor', lambda p: tmp_path)
    def freeze(command, **kwargs):
        stage = Path(command[command.index('--distpath') + 1])
        stage.mkdir()
        (stage/'GitHub-AI-MCP.exe').write_bytes(b'MZfixture')
        work_paths.append(Path(kwargs['env']['GITHUB_AI_BUILD_WORK']))
    monkeypatch.setattr(build.subprocess, 'run', freeze)
    monkeypatch.setattr(build.sys, 'argv', ['build.py', '--dist', str(tmp_path/'dist')])
    build.main()
    assert [p.name for p in (tmp_path/'dist').iterdir()] == ['GitHub-AI-MCP.exe']
    assert not work_paths[0].exists()


def test_setup_does_not_save_temporary_vendor_path(tmp_path, monkeypatch):
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    from github_ai_mcp.config import Config
    from github_ai_mcp.desktop import setup
    app = QApplication.instance() or QApplication([])
    bundled = str(tmp_path/'_MEI123/vendor/tunnel-client.exe')
    monkeypatch.setattr(setup, 'bundled_tool', lambda name: bundled)
    monkeypatch.setattr(setup.Setup, 'check_components', lambda self: None)
    dialog = setup.Setup(Config(), tmp_path/'config.json', QThreadPool.globalInstance())
    assert dialog.client.text() == bundled
    assert dialog.selected_config().tunnel_client == ''
    dialog.client.setText(str(tmp_path/'custom-client.exe'))
    assert dialog.selected_config().tunnel_client == str(tmp_path/'custom-client.exe')
    dialog.reject()
    app.processEvents()
