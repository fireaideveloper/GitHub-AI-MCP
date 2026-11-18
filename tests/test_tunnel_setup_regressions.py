"""Exercise the actual settings handlers without vendor binaries or credentials."""
import time

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from github_ai_mcp.config import Config, load_config, save_config
from github_ai_mcp.desktop import setup, tunnel
from github_ai_mcp.exceptions import AppError


@pytest.fixture
def dialog(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(setup.Setup, 'check_components', lambda self: None)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(setup.startup, 'disable', lambda: None)
    monkeypatch.setattr(setup, 'get_secret', lambda name: 'test-existing-secret')
    monkeypatch.setattr(setup, 'store_secret', lambda *a: None)
    path = tmp_path / 'config.json'
    yaml = tmp_path / 'profile.yaml'
    yaml.write_text('control_plane:\n  api_key: env:CONTROL_PLANE_API_KEY\nmcp:\n  commands:\n    - channel: main\n      command: stale\n')
    config = Config(data_dir=tmp_path / 'state', tunnel_profile_file=str(yaml))
    save_config(path, config)
    ui = setup.Setup(config, path, QThreadPool.globalInstance())
    ui.show()
    yield ui, path, yaml
    QThreadPool.globalInstance().waitForDone(10000)
    app.processEvents()
    ui.reject()


def settle(ui):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if ui.buttons.isEnabled() or ui.result() == QDialog.DialogCode.Accepted:
            return
        time.sleep(0.01)
    pytest.fail('Setup worker timed out')


def test_edit_stdio_save_persists_json_and_yaml(dialog):
    ui, path, yaml = dialog
    assert not ui.stdio.isReadOnly()
    command = '"C:/My MCP/server.exe" --transport stdio'
    ui.stdio.setText(command)
    ui.save()
    settle(ui)
    assert ui.result() == QDialog.DialogCode.Accepted
    config = load_config(path)
    assert config.tunnel_stdio_command == command
    assert tunnel.local_profile(config, path)['mcp']['commands'][0]['command'] == command
    assert len(list(yaml.parent.glob('*.github-ai-backup-*'))) == 1


def test_repair_button_works_without_vault_or_executable(dialog, monkeypatch):
    ui, path, yaml = dialog
    def missing(*args):
        raise AppError('AUTH_REQUIRED', 'missing')
    monkeypatch.setattr(tunnel, 'get_secret', missing)
    ui.repair_tunnel()
    settle(ui)
    assert tunnel.read_profile(yaml)['mcp']['commands'][0]['command'] == tunnel.command_text(path)
    assert 'Command saved' in ui.info.text()
    assert ui.content.isEnabled()


def test_validate_button_uses_unsaved_password(dialog, monkeypatch):
    ui, path, yaml = dialog
    seen = []
    monkeypatch.setattr(setup, 'preflight', lambda c, p, **kw: seen.append(kw['runtime_key']))
    ui.tunnel_key.setText('unsaved-runtime-fixture')
    ui.diagnose_tunnel()
    settle(ui)
    assert seen == ['unsaved-runtime-fixture']
    assert 'unsaved-runtime-fixture' not in path.read_text() + yaml.read_text() + ui.info.text()


def test_failed_save_preserves_entered_key_for_retry(dialog, monkeypatch):
    ui, path, yaml = dialog
    monkeypatch.setattr(setup.shutil, 'which', lambda name: None)
    ui.tunnel_key.setText('unsaved-runtime-fixture')
    ui.save()
    settle(ui)
    assert ui.tunnel_key.text() == 'unsaved-runtime-fixture'
    assert ui.content.isEnabled()
    assert ui.result() != QDialog.DialogCode.Accepted


def test_archive_excludes_old_builds_and_nested_archives(tmp_path):
    from scripts.source_archive import write_archive
    import zipfile
    root = tmp_path / 'source'
    root.mkdir()
    for name in ('main.py', 'old.zip', 'app.exe', 'dist-clean/old.exe', 'dist-clean/info.txt'):
        item = root / name
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text('fixture')
    output = tmp_path / 'source.zip'
    write_archive(root, output)
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ['GitHub-AI-MCP/main.py']
