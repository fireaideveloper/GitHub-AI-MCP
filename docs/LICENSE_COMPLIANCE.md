# License and binary distribution review — REVIEW REQUIRED

The root MIT LICENSE is retained verbatim, including `Copyright (c) 2026 GitHub-AI-MCP contributors.` No publisher, signing identity or third-party ownership is invented. The original icon is generated from project-native code/vector assets; it has no downloaded stock artwork. The source ZIP contains no Python/Qt/OpenSSL runtime binaries. Its ICO is an image asset, not an executable.

## Actual inventory mechanism

`launcher/GitHub-AI-MCP.spec` passes its actual Analysis module and binary tables to `scripts/release_tools.py`. Package ownership is resolved against installed wheel file lists, including shared namespaces, rather than treating every lock entry as shipped. Versions are compared with `uv.lock`; a discovered mismatch fails. Ambiguous shared namespace files are reported separately instead of inferring that every overlapping wheel was shipped. Wheel license/notice/copyright files and the interpreter license are copied into `legal`. DLLs receive byte hashes. Build-only pytest, Ruff, mypy, uv, PyInstaller, setuptools and pip fail the inventory if collected. The MCP SDK's optional developer CLI is excluded rather than installing its extra dependencies.

This is an inventory aid, not a completed legal audit. Unknown owners, absent license files, binary-specific copyrights, Python/OpenSSL/vendor-runtime notices and every selected Qt wheel require inspection of the native output. `inventory.json` and the generated notices explicitly say REVIEW_REQUIRED. Names in `uv.lock` alone do not prove redistribution. This delivery cannot inventory Windows DLL bytes because it did not build on Windows.

## Qt / PySide / Shiboken

The application uses dynamic Qt libraries through PySide/Shiboken. MIT on this project's code does not replace their LGPL/GPL/commercial or third-party terms. PyInstaller is onefile, UPX disabled, with dynamic Qt DLLs extracted temporarily. A monolithic distribution does not itself demonstrate LGPL replacement compliance. Supply the rebuildable application and exact corresponding sources/build inputs, or use a suitable commercial license, and verify the chosen compliance route for the actual release.

The recipe imports only needed modules. It excludes WebEngine, PDF, Charts and DataVisualization and rejects unexpected `Qt6*.dll` files. The current allowlist covers Core, Gui, Widgets, Network, DBus and OpenGL support; inclusion still requires checking the licenses for the exact wheel and DLL. An allowlist is not an assertion that all versions of these modules have identical terms. GPL-only modules must not be added under an assumed LGPL permission; use appropriate GPL compliance, a valid commercial license or omit them.

Before binary redistribution, record approval/evidence for each item:

- [ ] Check exact Qt/PySide/Shiboken distributions, module list, original copyrights and third-party components against generated Analysis and the lock.
- [ ] Supply complete applicable LGPL/GPL/project/third-party license texts and prominent attribution. Check Python, OpenSSL and Microsoft runtime DLL terms separately; metadata strings are insufficient.
- [ ] Provide exact corresponding LGPL sources, including modifications/build instructions, or a compliant source offer for the applicable distribution method. Record durable URLs, availability and offer terms. This source ZIP is application source and does not substitute for Qt's corresponding sources.
- [ ] Verify users can replace/relink dynamically linked Qt libraries with compatible modified versions by rebuilding the supplied application using the documented build recipe and modified dependency wheels. Document the procedure and test replacement on the exact native bundle; avoid technical or contractual restrictions on LGPL rights, including permitted reverse engineering for debugging modifications.
- [ ] Resolve any installation-information obligation applicable to the selected license/distribution, including signing or device restrictions. Authenticode is optional and no DRM or integrity lock prevents ordinary library replacement here.
- [ ] Inspect wheel license text completeness and every binary's copyright/license. Resolve unknown ownership and missing files; no automatic “compliant” status exists.
- [ ] Record reviewer, actual artifact hashes, sources/offer, date, unresolved issues and decision. No counsel sign-off is supplied here.

Offline access: GUI **About / Legal** opens MIT, this checklist, dependency information and generated license files. The texts are embedded read-only resources. Generated notices and exact package versions are legal/technical information, not visible product-version branding.

Official primary references for the reviewer:

- https://doc.qt.io/qt-6/licensing.html
- https://doc.qt.io/qtforpython-6/licenses.html
- https://www.qt.io/development/open-source-lgpl-obligations
- https://www.gnu.org/licenses/lgpl-3.0.html
- https://www.gnu.org/licenses/lgpl-2.1.html
- https://www.python.org/psf/license/
- https://www.openssl.org/source/license.html

Git for Windows, gh and the official tunnel client are now explicit vendor build inputs embedded in the EXE. They are not included in this source delivery. Retain their original notices and satisfy their applicable redistribution/source obligations; provider login/profile authorization remains required.

Linux diagnostic freeze found that the installed PySide6_Essentials/Shiboken wheels expose no license text files in their RECORD. This is explicitly unresolved; the pipeline does not manufacture texts or claim complete Qt notices. A native reviewer must obtain verified applicable upstream texts/copyrights and corresponding sources for the exact wheels before distribution. The filtered Linux diagnostic output contains no PDF or VirtualKeyboard libraries/plugins; that does not prove the Windows DLL set.
