"""Pick the Hann window for a clip from the card's memory, without torch.

The estimate is UPSTREAM's own: `_VRAM_PEAK_GB`, `_interp` and
`estimate_peak_vram_gb` are read out of corridorkey/runtime.py with `ast` and
executed as-is, so a table update upstream is picked up automatically.

Upstream's estimate is what tensors ALLOCATE. On this Windows machine the
process actually holds more (PyTorch's caching allocator reserves on top, plus
the CUDA context), so the need is scaled by OVERHEAD, measured 2026-10-28 on
holla_idle7 (1280x1664 padded = 2.13 MP, 97 frames, low_vram):

    window  upstream estimate  measured process GPU memory  ratio
    80/40   19.84 GiB          27.26 GiB (22.68 ded + 4.58 shared)  1.374
    48/24   12.77 GiB          17.29 GiB (dedicated, no spill)      1.354

    need_gib = estimate_gib * OVERHEAD          OVERHEAD = 1.40
    fits  <=>  need_gib <= budget_gib - MARGIN_GIB     MARGIN_GIB = 1.0
    budget_gib = free memory now (nvidia-smi), or min(cap, free) with --vram <GB>

1.40 is the larger measured ratio rounded up; MARGIN covers what other apps
may allocate while the clip runs. A spill during the run still steps down.
"""
from __future__ import annotations

import ast
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "corridorkey" / "runtime.py"
OVERHEAD = 1.40
MARGIN_GIB = 1.0
WINDOWS = ((80, 40), (48, 24), (24, 12), (8, 4), (1, 1))   # always --low_vram

_ns: dict = {}


def _load():
    if _ns:
        return _ns
    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"))
    quantum = 128
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_VRAM_PEAK_GB" for t in node.targets):
            _ns["_VRAM_PEAK_GB"] = ast.literal_eval(node.value)
        if (isinstance(node, ast.ClassDef) and node.name == "InferenceConfig"):
            for st in node.body:
                if isinstance(st, ast.AnnAssign) and getattr(st.target, "id", "") == "shape_quantum":
                    quantum = ast.literal_eval(st.value)
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in ("_interp", "estimate_peak_vram_gb")]
    if "_VRAM_PEAK_GB" not in _ns or len(funcs) != 2:
        raise RuntimeError("could not read the VRAM table from corridorkey/runtime.py")
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(RUNTIME), "exec"), _ns)
    _ns["quantum"] = quantum
    return _ns


def padded_hw(h: int, w: int) -> tuple[int, int]:
    q = _load()["quantum"]
    return math.ceil(h / q) * q, math.ceil(w / q) * q


def need_gib(megapixels: float, frames: int, chunk: int) -> tuple[float, float]:
    est = _load()["estimate_peak_vram_gb"](megapixels, min(chunk, frames), True)
    return est, est * OVERHEAD


def probe_clip(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,nb_frames,r_frame_rate", "-of", "default=nw=1", path],
        capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
        creationflags=0x08000000).stdout
    kv = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
    if "width" not in kv:
        raise ValueError(f"not a readable video: {path}")
    frames = int(kv["nb_frames"]) if kv.get("nb_frames", "N/A").isdigit() else None
    if frames is None:  # some containers carry no frame count: count packets
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                              "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL,
                             creationflags=0x08000000).stdout
        frames = int(out.strip())
    return {"width": int(kv["width"]), "height": int(kv["height"]), "frames": frames}


def plan(gpu: dict, vram: str, clip: dict) -> dict:
    """Largest window whose scaled estimate fits. Raises nothing; result has
    ok=False plus a plain-language `message` when nothing fits."""
    ph, pw = padded_hw(clip["height"], clip["width"])
    mp = ph * pw / 1e6
    card = f"{gpu['name']} {round(gpu['total_gib'])} GB"
    if vram == "auto":
        budget, how = gpu["free_gib"], f"auto: {gpu['free_gib']:.1f} GB free"
    else:
        cap = float(vram)
        budget = min(cap, gpu["free_gib"])
        how = f"capped at {cap:g} GB" + (f" (only {gpu['free_gib']:.1f} GB free)" if cap > gpu["free_gib"] else "")
    usable = budget - MARGIN_GIB
    tried = []
    for chunk, stride in WINDOWS:
        est, need = need_gib(mp, clip["frames"], chunk)
        tried.append({"window": f"{chunk}/{stride}", "estimate_gib": round(est, 2), "need_gib": round(need, 2)})
        if need <= usable:
            # A clip shorter than the window runs as one window over all its frames
            # (a still: 1/1). Report what will actually run.
            c_eff = min(chunk, clip["frames"])
            s_eff = max(1, min(stride, c_eff // 2 or 1))
            return {"ok": True, "chunk": c_eff, "stride": s_eff, "card": card, "budget_gib": round(budget, 2),
                    "usable_gib": round(usable, 2), "how": how, "padded": f"{pw}x{ph}", "megapixels": round(mp, 2),
                    "need_gib": round(need, 2), "tried": tried,
                    "summary": f"{card} ({how}) -> {c_eff}/{s_eff}"}
    # Nothing fits: say what would.
    smallest_need = tried[-1]["need_gib"]
    floor_need = need_gib(0.0, 1, 1)[1]  # the table floors at its smallest row
    if floor_need > usable:
        fit = (f"Nothing fits: even a tiny clip needs about {floor_need + MARGIN_GIB:.1f} GB free "
               f"on this machine.")
    else:
        lo, hi = 0.0, mp
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if need_gib(mid, 1, 1)[1] <= usable else (lo, mid)
        s = math.sqrt(lo / mp)
        fit = (f"At this card's memory, clips up to about {int(clip['width'] * s)}x{int(clip['height'] * s)} "
               f"({lo:.1f} MP) would fit with the 1/1 window.")
    msg = (f"Not enough GPU memory: {card}, {how}, {usable:.1f} GB usable after a {MARGIN_GIB:g} GB margin. "
           f"This clip is {clip['width']}x{clip['height']} (model size {pw}x{ph}, {mp:.2f} MP) and even the "
           f"smallest window (1/1) needs about {smallest_need:.1f} GB. {fit}")
    return {"ok": False, "card": card, "budget_gib": round(budget, 2), "usable_gib": round(usable, 2),
            "how": how, "padded": f"{pw}x{ph}", "megapixels": round(mp, 2), "tried": tried, "message": msg}
