"""Run upstream infer.py UNCHANGED, adding machine-readable progress.

Launched by ck_run.py, never by hand. Upstream prints a line per finished
stage-1 window but nothing during stage 2, so this patches the video writers
at runtime (no upstream file is modified) to report frames written, and
reports PyTorch's peak memory at exit. Its own lines start with "CKSHIM ".
"""
import atexit
import json
import runpy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import torch  # noqa: E402

import corridorkey.runtime as rt  # noqa: E402


def emit(**kv):
    print("CKSHIM " + json.dumps(kv), flush=True)


_counts = {}


def _counting(orig):
    def write_many(self, frames):
        r = orig(self, frames)
        _counts[id(self)] = _counts.get(id(self), 0) + len(frames)
        emit(frames_written=min(_counts.values()))
        return r
    return write_many


rt.ThreadedVideoWriter.write_many = _counting(rt.ThreadedVideoWriter.write_many)
rt.ExrSequenceWriter.write_many = _counting(rt.ExrSequenceWriter.write_many)  # still/sequence jobs
_t0 = time.perf_counter()


@atexit.register
def _peak():
    if torch.cuda.is_available() and torch.cuda.is_initialized():
        emit(torch_peak_allocated_gib=round(torch.cuda.max_memory_allocated() / 2**30, 3),
             torch_peak_reserved_gib=round(torch.cuda.max_memory_reserved() / 2**30, 3),
             wall_s=round(time.perf_counter() - _t0, 2))


sys.argv = [str(ROOT / "infer.py")] + sys.argv[1:]
runpy.run_path(str(ROOT / "infer.py"), run_name="__main__")
