"""Qt workers keep subprocess and network operations off the GUI thread."""
from PySide6.QtCore import QObject, QRunnable, Signal

from github_ai_mcp.exceptions import AppError


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = Signals()

    def run(self):
        try:
            self.signals.done.emit(self.fn())
        except AppError as error:
            self.signals.failed.emit(error.code + ": " + str(error))
        except Exception:
            self.signals.failed.emit("Operation failed; inspect configuration and diagnostics")
        finally:
            self.fn = None  # Release closures that may hold credentials.
