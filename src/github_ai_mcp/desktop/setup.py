"""Graphical first-run configuration; credentials never enter JSON or logs."""
import secrets
import sys
import shutil
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
                              QFormLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QPlainTextEdit, QVBoxLayout, QScrollArea, QWidget)

from github_ai_mcp.desktop import startup
from github_ai_mcp.desktop.tunnel import (SECRET, profile_path, preflight, repair_profile,
                                         command_text, local_profile, expected_command)
from github_ai_mcp.config import save_config
from github_ai_mcp.desktop.prerequisites import check_prerequisites
from github_ai_mcp.desktop.runtime import bundled_tool
from github_ai_mcp.core.github_api import GitHub
from github_ai_mcp.exceptions import AppError
from github_ai_mcp.gui.workers import Task
from github_ai_mcp.security.auth_github import get_secret, store_secret, store_token, remove_secret


class Setup(QDialog):
    def __init__(self, config, path, pool, parent=None):
        super().__init__(parent)
        self.config, self.path, self.pool = config, path, pool
        self.task = None
        self.edit_task = None
        self.diagnostic_task = None
        self.setWindowTitle("GitHub-AI-MCP")
        self.resize(780, 750)
        ru = config.locale == "ru"
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.content = content
        scroll.setWidget(content)
        outer.addWidget(scroll)
        form = QFormLayout(content)
        self.info = QLabel("Первый запуск: Git, защищённое хранилище, MCP и официальный туннель." if ru else
                           "First run: Git, OS credential vault, MCP and official tunnel.")
        self.info.setWordWrap(True)
        outer.addWidget(self.info)
        self.dependencies = QLabel("Проверка компонентов…" if ru else "Checking components…")
        self.dependencies.setWordWrap(True)
        self.dependencies.setOpenExternalLinks(True)
        form.addRow(self.dependencies)
        self.explore = QPushButton("Продолжить без настройки интеграций" if ru else "Explore without configuring integrations")
        self.explore.clicked.connect(self.reject)
        form.addRow(self.explore)
        self.client = QLineEdit(config.tunnel_client or bundled_tool("tunnel-client") or shutil.which("tunnel-client.exe") or shutil.which("tunnel-client") or "")
        form.addRow("Клиент туннеля" if ru else "Tunnel client", self.client)
        browse = QPushButton("Выбрать…" if ru else "Browse…")
        browse.clicked.connect(self.browse)
        form.addRow(browse)
        self.profile = QLineEdit(config.tunnel_profile)
        form.addRow("Профиль" if ru else "Profile", self.profile)
        self.profile_file = QLineEdit(config.tunnel_profile_file)
        form.addRow("YAML профиля" if ru else "Profile YAML", self.profile_file)
        select_profile = QPushButton("Выбрать YAML…" if ru else "Select YAML…")
        select_profile.clicked.connect(self.browse_profile)
        form.addRow(select_profile)
        self.tunnel_key = QLineEdit()
        self.tunnel_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Ключ control-plane туннеля" if ru else "Tunnel control-plane runtime key", self.tunnel_key)
        key_note = QLabel("Сохраняется в хранилище ОС. Это не GitHub PAT и не ключ модели OpenAI." if ru else
                          "Saved in the OS vault. Separate from GitHub PAT and OpenAI model keys.")
        key_note.setWordWrap(True)
        form.addRow(key_note)
        remove_key = QPushButton("Удалить ключ туннеля" if ru else "Remove tunnel key")
        remove_key.clicked.connect(self.remove_tunnel_key)
        form.addRow(remove_key)
        diagnostics = QPushButton("Проверить профиль и ключ" if ru else "Validate profile and key")
        diagnostics.clicked.connect(self.diagnose_tunnel)
        form.addRow(diagnostics)
        repair = QPushButton("Исправить команду MCP (с резервной копией)" if ru else "Repair MCP command (with backup)")
        repair.clicked.connect(self.repair_tunnel)
        form.addRow(repair)
        edit = QPushButton("Редактор YAML" if ru else "YAML editor")
        edit.clicked.connect(self.edit_profile)
        form.addRow(edit)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("GitHub PAT (необязательно)" if ru else "GitHub PAT (optional)", self.token)
        note = QLabel("PAT проверяется до сохранения. Для приватного Git требуется встроенный GitHub CLI.\n"
                      "Используется существующий профиль официального клиента; его вход остаётся у поставщика." if ru else
                      "PAT is validated before saving. Private Git also requires the bundled GitHub CLI.\n"
                      "Uses an existing official client profile; its sign-in is managed by the provider.")
        note.setWordWrap(True)
        form.addRow(note)
        self.stdio = QLineEdit(expected_command(config, Path(path)))
        self.stdio.setCursorPosition(0)
        self.stdio.setToolTip("Команда канала main в YAML. Сохраните настройки после изменения." if ru else
                              "YAML main-channel command. Save settings after editing.")
        form.addRow("Локальная команда stdio" if ru else "Local stdio command", self.stdio)
        reset_stdio = QPushButton("Подставить команду текущей программы" if ru else "Use current application command")
        reset_stdio.clicked.connect(lambda: self.stdio.setText(command_text(self.path)))
        form.addRow(reset_stdio)
        copy_stdio = QPushButton("Скопировать команду stdio" if ru else "Copy stdio command")
        copy_stdio.clicked.connect(lambda: QApplication.clipboard().setText(self.stdio.text()))
        form.addRow(copy_stdio)
        self.copy_button = QPushButton("Скопировать токен MCP" if ru else "Copy MCP token")
        self.copy_button.clicked.connect(self.copy_mcp)
        form.addRow(self.copy_button)
        self.start = QCheckBox("Запускать службы при открытии" if ru else "Start services on launch")
        self.start.setChecked(config.autostart_services)
        form.addRow(self.start)
        self.start_mcp = QCheckBox("Автоматически запускать MCP" if ru else "Start MCP automatically")
        self.start_mcp.setChecked(config.start_mcp)
        form.addRow(self.start_mcp)
        self.start_tunnel = QCheckBox("Автоматически запускать туннель" if ru else "Start optional tunnel automatically")
        self.start_tunnel.setChecked(config.start_tunnel)
        form.addRow(self.start_tunnel)
        self.minimize = QCheckBox("Сворачивать в трей при запуске" if ru else "Minimize to tray on startup")
        self.minimize.setChecked(config.minimize_on_startup)
        form.addRow(self.minimize)
        self.recovery = QCheckBox("Перезапускать службы после сбоя" if ru else "Restart services after failure")
        self.recovery.setChecked(config.restart_services)
        form.addRow(self.recovery)
        self.notifications = QCheckBox("Уведомлять о критических ошибках" if ru else "Notify about critical failures")
        self.notifications.setChecked(config.critical_notifications)
        form.addRow(self.notifications)
        self.windows_start = QCheckBox("Запускать при входе в Windows (текущий пользователь)" if ru else "Launch at Windows sign-in (current user)")
        registration = startup.status(path)
        self.windows_start.setChecked(registration["registered"])
        self.windows_start.setEnabled(sys.platform == "win32")
        form.addRow(self.windows_start)
        self.registration = QLabel()
        self.update_registration()
        self.registration.setWordWrap(True)
        form.addRow(self.registration)
        validate_start = QPushButton("Проверить автозапуск" if ru else "Validate startup")
        validate_start.clicked.connect(self.update_registration)
        form.addRow(validate_start)
        repair_start = QPushButton("Включить / исправить автозапуск" if ru else "Enable / repair startup")
        repair_start.setEnabled(sys.platform == "win32")
        repair_start.clicked.connect(self.repair_startup)
        form.addRow(repair_start)
        details = QPushButton("Открыть автозагрузку Windows" if ru else "Open Windows startup settings")
        details.setEnabled(sys.platform == "win32")
        details.clicked.connect(lambda: __import__("os").startfile("ms-settings:startupapps"))
        form.addRow(details)
        self.background = QCheckBox("Закрытие окна сворачивает в трей" if ru else "Close window to tray")
        self.background.setChecked(config.background_on_close)
        form.addRow(self.background)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить" if ru else "Save")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена" if ru else "Cancel")
        outer.addWidget(self.buttons)
        QTimer.singleShot(0, self.check_components)

    def update_registration(self):
        registration = startup.status(self.path)
        ru = self.config.locale == "ru"
        if sys.platform != "win32":
            text = "Автозапуск доступен только в Windows" if ru else "Logon startup is available on Windows"
        elif registration["valid"]:
            text = "Автозапуск Windows включён, команда корректна" if ru else "Windows startup enabled; command valid"
        elif registration["registered"]:
            text = "Автозапуск зарегистрирован; требуется исправление" if ru else "Startup registered; repair required"
        else:
            text = "Автозапуск Windows выключен" if ru else "Windows startup disabled"
        self.registration.setText(text)

    def selected_config(self):
        command = self.stdio.text().strip()
        return self.config.model_copy(update={"tunnel_client": self.selected_client(),
                "tunnel_profile": self.profile.text().strip(), "tunnel_profile_file": self.profile_file.text().strip(),
                "tunnel_stdio_command": "" if command == command_text(self.path) else command})

    def operation(self, fn):
        if not self.buttons.isEnabled():
            return
        self.buttons.setEnabled(False)
        self.content.setEnabled(False)
        self.task = Task(fn)
        def done(result):
            self.buttons.setEnabled(True)
            self.content.setEnabled(True)
            self.info.setText(str(result))
        self.task.signals.done.connect(done)
        self.task.signals.failed.connect(self.failed)
        self.pool.start(self.task)

    def browse_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "YAML", "", "YAML (*.yaml *.yml)")
        if path:
            self.profile_file.setText(path)

    def remove_tunnel_key(self):
        if QMessageBox.question(self, "GitHub-AI-MCP", "Удалить ключ туннеля из хранилища ОС? / Remove tunnel key from OS vault?") == QMessageBox.StandardButton.Yes:
            def remove():
                remove_secret(SECRET)
                return "Ключ удалён / Key removed"
            self.operation(remove)

    def diagnose_tunnel(self):
        config = self.selected_config()
        key = self.tunnel_key.text().strip() or None
        self.operation(lambda: (preflight(config, self.path, runtime_key=key), "Профиль и ключ приняты doctor; удалённое подключение не проверено / Doctor accepted profile and key; remote connection unverified")[1])

    def repair_tunnel(self):
        if QMessageBox.question(self, "GitHub-AI-MCP", "Изменить только команду MCP в профиле? Будет создана копия. / Change only the MCP command with backup?") == QMessageBox.StandardButton.Yes:
            config = self.selected_config()
            self.operation(lambda: "Команда записана в YAML. Сохраните настройки. Ключ и сеть ещё не проверены. Копия: / Command saved; save settings. Key/network not checked. Backup: " + repair_profile(config, self.path))

    def repair_startup(self):
        if self.windows_start.isChecked():
            try:
                startup.enable(self.path)
                self.update_registration()
            except (OSError, AppError) as error:
                self.info.setText(str(error))
        else:
            self.info.setText("Сначала включите запуск при входе / Select launch at sign-in first")

    def edit_profile(self):
        if not self.buttons.isEnabled():
            return
        # Explicit local editor. Raw secrets are never put in the editor or diagnostic output.
        try:
            config = self.selected_config()
            path = profile_path(config)
        except AppError as error:
            self.info.setText(str(error))
            return
        class EditorDialog(QDialog):
            def reject(inner):
                if not self.edit_task:
                    super(EditorDialog, inner).reject()
        dialog = EditorDialog(self)
        dialog.resize(700, 500)
        layout = QVBoxLayout(dialog)
        from github_ai_mcp.desktop.tunnel import safe_editor_text
        original = path.read_bytes()
        editor = QPlainTextEdit(safe_editor_text(original.decode("utf-8")))
        layout.addWidget(editor)
        note = QLabel("Сохранение: резервная копия и локальная проверка; без сети / Save: backup and local validation; offline")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        def save():
            if self.edit_task:
                return
            text = editor.toPlainText()
            editor.setEnabled(False)
            buttons.setEnabled(False)
            def write():
                import os
                import tempfile
                fd, name = tempfile.mkstemp(suffix=".yaml", dir=path.parent)
                temp = Path(name)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as stream:
                        stream.write(text)
                        stream.flush()
                        os.fsync(stream.fileno())
                    local_profile(config, self.path, path=temp)
                    if path.read_bytes() != original:
                        raise AppError("PROFILE_CHANGED", "Profile changed; retry / Профиль изменился: повторите")
                    # Backups are sanitized if original malformed text contained secrets.
                    backup = path.with_name(path.name + ".backup-" + secrets.token_hex(6))
                    backup.write_text(safe_editor_text(original.decode("utf-8")), encoding="utf-8")
                    os.chmod(backup, 0o600)
                    temp.replace(path)
                    return True
                finally:
                    temp.unlink(missing_ok=True)
            self.edit_task = Task(write)
            def done(_):
                self.edit_task = None
                dialog.accept()
            def failed(error):
                self.edit_task = None
                editor.setEnabled(True)
                buttons.setEnabled(True)
                note.setText(error)
            self.edit_task.signals.done.connect(done)
            self.edit_task.signals.failed.connect(failed)
            self.pool.start(self.edit_task)
        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def check_components(self):
        self.diagnostic_task = Task(check_prerequisites)
        def display(result):
            translations = {"Installed": "Установлен", "Missing": "Не найден", "Unusable": "Не работает",
                            "Available": "Доступно", "Unavailable": "Недоступно"}
            ru = self.config.locale == "ru"
            labels = {"git": "Git", "gh": "GitHub CLI", "vault": "Хранилище ОС" if ru else "OS vault"}
            self.dependencies.setText("<br>".join(
                f"{labels[name]}: {translations[item['status']] if ru else item['status']} · "
                f"<a href='{item['url']}'>{'Официальная справка' if ru else 'Official help'}</a>"
                for name, item in result.items()))
        self.diagnostic_task.signals.done.connect(display)
        self.diagnostic_task.signals.failed.connect(self.dependencies.setText)
        self.pool.start(self.diagnostic_task)

    def copy_mcp(self):
        if self.task and not self.buttons.isEnabled():
            return
        self.buttons.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.task = Task(lambda: get_secret("mcp-http"))
        def copy(value):
            self.buttons.setEnabled(True)
            self.copy_button.setEnabled(True)
            clipboard = QApplication.clipboard()
            clipboard.setText(value)
            self.info.setText("Токен скопирован; буфер очистится через 60 секунд" if self.config.locale == "ru" else
                              "Token copied; clipboard clears after 60 seconds")
            QTimer.singleShot(60000, lambda: clipboard.clear() if clipboard.text() == value else None)
        self.task.signals.done.connect(copy)
        self.task.signals.failed.connect(self.failed)
        self.pool.start(self.task)

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Официальный клиент туннеля" if self.config.locale == "ru" else "Official tunnel client")
        if path:
            self.client.setText(path)

    def save(self):
        if not self.buttons.isEnabled():
            return
        selected = self.selected_config()
        command_changed = selected.tunnel_stdio_command != self.config.tunnel_stdio_command
        tunnel_key = self.tunnel_key.text().strip()
        client, profile, token = self.selected_client(), self.profile.text().strip(), self.token.text().strip()
        ru = self.config.locale == "ru"
        if client and not Path(client).is_file():
            self.info.setText("Файл клиента не найден" if ru else "Client file not found")
            return
        if not profile or any(ord(c) < 32 for c in profile) or profile.startswith("-"):
            self.info.setText("Неверный профиль" if ru else "Invalid profile")
            return
        if token and QMessageBox.question(self, "GitHub", "Новый PAT заменит существующий локальный токен GitHub. Сохранить?" if ru else
                "The new PAT replaces any existing local GitHub token. Save it?") != QMessageBox.StandardButton.Yes:
            return
        self.buttons.setEnabled(False)
        self.content.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.token.clear()
        self.info.setText("Проверка…" if ru else "Validating…")
        def validate():
            if not shutil.which("git"):
                raise AppError("GIT_UNAVAILABLE", "Установите Git for Windows и повторите настройку" if ru else "Install Git for Windows, then retry Setup")
            expected_command(selected, self.path)
            if command_changed:
                repair_profile(selected, self.path)
            if tunnel_key:
                store_secret(SECRET, tunnel_key)
            if token:
                GitHub(token).request("GET", "/user")
                store_token(token)
            try:
                get_secret("mcp-http")
            except AppError:
                store_secret("mcp-http", secrets.token_urlsafe(32))
            return True
        self.task = Task(validate)
        def done(_):
            self.config.tunnel_client = client
            self.config.tunnel_profile = profile
            self.config.autostart_services = self.start.isChecked()
            self.config.start_mcp = self.start_mcp.isChecked()
            self.config.start_tunnel = self.start_tunnel.isChecked()
            self.config.minimize_on_startup = self.minimize.isChecked()
            self.config.restart_services = self.recovery.isChecked()
            self.config.critical_notifications = self.notifications.isChecked()
            self.config.tunnel_profile_file = self.profile_file.text().strip()
            self.config.tunnel_stdio_command = selected.tunnel_stdio_command
            self.config.background_on_close = self.background.isChecked()
            self.config.setup_complete = True
            try:
                save_config(self.path, self.config)
                if self.windows_start.isEnabled():
                    if self.windows_start.isChecked():
                        startup.enable(self.path)
                    else:
                        startup.disable()
            except (OSError, AppError) as error:
                self.failed(str(error))
                return
            self.accept()
            self.tunnel_key.clear()
        self.task.signals.done.connect(done)
        self.task.signals.failed.connect(self.failed)
        self.pool.start(self.task)

    def selected_client(self):
        value = self.client.text().strip()
        # Never persist _MEIPASS: a new launch has a different temporary path.
        return "" if value == bundled_tool("tunnel-client") else value

    def failed(self, message):
        self.info.setText(message)
        self.buttons.setEnabled(True)
        self.content.setEnabled(True)
        self.copy_button.setEnabled(True)

    def reject(self):
        if self.task and not self.buttons.isEnabled():
            return
        super().reject()
