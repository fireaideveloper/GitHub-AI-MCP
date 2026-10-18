import ctypes
import os
import subprocess
from typing import Any, cast
from ctypes import wintypes


def background_options(suspended=False) -> dict:
    return {"creationflags": 0x08000000 | (4 if suspended else 0)} if os.name == "nt" else {"start_new_session": True}


class ProcessTree:
    def __init__(self, process, suspended=False):
        self.process = process
        self.handle = None
        if os.name != "nt":
            return
        kernel = cast(Any, ctypes).WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]

        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t),
                        ("max_ws", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ["read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes"]]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                        ("peak_job", ctypes.c_size_t)]

        info = Extended()
        info.basic.flags = 0x2000
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise OSError("Cannot create Windows process job")
        if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle))):
            kernel.CloseHandle(handle)
            process.kill()
            process.wait(timeout=5)
            raise OSError("Cannot contain Windows service process")
        self.handle, self.kernel = handle, kernel
        if suspended:
            try:
                self._resume()
            except Exception:
                self.kill()
                process.wait(timeout=5)
                raise

    def _resume(self):
        class ThreadEntry(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                        ("id", wintypes.DWORD), ("owner", wintypes.DWORD),
                        ("base_priority", wintypes.LONG), ("delta", wintypes.LONG),
                        ("flags", wintypes.DWORD)]
        kernel = self.kernel
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenThread.restype = wintypes.HANDLE
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD
        snapshot = kernel.CreateToolhelp32Snapshot(4, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise OSError("Cannot inspect suspended service thread")
        entry = ThreadEntry()
        entry.size = ctypes.sizeof(entry)
        try:
            found = kernel.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.owner == self.process.pid:
                    thread = kernel.OpenThread(2, False, entry.id)
                    if not thread:
                        raise OSError("Cannot open owned service thread")
                    try:
                        if kernel.ResumeThread(thread) == 0xFFFFFFFF:
                            raise OSError("Cannot resume owned service thread")
                    finally:
                        kernel.CloseHandle(thread)
                    return
                found = kernel.Thread32Next(snapshot, ctypes.byref(entry))
            raise OSError("Owned service thread not found")
        finally:
            kernel.CloseHandle(snapshot)

    def kill(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        elif os.name != "nt":
            import signal
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif self.process.poll() is None:
            self.process.kill()

    def close(self):
        self.kill()


def run_background(*args, **kwargs):
    return cast(Any, subprocess.run)(*args, **background_options(), **kwargs)
