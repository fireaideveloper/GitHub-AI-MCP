import ctypes
import io
import os
import sys
from typing import Any, cast


def inherited_stream(index, mode):
    if os.name != "nt":
        return None
    import msvcrt
    kernel = cast(Any, ctypes).WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
    kernel.GetStdHandle.restype = ctypes.c_void_p
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.DuplicateHandle.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32,
                                      ctypes.c_int, ctypes.c_uint32]
    handle = kernel.GetStdHandle(index & 0xffffffff)
    if not handle or handle == ctypes.c_void_p(-1).value:
        return None
    duplicate = ctypes.c_void_p()
    owner = kernel.GetCurrentProcess()
    if not kernel.DuplicateHandle(owner, handle, owner, ctypes.byref(duplicate), 0, False, 2):
        return None
    flags = (os.O_RDONLY if mode == "r" else os.O_WRONLY) | cast(Any, os).O_BINARY
    try:
        fd = cast(Any, msvcrt).open_osfhandle(duplicate.value, flags)
    except OSError:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(duplicate)
        return None
    return io.TextIOWrapper(os.fdopen(fd, mode + "b", buffering=0),
                            encoding="utf-8", errors="replace", write_through=True)


def prepare_streams(require_input=False):
    for name, index, mode in (("stdin", -10, "r"), ("stdout", -11, "w"), ("stderr", -12, "w")):
        if getattr(sys, name) is None:
            stream = inherited_stream(index, mode)
            if stream is None:
                if require_input and name in {"stdin", "stdout"}:
                    raise SystemExit("MCP stdio requires inherited input/output pipes")
                stream = open(os.devnull, mode, encoding="utf-8")
            setattr(sys, name, stream)
            setattr(sys, "__" + name + "__", stream)
