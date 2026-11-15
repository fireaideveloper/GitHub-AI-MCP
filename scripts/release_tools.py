"""Release inventories and hashes from real bytes, not declared artifact names."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
import shutil
import sys
import tomllib
from pathlib import Path

BUILD_ONLY = {"pytest", "pytest-asyncio", "ruff", "mypy", "uv", "pyinstaller", "setuptools", "pip"}
QT_ALLOWED = {"Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll", "Qt6DBus.dll",
              "Qt6OpenGL.dll", "Qt6OpenGLWidgets.dll"}


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024*1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def runtime_inventory(module_names, binary_entries, destination: Path):
    """Called by PyInstaller's spec with its actual Analysis module/binary TOCs."""
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    mapping = metadata.packages_distributions()
    packages = set()
    owner_cache = {}
    ambiguous = []
    for entry in module_names:
        name, source = (entry, None) if isinstance(entry, str) else (entry[0], Path(entry[1]).resolve())
        owners = []
        for candidate in mapping.get(name.replace('/', '.').replace('\\', '.').split('.')[0], []):
            if source is None:
                owners.append(candidate)
                continue
            if candidate not in owner_cache:
                dist = metadata.distribution(candidate)
                owner_cache[candidate] = {Path(dist.locate_file(f)).resolve() for f in dist.files or []}
            if source in owner_cache[candidate]:
                owners.append(candidate)
        if len(owners) == 1:
            packages.add(owners[0])
        elif len(owners) > 1:
            # Shared namespace __init__ files can appear in several wheel RECORDs.
            # They do not prove every wheel's compiled modules were distributed.
            ambiguous.append({'module': name, 'candidate_owners': sorted(owners)})
    records = []
    for name in sorted(packages):
        if name.lower() in BUILD_ONLY:
            raise ValueError("Build-only dependency unexpectedly collected: " + name)
        dist = metadata.distribution(name)
        copied = []
        for entry in dist.files or []:
            if any(part.lower().startswith(("license", "notice", "copying", "copyright")) for part in entry.parts):
                source = Path(dist.locate_file(entry))
                if source.is_file():
                    target = destination / "texts" / name / str(entry)
                    # Wheel metadata must not escape the output directory.
                    if not target.resolve().is_relative_to(destination.resolve()):
                        raise ValueError("Unsafe license path")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    copied.append(target.relative_to(destination).as_posix())
        records.append({"name": name, "version": dist.version,
                        "license_expression": dist.metadata.get("License-Expression"),
                        "license_metadata": dist.metadata.get("License"),
                        "license_files": copied, "review": "REVIEW_REQUIRED"})
    python_license = Path(sys.base_prefix)/"LICENSE.txt"
    if not python_license.is_file():
        python_license = Path(sys.base_prefix)/"LICENSE"
    if python_license.is_file():
        shutil.copyfile(python_license, destination/"Python-LICENSE.txt")
    binaries = []
    for target, source, kind in binary_entries:
        path = Path(source)
        if path.name.startswith("Qt6") and path.suffix.lower() == ".dll" and path.name not in QT_ALLOWED:
            raise ValueError("Unreviewed Qt module collected: " + path.name)
        if path.is_file():
            binaries.append({"target": target, "sha256": digest(path), "kind": kind})
    lock_path = Path(__file__).resolve().parents[1]/'uv.lock'
    locked = {p['name'].lower().replace('_', '-'): p['version'] for p in
              tomllib.loads(lock_path.read_text(encoding='utf-8')).get('package', []) if 'version' in p}
    for record in records:
        expected = locked.get(record['name'].lower().replace('_', '-'))
        record['locked_version'] = expected
        record['lock_match'] = expected == record['version'] if expected else None
        if expected and expected != record['version']:
            raise ValueError('Runtime package differs from uv.lock: '+record['name'])
    report = {"provenance": "PyInstaller Analysis in the current build environment",
              "python": sys.version.split()[0], "packages": records, "binaries": binaries,
              "ambiguous_file_ownership": ambiguous,
              "missing_package_license_texts": [r["name"] for r in records if not r["license_files"]],
              "legal_status": "REVIEW_REQUIRED",
              "remaining": ["Review Qt module licenses and third-party notices for these exact wheels/DLLs",
                            "Provide exact corresponding LGPL sources or a compliant source offer before distribution",
                            "Verify replacement of dynamically linked Qt libraries with compatible modified builds",
                            "Resolve binary copyrights/licenses, including OpenSSL and Microsoft runtime DLLs",
                            "Verify Python license collection and all package license texts"]}
    (destination/"inventory.json").write_text(json.dumps(report, indent=2),encoding="utf-8")
    (destination/"THIRD-PARTY-NOTICES.txt").write_text(
        "GitHub-AI-MCP — third-party notices\nGenerated from actual PyInstaller Analysis.\n"
        "This inventory is not legal certification. See inventory.json and docs/LICENSE_COMPLIANCE.md.\n\n"+
        "\n".join(f"{r['name']} {r['version']} — {r['license_expression'] or r['license_metadata'] or 'License requires review'}\n"
                    +"\n".join(r['license_files']) for r in records), encoding="utf-8")
    return report


def validate_bundle(root: Path):
    from scripts.build import validate_output
    validate_output(root)
    return True


def hash_artifacts(directory: Path, names: list[str]):
    if not names or any(Path(n).name != n for n in names):
        raise ValueError("Artifact names must be nonempty basenames")
    lines = []
    for name in names:
        path = directory/name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("Missing actual artifact: " + name)
        lines.append(digest(path)+'  '+name+'\n')
    (directory/'SHA256SUMS.txt').write_text(''.join(lines), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action',choices=['validate','hash'])
    parser.add_argument('directory',type=Path)
    parser.add_argument('names',nargs='*')
    args = parser.parse_args()
    if args.action=='validate':
        validate_bundle(args.directory)
    else:
        hash_artifacts(args.directory,args.names)
