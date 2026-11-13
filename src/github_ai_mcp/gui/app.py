"""Russian/English local administration GUI; shares the CLI/MCP application service."""
import json
import sys
from typing import cast
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QAction, QPen, QIcon
from PySide6.QtWidgets import (QGridLayout, QMenu, QSystemTrayIcon, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QApplication, QComboBox, QDialog, QDialogButtonBox,
                              QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                              QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                              QSplitter, QVBoxLayout, QWidget, QCheckBox, QFormLayout, QSpinBox)

from github_ai_mcp.config import Config, save_config
from github_ai_mcp.exceptions import AppError
from github_ai_mcp.gui.workers import Task
from github_ai_mcp.desktop.supervisor import Supervisor

TEXT = {
    "ru": ["Панель управления", "Репозитории", "Задания", "Просмотр изменений", "GitHub",
           "Службы", "Настройки", "Журнал / поддержка", "Обновить", "Создать задание",
           "Изменить файл", "Удалить файл", "Одобрить снимок", "Создать коммиты", "Отправить ветку в GitHub",
           "Создать pull request", "Восстановить прерванное задание", "Отменить задание", "Вход GitHub", "Выйти GitHub",
           "Запустить MCP", "Остановить MCP", "Сохранить настройки", "Переключить тему"],
    "en": ["Dashboard", "Repositories", "Jobs", "Change review", "GitHub", "Services",
           "Settings", "Logs / support", "Refresh", "Create job", "Edit file", "Delete file",
           "Approve snapshot", "Create commits", "Push branch to GitHub", "Create pull request", "Recover interrupted job", "Cancel job",
           "GitHub login", "GitHub logout", "Start MCP", "Stop MCP", "Save settings", "Toggle theme"],
}


class NavigationDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        focus = bool(option.state & QStyle.StateFlag.State_HasFocus)
        styled = QStyleOptionViewItem(option)
        styled.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, styled, index)
        if focus:
            painter.save()
            painter.setPen(QPen(option.palette.highlight().color(), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(option.rect.adjusted(3, 3, -3, -3), 5, 5)
            painter.restore()


class Window(QMainWindow):
    def __init__(self, service, config_path: Path, bootstrap=False):
        super().__init__()
        self.service, self.config_path = service, config_path.resolve()
        self.job_id = None
        self.preview = None
        self.dark = True
        self.tasks: list[Task] = []
        self.pool = QThreadPool.globalInstance()
        self.supervisor = Supervisor(self.config_path)
        self.service_busy = False
        self.service_generation = 0
        self.poll_busy = False
        self.exiting = False
        self.github_actor = ""
        self.last_github_check = 0.0
        self.service_labels = {}
        self.service_buttons = []
        self.service_button_names = {}
        from github_ai_mcp.desktop.runtime import asset_path
        self.setWindowIcon(QIcon(str(asset_path("github-ai-mcp.ico"))))
        self.setWindowTitle("GitHub-AI-MCP · Local control")
        self.resize(1240, 820)
        self.setMinimumSize(960, 650)
        layout = QVBoxLayout()
        header = QHBoxLayout()
        self.summary = QLabel()
        self.language_selector = QComboBox()
        self.language_selector.addItems(["ru", "en"])
        self.language_selector.setCurrentText(service.config.locale)
        self.language_selector.currentTextChanged.connect(self.translate)
        header.addWidget(self.summary, 1)
        header.addWidget(self.language_selector)
        layout.addLayout(header)
        services = QGridLayout()
        for row, name in enumerate(("mcp", "tunnel")):
            label = QLabel()
            label.setWordWrap(True)
            self.service_labels[name] = label
            services.addWidget(label, row, 0)
            for column, action in enumerate(("start", "stop", "restart"), 1):
                button = QPushButton()
                button.clicked.connect(lambda checked=False, n=name, a=action: self.control_service(a, n))
                services.addWidget(button, row, column)
                self.service_buttons.append((button, action))
                button.setObjectName(f"{name}_{action}")
                self.service_button_names[f"{name}_{action}"] = button
        self.github_label = QLabel()
        services.addWidget(self.github_label, 2, 0)
        self.setup_button = QPushButton()
        self.setup_button.clicked.connect(self.setup)
        services.addWidget(self.setup_button, 2, 1)
        self.stop_all_button = QPushButton()
        self.stop_all_button.clicked.connect(lambda: self.control_service("stop_all"))
        services.addWidget(self.stop_all_button, 2, 2)
        self.exit_button = QPushButton()
        self.exit_button.clicked.connect(self.exit_application)
        services.addWidget(self.exit_button, 2, 3)
        self.diagnostics_button = QPushButton("Run Diagnostics / Диагностика")
        self.diagnostics_button.clicked.connect(lambda: self.execute(self.safe_diagnostics))
        services.addWidget(self.diagnostics_button, 3, 0)
        self.copy_diagnostics_button = QPushButton("Copy Safe Diagnostics / Копировать диагностику")
        self.copy_diagnostics_button.clicked.connect(lambda: self.execute(self.safe_diagnostics,
            lambda result: QApplication.clipboard().setText(json.dumps(result, ensure_ascii=False, indent=2))))
        services.addWidget(self.copy_diagnostics_button, 3, 1, 1, 3)
        services.setColumnStretch(0, 1)
        self.services_panel = QWidget()
        self.services_panel.setLayout(services)
        self.nav = QListWidget()
        self.nav.setItemDelegate(NavigationDelegate(self.nav))
        self.nav.currentRowChanged.connect(self.refresh)
        self.jobs = QComboBox()
        self.jobs.currentIndexChanged.connect(self.select_job)
        self.repo = QComboBox()
        self.repo.addItems(list(service.config.repositories))
        self.repo.currentIndexChanged.connect(self.refresh)
        selectors = QHBoxLayout()
        self.repo_label = QLabel()
        selectors.addWidget(self.repo_label)
        selectors.addWidget(self.repo, 1)
        self.job_label = QLabel()
        selectors.addWidget(self.job_label)
        selectors.addWidget(self.jobs, 2)
        layout.addLayout(selectors)
        self.log_filter = QLineEdit()
        self.log_filter.textChanged.connect(self.filter_logs)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.settings = QPlainTextEdit()
        self.settings.setPlainText(json.dumps(service.config.model_dump(mode="json"), ensure_ascii=False, indent=2))
        self.settings.hide()
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.health_summary = QLabel()
        self.health_summary.setWordWrap(True)
        right_layout.addWidget(self.health_summary)
        self.overview = QWidget()
        overview_layout = QGridLayout(self.overview)
        self.overview_cards = {}
        for index, name in enumerate(("repositories", "jobs", "mode", "next")):
            card = QLabel()
            card.setWordWrap(True)
            card.setMargin(18)
            card.setMinimumHeight(100)
            card.setObjectName("overview_card")
            overview_layout.addWidget(card, index // 2, index % 2)
            self.overview_cards[name] = card
        right_layout.addWidget(self.overview)
        self.guidance = QLabel()
        self.guidance.setWordWrap(True)
        right_layout.addWidget(self.guidance)
        right_layout.addWidget(self.github_label)
        right_layout.addWidget(self.services_panel)
        self.advanced = QCheckBox()
        self.advanced.toggled.connect(self.refresh)
        right_layout.addWidget(self.advanced)
        right_layout.addWidget(self.log_filter)
        right_layout.addWidget(self.output)
        right_layout.addWidget(self.settings)
        split = QSplitter()
        split.addWidget(self.nav)
        split.addWidget(right)
        split.setSizes([220, 900])
        layout.addWidget(split, 1)
        self.action_buttons = {}
        callbacks = {
            "refresh": self.refresh, "new_job": self.new_job, "edit_file": self.edit_file,
            "delete_file": self.delete_file, "approve": self.approve,
            "commit": lambda: self.job_operation("create_file_commits"),
            "push": lambda: self.job_operation("publish_branch"), "pr": self.pr,
            "recover": lambda: self.job_operation("resume_job"),
            "cancel_job": lambda: self.job_operation("cancel_job"),
            "login": self.login, "logout": self.logout, "save": self.save,
            "theme": lambda: self.theme(), "add_repository": self.add_repository,
            "branches": lambda: self.repository_operation("list_branches"),
            "history": lambda: self.repository_operation("list_recent_commits"),
            "contributions": lambda: self.repository_operation("check_contribution_eligibility"),
        }
        self.action_bar = QVBoxLayout()
        for name, callback in callbacks.items():
            button = QPushButton()
            button.setObjectName(name)
            button.clicked.connect(callback)
            self.action_bar.addWidget(button)
            self.action_buttons[name] = button
        right_layout.addLayout(self.action_bar)
        self.content_spacer = QWidget()
        right_layout.addWidget(self.content_spacer, 1)
        self.settings_form = QWidget()
        form = QFormLayout(self.settings_form)
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["READ_ONLY", "LOCAL_REVIEW", "AUTO_APPROVED"])
        self.mode_selector.setCurrentText(service.config.mode)
        self.port_selector = QSpinBox()
        self.port_selector.setRange(1024, 65535)
        self.port_selector.setValue(service.config.port)
        self.mode_label, self.port_label = QLabel(), QLabel()
        form.addRow(self.mode_label, self.mode_selector)
        form.addRow(self.port_label, self.port_selector)
        self.launch_settings = QPushButton()
        self.launch_settings.clicked.connect(self.setup)
        form.addRow(self.launch_settings)
        right_layout.insertWidget(4, self.settings_form)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.legal_action = QAction(self)
        self.legal_action.triggered.connect(self.show_legal)
        self.menuBar().addAction(self.legal_action)
        self.translate()
        self.theme(False)
        self.reload_jobs()
        self.nav.setCurrentRow(0)
        self.refresh()
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        menu = QMenu(self)
        self.show_action = QAction("GitHub-AI-MCP", self)
        self.show_action.triggered.connect(self.showNormal)
        menu.addAction(self.show_action)
        self.exit_action = QAction(self.exit_button.text(), self)
        self.exit_action.triggered.connect(self.exit_application)
        menu.addAction(self.exit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.poll_services)
        self.timer.start()
        self.poll_services()
        if bootstrap:
            QTimer.singleShot(0, self.startup)

    def translate(self, *_):
        labels = TEXT[self.language_selector.currentText()]
        row = max(self.nav.currentRow(), 0)
        self.nav.blockSignals(True)
        self.nav.clear()
        self.nav.addItems(labels[:8])
        self.nav.setCurrentRow(row)
        self.nav.blockSignals(False)
        names = ["refresh", "new_job", "edit_file", "delete_file", "approve", "commit", "push",
                 "pr", "recover", "cancel_job", "login", "logout", "save", "theme"]
        indices = list(range(8, 20)) + [22, 23]
        for name, index in zip(names, indices):
            self.action_buttons[name].setText(labels[index])
        self.action_buttons["branches"].setText(self.tr_text("View repository branches", "Посмотреть ветки репозитория"))
        self.action_buttons["history"].setText(self.tr_text("View recent commits", "Посмотреть последние коммиты"))
        self.action_buttons["contributions"].setText(self.tr_text("Check contribution eligibility", "Проверить учёт вклада в GitHub"))
        self.action_buttons["add_repository"].setText(self.tr_text("Add authorized repository", "Добавить разрешённый репозиторий"))
        self.log_filter.setPlaceholderText(self.tr_text("Search diagnostic events", "Поиск событий в журнале"))
        self.advanced.setText(self.tr_text("Advanced: raw JSON", "Дополнительно: исходный JSON"))
        self.mode_label.setText(self.tr_text("Security mode", "Режим безопасности"))
        self.port_label.setText(self.tr_text("Local MCP port", "Локальный порт MCP"))
        self.launch_settings.setText(self.tr_text("Configure credentials, tunnel and startup", "Настроить подключение, туннель и запуск"))
        self.launch_settings.setToolTip(self.tr_text("Configure local integrations. Tunnel is optional.", "Настройка локальных интеграций. Туннель необязателен."))
        self.update_actions()
        self.legal_action.setText(self.tr_text("About / Legal", "О программе / Лицензии"))
        self.repo_label.setText(self.tr_text("Repository", "Репозиторий"))
        self.job_label.setText(self.tr_text("Job", "Задание"))
        self.setup_button.setToolTip(self.tr_text("Configure optional tunnel and startup", "Настроить необязательный туннель и запуск"))
        self.stop_all_button.setToolTip(self.tr_text("Stop this application's owned MCP and tunnel processes", "Остановить принадлежащие приложению процессы MCP и туннеля"))
        self.exit_button.setToolTip(self.tr_text("Stop owned services and exit", "Остановить собственные службы и закрыть приложение"))
        for button, action in self.service_buttons:
            button.setText({"start": self.tr_text("Start", "Запустить"), "stop": self.tr_text("Stop", "Остановить"),
                            "restart": self.tr_text("Restart", "Перезапустить")}[action])
        self.setup_button.setText(self.tr_text("Setup", "Настройка запуска"))
        self.stop_all_button.setText(self.tr_text("Stop all", "Остановить всё"))
        self.exit_button.setText(self.tr_text("Exit application", "Закрыть приложение"))
        if hasattr(self, "exit_action"):
            self.exit_action.setText(self.exit_button.text())
        self.github_label.setText("GitHub: " + (self.github_actor or self.tr_text("Not verified", "Не проверен")))
        if hasattr(self, "latest_service_status"):
            self.render_services(self.latest_service_status)
        self.output.setPlaceholderText(self.tr_text("Select a repository or job. Use Setup to connect services.", "Выберите репозиторий или задание. Откройте настройку запуска для подключения служб."))
        self.summary.setText(f"GitHub-AI-MCP · {self.service.config.mode} · "
                             f"{len(self.service.config.repositories)} {self.tr_text('repositories', 'репозиториев')} · 127.0.0.1:{self.service.config.port}")

    def tr_text(self, en, ru):
        return ru if self.language_selector.currentText() == "ru" else en

    def theme(self, toggle=True):
        if toggle:
            self.dark = not self.dark
        bg, fg, panel, border = ("#101923", "#edf3fa", "#1b2a3b", "#52677e") if self.dark else ("#f4f7fa", "#162435", "#ffffff", "#667c90")
        self.setStyleSheet(f"QWidget {{background:{bg};color:{fg};font-size:14px;}} "
                          f"QPlainTextEdit,QListWidget,QComboBox,QLineEdit {{background:{panel};border:2px solid {border};"
                          "border-radius:8px;padding:6px;} QPushButton {background:#205d96;color:white;"
                          "padding:8px;border:2px solid transparent;border-radius:7px;}"
                          "QPushButton:hover {background:#286ea9;} QPushButton:pressed {background:#154570;}"
                          "QPushButton:focus,QLineEdit:focus,QComboBox:focus,QPlainTextEdit:focus {border:2px solid #72baff;}"
                          "QPushButton:disabled {background:#455565;color:#e2e8f0;}"
                          f"QLabel#overview_card {{background:{panel};border:1px solid {border};border-radius:10px;}} "
                          "QListWidget::item {padding:10px;margin:2px;border-radius:6px;}"
                          "QListWidget::item:hover {background:#364f69;}"
                          "QListWidget::item:selected {background:#205d96;color:white;} QLabel {padding:4px;}")

    def execute(self, fn, callback=None):
        if self.tasks:
            self.statusBar().showMessage(self.tr_text("Wait for the current operation", "Дождитесь текущей операции"))
            return
        page = self.nav.currentRow()
        task = Task(fn)
        self.tasks.append(task)
        self.statusBar().showMessage(self.tr_text("Working…", "Выполняется…"))
        self.update_actions()
        def done(value):
            self.statusBar().showMessage(self.tr_text("Done", "Готово"))
            self.tasks.remove(task)
            self.update_actions()
            if self.nav.currentRow() == page:
                self.display(value)
            if callback:
                callback(value)
            self.reload_jobs()
            self.update_actions()
        def failed(error):
            self.supervisor.log("gui", error)
            self.statusBar().showMessage(error)
            QMessageBox.warning(self, "GitHub-AI-MCP", error)
            self.tasks.remove(task)
            self.update_actions()
        task.signals.done.connect(done)
        task.signals.failed.connect(failed)
        self.pool.start(task)

    def display(self, value):
        self.last_display = value
        if self.advanced.isChecked():
            text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        elif isinstance(value, dict) and "diffs" in value:
            text = "\n\n".join(str(item.get("diff", item)) if isinstance(item, dict) else str(item)
                               for item in value["diffs"])
        elif self.nav.currentRow() == 0:
            text = self.tr_text(
                "Choose Repositories to add a repository. Create a job in Jobs, then review its changes.\n"
                "READ_ONLY allows inspection only. Services manages the local MCP server and optional tunnel.",
                "Добавьте репозиторий в разделе «Репозитории». Создайте задание в разделе «Задания», затем проверьте изменения.\n"
                "READ_ONLY разрешает только просмотр. Раздел «Службы» управляет MCP и необязательным туннелем.")
        else:
            labels = {"state": self.tr_text("State", "Состояние"), "repository": self.tr_text("Repository", "Репозиторий"),
                      "target_branch": self.tr_text("Branch", "Ветка"), "id": self.tr_text("Job ID", "ID задания"),
                      "pr_url": "Pull request", "created_commits": self.tr_text("Commits", "Коммиты")}
            records = value if isinstance(value, list) else [value]
            text = "\n\n".join("\n".join(f"{labels.get(k, k)}: {v}" for k, v in record.items()
                if k in labels or not isinstance(v, dict)) if isinstance(record, dict) else str(record)
                for record in records)
        if self.output.toPlainText() != text:
            self.output.setPlainText(text)

    def selected_job(self):
        if self.job_id:
            try:
                return self.service.db.get(self.job_id)
            except AppError:
                pass
        return None

    def update_actions(self):
        if not hasattr(self, "action_buttons"):
            return
        row = self.nav.currentRow()
        job = self.selected_job()
        state = job["state"] if job else ""
        writable = self.service.config.mode != "READ_ONLY"
        editable = bool(job and not job.get("commits") and state in
                        {"SNAPSHOT_READY", "PATCHING", "PREVIEW_READY", "CHECK_FAILED"})
        recovery = bool(job and ((state in {"COMMITTING", "RECOVERY_REQUIRED"} and job.get("final_tree"))
                               or (state == "CHECK_FAILED" and job.get("commits")) or state == "PUBLISHING"))
        pages = {"refresh": {0, 1, 2, 3, 4, 5, 7}, "new_job": {1, 2},
                 "edit_file": {3}, "delete_file": {3}, "approve": {3}, "commit": {3, 4},
                 "push": {4}, "pr": {4}, "recover": {2}, "cancel_job": {2},
                 "login": {4}, "logout": {4}, "save": {6}, "theme": {6}, "add_repository": {1}, "branches": {1}, "history": {1}, "contributions": {4}}
        allowed = {"new_job": writable and bool(self.repo.currentText()),
                   "edit_file": writable and editable, "delete_file": writable and editable,
                   "approve": writable and editable and bool(self.preview and self.preview.get("job_id") == self.job_id),
                   "commit": writable and bool(job) and state in {"PREVIEW_READY", "CHECK_FAILED"},
                   "push": self.service.config.mode == "AUTO_APPROVED" and state == "VERIFIED",
                   "pr": self.service.config.mode == "AUTO_APPROVED" and state == "PUBLISHED",
                   "recover": writable and recovery,
                   "cancel_job": writable and bool(job) and state not in {"CANCELLED", "COMPLETED", "NO_CHANGE"}}
        for name in ("branches", "history", "contributions"):
            allowed[name] = bool(self.repo.currentText())
        # Evaluate existing policy without changing state or granting permissions.
        policy_errors = {}
        if job:
            for name, action in (("commit", "commit"), ("push", "push"), ("pr", "pr")):
                try:
                    self.service.policy.authorize(job, action)
                except AppError as error:
                    allowed[name] = False
                    policy_errors[name] = error.code
        tips = {
            "branches": ("Inspect branches of the selected authorized repository", "Посмотреть ветки выбранного разрешённого репозитория"),
            "history": ("Read recent repository commits without modifying them", "Прочитать последние коммиты без изменения репозитория"),
            "contributions": ("Check author email association and GitHub contribution conditions; no writes", "Проверить email автора и условия учёта вклада в GitHub без изменений"),
            "refresh": ("Refresh this section", "Обновить выбранный раздел"),
            "new_job": ("Create an isolated workspace before editing repository files", "Создать отдельную рабочую копию для изменения файлов"),
            "edit_file": ("Edit a file in the selected job workspace", "Изменить файл в рабочей копии выбранного задания"),
            "delete_file": ("Delete a workspace file after confirmation", "Удалить файл рабочей копии после подтверждения"),
            "approve": ("Approve this exact reviewed snapshot for one hour; changes invalidate approval", "Одобрить проверенный снимок на час; изменение файлов отменяет одобрение"),
            "commit": ("Create one Git commit per reviewed changed path; policy and checks still apply", "Создать один коммит на каждый проверенный путь; политика и проверки обязательны"),
            "push": ("Push the selected job branch to its authorized remote; requires approval", "Отправить ветку задания в разрешённый репозиторий; требуется одобрение"),
            "pr": ("Create a pull request from the published job branch into the repository default branch", "Создать pull request из опубликованной ветки в основную ветку репозитория"),
            "recover": ("Recover commits, retry final checks or reconcile an interrupted push; never force-push", "Восстановить коммиты, повторить проверки или сверить прерванную отправку; без принудительной отправки"),
            "cancel_job": ("Mark the selected job CANCELLED. Retain workspace; published changes remain", "Пометить задание CANCELLED. Рабочая копия и опубликованные изменения сохранятся"),
            "login": ("Verify a GitHub PAT and save it in the OS credential vault", "Проверить GitHub PAT и сохранить в защищённом хранилище ОС"),
            "logout": ("Remove the local credential after confirmation; revoke separately on GitHub", "Удалить локальный токен после подтверждения; отзыв на GitHub выполняется отдельно"),
            "save": ("Save trusted settings; restart to apply", "Сохранить доверенные настройки; для применения нужен перезапуск"),
            "theme": ("Switch between dark and light themes", "Переключить тёмную и светлую тему"),
            "add_repository": ("Allow access to a repository with explicitly authorized Git author identity", "Разрешить доступ к репозиторию с явно указанным автором Git"),
        }
        for name, button in self.action_buttons.items():
            visible = row in pages[name] and (name != "recover" or recovery)
            button.setVisible(visible)
            enabled = allowed.get(name, True) and not self.tasks
            if button.isEnabled() != enabled:
                button.setEnabled(enabled)
            reason = ""
            if not enabled:
                if self.tasks:
                    reason = self.tr_text("An operation is running. Wait for completion.", "Выполняется операция. Дождитесь завершения.")
                elif not writable and name in allowed:
                    reason = self.tr_text("READ_ONLY prohibits changes.", "READ_ONLY запрещает изменения.")
                elif name == "new_job" and not self.repo.currentText():
                    reason = self.tr_text("Add and select an authorized repository.", "Добавьте и выберите разрешённый репозиторий.")
                elif name in {"push", "pr"} and self.service.config.mode != "AUTO_APPROVED":
                    reason = self.tr_text("Remote writes require AUTO_APPROVED and approval.", "Отправка требует AUTO_APPROVED и одобрения.")
                elif not job:
                    reason = self.tr_text("Select a job first.", "Сначала выберите задание.")
                elif name == "approve" and not self.preview:
                    reason = self.tr_text("Refresh and read the current change review first.", "Сначала обновите и прочитайте текущие изменения.")
                elif name in policy_errors:
                    reasons = {"APPROVAL_REQUIRED": ("Approve the exact snapshot or configure a scoped grant.", "Одобрите точный снимок либо настройте ограниченный грант."),
                               "IDENTITY_REQUIRED": ("Authorize the repository's real Git author identity.", "Разрешите использование реального автора Git в настройках репозитория.")}
                    reason = self.tr_text(*reasons.get(policy_errors[name], ("Blocked by security policy.", "Запрещено политикой безопасности.")))
                else:
                    reason = self.tr_text(f"Unavailable in job state {state}.", f"Недоступно в состоянии задания {state}.")
            button.setToolTip(self.tr_text(*tips[name]) + ("\n" + reason if reason else ""))
        if not self.service.config.repositories:
            guidance = self.tr_text("No repositories configured. Add an authorized repository to begin.", "Нет репозиториев. Добавьте разрешённый репозиторий для начала работы.")
        else:
            guidance = self.tr_text("Selected job", "Выбранное задание") + f": {self.job_id or '—'} · {state or '—'}"
        if not writable:
            guidance += "\n" + self.tr_text("READ_ONLY: inspection only. Writes are disabled by policy.", "READ_ONLY: только просмотр. Изменения запрещены политикой.")
        self.guidance.setText(guidance)
        self.overview.setVisible(row == 0 and not self.advanced.isChecked())
        active = sum(j["state"] not in {"CANCELLED", "COMPLETED", "NO_CHANGE"} for j in self.service.db.list_jobs()
                     if j["repository"] in self.service.config.repositories)
        self.overview_cards["repositories"].setText(self.tr_text("AUTHORIZED REPOSITORIES", "РАЗРЕШЁННЫЕ РЕПОЗИТОРИИ") + f"\n{len(self.service.config.repositories)}")
        self.overview_cards["jobs"].setText(self.tr_text("ACTIVE JOBS", "АКТИВНЫЕ ЗАДАНИЯ") + f"\n{active}")
        self.overview_cards["mode"].setText(self.tr_text("SECURITY MODE", "РЕЖИМ БЕЗОПАСНОСТИ") + f"\n{self.service.config.mode}")
        self.overview_cards["next"].setText(self.tr_text("NEXT STEP\nAdd a repository, create a job and review its changes.", "СЛЕДУЮЩИЙ ШАГ\nДобавьте репозиторий, создайте задание и проверьте изменения."))
        self.health_summary.setVisible(row == 0)
        self.content_spacer.setVisible(row in {0, 5})
        self.log_filter.setVisible(row == 7)
        self.services_panel.setVisible(row == 5)
        self.github_label.setVisible(row in {0, 4})
        self.settings_form.setVisible(row == 6 and not self.advanced.isChecked())


    def reload_jobs(self):
        jobs = [j for j in self.service.db.list_jobs() if j["repository"] in self.service.config.repositories]
        self.jobs.blockSignals(True)
        self.jobs.clear()
        for job in jobs:
            self.jobs.addItem(f"{job['id'][:8]} · {job['state']} · {job['target_branch']}", job["id"])
        if self.job_id:
            self.jobs.setCurrentIndex(self.jobs.findData(self.job_id))
        elif jobs:
            self.job_id = jobs[0]["id"]
        self.jobs.blockSignals(False)
        self.update_actions()

    def select_job(self, *_):
        self.job_id = self.jobs.currentData()
        self.preview = None
        self.refresh()

    def dashboard(self):
        result = self.service.health_check()
        import time
        if time.monotonic() - self.last_github_check >= 300:
            try:
                result["github_actor"] = self.service.github.request("GET", "/user")["login"]
            except AppError as e:
                result["github_actor"] = e.code
        else:
            result["github_actor"] = self.github_actor
        return result

    def refresh(self, *_):
        row = self.nav.currentRow()
        repo, job_id = self.repo.currentText(), self.job_id
        self.update_actions()
        self.settings.setVisible(row == 6 and self.advanced.isChecked())
        self.output.setVisible(row not in {0, 5, 6} or (row in {0, 5} and self.advanced.isChecked()))
        if row == 0:
            self.execute(self.dashboard, self.dashboard_done)
        elif row == 1 and repo:
            self.execute(lambda: self.service.get_repository_info(repo))
        elif row == 2:
            self.display([self.service._report(j) for j in self.service.db.list_jobs()
                       if j["repository"] in self.service.config.repositories])
        elif row == 3 and job_id:
            def get_all():
                preview = self.service.preview_job(job_id, limit=50)
                while preview["next_offset"] is not None:
                    more = self.service.preview_job(job_id, offset=preview["next_offset"], limit=50)
                    if more["fingerprint"] != preview["fingerprint"]:
                        raise AppError("STALE_APPROVAL", "Snapshot changed during review")
                    preview["diffs"].extend(more["diffs"])
                    preview["next_offset"] = more["next_offset"]
                return preview
            self.execute(get_all, lambda value: self.accept_preview(value))
        elif row == 4 and job_id:
            self.execute(lambda: self.service.get_job_status(job_id))
        elif row == 5:
            self.poll_services()
            self.output.setPlainText(self.tr_text("Local MCP requires its protected token. The external tunnel is optional.\nA live tunnel process does not confirm an external connection.", "Локальный MCP требует защищённый токен. Внешний туннель необязателен.\nРаботающий процесс туннеля не подтверждает внешнее подключение."))
        elif row == 7:
            self.log_text = self.supervisor.logs()
            self.filter_logs()
        elif row not in {6}:
            self.output.setPlainText(self.tr_text("Select a repository or job to view this section.", "Выберите репозиторий или задание для просмотра раздела."))

    def filter_logs(self, *_):
        query = self.log_filter.text().casefold()
        text = getattr(self, "log_text", "")
        if query:
            text = "\n".join(line for line in text.splitlines() if query in line.casefold())
        self.output.setPlainText(text)

    def accept_preview(self, value):
        if value.get("job_id") == self.job_id:
            self.preview = value

    def ask(self, label):
        value, ok = QInputDialog.getText(self, "GitHub-AI-MCP", label)
        return value if ok and value else None

    def repository_operation(self, name):
        repository = self.repo.currentText()
        if not repository:
            return
        if name == "check_contribution_eligibility":
            job = self.selected_job()
            branch = job["target_branch"] if job and job["repository"] == repository else self.service.config.repositories[repository].default_branch
            self.execute(lambda: self.service.check_contribution_eligibility(repository, branch))
        else:
            self.execute(lambda: getattr(self.service, name)(repository))

    def new_job(self):
        repo = self.repo.currentText()
        if not repo:
            QMessageBox.information(self, "Repositories", self.tr_text('Add an allowlisted repository in Settings first', 'Сначала добавьте разрешённый репозиторий в настройках'))
            return
        title = self.ask(self.tr_text('Unique task title (English)', 'Название задачи по-английски (уникальное)'))
        if title:
            self.execute(lambda: self.service.create_job(repo, title, task_name=title),
                         lambda j: setattr(self, "job_id", j["id"]))

    def edit_file(self):
        if not self.job_id:
            return
        path = self.ask(self.tr_text('Repository-relative path', 'Путь относительно репозитория'))
        if not path:
            return
        message = self.ask(self.tr_text('Commit subject: fix: … / feat: …', 'Сообщение коммита: fix: … / feat: …'))
        if not message:
            return
        job_id = self.job_id
        def prepare():
            job = self.service.db.get(job_id)
            try:
                current = self.service.read_file(job["repository"], path, job_id)
            except AppError as e:
                if e.code != "NOT_FOUND":
                    raise
                current = {"content": "", "checksum": None}
            return current
        def edit(current):
            dialog = QDialog(self)
            dialog.setWindowTitle(path)
            dialog.resize(800, 600)
            box = QVBoxLayout(dialog)
            editor = QPlainTextEdit(current["content"])
            box.addWidget(editor)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            box.addWidget(buttons)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                content = editor.toPlainText()
                def write():
                    self.service.plan_changes(job_id, {path: message})
                    return self.service.write_file(job_id, path, content, current["checksum"])
                self.preview = None
                self.execute(write)
        self.execute(prepare, edit)

    def delete_file(self):
        if not self.job_id:
            return
        path = self.ask(self.tr_text('Delete repository-relative file path', 'Удалить файл: путь относительно репозитория'))
        if path and QMessageBox.question(self, self.tr_text('Delete', 'Удаление'), path) == QMessageBox.StandardButton.Yes:
            job_id = self.job_id
            def delete():
                job = self.service.db.get(job_id)
                current = self.service.read_file(job["repository"], path, job_id)
                self.service.plan_changes(job_id, {path: "chore: delete " + path})
                return self.service.delete_file(job_id, path, current["checksum"])
            self.preview = None
            self.execute(delete)

    def approve(self):
        if not self.job_id or not self.preview or self.preview["job_id"] != self.job_id:
            QMessageBox.information(self, self.tr_text('Approval', 'Одобрение'), self.tr_text('Open Change review and read the current diff first', 'Откройте просмотр изменений и прочитайте текущий diff'))
            return
        actions = ["commit"]
        if self.service.config.mode == "AUTO_APPROVED":
            choice, ok = QInputDialog.getItem(self, self.tr_text('Approval', 'Одобрение'), self.tr_text('Approve exact snapshot for one hour', 'Одобрить точный снимок на один час'),
                                            ["commit", "commit,push", "commit,push,pr"], 0, False)
            if not ok:
                return
            actions = choice.split(",")
        if QMessageBox.question(self, self.tr_text('Human approval', 'Одобрение пользователя'), f"Approve {actions}?\n{self.preview['fingerprint']}\n"
                                + self.tr_text("Clone hooks/filters are disabled. Host tests run only if locally trusted.", "Хуки и фильтры отключены. Тесты выполняются только при локальном доверии.")) == QMessageBox.StandardButton.Yes:
            ident, fingerprint = self.job_id, self.preview["fingerprint"]
            self.execute(lambda: self.service.approve_local(ident, fingerprint, actions))

    def job_operation(self, name):
        if self.job_id:
            ident = self.job_id
            job = self.service.db.get(ident)
            descriptions = {
                "cancel_job": self.tr_text("Cancel this job? Its workspace is retained. Commits and changes already published to GitHub will not be undone.", "Отменить задание? Рабочая копия сохранится. Коммиты и уже опубликованные в GitHub изменения не будут отменены."),
                "resume_job": self.tr_text("Recover interrupted commits, retry final verification or reconcile publication according to the current state. Remote divergence stops recovery.", "Восстановить прерванные коммиты, повторить итоговую проверку или сверить публикацию по текущему состоянию. Расхождение удалённой ветки остановит восстановление."),
                "publish_branch": self.tr_text("Push this branch to its configured remote?", "Отправить эту ветку в настроенный удалённый репозиторий?"),
                "create_file_commits": self.tr_text("Create commits for the reviewed changes?", "Создать коммиты для проверенных изменений?"),
            }
            text = f"{ident} · {job['state']}\n{job['repository']} · {job['target_branch']}\n" + descriptions[name]
            if QMessageBox.question(self, "GitHub-AI-MCP", text) != QMessageBox.StandardButton.Yes:
                return
            self.execute(lambda: getattr(self.service, name)(ident))

    def pr(self):
        if not self.job_id:
            return
        title = self.ask(self.tr_text('PR title', 'Заголовок PR'))
        description = self.ask(self.tr_text('PR summary', 'Описание PR'))
        if title and description:
            ident = self.job_id
            job = self.service.db.get(ident)
            target = self.service.config.repositories[job["repository"]].default_branch
            if QMessageBox.question(self, "Pull request", f"{job['repository']}\n{job['target_branch']} → {target}\n{title}\n{description}") != QMessageBox.StandardButton.Yes:
                return
            self.execute(lambda: self.service.create_pull_request(ident, title, description))

    def login(self):
        token, ok = QInputDialog.getText(self, self.tr_text('GitHub login', 'Вход GitHub'), self.tr_text('Fine-grained PAT → OS credential vault', 'Fine-grained PAT → защищённое хранилище ОС'),
                                        QLineEdit.EchoMode.Password)
        if ok and token:
            if QMessageBox.question(self, "GitHub", self.tr_text("Save this token? It will replace any existing local GitHub credential.", "Сохранить этот токен? Он заменит существующий локальный токен GitHub.")) != QMessageBox.StandardButton.Yes:
                return
            from github_ai_mcp.security.auth_github import store_token
            def login():
                from github_ai_mcp.core.github_api import GitHub
                actor = GitHub(token).request("GET", "/user")["login"]
                store_token(token)
                return {"github_actor": actor}
            self.execute(login, self.dashboard_done)

    def logout(self):
        if QMessageBox.question(self, "GitHub", self.tr_text("Delete the saved local GitHub token? This does not revoke it on GitHub.", "Удалить сохранённый локальный токен GitHub? Это не отзывает его на GitHub.")) != QMessageBox.StandardButton.Yes:
            return
        from github_ai_mcp.security.auth_github import logout
        def delete_token():
            logout()
            return {"revoke_url": "https://github.com/settings/tokens"}
        self.execute(delete_token, lambda _: self.dashboard_done({"github_actor": "AUTH_REQUIRED"}))

    def save(self):
        try:
            config = Config.model_validate_json(self.settings.toPlainText()) if self.advanced.isChecked() else self.service.config.model_copy(deep=True)
            if not self.advanced.isChecked():
                config.mode = self.mode_selector.currentText()
                config.port = self.port_selector.value()
            config.locale = self.language_selector.currentText()
            if QMessageBox.question(self, self.tr_text('Trusted configuration', 'Доверенная конфигурация'), self.tr_text('Save local policy? Restart GUI/server to apply.', 'Сохранить локальную политику? Для применения перезапустите приложение.')) != QMessageBox.StandardButton.Yes:
                return
            save_config(self.config_path, config)
            QMessageBox.information(self, self.tr_text('Saved', 'Сохранено'), self.tr_text('Restart GUI and server to apply configuration', 'Перезапустите приложение для применения настроек'))
        except Exception:
            QMessageBox.warning(self, self.tr_text('Configuration', 'Конфигурация'), self.tr_text('Invalid JSON/schema or file not writable', 'Неверный JSON, схема или файл недоступен для записи'))

    def show_legal(self):
        from github_ai_mcp.desktop.legal import legal_files
        from github_ai_mcp.desktop.runtime import program_root
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_text("GitHub-AI-MCP — Legal", "GitHub-AI-MCP — Лицензии"))
        dialog.resize(820, 620)
        layout = QVBoxLayout(dialog)
        selector = QComboBox()
        files = legal_files()
        for path in files:
            selector.addItem(path.relative_to(program_root()).as_posix(), str(path))
        layout.addWidget(selector)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        layout.addWidget(viewer)
        def read(index):
            if index >= 0:
                viewer.setPlainText(Path(selector.itemData(index)).read_text(encoding="utf-8", errors="replace"))
        selector.currentIndexChanged.connect(read)
        read(0)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText(self.tr_text("Close", "Закрыть"))
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    def dashboard_done(self, value):
        if "github_actor" in value:
            self.github_actor = value["github_actor"]
            import time
            self.last_github_check = time.monotonic()
            valid = bool(self.github_actor) and self.github_actor not in {"AUTH_REQUIRED", "GITHUB_ERROR", "VAULT_UNAVAILABLE", "RETRYABLE_ERROR", "RATE_LIMITED", "PERMISSION_DENIED"}
            note = self.tr_text("Verified account · credential from OS vault", "Аккаунт проверен · токен из защищённого хранилища ОС") if valid else self.tr_text("Account not verified; a saved token may be invalid or unavailable", "Аккаунт не проверен; сохранённый токен может быть недействителен или недоступен")
            self.github_label.setText("GitHub: " + self.github_actor + "\n" + note)
        if "services" in value:
            self.render_services(value["services"])

    def add_repository(self):
        from github_ai_mcp.config import Repository
        dialog = QDialog(self)
        dialog.setWindowTitle(self.action_buttons["add_repository"].text())
        form = QFormLayout(dialog)
        fields = {}
        for key, en, ru in [("name", "Repository owner/name", "Репозиторий владелец/имя"),
                            ("source", "HTTPS URL or absolute local path", "HTTPS URL или абсолютный локальный путь"),
                            ("author_name", "Authorized Git author name", "Имя автора Git"),
                            ("author_email", "Authorized Git author email", "Email автора Git")]:
            fields[key] = QLineEdit()
            form.addRow(self.tr_text(en, ru), fields[key])
        consent = QCheckBox(self.tr_text("I authorize this repository and author identity", "Я разрешаю доступ к репозиторию и использование указанного автора"))
        form.addRow(consent)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_text("Add", "Добавить"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_text("Close dialog", "Закрыть диалог"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted or not consent.isChecked():
            return
        try:
            name = fields["name"].text().strip()
            if name in self.service.config.repositories:
                raise ValueError("Repository already exists")
            config = self.service.config.model_copy(deep=True)
            if not fields["author_email"].text().strip():
                raise ValueError("Explicit author email required")
            config.repositories[name] = Repository(source=fields["source"].text().strip(),
                author_name=fields["author_name"].text().strip(), author_email=fields["author_email"].text().strip(), identity_authorized=True)
            config = Config.model_validate(config.model_dump())
            save_config(self.config_path, config)
            self.service.config = config
            self.service.policy.config = config
            self.settings.setPlainText(json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2))
            self.repo.addItem(name)
            self.repo.setCurrentText(name)
            self.translate()
        except (ValueError, OSError):
            QMessageBox.warning(self, "GitHub-AI-MCP", self.tr_text("Invalid repository or identity, duplicate name, or configuration not writable.", "Неверный репозиторий или автор, имя уже существует либо настройки недоступны для записи."))

    def safe_diagnostics(self):
        from github_ai_mcp.desktop import startup
        status = self.supervisor.status()
        # No raw stderr/error text in exports; stable states and observations only.
        services = {name: {key: value for key, value in item.items() if key != "error"}
                    for name, item in status.items()}
        registration = startup.status(self.config_path)
        return {"services": services, "startup": {key: value for key, value in registration.items() if key != "error"}}

    def render_services(self, status):
        previous = getattr(self, "latest_service_status", {})
        self.latest_service_status = status
        if self.service.config.critical_notifications and QSystemTrayIcon.isSystemTrayAvailable():
            for name, item in status.items():
                if item["state"] in {"Failed", "Degraded"} and previous.get(name, {}).get("state") != item["state"]:
                    self.tray.showMessage("GitHub-AI-MCP", name + ": " + item["state"], QSystemTrayIcon.MessageIcon.Warning)
        if self.nav.currentRow() == 5 and self.advanced.isChecked():
            self.display(status)
        self.health_summary.setText("MCP: " + self.tr_text(status["mcp"]["state"], {"Running": "Работает", "Starting": "Запускается", "Stopped": "Остановлен", "Failed": "Ошибка"}.get(status["mcp"]["state"], status["mcp"]["state"]))
            + " · " + self.tr_text("Optional tunnel", "Необязательный туннель") + ": "
            + self.tr_text(status["tunnel"]["state"], {"Not configured": "Не настроен", "Running": "Процесс работает, подключение не проверено", "Stopped": "Остановлен", "Starting": "Запускается", "Failed": "Ошибка", "Running, connection unverified": "Процесс работает, соединение не проверено", "External process detected, ownership unverified": "Внешний процесс, не управляется", "Reconnecting": "Повторный запуск", "Degraded": "Нарушена работа"}.get(status["tunnel"]["state"], status["tunnel"]["state"])))
        states = {"Running, connection unverified": "Процесс работает, соединение не проверено", "External process detected, ownership unverified": "Найден внешний процесс, не управляется", "Reconnecting": "Повторный запуск", "Degraded": "Нарушена работа", "Running": "Работает", "Starting": "Запускается", "Stopped": "Остановлен", "Failed": "Ошибка", "Not configured": "Не настроен"}
        for name, label in self.service_labels.items():
            item = status[name]
            state = item["state"] if self.language_selector.currentText() == "en" else states.get(item["state"], item["state"])
            detail = item.get("endpoint", item.get("profile", ""))
            if name == "tunnel" and item["process_alive"]:
                detail += " · " + self.tr_text("connection unverified", "соединение не подтверждено")
            if name == "tunnel" and item.get("observations"):
                observation = item["observations"]
                verified = observation.get("mcp") == observation.get("control-plane") == "Recent successful observation"
                detail += " · " + self.tr_text("recent local evidence verified" if verified else "local evidence unverified",
                                               "есть свежие локальные подтверждения" if verified else "локальные подтверждения не получены")
            error = item["error"]
            errors = {"Service exited unexpectedly": "Процесс службы неожиданно завершился. Проверьте журнал, клиент и профиль.",
                      "Owned process is alive but authenticated health verification failed; check service logs": "Процесс работает, но защищённая проверка MCP не прошла. Проверьте журнал.",
                      "Port occupied by an external instance; this controller does not own it": "Порт занят чужим процессом. Измените порт или остановите процесс в его приложении."}
            if self.language_selector.currentText() == "ru":
                error = errors.get(error, error)
            text = (f"{'MCP' if name == 'mcp' else self.tr_text('Optional tunnel', 'Необязательный туннель')}: {state} · {detail}"
                    + ("\n" + error if error else ""))
            if label.text() != text:
                label.setText(text)
            for action in ("start", "stop", "restart"):
                button = self.service_button_names[f"{name}_{action}"]
                enabled = not self.service_busy and (not item["process_alive"] if action == "start" else item["process_alive"] and item.get("owned", False))
                if name == "tunnel" and item["state"] in {"Not configured", "External process detected, ownership unverified"}:
                    enabled = False
                if button.isEnabled() != enabled:
                    button.setEnabled(enabled)
                tip = self.tr_text(f"{action.capitalize()} the {name} service. Only owned processes are controlled.", f"Служба {name}: {button.text().lower()}. Управление только собственными процессами.")
                if not enabled:
                    if self.service_busy:
                        tip += "\n" + self.tr_text("Wait for the service operation.", "Дождитесь операции со службой.")
                    elif item["state"] == "Not configured":
                        tip += "\n" + self.tr_text("Select the official tunnel client in setup.", "Выберите официальный клиент туннеля в настройке запуска.")
                    else:
                        tip += "\n" + self.tr_text("The service is already running." if action == "start" else "The service is stopped.", "Служба уже запущена." if action == "start" else "Служба остановлена.")
                button.setToolTip(tip)

    def service_work(self, fn, quiet=False):
        if self.service_busy:
            return
        self.service_busy = True
        if not quiet:
            self.service_generation += 1
            for button, _ in self.service_buttons:
                button.setEnabled(False)
            self.stop_all_button.setEnabled(False)
        task = Task(fn)
        # Separate from Git tasks; the supervisor serializes lifecycle changes.
        self.service_task = task
        def finish(value):
            self.service_busy = False
            if not quiet:
                self.stop_all_button.setEnabled(True)
            self.render_services(value)
            if "github_actor" in value:
                self.dashboard_done(value)
        def failed(error):
            self.service_busy = False
            self.poll_services()
            if not quiet:
                QMessageBox.warning(self, "GitHub-AI-MCP", error)
        task.signals.done.connect(finish)
        task.signals.failed.connect(failed)
        self.pool.start(task)

    def control_service(self, action, name=None):
        self.service_work(lambda: getattr(self.supervisor, action)(name) if name else self.supervisor.stop_all())

    def poll_services(self):
        if self.poll_busy or self.service_busy or self.exiting:
            return
        self.poll_busy = True
        generation = self.service_generation
        task = Task(self.supervisor.poll)
        self.poll_task = task
        def done(status):
            self.poll_busy = False
            if generation == self.service_generation and not self.service_busy and not self.exiting:
                self.render_services(status)
        def failed(error):
            self.poll_busy = False
            self.statusBar().showMessage(error)
        task.signals.done.connect(done)
        task.signals.failed.connect(failed)
        self.pool.start(task)

    def setup(self):
        from github_ai_mcp.desktop.setup import Setup
        self.service.config.locale = self.language_selector.currentText()
        dialog = Setup(self.service.config, self.config_path, self.pool, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings.setPlainText(json.dumps(self.service.config.model_dump(mode="json"), ensure_ascii=False, indent=2))
            self.service_work(self.supervisor.reload_config)
            self.translate()

    def startup(self):
        from github_ai_mcp.desktop.runtime import bundled_tool
        if not self.service.config.setup_complete:
            self.setup()
        if self.service.config.setup_complete and self.service.config.autostart_services:
            def start():
                for name, enabled in (("mcp", self.service.config.start_mcp),
                                      ("tunnel", self.service.config.start_tunnel and bool(self.service.config.tunnel_client or bundled_tool("tunnel-client")))):
                    if enabled:
                        try:
                            self.supervisor.start(name)
                        except AppError:
                            pass  # Each service retains its error; optional failure never crashes GUI.
                return self.supervisor.status()
            self.service_work(start)

    def exit_application(self):
        if self.tasks or self.service_busy or self.poll_busy:
            QMessageBox.information(self, "GitHub-AI-MCP", self.tr_text("Wait for the current operation, then exit", "Дождитесь операции, затем закройте приложение"))
            return
        self.timer.stop()
        self.exiting = True
        self.setEnabled(False)
        task = Task(self.supervisor.stop_all)
        self.exit_task = task
        def finished(_):
            self.tray.hide()
            self.close()
            cast(QApplication, QApplication.instance()).quit()
        def failed(error):
            self.exiting = False
            self.setEnabled(True)
            self.timer.start()
            QMessageBox.warning(self, "GitHub-AI-MCP", error)
        task.signals.done.connect(finished)
        task.signals.failed.connect(failed)
        self.pool.start(task)

    def closeEvent(self, event):
        if self.exiting:
            event.accept()
            return
        if self.service.config.background_on_close and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        elif self.tasks or self.service_busy or self.poll_busy:
            event.ignore()
            self.statusBar().showMessage(self.tr_text("Wait for operation", "Дождитесь операции"))
        else:
            event.ignore()
            self.exit_application()


def run(service, config_path):
    from github_ai_mcp.core.locking import lock
    app = cast(QApplication, QApplication.instance() or QApplication(sys.argv))
    app.setQuitOnLastWindowClosed(False)
    try:
        with lock(service.config.data_dir / "locks", "desktop-controller"):
            window = Window(service, config_path, bootstrap=True)
            if service.config.minimize_on_startup and QSystemTrayIcon.isSystemTrayAvailable():
                window.hide()
            else:
                window.show()
            try:
                app.exec()
            finally:
                window.supervisor.stop_all()
    except AppError as error:
        QMessageBox.warning(None, "GitHub-AI-MCP", str(error))
