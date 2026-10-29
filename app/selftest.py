"""CorridorKey Pack self-test, run by the installer after copying (pack-only file).

Steps (the installer runs them one by one so its progress page can move):
  verify   every installed file against manifest\\payload.sha256 (verify.py)
  smoke    CorridorKey's own scripts\\smoke_test_runtime.py --load_model
  key      ck_run.py keys selftest\\green_test.png; the key PNG must exist AND be
           keyed: alpha ~0 on the known background box, ~1 on the subject box
           (selftest\\regions.json). "A file exists" alone could pass a broken keyer.
  finish   writes data\\install\\selftest.json + the one-line summary the
           installer shows, and %LOCALAPPDATA%\\CorridorKey\\install.json (N0DUS discovery)
  uninstall  removes install.json if it still points at THIS install

Log: data\\install\\selftest.log (appended). Exit 0 = step passed, 1 = failed.

    python -I app\\selftest.py --step verify|smoke|key|finish|all|uninstall
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
# The user's own temp folder, captured BEFORE ck_env.apply() points TEMP inside the
# install: the runner (rightly) refuses output inside the install folder.
USER_TEMP = Path(os.environ.get("TEMP") or os.environ.get("TMP") or Path.home())
import ck_env  # noqa: E402

ck_env.apply()
import verify  # noqa: E402

INSTALL_DIR = ck_env.DATA / "install"
LOG = INSTALL_DIR / "selftest.log"
STATE = INSTALL_DIR / "selftest_state.json"
SUMMARY = INSTALL_DIR / "selftest_summary.txt"
OUT = ck_env.DATA / "selftest"
DISCOVERY = Path(os.environ["LOCALAPPDATA"]) / "CorridorKey" / "install.json"
NO_WINDOW = 0x08000000

# Plain sentences shown on the installer's last page when a step fails.
FAIL_TEXT = {
    "verify": "Some installed files are missing or damaged. Run the installer again; if it repeats, "
              "the installer copy itself is damaged.",
    "smoke": "CorridorKey could not load its model on this graphics card.",
    "key": "CorridorKey loaded but could not key the test image.",
}


def log(msg):
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    print(msg, flush=True)


def state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(step, ok, detail):
    s = state()
    s[step] = {"ok": ok, "detail": detail, "at": dt.datetime.now().isoformat(timespec="seconds")}
    STATE.write_text(json.dumps(s, indent=1), encoding="utf-8")


def run_logged(cmd, timeout):
    log("$ " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, cwd=str(ck_env.ROOT), timeout=timeout, creationflags=NO_WINDOW)
    for line in (r.stdout + r.stderr).splitlines()[-60:]:
        log("  | " + line)
    return r


def step_verify():
    r = verify.verify(ck_env.ROOT, ck_env.ROOT / verify.LIST_REL)
    if r["ok"]:
        return True, f"{r['files']} files, {r['bytes'] / 1e9:.2f} GB, all match ({r['seconds']} s)"
    for rel in r["missing"][:30]:
        log(f"  missing:   {rel}")
    for rel in r["wrong"][:30]:
        log(f"  different: {rel}")
    return False, f"{len(r['missing'])} missing, {len(r['wrong'])} different"


def step_smoke():
    r = run_logged(ck_env.python_cmd(ck_env.ROOT / "scripts" / "smoke_test_runtime.py", "--load_model"), 900)
    ok = r.returncode == 0 and "checkpoint ok" in r.stdout and "model ok" in r.stdout
    return ok, ("model loaded on the GPU" if ok else f"exit code {r.returncode}")


def mean_alpha(png: Path, box) -> float:
    from PIL import Image
    import numpy as np
    with Image.open(png) as im:
        if "A" not in im.getbands():
            raise ValueError(f"{png.name} has no alpha channel")
        a = np.asarray(im.getchannel("A"), dtype=np.float32)
    scale = 65535.0 if a.max() > 255 else 255.0
    x0, y0, x1, y1 = box
    return float(a[y0:y1, x0:x1].mean() / scale)


def step_key():
    regions = json.loads((ck_env.ROOT / "selftest" / "regions.json").read_text(encoding="utf-8"))
    src = ck_env.ROOT / "selftest" / regions["image"]
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    # The self-test result is ours (uninstall removes data\), but ck_run refuses output inside
    # the install, as it must for users: key into the user's temp folder, then move it in.
    out_dir = USER_TEMP / f"CorridorKeyPack-selftest-{os.getpid()}"
    shutil.rmtree(out_dir, ignore_errors=True)
    r = run_logged(ck_env.python_cmd(APP / "ck_run.py", src, "--out_dir", out_dir, "--overwrite"), 900)
    done = [json.loads(x) for x in r.stdout.splitlines() if x.startswith('{"event": "done"')]
    if r.returncode != 0 or not done:
        return False, f"runner exit code {r.returncode}"
    key = out_dir / f"{src.stem}_key.png"
    if not key.is_file():
        return False, "the runner reported done but wrote no key image"
    bg, fg = mean_alpha(key, regions["background"]), mean_alpha(key, regions["subject"])
    for p in out_dir.iterdir():
        shutil.move(str(p), OUT / p.name)
    shutil.rmtree(out_dir, ignore_errors=True)
    ok = bg < 0.1 and fg > 0.9
    detail = f"alpha background {bg:.3f} (needs < 0.1), subject {fg:.3f} (needs > 0.9), {done[0]['seconds']} s"
    return ok, detail


def step_finish():
    s = state()
    steps = ["verify", "smoke", "key"]
    failed = [k for k in steps if not s.get(k, {}).get("ok")]
    if failed:
        first = failed[0]
        why = FAIL_TEXT.get(first, "") if first in s else f"The '{first}' check did not run."
        message = f"{why} Details: {s.get(first, {}).get('detail', 'not run')}."
        result = "fail"
    else:
        message = "CorridorKey loaded its model and keyed the test image correctly."
        result = "pass"
    summary = {"result": result, "message": message, "steps": s,
               "at": dt.datetime.now().isoformat(timespec="seconds"), "log": str(LOG)}
    ck_env.SELFTEST_JSON.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    SUMMARY.write_text(("PASS: " if result == "pass" else "FAIL: ") + message, encoding="utf-8")
    try:
        version = (ck_env.ROOT / "VERSION").read_text().strip()
        sources = json.loads((ck_env.ROOT / "manifest" / "sources.json").read_text(encoding="utf-8"))
        DISCOVERY.parent.mkdir(parents=True, exist_ok=True)
        DISCOVERY.write_text(json.dumps({
            "schema": 1, "product": "CorridorKey Pack", "pack_version": version,
            "corridorkey_commit": sources["corridorkey"]["commit"],
            "install_dir": str(ck_env.ROOT), "python": str(ck_env.PY), "python_args": ["-I"],
            "ck_run": str(APP / "ck_run.py"), "ffmpeg": str(ck_env.FFMPEG),
            "installed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "self_test": result}, indent=1), encoding="utf-8")
        log(f"discovery file written: {DISCOVERY}")
    except Exception as e:
        log(f"could not write the discovery file {DISCOVERY}: {e}")
    log(f"RESULT {result.upper()}: {message}")
    return result == "pass", message


def step_uninstall():
    try:
        d = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    except Exception:
        return True, "no discovery file"
    if Path(d.get("install_dir", "")).resolve() == ck_env.ROOT.resolve():
        DISCOVERY.unlink(missing_ok=True)
        try:
            DISCOVERY.parent.rmdir()
        except OSError:
            pass
        return True, "discovery file removed"
    return True, "discovery file belongs to another install; left alone"


STEPS = {"verify": step_verify, "smoke": step_smoke, "key": step_key}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True, choices=list(STEPS) + ["finish", "all", "uninstall", "reset"])
    a = ap.parse_args()
    if a.step == "uninstall":
        print(step_uninstall()[1])
        return 0
    if a.step == "reset":
        STATE.unlink(missing_ok=True)
        return 0
    todo = list(STEPS) + ["finish"] if a.step == "all" else [a.step]
    ok_all = True
    for name in todo:
        t0 = time.monotonic()
        log(f"== {name}")
        if name == "finish":
            ok, detail = step_finish()
        else:
            try:
                ok, detail = STEPS[name]()
            except Exception as e:
                ok, detail = False, f"{type(e).__name__}: {e}"
            save_state(name, ok, detail)
        log(f"== {name}: {'PASS' if ok else 'FAIL'} ({detail}) {time.monotonic() - t0:.1f} s")
        ok_all = ok_all and ok
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
