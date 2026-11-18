"""Invoke real GUI handlers and verify their effects in disposable Git repositories."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from conftest import modify
from github_ai_mcp.config import save_config
from github_ai_mcp.gui.app import Window


def settle(window):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if not window.tasks and not window.service_busy and not window.poll_busy:
            QApplication.processEvents()
            return
        time.sleep(0.01)
    pytest.fail("GUI worker failed to finish")


@pytest.fixture
def ui(factory, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    service, _, _ = factory()
    service.config.autostart_services = False
    path = tmp_path / "config.json"
    save_config(path, service.config)
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window = Window(service, path)
    window.show()
    settle(window)
    yield window, errors
    settle(window)
    window.timer.stop()
    window.supervisor.stop_all()
    window.exiting = True
    window.close()
    QApplication.processEvents()


def test_create_cancel_job_and_selection(ui, monkeypatch):
    window, errors = ui
    monkeypatch.setattr(window, "ask", lambda _: "gui-job")
    window.nav.setCurrentRow(2)
    settle(window)
    window.action_buttons["new_job"].click()
    settle(window)
    assert window.job_id
    assert window.jobs.currentData() == window.job_id
    window.action_buttons["cancel_job"].click()
    settle(window)
    assert window.service.get_job_status(window.job_id)["state"] == "CANCELLED"
    assert not errors


def test_delete_preview_approve_commit_resume_publish_controls(ui, monkeypatch):
    window, errors = ui
    job = window.service.create_job("test/repo", "gui-delete")
    window.job_id = job["id"]
    window.reload_jobs()
    monkeypatch.setattr(window, "ask", lambda _: "README.md")
    window.nav.setCurrentRow(3)
    settle(window)
    window.action_buttons["delete_file"].click()
    settle(window)
    assert not (window.service._work(job) / "README.md").exists()
    window.nav.setCurrentRow(3)
    settle(window)
    window.refresh()
    settle(window)
    assert window.preview["job_id"] == job["id"]
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: ("commit,push,pr", True))
    window.action_buttons["approve"].click()
    settle(window)
    window.action_buttons["commit"].click()
    settle(window)
    committed = window.service.get_job_status(job["id"])
    assert committed["state"] == "VERIFIED"
    assert committed["created_commits"] == 1
    assert window.action_buttons["recover"].isHidden()
    window.nav.setCurrentRow(4)
    settle(window)
    window.action_buttons["push"].click()
    settle(window)
    assert window.service.get_job_status(job["id"])["state"] == "PUBLISHED"
    assert not errors


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_all_navigation_theme_settings_and_logs(ui, locale):
    window, errors = ui
    job = window.service.create_job("test/repo", "gui-nav")
    modify(window.service, job, "README.md", "changed\n")
    window.job_id = job["id"]
    window.reload_jobs()
    window.language_selector.setCurrentText(locale)
    for page in range(8):
        window.nav.setCurrentRow(page)
        settle(window)
        assert window.settings_form.isVisible() == (page == 6)
        assert not window.settings.isVisible()
    window.nav.setCurrentRow(6)
    settle(window)
    window.action_buttons["save"].click()
    assert window.config_path.exists()
    before = window.dark
    window.action_buttons["theme"].click()
    assert window.dark != before
    assert "QPushButton:focus" in window.styleSheet()
    assert "1.0" not in window.summary.text()
    window.supervisor.log("gui", "diagnostic fixture")
    window.nav.setCurrentRow(7)
    settle(window)
    assert "diagnostic fixture" in window.output.toPlainText()
    assert not errors


def test_repeated_operation_click_does_not_duplicate_job(ui, monkeypatch):
    window, errors = ui
    monkeypatch.setattr(window, "ask", lambda _: "same-key")
    window.nav.setCurrentRow(2)
    settle(window)
    window.action_buttons["new_job"].click()
    window.nav.setCurrentRow(2)
    settle(window)
    window.action_buttons["new_job"].click()
    settle(window)
    assert len(window.service.db.list_jobs()) == 1
    assert not errors


def test_invalid_settings_are_rejected_without_overwriting(ui):
    window, errors = ui
    before = window.config_path.read_bytes()
    window.advanced.setChecked(True)
    settle(window)
    window.settings.setPlainText('{"unknown": "setting"}')
    window.save()
    assert errors
    assert window.config_path.read_bytes() == before


def test_github_login_validates_before_vault_write_and_logout(ui, monkeypatch):
    window, errors = ui
    calls = []
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("fixture-token", True))
    monkeypatch.setattr("github_ai_mcp.core.github_api.GitHub.request", lambda *args: {"login": "fixture-user"})
    monkeypatch.setattr("github_ai_mcp.security.auth_github.store_token", lambda value: calls.append(value))
    window.nav.setCurrentRow(4)
    settle(window)
    window.action_buttons["login"].click()
    settle(window)
    assert calls == ["fixture-token"]
    assert "GitHub: fixture-user" in window.github_label.text()
    assert "хранилища" in window.github_label.text()
    monkeypatch.setattr("github_ai_mcp.security.auth_github.logout", lambda: calls.append("logout"))
    window.action_buttons["logout"].click()
    settle(window)
    assert calls[-1] == "logout"
    assert "fixture-user" not in window.github_label.text()
    assert not errors


def test_edit_control_changes_real_file(ui, monkeypatch):
    from PySide6.QtWidgets import QDialog, QPlainTextEdit
    window, errors = ui
    job = window.service.create_job("test/repo", "gui-edit")
    window.job_id = job["id"]
    window.reload_jobs()
    answers = iter(["README.md", "fix: update readme"])
    monkeypatch.setattr(window, "ask", lambda _: next(answers))
    def edit(dialog):
        dialog.findChild(QPlainTextEdit).setPlainText("edited through GUI\n")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", edit)
    window.nav.setCurrentRow(3)
    settle(window)
    window.action_buttons["edit_file"].click()
    settle(window)
    assert (window.service._work(job) / "README.md").read_text() == "edited through GUI\n"
    assert not errors


def test_pr_control_publishes_only_after_explicit_click(ui, monkeypatch):
    import httpx
    from github_ai_mcp.core.github_api import GitHub
    window, errors = ui
    job = window.service.create_job("test/repo", "gui-pr")
    modify(window.service, job, "README.md", "changed\n")
    window.service.preview_job(job["id"])
    window.service.create_file_commits(job["id"])
    window.service.publish_branch(job["id"])
    window.service.config.repositories["test/repo"].source = "https://github.com/test/repo.git"
    calls = []
    def api(request):
        calls.append(request.method)
        return httpx.Response(200, json=[]) if request.method == "GET" else httpx.Response(201, json={"html_url": "https://github.com/test/repo/pull/2"})
    window.service.github = GitHub(token="fixture", transport=httpx.MockTransport(api))
    window.job_id = job["id"]
    window.reload_jobs()
    answers = iter(["Reviewed changes", "Explicitly approved PR"])
    monkeypatch.setattr(window, "ask", lambda _: next(answers))
    window.nav.setCurrentRow(4)
    settle(window)
    assert not calls
    window.action_buttons["pr"].click()
    settle(window)
    assert calls == ["GET", "POST"]
    assert window.service.db.get(job["id"])["pr_url"].endswith("/pull/2")
    assert not errors


def test_single_service_controls_delegate_and_render(ui, monkeypatch):
    window, errors = ui
    calls = []
    state = window.supervisor.status()
    def start(name):
        calls.append(("start", name))
        state[name].update(state="Running", process_alive=True, owned=True)
        return state
    def stop(name):
        calls.append(("stop", name))
        state[name].update(state="Stopped", process_alive=False)
        return state
    monkeypatch.setattr(window.supervisor, "start", start)
    monkeypatch.setattr(window.supervisor, "stop", stop)
    monkeypatch.setattr(window.supervisor, "restart", lambda name: (calls.append(("restart", name)), state)[1])
    window.nav.setCurrentRow(5)
    settle(window)
    for name in ("mcp", "tunnel"):
        state[name].update(state="Stopped", process_alive=False)
        window.render_services(state)
        for action in ("start", "restart", "stop"):
            window.service_button_names[f"{name}_{action}"].click()
            settle(window)
    assert calls == [(a, n) for n in ("mcp", "tunnel") for a in ("start", "restart", "stop")]
    assert "MCP:" in window.service_labels["mcp"].text()
    assert "start_mcp" not in window.action_buttons and "stop_mcp" not in window.action_buttons
    assert not errors


def test_setup_reuses_existing_vault_credentials(ui, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from github_ai_mcp.desktop.setup import Setup
    window, errors = ui
    writes = []
    monkeypatch.setattr("github_ai_mcp.desktop.setup.get_secret", lambda _: "existing-secure-secret")
    monkeypatch.setattr("github_ai_mcp.desktop.setup.store_secret", lambda *args: writes.append(args))
    dialog = Setup(window.service.config, window.config_path, window.pool, window)
    dialog.start.setChecked(False)
    dialog.save()
    deadline = time.monotonic() + 5
    while not dialog.result() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not writes
    assert window.service.config.setup_complete
    assert not errors


def test_passive_poll_never_toggles_buttons_or_overlaps(ui, monkeypatch):
    import threading
    window, _ = ui
    window.timer.stop()
    state = window.supervisor.status()
    window.render_services(state)
    transitions = []
    for name, button in window.service_button_names.items():
        original = button.setEnabled
        monkeypatch.setattr(button, "setEnabled", lambda enabled, n=name, f=original:
                            (transitions.append((n, enabled)), f(enabled))[-1])
    for _ in range(3):
        window.poll_services()
        settle(window)
    assert transitions == []
    gate = threading.Event()
    calls = []
    def delayed():
        calls.append(1)
        gate.wait(3)
        return state
    monkeypatch.setattr(window.supervisor, "poll", delayed)
    window.poll_services()
    window.poll_services()
    window.poll_services()
    gate.set()
    settle(window)
    assert calls == [1]
    assert transitions == []


def test_old_poll_result_cannot_overwrite_mutation(ui, monkeypatch):
    import threading
    import copy
    window, _ = ui
    window.timer.stop()
    old = window.supervisor.status()
    new = copy.deepcopy(old)
    new["mcp"].update(state="Running", process_alive=True, healthy=True)
    gate = threading.Event()
    monkeypatch.setattr(window.supervisor, "poll", lambda: (gate.wait(3), old)[1])
    window.poll_services()
    window.service_work(lambda: new)
    deadline = time.monotonic() + 3
    while window.service_busy and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    gate.set()
    settle(window)
    assert window.latest_service_status["mcp"]["state"] == "Running"


def test_readonly_empty_context_and_recovery_visibility(ui):
    window, _ = ui
    window.service.config.mode = "READ_ONLY"
    window.repo.clear()
    window.service.config.repositories.clear()
    window.nav.setCurrentRow(2)
    settle(window)
    assert not window.action_buttons["new_job"].isEnabled()
    assert not window.action_buttons["cancel_job"].isEnabled()
    assert window.action_buttons["recover"].isHidden()
    assert "READ_ONLY" in window.guidance.text()
    assert "Нет репозиториев" in window.guidance.text()
    window.nav.setCurrentRow(1)
    assert window.action_buttons["add_repository"].isVisible()


def test_cancel_confirmation_retains_workspace_and_no_means_no(ui, monkeypatch):
    window, _ = ui
    job = window.service.create_job("test/repo", "cancel-confirm")
    window.job_id = job["id"]
    window.reload_jobs()
    window.nav.setCurrentRow(2)
    settle(window)
    prompts = []
    def reject(*args):
        prompts.append(args[-1])
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "question", reject)
    window.action_buttons["cancel_job"].click()
    assert window.service.db.get(job["id"])["state"] != "CANCELLED"
    assert job["id"] in prompts[0]
    assert "сохранится" in prompts[0] and "не будут отменены" in prompts[0]
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.action_buttons["cancel_job"].click()
    settle(window)
    assert window.service._work(job).exists()
    assert not window.action_buttons["cancel_job"].isEnabled()


def test_recovery_only_for_meaningful_state_and_explains_operation(ui):
    window, _ = ui
    job = window.service.create_job("test/repo", "recovery-context")
    window.job_id = job["id"]
    window.reload_jobs()
    window.nav.setCurrentRow(2)
    settle(window)
    assert window.action_buttons["recover"].isHidden()
    job = window.service.db.get(job["id"])
    job.update(state="RECOVERY_REQUIRED", final_tree="fixture-tree")
    window.service.db.save(job, "TEST_INTERRUPTION")
    window.update_actions()
    assert window.action_buttons["recover"].isVisible()
    assert window.action_buttons["recover"].isEnabled()
    assert "прерванное" in window.action_buttons["recover"].text()
    window.language_selector.setCurrentText("en")
    assert "interrupted" in window.action_buttons["recover"].text()
    assert "force-push" in window.action_buttons["recover"].toolTip()


def test_logout_denial_never_touches_vault(ui, monkeypatch):
    window, _ = ui
    calls = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    monkeypatch.setattr("github_ai_mcp.security.auth_github.logout", lambda: calls.append(1))
    window.logout()
    assert calls == []


def test_log_search_and_advanced_service_status_share_current_snapshot(ui):
    window, _ = ui
    window.supervisor.log("gui", "searchable event")
    window.supervisor.log("gui", "another event")
    window.nav.setCurrentRow(7)
    settle(window)
    window.log_filter.setText("searchable")
    assert "searchable event" in window.output.toPlainText()
    assert "another event" not in window.output.toPlainText()
    window.log_filter.clear()
    assert "another event" in window.output.toPlainText()
    window.nav.setCurrentRow(5)
    settle(window)
    window.advanced.setChecked(True)
    settle(window)
    status = window.supervisor.status()
    window.render_services(status)
    import json
    assert json.loads(window.output.toPlainText()) == status


@pytest.mark.parametrize('locale', ['ru', 'en'])
def test_external_tunnel_localization_and_ownership_controls(ui, locale):
    window, errors = ui
    window.language_selector.setCurrentText(locale)
    state = window.supervisor.status()
    state['tunnel'].update(state='External process detected, ownership unverified', process_alive=False, owned=False)
    window.render_services(state)
    assert not window.service_button_names['tunnel_stop'].isEnabled()
    assert not window.service_button_names['tunnel_restart'].isEnabled()
    assert not window.service_button_names['tunnel_start'].isEnabled()
    label = window.service_labels['tunnel'].text()
    assert ('Внешний' in label or 'внешний' in label) if locale == 'ru' else 'External' in label
    assert not errors


def test_safe_diagnostics_excludes_raw_service_error(ui, monkeypatch):
    window, errors = ui
    state = window.supervisor.status()
    state['tunnel']['error'] = 'short-unrecognized-secret'
    state['tunnel']['error_code'] = 'MCP_COMMAND'
    monkeypatch.setattr(window.supervisor, 'status', lambda: state)
    import json
    assert 'short-unrecognized-secret' not in json.dumps(window.safe_diagnostics())
    assert window.safe_diagnostics()['services']['tunnel']['error_code'] == 'MCP_COMMAND'
