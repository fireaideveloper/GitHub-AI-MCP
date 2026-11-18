import os
import sys

from mcp import Client, StdioServerParameters

from github_ai_mcp.config import save_config
from github_ai_mcp.server import build_server


async def test_stdio_wire_protocol(factory, tmp_path):
    service, _, _ = factory(mode="READ_ONLY")
    path = tmp_path / "config.json"
    save_config(path, service.config)
    parameters = StdioServerParameters(command=sys.executable,
                                       args=["-m", "github_ai_mcp", "--config", str(path), "serve"])
    async with Client(parameters) as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 26
        result = await client.call_tool("github_mcp.health_check", {})
        assert result.structured_content["ok"]
        assert result.structured_content["data"]["mode"] == "READ_ONLY"
        read = await client.call_tool("github_mcp.read_file", {"repository": "test/repo", "path": "README.md"})
        assert read.structured_content["data"]["content"] == "original\n"


async def test_inmemory_full_mcp_workflow(factory):
    svc, _, _ = factory()
    async with Client(build_server(svc)) as client:
        async def call(name, args):
            result = await client.call_tool("github_mcp." + name, args)
            assert result.structured_content["ok"], result
            return result.structured_content["data"]
        job = await call("create_job", {"repository": "test/repo", "idempotency_key": "wire-e2e"})
        paths = [f"p{i}.txt" for i in range(5)]
        await call("plan_changes", {"job_id": job["id"], "messages": {p: "feat: add " + p for p in paths}})
        for p in paths:
            await call("write_file", {"job_id": job["id"], "path": p, "content": "new\n"})
        await call("preview_job", {"job_id": job["id"]})
        report = await call("create_file_commits", {"job_id": job["id"]})
        assert report["created_commits"] == 5
        published = await call("publish_branch", {"job_id": job["id"]})
        assert published["pushed_commits"] == 5


def test_gui_actual_render(factory, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from github_ai_mcp.gui.app import Window
    app = QApplication.instance() or QApplication([])
    service, _, _ = factory(mode="READ_ONLY")
    path = tmp_path / "config.json"
    save_config(path, service.config)
    window = Window(service, path)
    window.show()
    app.processEvents()
    assert window.nav.count() == 8
    assert "start_mcp" not in window.action_buttons
    assert window.action_buttons["recover"].objectName() == "recover"
    window.language_selector.setCurrentText("en")
    assert window.nav.item(0).text() == "Dashboard"
    window.grab().save(str(tmp_path / "gui.png"))
    import time
    deadline = time.monotonic() + 10
    while (window.tasks or window.poll_busy) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    window.timer.stop()
    window.exiting = True
    window.close()
    app.processEvents()
