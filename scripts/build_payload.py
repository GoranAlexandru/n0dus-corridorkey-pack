"""Build the CorridorKey Pack payload from official sources, every file hash-checked.

    py -3 scripts\\build_payload.py [--payload Q:\\tools\\ck-pack-payload] [--record-new-pins]

1. DOWNLOAD into PAYLOAD\\downloads\\ everything manifest/sources.json pins:
   Python (python-build-standalone), 35 wheels (PyPI + PyTorch cu128 index),
   35 model files (Hugging Face at pinned revisions + Google DeepMind's bucket),
   ffmpeg 6.0 essentials (gyan.dev, GitHub), the ffmpeg 6.0 source tarball
   (ffmpeg.org), licence documents. A file already there is re-hashed, not
   re-downloaded. ANY SHA-256 MISMATCH STOPS THE BUILD. A pin that is still
   null is recorded only with --record-new-pins (and printed), never silently.
2. CLONE CorridorKey and utils3d at their pinned commits; the commit hash IS
   the integrity check (git refuses content that does not match it).
3. STAGE PAYLOAD\\stage\\ = the exact tree the installer copies (layout:
   PACK_PLAN.md 9.1): Python + every package pre-installed (no venv, ruling Q2a),
   CorridorKey at the root, models, ffmpeg, app, self-test media, licences.
4. WRITE stage\\manifest\\payload.sha256 (every staged file) + a copy in the repo.
5. CHECK: imports in the staged Python, CUDA visible, then verify.py on the stage.

Isolated throughout: pip ignores user config (PIP_CONFIG_FILE=nul), Python runs
with -I, ffmpeg is the downloaded copy by full path.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import verify  # noqa: E402

SOURCES = REPO / "manifest" / "sources.json"
LOCK = REPO / "manifest" / "requirements.lock"
PACK_VERSION = (REPO / "VERSION").read_text().strip()
UA = {"User-Agent": "ck-pack-build/1 (studio-internal)"}

LOG = None


def log(msg=""):
    line = f"{dt.datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    if LOG:
        LOG.write(line + "\n")
        LOG.flush()


class PinError(SystemExit):
    pass


# ------------------------------------------------------------------ download
def download(url: str, dest: Path, sha256: str | None, label: str, sources: dict, pin_ref: dict,
             record: bool) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        got = verify.sha256_file(dest)
        if sha256 and got == sha256:
            log(f"  ok (already here)  {label}")
            return dest
        if sha256:
            log(f"  {label}: existing file does not match its pin; downloading again")
            dest.unlink()
        else:
            return _record(dest, got, label, pin_ref, sources, record)
    part = dest.with_name(dest.name + ".part")
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done, last, t0 = 0, -1, time.monotonic()
                while True:
                    b = r.read(1 << 22)
                    if not b:
                        break
                    f.write(b)
                    done += len(b)
                    if total > 200e6:
                        pct = int(done * 20 / total)
                        if pct != last:
                            last = pct
                            mbs = done / 1e6 / max(time.monotonic() - t0, 1e-3)
                            log(f"    {label}: {done / 1e9:.2f}/{total / 1e9:.2f} GB ({mbs:.0f} MB/s)")
            break
        except OSError as e:
            log(f"  {label}: download attempt {attempt} failed: {e}")
            if attempt == 3:
                raise
            time.sleep(5 * attempt)
    got = verify.sha256_file(part)
    if sha256 and got != sha256:
        part.unlink()
        raise PinError(f"REFUSED: {label} from {url}\n  expected sha256 {sha256}\n  got      {got}\n"
                       "The official file no longer matches the pinned one. Nothing was staged.")
    os.replace(part, dest)
    if not sha256:
        return _record(dest, got, label, pin_ref, sources, record)
    log(f"  downloaded + verified  {label}")
    return dest


def _record(dest, got, label, pin_ref, sources, record):
    if not record:
        raise PinError(f"REFUSED: {label} has no pin yet. Its sha256 is {got}.\n"
                       "Re-run with --record-new-pins to record it in manifest/sources.json "
                       "(do this only for a source you trust, and commit the change).")
    pin_ref["sha256"] = got
    SOURCES.write_text(json.dumps(sources, indent=1) + "\n", newline="\n")
    log(f"  NEW PIN RECORDED  {label}: {got}")
    return dest


def git_checkout(repo: str, commit: str, dest: Path) -> Path:
    if not (dest / ".git").is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        subprocess.run(["git", "clone", "--quiet", repo, str(dest)], check=True)
    head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != commit:
        subprocess.run(["git", "-C", str(dest), "fetch", "--quiet", "origin"], check=True)
        subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", "--force", commit], check=True)
    subprocess.run(["git", "-C", str(dest), "reset", "--quiet", "--hard", commit], check=True)
    subprocess.run(["git", "-C", str(dest), "clean", "-qfdx"], check=True)
    head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != commit:
        raise PinError(f"REFUSED: {repo} is at {head}, expected {commit}")
    log(f"  git ok  {repo} @ {commit[:12]}")
    return dest


# ------------------------------------------------------------------ stage
def run(cmd, **kw):
    log("  $ " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        log(r.stdout[-4000:])
        log(r.stderr[-4000:])
        raise SystemExit(f"command failed ({r.returncode}): {cmd[0]}")
    return r


def clean_env(extra=None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("PYTHON", "PIP_", "CONDA", "VIRTUAL_ENV"))}
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_NO_CACHE_DIR="1", PIP_DISABLE_PIP_VERSION_CHECK="1",
               PYTHONNOUSERSITE="1", PYTHONIOENCODING="utf-8")
    env.update(extra or {})
    return env


def collect_licences(stage: Path):
    """Every installed package's licence files -> licences/python-packages/<dist>/."""
    site = stage / "python" / "Lib" / "site-packages"
    out = stage / "licences" / "python-packages"
    n = 0
    for di in sorted(site.glob("*.dist-info")):
        files = [p for p in di.rglob("*") if p.is_file() and (
            p.parent.name.lower() in ("licenses", "license_files") or
            p.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")))]
        for p in files:
            dst = out / di.name.replace(".dist-info", "") / p.relative_to(di)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dst)
            n += 1
    log(f"  collected {n} licence files from package metadata")


def build(payload: Path, record: bool, download_only: bool = False):
    src = json.loads(SOURCES.read_text())
    dl = payload / "downloads"
    stage = payload / "stage"

    log("== 1. downloads (official sources, SHA-256 checked)")
    py = src["python"]
    py_arc = download(py["url"], dl / "python" / py["file"], py["sha256"], "python", src, py, record)
    wheels = []
    for w in src["wheels"]:
        wheels.append(download(w["url"], dl / "wheels" / w["file"], w["sha256"], w["file"], src, w, record))
    for m in src["models"]:
        download(m["url"], dl / "models" / m["dest"], m["sha256"], m["dest"], src, m, record)
    ff = src["ffmpeg"]
    ff_zip = download(ff["url"], dl / "ffmpeg" / ff["file"], ff["sha256"], ff["file"], src, ff, record)
    fs = src["ffmpeg_source"]
    download(fs["url"], dl / "ffmpeg" / fs["file"], fs["sha256"], fs["file"], src, fs, record)
    for d in src.get("licence_docs", []):
        download(d["url"], dl / "licence_docs" / d["file"], d["sha256"], d["file"], src, d, record)

    log("== 2. git sources at pinned commits")
    ck = git_checkout(src["corridorkey"]["repo"], src["corridorkey"]["commit"], dl / "git" / "corridorkey")
    u3 = git_checkout(src["utils3d"]["repo"], src["utils3d"]["commit"], dl / "git" / "utils3d")
    if download_only:
        log("== downloads complete (--download-only)")
        return

    log("== 3. stage")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    # 3a. Python: the archive holds python/...
    with tarfile.open(py_arc) as t:
        t.extractall(stage, filter="data")
    pyexe = stage / "python" / "python.exe"
    if not pyexe.is_file():
        raise SystemExit("python archive did not contain python/python.exe")
    env = clean_env()
    # 3b. packages: offline, hash-locked, from the downloaded wheels only.
    run([pyexe, "-I", "-m", "pip", "install", "--no-index", "--no-deps", "--no-compile",
         "--require-hashes", "--find-links", dl / "wheels", "-r", LOCK, "--no-warn-script-location"], env=env)
    # utils3d: pure Python, installed from the verified checkout (setuptools is already in).
    run([pyexe, "-I", "-m", "pip", "install", "--no-index", "--no-deps", "--no-compile",
         "--no-build-isolation", "--no-warn-script-location", u3], env=env)
    # The .exe launchers in Scripts\ hard-code this build folder's path and the pack never uses
    # them (it always runs python.exe -m ...). Removing them keeps the tree free of absolute paths.
    for exe in (stage / "python" / "Scripts").glob("*.exe"):
        exe.unlink()
    # Byte-code with checked-hash invalidation: identical bytes on every build, valid wherever
    # the folder is moved, independent of file timestamps.
    # The WHOLE library (stdlib too, -f), so nothing run later writes new byte-code into the tree;
    # every later call into the staged Python uses -B for the same reason.
    # The stdlib in ONE process: parallel workers import stdlib modules while others replace
    # their .pyc (Windows refuses the replace: "Access is denied"). site-packages in parallel.
    run([pyexe, "-I", "-m", "compileall", "-f", "-q", "-j", "1", "--invalidation-mode", "checked-hash",
         "-x", r"[\\/]site-packages[\\/]", stage / "python" / "Lib"], env=env)
    run([pyexe, "-I", "-m", "compileall", "-f", "-q", "-j", "0", "--invalidation-mode", "checked-hash",
         stage / "python" / "Lib" / "site-packages"], env=env)
    # 3c. CorridorKey code at the root (the reference layout), tracked files only.
    tracked = subprocess.run(["git", "-C", str(ck), "ls-files", "-z"], capture_output=True, check=True).stdout
    for rel in tracked.decode().split("\0"):
        # Upstream's drag-and-drop launchers fall back to whatever "python" is on PATH (the pack's
        # whole point is never to do that); the Start-menu window replaces them. No code is changed.
        if not rel or rel.startswith(".github/") or rel in (".gitignore", "CorridorKey_DRAG_CLIPS_HERE.bat",
                                                             "CorridorKey_DRAG_CLIPS_HERE.sh"):
            continue
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ck / rel, dst)
    # 3d. models
    for m in src["models"]:
        dst = stage / m["dest"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dl / "models" / m["dest"], dst)
    # 3e. ffmpeg: only what the pack runs, plus its licence
    with zipfile.ZipFile(ff_zip) as z:
        for name in z.namelist():
            tail = name.split("/", 1)[1] if "/" in name else name
            if tail in ff["keep"]:
                dst = (stage / "ffmpeg" / tail) if tail.startswith("bin/") else (stage / "licences" / "ffmpeg" / tail)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(z.read(name))
    ffmpeg = stage / "ffmpeg" / "bin" / "ffmpeg.exe"
    # 3f. app + licences + self-test media + manifest copies
    shutil.copytree(REPO / "app", stage / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(REPO / "scripts" / "verify.py", stage / "app" / "verify.py")
    shutil.copytree(REPO / "licences", stage / "licences", dirs_exist_ok=True)
    for d in src.get("licence_docs", []):
        # (the target folder may not exist in a fresh clone: git does not keep empty folders)
        (stage / "licences" / d["into"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dl / "licence_docs" / d["file"], stage / "licences" / d["into"])
    (stage / "licences" / "python").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stage / "python" / "LICENSE.txt", stage / "licences" / "python" / "LICENSE.txt")
    collect_licences(stage)
    run([pyexe, "-I", "-B", REPO / "scripts" / "make_test_media.py", stage / "selftest"], env=env)
    run([pyexe, "-I", "-B", REPO / "scripts" / "make_icon.py", stage / "app" / "corridorkey.ico"], env=env)
    (stage / "manifest").mkdir()
    shutil.copyfile(SOURCES, stage / "manifest" / "sources.json")
    (stage / "VERSION").write_text(PACK_VERSION + "\n", newline="\n")

    log("== 4. file list")
    entries = verify.scan(stage)
    header = f"CorridorKey Pack {PACK_VERSION} payload, built {dt.datetime.now():%Y-%m-%d %H:%M}"
    verify.write_list(stage, entries, stage / verify.LIST_REL, header)
    shutil.copyfile(stage / verify.LIST_REL, REPO / "manifest" / "payload.sha256")
    log(f"  {len(entries)} files, {sum(e[1] for e in entries) / 1e9:.2f} GB")

    log("== 5. checks")
    r = run([pyexe, "-I", "-B", "-c",
             "import torch, torchvision, cv2, numpy, scipy, PIL, tkinter, tkinterdnd2, transformers, timm, "
             "safetensors, einops, utils3d, huggingface_hub; "
             "print('torch', torch.__version__, 'cuda', torch.version.cuda, 'available', torch.cuda.is_available()); "
             "print('tk', tkinter.TkVersion, 'cv2', cv2.__version__, 'numpy', numpy.__version__)"], env=env)
    log("  " + r.stdout.strip().replace("\n", "\n  "))
    r = run([ffmpeg, "-hide_banner", "-version"])
    log("  " + r.stdout.splitlines()[0])
    if "--enable-libx264" not in r.stdout:
        raise SystemExit("the staged ffmpeg has no libx264, which CorridorKey's default encoder needs")
    vr = verify.verify(stage, stage / verify.LIST_REL)
    if not vr["ok"] or vr["extra_count"]:
        raise SystemExit(f"stage does not match its own list exactly: {vr}")
    log(f"  verify.py on the stage: PASS ({vr['files']} files)")

    sizes = {}
    for part in ("downloads", "stage"):
        sizes[part] = sum(p.stat().st_size for p in (payload / part).rglob("*") if p.is_file())
    log(f"== done. downloads {sizes['downloads'] / 1e9:.2f} GB, stage {sizes['stage'] / 1e9:.2f} GB")
    (payload / "BUILD_INFO.json").write_text(json.dumps(
        {"pack_version": PACK_VERSION, "built": dt.datetime.now().isoformat(timespec="seconds"),
         "repo_commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                                       text=True).stdout.strip(),
         "files": len(entries), "bytes_downloads": sizes["downloads"], "bytes_stage": sizes["stage"]}, indent=1))


def main():
    global LOG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--payload", default=r"Q:\tools\ck-pack-payload")
    ap.add_argument("--record-new-pins", action="store_true")
    ap.add_argument("--download-only", action="store_true", help="steps 1-2 only")
    a = ap.parse_args()
    payload = Path(a.payload)
    payload.mkdir(parents=True, exist_ok=True)
    LOG = open(payload / "build_payload.log", "a", encoding="utf-8")
    log(f"build_payload {PACK_VERSION} -> {payload}")
    try:
        build(payload, a.record_new_pins, a.download_only)
    except PinError as e:
        log(str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
