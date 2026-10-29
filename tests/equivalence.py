"""Prove the installed pack keys exactly like the reference install.

Runs upstream infer.py with the REFERENCE install's own Python (read-only use:
-B so no byte-code is written, temp/HF cache/outputs all in WORK), then the
installed pack's ck_run.py on the same synthetic inputs with the same window,
and compares:
  * still: the pack's key/alpha PNGs vs the reference EXRs converted by the very
    same function -> must be pixel-identical;
  * clip: decoded frames (ffmpeg framemd5) of the pack's fg/alpha mp4 vs the
    reference's -> must be identical (the pack's retag is a stream copy).
Both sides use the pack's bundled ffmpeg, so only the keying is compared.

    py -3 tests\\equivalence.py --pack C:\\ck-test\\CorridorKey --ref Q:\\tools\\CorridorKey2.0 --work <empty dir>
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def sh(cmd, env=None, cwd=None):
    print("$ " + " ".join(map(str, cmd)), flush=True)
    r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, env=env, cwd=cwd,
                       stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit(f"failed: {cmd[0]} (exit {r.returncode})")
    return r


def framemd5(ffmpeg, mp4):
    r = sh([ffmpeg, "-nostdin", "-v", "error", "-i", mp4, "-map", "0:v", "-f", "framemd5", "-"])
    return [l.split(",")[-1].strip() for l in r.stdout.splitlines() if l and not l.startswith("#")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    pack, ref, work = Path(a.pack), Path(a.ref), Path(a.work)
    if work.exists() and any(work.iterdir()):
        raise SystemExit(f"--work must be empty: {work}")
    work.mkdir(parents=True, exist_ok=True)
    ppy, rpy = pack / "python" / "python.exe", ref / "venv" / "Scripts" / "python.exe"
    ffmpeg = pack / "ffmpeg" / "bin" / "ffmpeg.exe"
    media = work / "media"
    sh([ppy, "-I", REPO / "scripts" / "make_test_media.py", media, "--clip", "--ffmpeg", ffmpeg])
    still_dir = work / "still_in" / "green_test"
    still_dir.mkdir(parents=True)
    shutil.copyfile(media / "green_test.png", still_dir / "000000.png")

    # ---- pack side (installed ck_run, its own clean environment)
    results = {}
    for name, src in (("still", media / "green_test.png"), ("clip", media / "green_clip.mp4")):
        out = work / f"pack_{name}"
        r = sh([ppy, "-I", pack / "app" / "ck_run.py", src, "--out_dir", out])
        done = [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{"event": "done"')][0]
        results[name] = done
        print(f"  pack {name}: window {done['window']}, {done['seconds']} s")

    # ---- reference side: upstream infer.py with the reference's Python, nothing written into it
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "CONDA"))}
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", HF_HOME=str(work / "ref_hf"),
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", CUDA_DEVICE_ORDER="PCI_BUS_ID",
               TEMP=str(work / "ref_temp"), TMP=str(work / "ref_temp"))
    (work / "ref_temp").mkdir()
    common = ["--low_vram", "--outputs", "alpha", "fg", "--despill_strength", "0", "--ffmpeg_bin", ffmpeg]
    c, s = results["still"]["window"].split("/")
    sh([rpy, "-B", "-s", ref / "infer.py", "--input", still_dir, "--output_dir", work / "ref_still",
        "--temp_dir", work / "ref_tmp1", "--hann_chunk", c, "--hann_stride", s,
        "--output_format", "exr", "--exr_dtype", "half"] + common, env=env, cwd=work)
    c, s = results["clip"]["window"].split("/")
    sh([rpy, "-B", "-s", ref / "infer.py", "--input", media / "green_clip.mp4", "--output_dir", work / "ref_clip",
        "--temp_dir", work / "ref_tmp2", "--hann_chunk", c, "--hann_stride", s] + common, env=env, cwd=work)

    # ---- compare
    fg = next((work / "ref_still").rglob("*_fg_exr/*.exr"))
    al = next((work / "ref_still").rglob("*_alpha_exr/*.exr"))
    cmp = (
        "import sys;sys.path.insert(0,sys.argv[1]);import stills,cv2,numpy as np;"
        "from pathlib import Path;w=Path(sys.argv[2]);"
        "stills.exr_to_png(Path(sys.argv[3]),Path(sys.argv[4]),w/'ref_key.png',w/'ref_alpha.png',8);"
        "a=cv2.imread(str(w/'ref_key.png'),-1);b=cv2.imread(str(w/'pack_still'/'green_test_key.png'),-1);"
        "c=cv2.imread(str(w/'ref_alpha.png'),-1);d=cv2.imread(str(w/'pack_still'/'green_test_alpha.png'),-1);"
        "print('key_identical',bool((a==b).all()),'alpha_identical',bool((c==d).all()),"
        "'max_diff',int(np.abs(a.astype(int)-b).max()))")
    r = sh([ppy, "-I", "-c", cmp, pack / "app", work, fg, al])
    still_line = r.stdout.strip()
    print("  still: " + still_line)
    clip_ok = {}
    for k in ("fg", "alpha"):
        pm = framemd5(ffmpeg, work / "pack_clip" / f"green_clip_{k}.mp4")
        rm = framemd5(ffmpeg, next((work / "ref_clip").rglob(f"*_{k}.mp4")))
        clip_ok[k] = (pm == rm, len(pm))
        print(f"  clip {k}: {len(pm)} frames, decoded frames identical: {pm == rm}")
    ok = "key_identical True alpha_identical True" in still_line and all(v[0] for v in clip_ok.values())
    print("EQUIVALENCE " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
