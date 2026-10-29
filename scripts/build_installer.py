"""Build CorridorKey-Setup.exe + CorridorKey-Setup-1.bin from a verified payload stage.

    py -3 scripts\\build_installer.py [--payload Q:\\tools\\ck-pack-payload] [--iscc PATH]

Refuses unless:
  * the stage verifies against its own file list (every file, every byte), and
  * that list is identical to the one committed in the repo (manifest/payload.sha256),
    so the installer contains exactly what the repo says it contains.
Writes PAYLOAD\\out\\ (the two installer files + SHA256SUMS.txt for them).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import verify  # noqa: E402

DEFAULT_ISCC = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--payload", default=r"Q:\tools\ck-pack-payload")
    ap.add_argument("--iscc", default=None)
    a = ap.parse_args()
    payload = Path(a.payload)
    stage, out = payload / "stage", payload / "out"
    version = (REPO / "VERSION").read_text().strip()
    iscc = Path(a.iscc) if a.iscc else DEFAULT_ISCC
    if not iscc.is_file():
        for c in (Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"), Path(r"C:\Program Files\Inno Setup 6\ISCC.exe")):
            if c.is_file():
                iscc = c
    if not iscc.is_file():
        print("Inno Setup 6 (ISCC.exe) not found; install Inno Setup 6.7+ or pass --iscc")
        return 1

    staged_list = stage / verify.LIST_REL
    repo_list = REPO / "manifest" / "payload.sha256"
    if not staged_list.is_file():
        print(f"REFUSED: no file list in {stage}; run build_payload.py first")
        return 1
    strip = lambda p: [x for x in p.read_text(encoding="utf-8").splitlines() if not x.startswith("#")]
    if strip(staged_list) != strip(repo_list):
        print("REFUSED: the stage's file list differs from manifest/payload.sha256 in the repo.\n"
              "Rebuild the payload, or commit the new list if the change is intended.")
        return 1
    if (stage / "VERSION").read_text().strip() != version:
        print(f"REFUSED: stage is version {(stage / 'VERSION').read_text().strip()}, repo VERSION is {version}")
        return 1
    print("verifying the stage, every file…", flush=True)
    r = verify.verify(stage, staged_list)
    if not r["ok"]:
        print(f"REFUSED: stage does not verify: {len(r['missing'])} missing, {len(r['wrong'])} different")
        for x in (r["missing"] + r["wrong"])[:30]:
            print("  " + x)
        return 1
    if r["extra_count"]:
        print(f"REFUSED: {r['extra_count']} files in the stage are not in its list, e.g. {r['extra_sample'][:5]}")
        return 1
    print(f"stage PASS: {r['files']} files, {r['bytes'] / 1e9:.2f} GB")

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("CorridorKey-Setup*"):
        old.unlink()
    t0 = time.monotonic()
    cmd = [str(iscc), "/Q", f"/DAppVersion={version}", f"/DStageDir={stage}", f"/DOutDir={out}",
           str(REPO / "installer" / "corridorkey.iss")]
    print("$ " + " ".join(cmd), flush=True)
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        print(f"ISCC failed (exit {rc})")
        return 1
    files = sorted(out.glob("CorridorKey-Setup*"))
    lines = []
    for f in files:
        lines.append(f"{verify.sha256_file(f)}  {f.name}")
        print(f"  {f.name}: {f.stat().st_size / 1e9:.2f} GB")
    (out / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n")
    total = sum(f.stat().st_size for f in files)
    print(f"installer built in {time.monotonic() - t0:.0f} s: {len(files)} files, {total / 1e9:.2f} GB -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
