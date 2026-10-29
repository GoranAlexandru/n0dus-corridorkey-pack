"""Where everything lives in an installed CorridorKey Pack, and the clean
environment every process runs in. (Pack-only file; see docs/CHANGES_FROM_REFERENCE.md.)

Layout (PACK_PLAN.md 9.1): CorridorKey at ROOT, our app in ROOT\\app, the private
Python in ROOT\\python, ffmpeg in ROOT\\ffmpeg\\bin, user state in ROOT\\data,
temp + caches in ROOT\\tmp and ROOT\\.cache.

apply() scrubs THIS process's environment, so every child (runner, CorridorKey,
ffmpeg, nvidia-smi) inherits the clean one:
  * PYTHONPATH / PYTHONHOME / every PYTHON* / CONDA_* / VIRTUAL_ENV removed,
    PYTHONNOUSERSITE=1 (the Anaconda trap, SETUP_RECIPE.md "Install" step 2);
  * PATH cut to Windows' own folders + the private Python: nothing from Anaconda
    or another CUDA install can be picked up;
  * TEMP/TMP, Hugging Face, torch and the NVIDIA shader cache inside ROOT;
  * offline flags; CUDA_DEVICE_ORDER=PCI_BUS_ID so GPU 0 means the same card to
    nvidia-smi (which the planner reads) and to PyTorch (which runs the job).
Child Pythons are also always started with -I (python_cmd()).
"""
from __future__ import annotations

import os
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
PY = ROOT / "python" / "python.exe"
PYW = ROOT / "python" / "pythonw.exe"
FFMPEG = ROOT / "ffmpeg" / "bin" / "ffmpeg.exe"
FFPROBE = ROOT / "ffmpeg" / "bin" / "ffprobe.exe"
DATA = ROOT / "data"
LOGS = DATA / "logs"
SETTINGS = DATA / "settings.json"
SELFTEST_JSON = DATA / "install" / "selftest.json"
TMP = ROOT / "tmp"
CACHE = ROOT / ".cache"
LICENCES = ROOT / "licences"
MUTEX_NAME = "CorridorKeyPack.App"   # installer/corridorkey.iss AppMutex uses the same name

_SYS = os.environ.get("SystemRoot", r"C:\Windows")
_STRIP_PREFIXES = ("PYTHON", "CONDA", "VIRTUAL_ENV", "PIP_")


def _tool(name: str) -> str:
    """A Windows tool by full path when it is where Windows keeps it."""
    for d in (Path(_SYS) / "System32", Path(r"C:\Program Files\NVIDIA Corporation\NVSMI")):
        if (d / name).is_file():
            return str(d / name)
    return name


NVIDIA_SMI = _tool("nvidia-smi.exe")
TASKKILL = _tool("taskkill.exe")


def apply() -> None:
    env = os.environ
    for k in list(env):
        if k.upper().startswith(_STRIP_PREFIXES):
            del env[k]
    temp = TMP / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    path = [str(Path(_SYS) / "System32"), _SYS, str(Path(_SYS) / "System32" / "Wbem"), str(PY.parent)]
    nvsmi = Path(r"C:\Program Files\NVIDIA Corporation\NVSMI")
    if nvsmi.is_dir():
        path.append(str(nvsmi))
    env.update({
        "PATH": os.pathsep.join(path),
        "PYTHONNOUSERSITE": "1",
        "PYTHONIOENCODING": "utf-8",
        "TEMP": str(temp), "TMP": str(temp),
        "HF_HOME": str(CACHE / "huggingface"),
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
        "TORCH_HOME": str(CACHE / "torch"),
        "XDG_CACHE_HOME": str(CACHE),
        "CUDA_CACHE_PATH": str(CACHE / "nv"),
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "OPENCV_IO_ENABLE_OPENEXR": "1",
    })


def python_cmd(script, *args, windowed: bool = False) -> list[str]:
    """Command line for a child Python: the private interpreter, isolated (-I)."""
    return [str(PYW if windowed else PY), "-I", str(script), *map(str, args)]


def inside_install(path) -> bool:
    """True if `path` is the install folder or anything under it. Output must
    never go there: an upgrade or uninstall replaces that folder."""
    try:
        p = Path(path).resolve()
    except OSError:
        return False
    root = ROOT.resolve()
    return p == root or root in p.parents


_mutex = None


def hold_single_instance_marker() -> None:
    """A named mutex the installer's AppMutex looks for, so an upgrade/uninstall
    asks the user to close CorridorKey first. Several processes may hold it."""
    global _mutex
    try:
        import ctypes
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    except Exception:
        _mutex = None
