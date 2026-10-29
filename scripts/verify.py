"""Check a folder against the pack's file list (manifest/payload.sha256).

One checker for every stage: the built payload (stage folder), the folder
build_installer is about to pack, and an installed copy on a colleague's PC
(the installer's self-test runs this file from <install>\\app).

  missing file or wrong SHA-256  -> FAIL (exit 1), each one named
  files not in the list          -> reported, never a failure (logs, caches,
                                    __pycache__ written at run time)

Standard library only, so any Python 3.8+ can run it.

    python verify.py ROOT [--list ROOT/manifest/payload.sha256] [--json OUT]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

LIST_REL = "manifest/payload.sha256"


def sha256_file(path, bufsize=1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                return h.hexdigest()
            h.update(b)


def read_list(path: Path) -> list[tuple[str, int, str]]:
    """Lines: '<sha256> <size> <relative/path>' (path may contain spaces)."""
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        try:
            h, size, rel = line.split(" ", 2)
            out.append((h, int(size), rel))
        except ValueError:
            raise SystemExit(f"{path}:{n}: malformed line")
    return out


def write_list(root: Path, entries, path: Path, header: str):
    lines = [f"# {header}", "# sha256 size path (relative, forward slashes)"]
    lines += [f"{h} {size} {rel}" for h, size, rel in sorted(entries, key=lambda e: e[2])]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def scan(root: Path, skip=(LIST_REL,)) -> list[tuple[str, int, str]]:
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            rel = p.relative_to(root).as_posix()
            if rel in skip:
                continue
            entries.append((sha256_file(p), p.stat().st_size, rel))
    return entries


def verify(root: Path, list_path: Path, progress=None) -> dict:
    expected = read_list(list_path)
    total = sum(s for _, s, _ in expected)
    done = 0
    missing, wrong = [], []
    t0 = time.monotonic()
    for i, (h, size, rel) in enumerate(expected):
        p = root / rel
        if not p.is_file():
            missing.append(rel)
        elif p.stat().st_size != size:
            wrong.append(f"{rel} (size {p.stat().st_size}, expected {size})")
        elif sha256_file(p) != h:
            wrong.append(f"{rel} (content differs)")
        done += size
        if progress and (i % 500 == 0 or i == len(expected) - 1):
            progress(done / total if total else 1.0)
    listed = {rel for _, _, rel in expected}
    extra = []
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            rel = (Path(dirpath) / fn).relative_to(root).as_posix()
            if rel not in listed and rel != LIST_REL:
                extra.append(rel)
    return {"ok": not missing and not wrong, "files": len(expected), "bytes": total,
            "missing": missing, "wrong": wrong, "extra_count": len(extra), "extra_sample": sorted(extra)[:20],
            "seconds": round(time.monotonic() - t0, 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--list", default=None, help=f"default: ROOT/{LIST_REL}")
    ap.add_argument("--json", default=None, help="also write the result as JSON here")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    list_path = Path(a.list) if a.list else root / LIST_REL
    if not list_path.is_file():
        print(f"FAIL: file list not found: {list_path}")
        return 1
    r = verify(root, list_path, progress=lambda f: print(f"  {f * 100:5.1f}%", flush=True))
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1), encoding="utf-8")
    gb = r["bytes"] / 1e9
    if r["ok"]:
        print(f"PASS: {r['files']} files, {gb:.2f} GB, all match ({r['seconds']} s); "
              f"{r['extra_count']} extra files not in the list (not an error)")
        return 0
    print(f"FAIL: {len(r['missing'])} missing, {len(r['wrong'])} different, of {r['files']} files")
    for rel in r["missing"][:50]:
        print(f"  missing:   {rel}")
    for rel in r["wrong"][:50]:
        print(f"  different: {rel}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
