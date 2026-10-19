import sys
from pathlib import Path


def main():
    from multiprocessing import freeze_support
    freeze_support()
    from github_ai_mcp.desktop.runtime import initialize_runtime
    initialize_runtime()
    from github_ai_mcp.desktop.streams import prepare_streams
    internal = "--internal-server" in sys.argv[1:]
    cli = "--cli" in sys.argv[1:]

    service = internal or "serve" in sys.argv[1:]
    prepare_streams(require_input=service and "streamable-http" not in sys.argv)
    if service or cli:
        if internal:
            sys.argv.remove("--internal-server")
        if cli:
            sys.argv.remove("--cli")
        from github_ai_mcp.cli.app import main as cli_main
        cli_main()
        return
    from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout
    from github_ai_mcp.config import Config, load_config, resolve_config, save_config
    from github_ai_mcp.core.job_engine import Service
    from github_ai_mcp.gui.app import run
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("GitHub-AI-MCP")
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=Path)
    args, _ = parser.parse_known_args()
    path = resolve_config(args.config)
    if not path.exists():
        try:
            save_config(path, Config())
        except OSError:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(None, "GitHub-AI-MCP", "Configuration is not writable / Конфигурация недоступна для записи")
            return
    while True:
        try:
            config = load_config(path)
            break
        except (ValueError, OSError):
            dialog = QDialog()
            dialog.setWindowTitle("GitHub-AI-MCP — Configuration / Конфигурация")
            dialog.resize(720, 550)
            layout = QVBoxLayout(dialog)
            info = QLabel("Invalid configuration. Edit and save, or cancel.\nНеверная конфигурация. Исправьте и сохраните либо отмените.")
            layout.addWidget(info)
            editor = QPlainTextEdit()
            try:
                editor.setPlainText(path.read_text(encoding="utf-8"))
            except OSError:
                pass
            layout.addWidget(editor)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            def save():
                try:
                    config = Config.model_validate_json(editor.toPlainText())
                    save_config(path, config)
                    dialog.accept()
                except (ValueError, OSError):
                    info.setText("Invalid schema or file not writable / Неверная схема или файл недоступен")
            buttons.accepted.connect(save)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
    run(Service(config), path)


if __name__ == "__main__":
    main()
