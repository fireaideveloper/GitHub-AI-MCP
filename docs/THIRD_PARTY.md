# Third-party dependencies

Project code and original icon are covered by the preserved root MIT license; dependencies retain their own terms. The complete source ZIP does not redistribute Python/Qt runtime binaries. A future native build generates `legal/inventory.json`, `THIRD-PARTY-NOTICES.txt`, wheel license texts and binary hashes from actual PyInstaller Analysis, with versions compared to `uv.lock`. It does not falsely label every locked or build-only package as bundled.

See [the unresolved binary compliance checklist](LICENSE_COMPLIANCE.md). Qt/PySide/Shiboken dynamic replacement, exact corresponding sources/source offer, module-specific LGPL/GPL/commercial terms and Python/OpenSSL/Microsoft-runtime notices need review for actual Windows artifacts. Legal status remains REVIEW_REQUIRED, never automatic certification.

Runtime dependency pins are in `pyproject.toml` and `uv.lock`. Separate build pins are in `launcher/build-requirements.txt`. Git, GitHub CLI and the official tunnel client must be supplied as reviewed build inputs, with their original licenses and required corresponding-source obligations. They are embedded into the onefile EXE. No vendor binaries are present in this source archive. No signing certificate or fabricated publisher is provided.

Primary upstreams: https://github.com/modelcontextprotocol/python-sdk · https://doc.qt.io/qtforpython-6/ · https://git-scm.com · https://cli.github.com
