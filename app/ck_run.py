#!/usr/bin/env python3
"""CorridorKey runner: one input in, keyed outputs out.

  video (.mp4/.mov/.m4v)       -> <clip>_fg.mp4 + <clip>_alpha.mp4
  image (.png/.jpg/.jpeg)      -> <name>_key.png (RGBA, straight alpha) + <name>_alpha.png, window 1/1
  folder of numbered frames    -> <name>\\<name>_key_####.png + <name>_alpha_####.png (time-aware)
  PNGs are 8-bit, or 16-bit with --png16. Inputs that already have transparency
  are skipped (exit 4) unless --key_anyway.

Holds this machine's recipe (SETUP_RECIPE.md) so callers don't have to:
  * always --low_vram; window picked per clip from GPU memory (--vram auto|GB),
    stepped down automatically if the run spills into shared GPU memory;
  * default outputs only (alpha + fg mp4), never checker/cutout, despill off;
  * temp files inside the tool folder (tmp\\jobs\\<job>), partial outputs never
    reach the output folder;
  * fixes the mp4 colour tag (CorridorKey encodes BT.601, tags BT.709) without
    re-encoding, and checks the result;
  * Cancel = kill the whole process tree, delete partial outputs.

Machine-readable: every stdout line is one JSON event ({"event": ...}).
Cancel: write "cancel" on stdin, create the --cancel_file, or Ctrl+C.
Exit codes: 0 done, 1 error, 2 bad arguments, 3 cancelled, 4 skipped (has alpha),
5 not enough GPU memory.

usage: python\\python.exe -I app\\ck_run.py CLIP --out_dir DIR [--vram auto|GB]
       [--copy_original] [--overwrite] [--screen auto|green|blue] [--plan_only]
       [--png16] [--key_anyway] [--window C/S] [--cancel_file PATH]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
sys.path.insert(0, str(APP))

import ck_env  # noqa: E402  (pack: paths + clean environment, applied before anything runs)

ck_env.apply()
ck_env.hold_single_instance_marker()

import gpu_win  # noqa: E402
import stills  # noqa: E402
import vram_plan  # noqa: E402

PY = ck_env.PY
SHIM = APP / "ck_infer_shim.py"
JOBS = ck_env.TMP / "jobs"
LOGS = ck_env.LOGS

# Spill watchdog (docs: SETUP_RECIPE.md "GPU memory").
SAMPLE_S = 2.0
SHARED_GROWTH_GIB = 0.5     # shared above its post-load level = spilling
SPILL_SAMPLES = 3           # consecutive samples before acting
WATCH_FROM_GIB = 2.0        # reference shared level is taken once the model is on the GPU

# Progress weights per phase, from a timed 48/24 run on this machine (load 10 s,
# prepass 8 s, stage 1 46 s, stage 2 44 s, retag+move <1 s); ETA self-corrects.
WEIGHTS = {"load": 0.09, "prepass": 0.07, "stage1": 0.42, "stage2": 0.41, "finish": 0.01}
# A single still is dominated by model load (calibrated from a timed still run).
WEIGHTS_STILL = {"load": 0.60, "prepass": 0.15, "stage1": 0.12, "stage2": 0.08, "finish": 0.05}

# The BT.601 matrix (6 = SMPTE 170M) is what CorridorKey's writer actually
# uses; primaries (1 = BT.709) and transfer (13 = sRGB) are already true.
RETAG_BSF = ("h264_metadata=matrix_coefficients=6:colour_primaries=1:"
             "transfer_characteristics=13:video_full_range_flag=0")


class Cancelled(Exception):
    pass


class Spilled(Exception):
    pass


class JobError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Runner:
    def __init__(self, args):
        self.a = args
        self.cancel = threading.Event()
        self.job = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.jobdir = JOBS / self.job
        self.proc = None
        self.t0 = time.monotonic()
        self.log = None
        self.last_fraction = 0.0
        self.lock = threading.RLock()
        self.screen_flag = None
        self.weights = WEIGHTS
        self.placed = []   # final outputs already in the output folder

    # ------------------------------------------------------------ io
    def emit(self, event, **kv):
        rec = {"event": event, "t": round(time.monotonic() - self.t0, 2), **kv}
        line = json.dumps(rec, ensure_ascii=False)
        with self.lock:  # the child-output reader thread emits too
            try:
                print(line, flush=True)
            except (OSError, ValueError):
                pass  # caller went away (window closed): finish the job, the log still has it
        self.write_log("EVENT " + line)

    def write_log(self, text):
        with self.lock:
            if self.log and not self.log.closed:
                self.log.write(f"{dt.datetime.now():%H:%M:%S} {text}\n")
                self.log.flush()

    def watch_cancel(self):
        if self.a.cancel_file:
            def poll():
                while not self.cancel.is_set():
                    if os.path.exists(self.a.cancel_file):
                        self.cancel.set()
                    time.sleep(0.5)
            threading.Thread(target=poll, daemon=True).start()
        # Polled, never a blocking read: see gpu_win.watch_stdin_pipe for the hang
        # a blocked stdin reader caused. A console uses Ctrl+C instead.
        gpu_win.watch_stdin_pipe(lambda ln: ln.lower() == "cancel" and self.cancel.set(), self.cancel)

    # ------------------------------------------------------------ main
    def run(self) -> int:
        a = self.a
        src = Path(a.clip).resolve()
        out_dir = Path(a.out_dir).resolve()
        kind = stills.classify(src) if src.exists() else "missing"
        stem = src.name if kind == "sequence" else src.stem
        dests = {}
        LOGS.mkdir(parents=True, exist_ok=True)
        log_path = LOGS / f"{stem}_{self.job}.log"
        self.log = open(log_path, "w", encoding="utf-8")
        self.write_log(f"ck_run job {self.job}: {src} -> {out_dir} ({kind})")
        self.write_log("argv: " + json.dumps(sys.argv, ensure_ascii=False))
        try:
            ck_input, seq = src, None
            if kind == "missing":
                raise JobError("input_missing", f"Input not found: {src}")
            if kind == "unsupported":
                raise JobError("unsupported_input",
                               f"{src.name}: not supported. Use .mp4/.mov/.m4v video, .png/.jpg/.jpeg images, "
                               "or a folder of numbered .png/.jpg frames.")
            if kind == "video":
                try:
                    clip = vram_plan.probe_clip(str(src))
                except Exception as e:
                    raise JobError("input_unreadable", f"Cannot read the clip: {e}")
                dests = {"fg": out_dir / f"{stem}_fg.mp4", "alpha": out_dir / f"{stem}_alpha.mp4"}
                if a.copy_original:
                    dests["original"] = out_dir / src.name
            elif kind == "image":
                info = stills.probe_image(src)
                clip = {"width": info["width"], "height": info["height"], "frames": 1}
                if info["transparent"] and not a.key_anyway:
                    return self.skip(f"{src.name} already has transparency (an alpha channel that is not "
                                     "fully opaque). Skipped; tick 'Key anyway' / pass --key_anyway to key it "
                                     "(CorridorKey then ignores the existing alpha).", log_path)
                dests = {"key": out_dir / f"{stem}_key.png", "alpha": out_dir / f"{stem}_alpha.png"}
                if a.copy_original:
                    dests["original"] = out_dir / src.name
            else:  # sequence
                seq = stills.scan_sequence(src)
                info = stills.check_sequence_frames(seq["files"])
                clip = {"width": info["width"], "height": info["height"], "frames": len(seq["files"])}
                stem = seq["name"]
                if info["transparent_frames"] and not a.key_anyway:
                    return self.skip(f"{src.name}: frames already have transparency "
                                     f"({', '.join(info['transparent_frames'][:3])}). Skipped; tick 'Key anyway' "
                                     "/ pass --key_anyway to key them.", log_path)
                sub = out_dir / seq["name"]
                pad = seq["pad"]
                for i, n in enumerate(seq["numbers"]):
                    dests[f"key{i}"] = sub / f"{seq['name']}_key_{n:0{pad}d}.png"
                    dests[f"alpha{i}"] = sub / f"{seq['name']}_alpha_{n:0{pad}d}.png"
                if a.copy_original:
                    for i, p in enumerate(seq["files"]):
                        dests[f"orig{i}"] = sub / p.name
                if seq["gaps"]:
                    self.emit("warning", code="sequence_gaps",
                              message=f"{src.name}: numbering has gaps (e.g. before frame {seq['gaps'][0]}); "
                                      "CorridorKey treats the frames as consecutive.")
            self.weights = WEIGHTS_STILL if clip["frames"] == 1 else WEIGHTS
            gpu = gpu_win.gpu_info()
            if gpu is None:
                raise JobError("no_nvidia_gpu", "nvidia-smi did not report an NVIDIA GPU.")
            p = vram_plan.plan(gpu, a.vram, clip)
            self.write_log("plan: " + json.dumps(p))
            if a.window and p["ok"]:
                p["chunk"], p["stride"] = a.window
                p["summary"] = f"{p['card']} -> {a.window[0]}/{a.window[1]} (forced by --window)"
                self.write_log("window forced: " + p["summary"])
            if kind != "video" and a.copy_original and src.parent == out_dir:
                dests = {k: v for k, v in dests.items() if not k.startswith(("orig", "original"))}
            if kind == "video" and a.copy_original and src.parent == out_dir:
                dests.pop("original", None)  # the original is already there
            existing = [str(d) for d in dests.values() if d.exists()]
            self.emit("plan", clip=str(src), kind=kind, width=clip["width"], height=clip["height"],
                      frames=clip["frames"], **{k: v for k, v in p.items() if k != "tried"}, tried=p["tried"],
                      outputs=len(dests), existing=existing[:20], existing_count=len(existing))
            if not p["ok"]:
                self.emit("error", code="vram_insufficient", message=p["message"], log=str(log_path))
                return 5
            if a.plan_only:
                return 0
            if ck_env.inside_install(out_dir):
                raise JobError("output_inside_install",
                               f"The output folder {out_dir} is inside CorridorKey's own install folder "
                               f"({ck_env.ROOT}), which an update or uninstall replaces. Choose a folder "
                               "outside it.")
            if existing and not a.overwrite:
                raise JobError("output_exists", f"{len(existing)} output file(s) already exist (use --overwrite): "
                                                + ", ".join(existing[:5]))
            out_dir.mkdir(parents=True, exist_ok=True)
            self.sweep_stale_jobs()
            self.jobdir.mkdir(parents=True, exist_ok=True)
            (self.jobdir / "owner.pid").write_text(str(os.getpid()))
            self.emit("start", clip=str(src), kind=kind, out_dir=str(out_dir), job=self.job, log=str(log_path),
                      window=f"{p['chunk']}/{p['stride']}", summary=p["summary"])
            self.screen_note()
            self.watch_cancel()
            if kind == "image":   # CorridorKey reads folders, not single images: a 1-frame folder
                ck_input = self.jobdir / "input" / stem
                ck_input.mkdir(parents=True)
                shutil.copyfile(src, ck_input / f"000000{src.suffix.lower()}")
            elif kind == "sequence" and not seq["direct"]:
                ck_input = self.jobdir / "input" / stem
                self.write_log("sequence staged (folder holds other images, or sorted() order != frame order)")
                stills.stage_sequence(seq["files"], seq["ext"], ck_input)
            windows = [(p["chunk"], p["stride"])] + [w for w in vram_plan.WINDOWS if w[0] < p["chunk"]]
            cap = None if a.vram == "auto" else float(a.vram)
            result = None
            for attempt, (chunk, stride) in enumerate(windows, 1):
                try:
                    result = self.infer(ck_input, clip, chunk, stride, attempt, cap, gpu, exr=kind != "video")
                    break
                except Spilled as s:
                    nxt = windows[attempt] if attempt < len(windows) else None
                    self.emit("spill", window=f"{chunk}/{stride}", detail=str(s),
                              next_window=f"{nxt[0]}/{nxt[1]}" if nxt else None)
                    self.write_log(f"WINDOW {chunk}/{stride} spilled: {s}")
                    if not nxt:
                        raise JobError("spill_at_minimum",
                                       "Spilled into shared GPU memory even with the 1/1 window.")
            done = {}
            staged = result["files"]
            if kind == "video":
                self.phase("finish", 0.0, "fixing colour tags")
                for key in ("fg", "alpha"):
                    self.retag(staged[key])
                self.check_cancel()
                for key in ("fg", "alpha"):
                    self.place(staged[key], dests[key])
                    done[key] = str(dests[key])
                if "original" in dests:
                    self.copy_verified(src, dests["original"])
                    done["original_copy"] = str(dests["original"])
                extra = {"colour_tag": "BT.601 matrix, BT.709 primaries, sRGB transfer"}
            else:
                pngs = self.jobdir / "png"
                pngs.mkdir()
                bits = 16 if a.png16 else 8
                n = clip["frames"]
                keys = [k for k in dests if k.startswith("key")]
                alphas = [k for k in dests if k.startswith("alpha")]
                # Parallel: EXR decode, the sRGB maths and PNG encode release the GIL.
                with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
                    futs = [pool.submit(stills.exr_to_png, fg_exr, a_exr, pngs / dests[keys[i]].name,
                                        pngs / dests[alphas[i]].name, bits)
                            for i, (fg_exr, a_exr) in enumerate(zip(staged["fg"], staged["alpha"]))]
                    for done_n, f in enumerate(as_completed(futs), 1):
                        f.result()
                        if self.cancel.is_set():
                            for g in futs:
                                g.cancel()
                            raise Cancelled()
                        self.phase("finish", done_n / n, f"writing PNG {done_n}/{n}")
                for k in keys + alphas:
                    self.check_cancel()
                    dests[k].parent.mkdir(parents=True, exist_ok=True)
                    self.place(pngs / dests[k].name, dests[k])
                origs = [k for k in dests if k.startswith(("orig", "original"))]
                for k in origs:
                    s = src if kind == "image" else seq["files"][int(k[4:])]
                    self.copy_verified(s, dests[k])
                if kind == "image":
                    done = {"key": str(dests["key"]), "alpha": str(dests["alpha"])}
                    if origs:
                        done["original_copy"] = str(dests["original"])
                else:
                    done = {"folder": str(out_dir / seq["name"]), "key_first": dests[keys[0]].name,
                            "key_last": dests[keys[-1]].name, "originals_copied": len(origs)}
                extra = {"png_bits": bits, "alpha_mode": "straight (not premultiplied)",
                         "colour": "fg converted scene-linear -> sRGB (IEC 61966-2-1), as the video route"}
            elapsed = time.monotonic() - self.t0
            self.emit("progress", fraction=1.0, eta_s=0, phase="finish", detail="done")
            fields = {"kind": kind, "frames": clip["frames"], "window": result["window"],
                      "attempts": result["attempt"], "seconds": round(elapsed, 1),
                      "inference_s": result["inference_s"],
                      "s_per_frame": round(result["inference_s"] / clip["frames"], 3),
                      "peak_dedicated_gib": result["peak_dedicated"], "peak_shared_gib": result["peak_shared"],
                      "torch": result.get("torch"), "log": str(log_path)}
            clash = (set(done) & set(extra)) | (set(done) & set(fields)) | (set(extra) & set(fields))
            if clash:  # a key collision once crashed AFTER outputs were placed; fail loudly in testing instead
                raise JobError("internal", f"done-event field collision: {sorted(clash)}")
            self.emit("done", **fields, **done, **extra)
            return 0
        except (Cancelled, KeyboardInterrupt):
            self.kill()
            removed = self.cleanup_partials(dests)
            self.emit("cancelled", removed=removed, log=str(log_path))
            return 3
        except (JobError, stills.StillError) as e:
            self.kill()
            self.cleanup_partials(dests)
            self.emit("error", code=e.code, message=str(e), log=str(log_path), written=self.placed)
            return 1
        except Exception as e:  # never die silently
            self.kill()
            self.cleanup_partials(dests)
            self.emit("error", code="internal", message=f"{type(e).__name__}: {e}", log=str(log_path),
                      written=self.placed)
            return 1
        finally:
            if self.jobdir.exists() and not self.remove_jobdir():
                self.write_log(f"temp folder left behind (locked): {self.jobdir}")
            if self.log:
                self.log.close()

    # ------------------------------------------------------------ pieces
    def screen_note(self):
        text = (ROOT / "infer.py").read_text(encoding="utf-8")
        flag = re.search(r'"(--screen[_a-z]*)"', text)
        self.screen_flag = flag.group(1) if flag else None
        if self.a.screen != "auto" and not self.screen_flag:
            self.emit("warning", code="screen_colour_unsupported",
                      message=f"--screen {self.a.screen} ignored: CorridorKey's CLI has no screen-colour option; "
                              "the model finds the subject itself. Despill (green-only) is disabled anyway.")

    def skip(self, message, log_path) -> int:
        self.emit("warning", code="has_alpha", message=message)
        self.emit("skipped", code="has_alpha", message=message, log=str(log_path))
        return 4

    def check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled()

    def phase(self, name, within, detail):
        w = self.weights
        order = list(w)
        base = sum(w[k] for k in order[:order.index(name)])
        f = min(0.999, base + w[name] * within)
        f = max(f, self.last_fraction)
        self.last_fraction = f
        el = time.monotonic() - self.attempt_t0 if hasattr(self, "attempt_t0") else 0
        eta = el * (1 - f) / f if f > 0.05 else None
        self.emit("progress", fraction=round(f, 4), eta_s=None if eta is None else round(eta, 1),
                  phase=name, detail=detail)

    def infer(self, src, clip, chunk, stride, attempt, cap, gpu, exr=False):
        out = self.jobdir / f"try{attempt}" / "out"
        temp = self.jobdir / f"try{attempt}" / "temp"
        out.mkdir(parents=True, exist_ok=True)
        temp.mkdir(parents=True, exist_ok=True)
        chunk_eff = min(chunk, clip["frames"])
        stride_eff = max(1, min(stride, chunk_eff // 2 or 1))
        cmd = [str(PY), "-I", "-u", str(SHIM), "--input", str(src), "--output_dir", str(out),
               "--temp_dir", str(temp), "--low_vram", "--hann_chunk", str(chunk_eff),
               "--hann_stride", str(stride_eff), "--outputs", "alpha", "fg",
               "--despill_strength", "0", "--ffmpeg_bin", str(ck_env.FFMPEG)]
        if exr:  # stills/sequences: EXR (no video codec in the way), converted to PNG by the runner
            # float only where it can matter: half's ~11-bit mantissa is ~0.05 of an
            # 8-bit step, but coarser than a 16-bit step. Half EXRs halve stage-2 I/O.
            cmd += ["--output_format", "exr", "--exr_dtype", "float" if self.a.png16 else "half"]
        if self.screen_flag and self.a.screen != "auto":
            cmd += [self.screen_flag, self.a.screen]
        self.write_log(f"WINDOW {chunk}/{stride} (attempt {attempt}): " + " ".join(cmd))
        self.emit("attempt", attempt=attempt, window=f"{chunk}/{stride}")
        # os.environ is already the clean pack environment (ck_env.apply(): HF_HOME,
        # offline flags, temp, caches, no PYTHON* leaks)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        self.attempt_t0 = time.monotonic()
        self.last_fraction = 0.0
        self.phase("load", 0.0, "loading model")
        self.proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, env=env,
                                     creationflags=0x00000200 | gpu_win.CREATE_NO_WINDOW)
        state = {"windows": None, "torch": None, "spill": None, "peak_d": 0.0, "peak_s": 0.0,
                 "t_inf0": None, "t_inf1": None, "lines": []}
        reader = threading.Thread(target=self.read_child, args=(state, clip), daemon=True)
        reader.start()
        ded_limit = cap if cap is not None else gpu["total_gib"] - 0.25
        ref_shared, bad, last = None, 0, 0.0
        while self.proc.poll() is None:
            if self.cancel.is_set():
                raise Cancelled()
            now = time.monotonic()
            if now - last >= SAMPLE_S:
                last = now
                m = gpu_win.process_gpu_memory(gpu_win.descendants(self.proc.pid))
                if m:
                    d, s = m
                    state["peak_d"], state["peak_s"] = max(state["peak_d"], d), max(state["peak_s"], s)
                    if ref_shared is None and d > WATCH_FROM_GIB:
                        ref_shared = s
                    over_shared = ref_shared is not None and s > ref_shared + SHARED_GROWTH_GIB
                    over_ded = d > ded_limit
                    bad = bad + 1 if (over_shared or over_ded) else 0
                    if bad >= SPILL_SAMPLES:
                        why = (f"shared GPU memory {s:.2f} GiB, {s - ref_shared:.2f} above its post-load level"
                               if over_shared else f"dedicated {d:.2f} GiB over the {ded_limit:g} GiB limit")
                        self.kill()
                        raise Spilled(why)
                    self.write_log(f"GPU dedicated={d:.2f} shared={s:.2f} ref={ref_shared}")
            time.sleep(0.25)
        reader.join(timeout=10)
        self.check_cancel()
        code = self.proc.returncode
        if code != 0:
            tail = "\n".join(state["lines"][-15:])
            raise JobError("corridorkey_failed", f"CorridorKey exited with code {code}. Last output:\n{tail}")
        if exr:
            fg_dir, a_dir = next(out.glob("*_fg_exr"), None), next(out.glob("*_alpha_exr"), None)
            files = {"fg": sorted(fg_dir.glob("*.exr")) if fg_dir else [],
                     "alpha": sorted(a_dir.glob("*.exr")) if a_dir else []}
            if not (len(files["fg"]) == len(files["alpha"]) == clip["frames"]):
                raise JobError("outputs_missing", f"CorridorKey wrote {len(files['fg'])} fg / "
                               f"{len(files['alpha'])} alpha EXRs, expected {clip['frames']}, in {out}")
        else:
            files = {"fg": next(out.glob("*_fg.mp4"), None), "alpha": next(out.glob("*_alpha.mp4"), None)}
            if not all(files.values()):
                raise JobError("outputs_missing", f"CorridorKey finished but outputs are missing in {out}")
        t1 = state["t_inf1"] or time.monotonic()
        inf_s = t1 - (state["t_inf0"] or self.attempt_t0)
        return {"files": files, "window": f"{chunk}/{stride}", "attempt": attempt, "inference_s": round(inf_s, 2),
                "peak_dedicated": round(state["peak_d"], 2), "peak_shared": round(state["peak_s"], 2),
                "torch": state["torch"]}

    def read_child(self, state, clip):
        T = clip["frames"]
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            state["lines"].append(line)
            del state["lines"][:-200]
            self.write_log("CK " + line)
            if line.startswith("CKSHIM "):
                try:
                    d = json.loads(line[7:])
                except ValueError:
                    continue
                if "frames_written" in d:
                    n = d["frames_written"]
                    self.phase("stage2", n / T, f"frame {n}/{T}")
                if "torch_peak_reserved_gib" in d:
                    state["torch"] = d
                continue
            s = line.strip()
            if s.startswith("probed "):
                state["t_inf0"] = time.monotonic()  # model loaded; inference starts
                self.phase("prepass", 0.0, "analysing clip")
            elif s.startswith("frozen VFM prepass"):
                self.phase("prepass", 0.5, "analysing clip")
            elif s.startswith("Hann stage1:"):
                m = re.search(r"windows=(\d+)", s)
                state["windows"] = int(m.group(1)) if m else None
                self.phase("stage1", 0.0, "stage 1")
            elif s.startswith("window "):
                m = re.match(r"window (\d+)/(\d+)", s)
                if m:
                    i, n = int(m.group(1)), int(m.group(2))
                    self.phase("stage1", i / n, f"stage 1 window {i}/{n}")
            elif s.startswith("wrote "):
                state["t_inf1"] = time.monotonic()
            elif "WARNING" in s:
                self.emit("warning", code="corridorkey", message=s)

    def retag(self, path: Path):
        tmp = path.with_name(path.stem + ".retag.mp4")
        # -nostdin: ffmpeg otherwise reads stdin for key commands and blocks on an
        # inherited pipe (it hung 12 min under the window, whose stdin is a pipe).
        # +faststart puts the moov (and its colr box) at the front, so the check
        # below reads only the head of the file.
        cmd = [str(ck_env.FFMPEG), "-nostdin", "-v", "error", "-y", "-i", str(path), "-map", "0", "-c", "copy",
               "-bsf:v", RETAG_BSF, "-colorspace", "smpte170m", "-color_primaries", "bt709",
               "-color_trc", "iec61966-2-1", "-movflags", "+write_colr+faststart", str(tmp)]
        r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           creationflags=gpu_win.CREATE_NO_WINDOW)
        if r.returncode != 0:
            raise JobError("retag_failed", f"ffmpeg retag failed for {path.name}: {r.stderr.strip()}")
        tags = subprocess.run([str(ck_env.FFPROBE), "-v", "error", "-select_streams", "v:0", "-show_entries",
                               "stream=color_space,color_primaries,color_transfer,color_range,nb_frames",
                               "-of", "json", str(tmp)], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, creationflags=gpu_win.CREATE_NO_WINDOW).stdout
        st = json.loads(tags)["streams"][0]
        want = {"color_space": "smpte170m", "color_primaries": "bt709",
                "color_transfer": "iec61966-2-1", "color_range": "tv"}
        bad = {k: st.get(k) for k in want if st.get(k) != want[k]}
        with open(tmp, "rb") as f:
            data = f.read(16 << 20)
        i = data.find(b"colrnclx")
        colr = (int.from_bytes(data[i + 8:i + 10], "big"), int.from_bytes(data[i + 10:i + 12], "big"),
                int.from_bytes(data[i + 12:i + 14], "big")) if i >= 0 else None
        if bad or colr != (1, 13, 6):  # a missing colr box is a failure, not a pass
            raise JobError("retag_unverified", f"retag check failed for {path.name}: stream={bad} colr={colr}")
        os.replace(tmp, path)
        self.write_log(f"retagged {path.name}: stream tags {want}, colr={colr}")

    def place(self, staged: Path, dest: Path):
        part = dest.with_name(dest.name + ".part")
        shutil.copyfile(staged, part)
        os.replace(part, dest)
        self.placed.append(str(dest))

    def copy_verified(self, src: Path, dest: Path):
        part = dest.with_name(dest.name + ".part")
        shutil.copy2(src, part)

        def sha(p):
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for b in iter(lambda: f.read(1 << 20), b""):
                    h.update(b)
            return h.hexdigest()
        if sha(src) != sha(part):
            part.unlink(missing_ok=True)
            raise JobError("copy_mismatch", f"Copy of the original did not verify: {dest}")
        os.replace(part, dest)
        self.placed.append(str(dest))

    def kill(self):
        if self.proc and self.proc.poll() is None:
            tree = gpu_win.descendants(self.proc.pid)   # snapshot BEFORE the parent dies
            gpu_win.kill_tree(self.proc.pid)
            # taskkill returns before handles close; wait until the whole tree is gone,
            # or the temp memmaps stay locked and cannot be deleted.
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and tree & set(gpu_win._parent_map()):
                time.sleep(0.2)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def sweep_stale_jobs(self):
        """Delete job folders whose runner is gone (force-killed, power cut).
        A folder with a live owner (another clip running) is left alone."""
        if not JOBS.exists():
            return
        alive = set(gpu_win._parent_map())
        for d in JOBS.iterdir():
            try:
                owner = int((d / "owner.pid").read_text())
            except (OSError, ValueError):
                owner = None  # no pid file: only old enough folders count as stale
                if time.time() - d.stat().st_mtime < 24 * 3600:
                    continue
            if owner is not None and owner in alive:
                continue
            shutil.rmtree(d, ignore_errors=True)
            self.write_log(f"swept stale job folder {d}" + ("" if not d.exists() else " (still locked)"))

    def remove_jobdir(self) -> bool:
        for _ in range(50):  # up to ~10 s for lingering file handles
            shutil.rmtree(self.jobdir, ignore_errors=True)
            if not self.jobdir.exists():
                return True
            time.sleep(0.2)
        return False

    def cleanup_partials(self, dests) -> list[str]:
        removed = []
        for d in dests.values():
            part = Path(str(d) + ".part")
            if part.exists():
                part.unlink(missing_ok=True)
                removed.append(str(part))
        if self.jobdir.exists():
            if self.remove_jobdir():
                removed.append(str(self.jobdir))
            else:
                self.emit("warning", code="temp_not_removed",
                          message=f"Could not delete temp folder (still locked): {self.jobdir}")
        return removed


def main():
    ap = argparse.ArgumentParser(description="CorridorKey runner: clip -> <clip>_fg.mp4 + <clip>_alpha.mp4")
    ap.add_argument("clip")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--vram", default="auto", help="auto, or a GPU memory cap in GB (e.g. 8)")
    ap.add_argument("--copy_original", action="store_true", help="also copy the source clip to out_dir")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--screen", choices=("auto", "green", "blue"), default="auto",
                    help="screen colour, passed on only if CorridorKey's CLI supports it (today it does not)")
    ap.add_argument("--plan_only", action="store_true", help="report the GPU/window plan and exit")
    ap.add_argument("--png16", action="store_true", help="16-bit PNGs for image/sequence jobs (default 8-bit)")
    ap.add_argument("--key_anyway", action="store_true",
                    help="key images that already have transparency (their alpha is ignored)")
    ap.add_argument("--cancel_file", default=None, help="cancel when this file appears")
    ap.add_argument("--window", default=None, metavar="CHUNK/STRIDE",
                    help="force a starting window instead of the memory-based pick (still steps down on spill)")
    a = ap.parse_args()
    if a.window:
        try:
            c, s = (int(x) for x in a.window.split("/"))
            if c < 1 or s < 1:
                raise ValueError
            a.window = (c, s)
        except ValueError:
            print(json.dumps({"event": "error", "code": "bad_arguments", "message": "--window must look like 48/24"}))
            sys.exit(2)
    if a.vram != "auto":
        try:
            if float(a.vram) <= 0:
                raise ValueError
        except ValueError:
            print(json.dumps({"event": "error", "code": "bad_arguments", "message": "--vram must be auto or GB > 0"}))
            sys.exit(2)
    sys.exit(Runner(a).run())


if __name__ == "__main__":
    main()
