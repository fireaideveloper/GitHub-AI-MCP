"""Release regressions without pretending to execute a native Windows build."""
import hashlib
import importlib.util
import json
import struct
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from github_ai_mcp.config import Config, resolve_config, save_config
from github_ai_mcp.desktop import prerequisites, runtime
from github_ai_mcp.exceptions import AppError

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_service_arguments_preserve_unicode(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    config = tmp_path/'папка с пробелами'/'config.json'
    assert runtime.service_command(config) == [sys.executable, '-m', 'github_ai_mcp',
        '--config', str(config.resolve()), 'serve', '--transport', 'streamable-http']


def test_frozen_service_uses_same_exe_and_bundle_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path/'GitHub-AI-MCP.exe'))
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path/'extracted'), raising=False)
    args = runtime.service_command(tmp_path/'настройки.json')
    assert args[:2] == [sys.executable, '--internal-server']
    assert args[-1] == 'streamable-http'
    assert runtime.asset_path('github-ai-mcp.ico') == tmp_path/'extracted/assets/github-ai-mcp.ico'


def test_config_precedence_user_then_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path/'GitHub-AI-MCP.exe'))
    monkeypatch.delenv('GITHUB_AI_CONFIG', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'user'))
    save_config(tmp_path/'config/config.json', Config())
    assert resolve_config() == tmp_path/'user/GitHub-AI-MCP/config.json'
    monkeypatch.setenv('GITHUB_AI_CONFIG', str(tmp_path/'environment.json'))
    assert resolve_config() == tmp_path/'environment.json'
    assert resolve_config(tmp_path/'explicit.json') == tmp_path/'explicit.json'


def test_prerequisites_missing_vault_unavailable(monkeypatch):
    monkeypatch.setattr(prerequisites.shutil, 'which', lambda _: None)
    def unavailable():
        raise AppError('AUTH_REQUIRED', 'unavailable')
    monkeypatch.setattr(prerequisites, 'vault', unavailable)
    result = prerequisites.check_prerequisites()
    assert result['git']['status'] == result['gh']['status'] == 'Missing'
    assert result['vault']['status'] == 'Unavailable'


def test_prerequisites_installed_and_unusable(monkeypatch):
    monkeypatch.setattr(prerequisites.shutil, 'which', lambda tool: tool)
    monkeypatch.setattr(prerequisites, 'run_background',
                        lambda args, **kw: SimpleNamespace(returncode=0 if args[0]=='git' else 1))
    monkeypatch.setattr(prerequisites, 'vault', lambda: object())
    result = prerequisites.check_prerequisites()
    assert result['git']['status'] == 'Installed'
    assert result['gh']['status'] == 'Unusable'
    assert result['vault']['status'] == 'Available'


def test_hashes_actual_bytes_and_missing_never_written(tmp_path):
    release = script('release_tools')
    artifact = tmp_path/'GitHub-AI-MCP-Complete.zip'
    artifact.write_bytes(b'actual test bytes')
    release.hash_artifacts(tmp_path, [artifact.name])
    assert (tmp_path/'SHA256SUMS.txt').read_text() == hashlib.sha256(artifact.read_bytes()).hexdigest()+'  '+artifact.name+'\n'
    with pytest.raises(ValueError, match='Missing actual'):
        release.hash_artifacts(tmp_path, ['GitHub-AI-MCP-Setup.exe'])
    with pytest.raises(ValueError):
        release.hash_artifacts(tmp_path, ['../fake.exe'])


@pytest.fixture
def bundle(tmp_path):
    (tmp_path/'GitHub-AI-MCP.exe').write_bytes(b'MZfixture')
    return tmp_path


def test_bundle_requires_exactly_one_exe(bundle):
    assert script('release_tools').validate_bundle(bundle)
    (bundle/'GitHub-AI-MCP-Server.exe').write_bytes(b'MZfixture')
    with pytest.raises(ValueError, match='exactly'):
        script('release_tools').validate_bundle(bundle)


@pytest.mark.parametrize('name', ['.env', 'config.json', 'release.zip', '_internal', 'SHA256SUMS.txt'])
def test_bundle_rejects_extra_output(bundle, name):
    (bundle/name).touch()
    with pytest.raises(ValueError):
        script('release_tools').validate_bundle(bundle)


def test_inventory_actual_ownership_and_license_text(tmp_path, monkeypatch):
    release = script('release_tools')
    wheel = tmp_path/'wheel'
    (wheel/'licenses').mkdir(parents=True)
    (wheel/'module.py').write_text('')
    (wheel/'licenses'/'LICENSE.txt').write_text('test license')
    dist = SimpleNamespace(files=[Path('module.py'), Path('licenses/LICENSE.txt')], version='test',
        metadata={'License-Expression':'MIT'}, locate_file=lambda path: wheel/path)
    monkeypatch.setattr(release.metadata, 'packages_distributions', lambda: {'fixture':['fixture-dist', 'other-dist']})
    other = SimpleNamespace(files=[], locate_file=lambda path: wheel/'other'/path)
    monkeypatch.setattr(release.metadata, 'distribution', lambda name: dist if name=='fixture-dist' else other)
    dest = tmp_path/'legal'
    report = release.runtime_inventory([('fixture', str(wheel/'module.py'), 'PYMODULE')], [], dest)
    assert [p['name'] for p in report['packages']] == ['fixture-dist']
    assert (dest/report['packages'][0]['license_files'][0]).read_text() == 'test license'
    assert report['legal_status'] == 'REVIEW_REQUIRED'
    assert json.loads((dest/'inventory.json').read_text())['packages'][0]['lock_match'] is None


def test_inventory_refuses_build_only_dependency(tmp_path, monkeypatch):
    release = script('release_tools')
    monkeypatch.setattr(release.metadata, 'packages_distributions', lambda: {'pytest':['pytest']})
    with pytest.raises(ValueError, match='Build-only'):
        release.runtime_inventory(['pytest'], [], tmp_path/'legal')


def test_source_archive_complete_excludes_state_and_is_deterministic(tmp_path):
    root = tmp_path/'source'
    root.mkdir()
    for name in ['README_RU.md', '.env.example', 'LICENSE', '.env', 'config.json', 'jobs.sqlite3',
                 'launcher/start.ps1', '.github/workflows/test.yml', '.venv/private.py', 'build/temp.txt']:
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('test')
    archive = script('source_archive')
    a, b = tmp_path/'a.zip', tmp_path/'b.zip'
    archive.write_archive(root, a)
    archive.write_archive(root, b)
    assert a.read_bytes() == b.read_bytes()
    with zipfile.ZipFile(a) as file:
        assert set(file.namelist()) == {'GitHub-AI-MCP/'+name for name in
            ['README_RU.md', '.env.example', 'LICENSE', 'launcher/start.ps1', '.github/workflows/test.yml']}


def test_original_icon_native_sizes_and_png():
    ico = (ROOT/'assets/github-ai-mcp.ico').read_bytes()
    assert struct.unpack('<HHH', ico[:6]) == (0, 1, 6)
    png = (ROOT/'assets/github-ai-mcp.png').read_bytes()
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    assert struct.unpack('>II', png[16:24]) == (256, 256)


async def test_raw_stdio_driver_source_wire(factory, tmp_path):
    service, _, _ = factory(mode='READ_ONLY')
    config = tmp_path/'настройки с пробелами'/'config.json'
    save_config(config, service.config)
    result = script('windows_smoke').stdio_exchange([sys.executable, '-m', 'github_ai_mcp'], config, tmp_path)
    assert result['tools'] == 26 and result['exit_code'] == 0
    assert result['stdout_protocol_messages'] >= 3


def test_inventory_rejects_unreviewed_qt_binary(tmp_path):
    dll = tmp_path/'Qt6Charts.dll'
    dll.write_bytes(b'test binary fixture')
    with pytest.raises(ValueError, match='Unreviewed Qt module'):
        script('release_tools').runtime_inventory([], [('Qt6Charts.dll', str(dll), 'BINARY')], tmp_path/'legal')


def test_bundle_rejects_private_pem(bundle):
    (bundle/'certificate.pem').write_text('-----BEGIN PRIVATE KEY-----')
    with pytest.raises(ValueError):
        script('release_tools').validate_bundle(bundle)


def test_offline_legal_discovery_includes_all_license_extensions(tmp_path, monkeypatch):
    from github_ai_mcp.desktop import legal
    (tmp_path/'LICENSE').write_text('MIT')
    (tmp_path/'legal').mkdir()
    (tmp_path/'legal'/'COPYING').write_text('test license')
    monkeypatch.setattr(legal, 'program_root', lambda: tmp_path)
    assert {p.name for p in legal.legal_files()} == {'LICENSE', 'COPYING'}


def test_readonly_health_remains_available_without_git(factory, monkeypatch):
    service, _, _ = factory(mode='READ_ONLY')
    def missing(*args):
        raise AppError('GIT_UNAVAILABLE', 'missing')
    monkeypatch.setattr(service.git, 'text', missing)
    assert service.health_check()['git'] == 'Unavailable'
    assert service.health_check()['mode'] == 'READ_ONLY'


def test_icon_generator_reproduces_assets(tmp_path):
    script('make_icon').generate(tmp_path)
    for name in ['github-ai-mcp.ico', 'github-ai-mcp.png']:
        assert (tmp_path/name).read_bytes() == (ROOT/'assets'/name).read_bytes()


def test_qt_gui_hook_keeps_platform_and_excludes_gpl_plugins():
    # Execute our hook with fixture TOC: dependency expansion must not see qpdf or virtual keyboard.
    import types
    from unittest.mock import patch
    fake = types.ModuleType('PyInstaller.utils.hooks.qt')
    fake.add_qt6_dependencies = lambda _: ([], [
        ('C:/Qt/plugins/platforms/qwindows.dll', 'platforms'),
        ('C:/Qt/plugins/imageformats/qico.dll', 'imageformats'),
        ('C:/Qt/plugins/imageformats/qpdf.dll', 'imageformats'),
        ('C:/Qt/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll', 'input')], [])
    namespace = {'__file__': str(ROOT/'launcher/hooks/hook-PySide6.QtGui.py')}
    with patch.dict(sys.modules, {'PyInstaller.utils.hooks.qt': fake}):
        exec(compile(Path(namespace['__file__']).read_text(), namespace['__file__'], 'exec'), namespace)
    assert [Path(p).name for p, _ in namespace['binaries']] == ['qwindows.dll', 'qico.dll']


def test_setup_shows_absolute_frozen_stdio_command(tmp_path, monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    from github_ai_mcp.desktop.setup import Setup
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path/'Приложение с пробелами'/'GitHub-AI-MCP.exe'))
    monkeypatch.setattr(Setup, 'check_components', lambda self: None)
    path = tmp_path/'Настройки с пробелами'/'config.json'
    dialog = Setup(Config(), path, QThreadPool.globalInstance())
    assert not dialog.stdio.isReadOnly()
    assert 'GitHub-AI-MCP.exe' in dialog.stdio.text()
    assert '--internal-server' in dialog.stdio.text()
    assert str(path.resolve()) in dialog.stdio.text()
    assert dialog.stdio.text().endswith('serve --transport stdio')
    dialog.reject()
    app.processEvents()
