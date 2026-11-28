"""Check package metadata and distribution contents before publishing."""
import json
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

root = Path(__file__).resolve().parents[1]
project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
server = json.loads((root / "server.json").read_text())
package = server["packages"][0]
assert project["version"] == server["version"] == package["version"]
assert project["name"] == package["identifier"]
assert package["transport"]["type"] == "stdio"
assert not server.get("remotes")
wheels = list((root / "dist").glob("*.whl"))
assert len(wheels) == 1
with zipfile.ZipFile(wheels[0]) as wheel:
    names = wheel.namelist()
    assert all(n.startswith("github_ai_mcp/") or ".dist-info/" in n for n in names)
    assert not any(n.lower().endswith((".exe", ".dll", ".key", ".pem", ".env", ".db")) for n in names)
    metadata = BytesParser().parsebytes(wheel.read(next(n for n in names if n.endswith(".dist-info/METADATA"))))
    assert metadata["Version"] == project["version"]
    assert f'mcp-name: {server["name"]}' in metadata.get_payload()
print("Registry metadata and wheel layout checks passed")
