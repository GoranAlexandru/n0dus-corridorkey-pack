"""Windows-only GPU/process helpers for ck_run.py (ctypes, no extra packages).

- gpu_info(): card name and total/used/free memory from nvidia-smi.
- process_gpu_memory(pids): this process tree's Dedicated and Shared GPU
  memory from the Windows performance counters ("GPU Process Memory"), the
  same numbers Task Manager shows. Shared growth = spill into system RAM.
- descendants(pid) / kill_tree(pid): whole process tree.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
from pathlib import Path

GiB = 1024 ** 3
CREATE_NO_WINDOW = 0x08000000
_SYS32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
# pack: Windows/NVIDIA tools by full path where Windows keeps them
NVIDIA_SMI = str(_SYS32 / "nvidia-smi.exe") if (_SYS32 / "nvidia-smi.exe").is_file() else "nvidia-smi"
TASKKILL = str(_SYS32 / "taskkill.exe") if (_SYS32 / "taskkill.exe").is_file() else "taskkill"


# ---------------------------------------------------------------- nvidia-smi
def gpu_info(index: int = 0) -> dict | None:
    try:
        out = subprocess.run(
            [NVIDIA_SMI, f"--id={index}", "--query-gpu=name,memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW).stdout
        name, total, used, free = [x.strip() for x in out.strip().split(",")]
        return {"name": name, "total_gib": int(total) / 1024, "used_gib": int(used) / 1024,
                "free_gib": int(free) / 1024}
    except Exception:
        return None


# ---------------------------------------------------------------- processes
class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
_k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_k32.CloseHandle.argtypes = [wt.HANDLE]


def _parent_map() -> dict[int, int]:
    snap = _k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    out = {}
    try:
        e = _PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = _k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out[e.th32ProcessID] = e.th32ParentProcessID
            ok = _k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        _k32.CloseHandle(snap)
    return out


def descendants(pid: int) -> set[int]:
    parents = _parent_map()
    tree, frontier = {pid}, {pid}
    while frontier:
        frontier = {c for c, p in parents.items() if p in frontier and c not in tree}
        tree |= frontier
    return tree & (set(parents) | {pid})


_k32.GetFileType.argtypes = [wt.HANDLE]
_k32.PeekNamedPipe.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p,
                               ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
_FILE_TYPE_PIPE = 3


def watch_stdin_pipe(on_line, stop) -> bool:
    """Call on_line(text) for each line arriving on stdin, WITHOUT ever blocking in
    a read: the pipe is polled with PeekNamedPipe and only bytes already waiting
    are read. A thread parked in a blocking ReadFile on the stdin pipe made the
    first load of OpenCV's native code hang in every other thread (reproduced:
    app_test\\repro_stdin_variants.py). Returns False when stdin is not a pipe
    (a console: use Ctrl+C; a file or nothing: no stdin cancel)."""
    import msvcrt
    import os
    import sys
    import threading
    import time
    try:
        fd = sys.stdin.fileno()
        h = msvcrt.get_osfhandle(fd)
    except (AttributeError, OSError, ValueError):
        return False
    if _k32.GetFileType(h) != _FILE_TYPE_PIPE:
        return False

    def poll():
        buf = b""
        while not stop.is_set():
            avail = wt.DWORD(0)
            if not _k32.PeekNamedPipe(h, None, 0, None, ctypes.byref(avail), None):
                return  # writer closed the pipe: no more commands can arrive
            if avail.value:
                buf += os.read(fd, avail.value)  # never blocks: these bytes are already there
                *lines, buf = buf.split(b"\n")
                for ln in lines:
                    on_line(ln.decode("utf-8", "replace").strip())
            time.sleep(0.2)
    threading.Thread(target=poll, daemon=True).start()
    return True


def kill_tree(pid: int) -> None:
    subprocess.run([TASKKILL, "/PID", str(pid), "/T", "/F"], capture_output=True, stdin=subprocess.DEVNULL,
                   creationflags=CREATE_NO_WINDOW)


# ---------------------------------------------------------------- PDH counters
_pdh = ctypes.WinDLL("pdh")
_PDH_MORE_DATA = 0x800007D2
_PDH_FMT_LARGE = 0x00000400


class _FMTVALUE(ctypes.Structure):
    _fields_ = [("CStatus", wt.DWORD), ("largeValue", ctypes.c_longlong)]


class _ITEM(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", _FMTVALUE)]


for _f in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData",
           "PdhGetFormattedCounterArrayW", "PdhCloseQuery"):
    getattr(_pdh, _f).restype = ctypes.c_ulong


def _counter_array(query, counter) -> dict[str, int]:
    size, count = wt.DWORD(0), wt.DWORD(0)
    rc = _pdh.PdhGetFormattedCounterArrayW(counter, _PDH_FMT_LARGE, ctypes.byref(size),
                                           ctypes.byref(count), None)
    if rc != _PDH_MORE_DATA:
        return {}
    buf = ctypes.create_string_buffer(size.value)
    rc = _pdh.PdhGetFormattedCounterArrayW(counter, _PDH_FMT_LARGE, ctypes.byref(size),
                                           ctypes.byref(count), buf)
    if rc != 0:
        return {}
    items = ctypes.cast(buf, ctypes.POINTER(_ITEM))
    return {items[i].szName: items[i].FmtValue.largeValue for i in range(count.value)}


def process_gpu_memory(pids: set[int]) -> tuple[float, float] | None:
    """(dedicated_gib, shared_gib) summed over `pids`, or None if unreadable.

    A fresh query per call: wildcard instances are enumerated when the counter
    is added, and the job's GPU process appears only after the query starts.
    """
    q = wt.HANDLE()
    if _pdh.PdhOpenQueryW(None, 0, ctypes.byref(q)) != 0:
        return None
    try:
        cd, cs = wt.HANDLE(), wt.HANDLE()
        if (_pdh.PdhAddEnglishCounterW(q, r"\GPU Process Memory(*)\Dedicated Usage", 0, ctypes.byref(cd))
                or _pdh.PdhAddEnglishCounterW(q, r"\GPU Process Memory(*)\Shared Usage", 0, ctypes.byref(cs))
                or _pdh.PdhCollectQueryData(q)):
            return None
        tot = []
        for c in (cd, cs):
            s = 0
            for name, v in _counter_array(q, c).items():
                # instance names look like pid_1234_luid_0x..._phys_0
                if name.startswith("pid_"):
                    try:
                        if int(name.split("_")[1]) in pids:
                            s += v
                    except ValueError:
                        pass
            tot.append(s / GiB)
        return tot[0], tot[1]
    finally:
        _pdh.PdhCloseQuery(q)
