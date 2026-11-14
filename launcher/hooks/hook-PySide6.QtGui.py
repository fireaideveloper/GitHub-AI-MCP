"""Keep the platform and raster plugins used by this QWidget application.

Filtering happens in the hook, before plugin dependency closure; excluding Python
QtPdf alone would still collect the qpdf image plugin and its QtPdf library.
"""
from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
plugins = {'qwindows.dll', 'qoffscreen.dll', 'qminimal.dll', 'qico.dll', 'qjpeg.dll',
           'libqoffscreen.so', 'libqminimal.so', 'libqico.so', 'libqjpeg.so'}
binaries = [(source, target) for source, target in binaries if Path(source).name in plugins]
