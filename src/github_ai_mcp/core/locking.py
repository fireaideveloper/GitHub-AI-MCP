import hashlib
import importlib
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from github_ai_mcp.exceptions import AppError


@contextmanager
def lock(root: Path, key: str):
    root.mkdir(parents=True, exist_ok=True)
    path = root / (hashlib.sha256(key.encode()).hexdigest() + ".lock")
    with path.open("a+b") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl = cast(Any, importlib.import_module("fcntl"))
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise AppError("BUSY", "An active operation owns this application lock. Wait for it to finish; a crashed owner releases the kernel lock automatically. Do not delete lock files.") from None
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl = cast(Any, importlib.import_module("fcntl"))
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
