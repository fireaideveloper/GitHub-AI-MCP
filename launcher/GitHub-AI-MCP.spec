# One windowed executable: Qt desktop plus isolated internal MCP workers.
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata
root = Path(SPECPATH).parent
sys.path.insert(0, str(root))
from scripts.release_tools import runtime_inventory
from scripts.build import validate_vendor
vendor = validate_vendor(Path(os.environ['GITHUB_AI_BUILD_VENDOR']))
work = Path(os.environ['GITHUB_AI_BUILD_WORK'])
mcp_data, mcp_bins, mcp_hidden = collect_all('mcp', filter_submodules=lambda n: not (n == 'mcp.cli' or n.startswith('mcp.cli.')))
data = mcp_data + copy_metadata('keyring') + copy_metadata('pydantic')
data += [(str(root/'assets'), 'assets'), (str(root/'LICENSE'), '.'),
         (str(root/'docs/THIRD_PARTY.md'), 'docs'),
         (str(root/'docs/LICENSE_COMPLIANCE.md'), 'docs')]
# Preserve PortableGit's directory layout (DLLs, helpers, shell, certificates, notices).
# Treat vendor files as opaque data; their upstream layout is already self-contained.
# Collecting them as binaries would flatten/expand their DLL dependencies.
data += [(str(p), 'vendor/' + p.relative_to(vendor).parent.as_posix())
         for p in vendor.rglob('*') if p.is_file()]
a = Analysis([str(root/'launcher/release/gui_entry.py')],
    pathex=[str(root/'src')], hookspath=[str(root/'launcher/hooks')],
    binaries=mcp_bins, datas=data,
    hiddenimports=mcp_hidden + collect_submodules('github_ai_mcp') +
        ['keyring.backends.Windows', 'ruamel.yaml', 'psutil', 'psutil._psutil_windows'],
    excludes=['pytest','_pytest','setuptools','pkg_resources','_distutils_hack','pip','uv',
              'PyInstaller','ruff','mypy','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets',
              'PySide6.QtPdf','PySide6.QtPdfWidgets','PySide6.QtCharts','PySide6.QtDataVisualization'],
    noarchive=False)
legal = work/'legal'
runtime_inventory(a.pure + a.binaries, a.binaries, legal)
a.datas += [('legal/' + p.relative_to(legal).as_posix(), str(p), 'DATA')
            for p in legal.rglob('*') if p.is_file()]
exe = EXE(PYZ(a.pure), a.scripts, a.binaries, a.datas, [],
          name='GitHub-AI-MCP', console=False, upx=False, strip=False,
          icon=str(root/'assets/github-ai-mcp.ico'))
