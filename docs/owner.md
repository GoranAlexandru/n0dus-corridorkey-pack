# CorridorKey Pack — the owner's guide

For you, the pack's owner: what the pack is, the decisions behind it, and how to
rebuild it, release a new version, and keep an emergency copy. Colleagues only
need `README.md`.

## 1. Decisions on record

### Licence decision (STOP 1, Q6 c), 2026-10-29

> **The owner has decided**, on their own reading of the CorridorKey licence
> (Corridor Key Licence 2.0 = CC BY-NC-SA 4.0 + Corridor's additional terms),
> that the pack is used **studio-internally only**: handed only to people
> inside the company, never to freelancers, clients, partner studios or the
> public, and never sold or charged for. **No email to Corridor Digital.**
> The CorridorKey name stays prominent (licence §4): the product, the
> Start-menu entry and the window are all called "CorridorKey".

What that leaves on you:
- **Licence §2a** ("no repackaging or redistribution as a standalone product")
  is the clause this decision rests on. Keep the pack inside the company.
- **Licence §3:** if the company *together with its parent/sister companies*
  ever exceeds **US $20M gross revenue** in a fiscal year, every user needs a
  paid CorridorKey seat (https://corridorkey.com).
- The installer shows every colleague a "studio-internal only" notice they
  must accept, and the window's About box repeats it.

### Fallback (documented, not built): CorridorKey fetched at install time

If the decision above ever has to change, the pack can stop carrying
Corridor's own files without changing anything else:

1. `build_payload` leaves out CorridorKey's code (`infer.py`, `corridorkey\`,
   `third_party\`, `scripts\`, `LICENSE`, …) and its weights (`weights\`).
   The NVIDIA / Microsoft / Google models, Python, packages, ffmpeg and our app
   stay in the installer.
2. The installer gains one step before the self-test: download CorridorKey's
   code from GitHub (`nikopueringer/CorridorKey2.0`, commit `485f5e9`) and
   its two weight files from Hugging Face (revision `cf44a8d`), straight from
   Corridor's own official locations, then check every file against the SHA-256
   pins already in `manifest/sources.json`. Any mismatch stops the install
   before anything runs.
3. Effect: each colleague obtains CorridorKey from Corridor directly. The
   studio passes on only third-party files whose licences allow it.
4. Costs: those installs need internet (~2.7 GB) and stop working if Corridor
   moves or removes the files (your emergency archive, §5, still has them).
   The pre-check gains "internet reachable".

### The other STOP 1 rulings

Q1 a (Inno, two files) · Q2 a (pre-built Python, copied) · Q3 a (driver
570.65+) · Q4 b (refuse under 6 GB, warn 6–8 GB) · Q5 a (per-user folder,
`C:\CorridorKey` for non-ASCII user names) · Q7 a (uninstall removes settings)
· Q8 a (`%LOCALAPPDATA%\CorridorKey\install.json`) · Q9 c (local git + private
GitHub repo `n0dus-corridorkey-pack`) · Q10 a (gyan.dev ffmpeg 6.0 essentials,
GPL). Details: `PACK_PLAN.md`, "OWNER RULINGS AT STOP 1".

## 2. What is where

| Place | What | In git? |
|---|---|---|
| `Q:\tools\ck-pack\` | this repo: app, scripts, installer script, manifest, licences, docs | yes; pushed to the private GitHub repo https://github.com/GoranAlexandru/n0dus-corridorkey-pack |
| `Q:\tools\ck-pack-payload\downloads\` | every original download, as fetched (8.2 GB) | **never** |
| `Q:\tools\ck-pack-payload\stage\` | the exact folder the installer copies (10.5 GB, 34 286 files) | **never** |
| `Q:\tools\ck-pack-payload\out\` | `CorridorKey-Setup.exe` + `CorridorKey-Setup-1.bin` + `SHA256SUMS.txt` | **never** |
| `Q:\tools\CorridorKey2.0\` | the reference install. Read, never changed | (its own) |

**Push rule for GitHub:** code, docs and `manifest\` only. `.gitignore` blocks
installers, `.bin`, wheels, weights, archives and media; check
`git status` shows nothing big before every push.

## 3. Rebuild the installer (same version, e.g. on a new PC)

Needs: Windows, git, any Python 3.10+ (only to run the scripts), Inno Setup
6.7+ (free), internet for step 1.

```
cd Q:\tools\ck-pack
py -3 scripts\build_payload.py          (downloads ~8.2 GB, checks every hash, ~10 min)
py -3 scripts\build_installer.py        (verifies again, compiles the two installer files)
```

- If any download no longer matches its pin, `build_payload` stops with
  "REFUSED" and names the file. **Do not "fix" the pin**: it means the official
  file changed. Use the emergency copy (§5) instead.
- `build_installer` refuses if the stage differs by even one byte from
  `manifest\payload.sha256`, or contains anything not on that list.

## 4. Release a new version

1. Make the change (e.g. a new CorridorKey commit → update `manifest\sources.json`
   and the model pins; a package update → `manifest\requirements.in`, then
   `py -3 scripts\pin_wheels.py`).
2. Raise `VERSION` (e.g. `1.0.1`).
3. `build_payload` (new pins are only accepted with `--record-new-pins`; read
   what it records), then commit `manifest\` + your change.
4. `build_installer`, then install over an existing copy on a test PC: the
   self-test must PASS and the old settings must still be there.
5. Push code/docs/manifest to GitHub; copy the `out\` folder to wherever
   colleagues get it from; archive (§5).

A newer installer run over an older install keeps `data\` (settings, logs) and
replaces everything else. The installer asks the user to close CorridorKey first.

## 5. Emergency copy (archive this)

If any upstream source disappears (a Hugging Face repo, the GitHub release,
the PyTorch index), the pack can still be rebuilt from your archive.

Copy to a second drive or the NAS: **`Q:\tools\ck-pack-payload\` without
`stage\` = 16.28 GB** (measured 2026-10-29, pack 1.0.0):
- `downloads\` (8.21 GB): every original download, as fetched;
- `out\` (8.07 GB): the finished installer (`CorridorKey-Setup.exe`
  5.4 MB + `CorridorKey-Setup-1.bin` 8.07 GB + `SHA256SUMS.txt`);
- `BUILD_INFO.json` and `build_payload.log`;
- the repo (or rely on the GitHub copy).

`stage\` (10.51 GB) need not be archived: `build_payload` rebuilds it from
`downloads\` offline in about 5 minutes.

Installer checksums (pack 1.0.0), to check an archived copy is intact:
```
77af27369e44f503b2c8fb025a42af853a4917a50a0504e88e1a1b9970064212  CorridorKey-Setup.exe
a422746276139e464158ff7ca4f24823f6d8cea208adbbae9a886011f86ff801  CorridorKey-Setup-1.bin
```

Rebuilding from the archive: put `downloads\` back under
`Q:\tools\ck-pack-payload\`, run `build_payload` (it re-hashes everything
already there and downloads nothing), then `build_installer`.

## 6. Testing hooks and logs

- **Simulated pre-check failures** (proves the messages without the hardware):
  `CorridorKey-Setup.exe /CKSIMULATE=olddriver` (also `nogpu`, `oldgpu`,
  `lowvram`, `smallvram` (the 6–8 GB warning), `oldwindows`, `lowdisk`,
  `unicodedir`, `unicodeuser`; comma-separate several). Colleagues never use it.
- On a colleague's PC: `<install>\data\install\selftest.log` and `setup.log`
  (the installer's own log); per-job logs in `<install>\data\logs\`.
- `py -3 tests\equivalence.py --pack <install> --ref Q:\tools\CorridorKey2.0 --work <empty folder>`
  proves the installed pack keys exactly like the reference (see §7).
- `py -3 -m unittest discover -s tests` checks the scripts.

## 7. Test results (Phase 1)

All on the build PC (Windows 10 22H2 build 19045, RTX 3090 24 GB, driver 610.62),
2026-10-29, installer 1.0.0 as checksummed in §5.

| Test | Result |
|---|---|
| Build from official sources | 71 pinned downloads + 5 new pins (ffmpeg zip, ffmpeg source, 3 licence documents) recorded on first download; 2 git sources at their commits. Stage 34 286 files, 10.51 GB, matches its list exactly |
| Installer compile | 132 s → `CorridorKey-Setup.exe` 5.4 MB + `CorridorKey-Setup-1.bin` 8.07 GB |
| Pre-checks forced to fail (`tests\test_installer_prechecks.ps1`) | **8/8 PASS**: old Windows, no GPU, old GPU, old driver, under 6 GB, low disk, non-ASCII folder, and the 6–8 GB warning; each logged its plain message and wrote nothing |
| Pre-checks on this real PC | pass (`RTX 3090, 8.6, 610.62, 24576`) |
| Fresh silent install into `C:\ck-test\CorridorKey` | **276 s** total; self-test **PASS**: verify 34 286 files 48.6 s, model load 10.3 s, key 14.3 s with alpha 0.000 on the background box and 1.000 on the subject box |
| Relocation | Python built in `Q:\tools\ck-pack-payload\stage`, ran from `C:\ck-test\CorridorKey` |
| Isolation | runner keyed a still AND a clip with a hostile environment: bogus `PYTHONHOME`, a booby-trapped `numpy` on `PYTHONPATH`, Anaconda first on PATH, failing fake `ffmpeg`/`ffprobe` on PATH. A normal Python cannot even start in that environment; the pack keyed fine and the colour-tag check passed with the bundled ffprobe |
| Equivalence with the reference (`tests\equivalence.py`) | **PASS**: still key/alpha PNGs pixel-identical (max difference 0); clip fg and alpha, all 48 decoded frames identical. The reference folder was unchanged afterwards (git status and file times checked) |
| Window | built hidden: drag-and-drop loaded, GPU "NVIDIA GeForce RTX 3090 24 GB", settings in `data\`, stray `PYTHONPATH` removed |
| Output inside the install folder | refused (`output_inside_install`), nothing created |
| Upgrade (same 1.0.0 installer re-run, no folder given) | 279 s, found the old folder itself; settings byte-identical, 9 old logs kept, a stale file planted in `python\` removed, self-test PASS |
| Uninstall | 12 s; Apps entry, Start-menu entry, `install.json` all gone; only a user note planted in the install root survived (so the folder stayed); the outputs folder beside it untouched |

Not tested here: a second, different PC (the real test, ideally one RTX 30/40
card with 8–12 GB), and a true version-to-version upgrade (1.0.0 → 1.0.1;
the steps involved don't depend on the version number). The interactive
wizard pages were not clicked through (no desktop automation on this PC); every
check they show was exercised silently.
