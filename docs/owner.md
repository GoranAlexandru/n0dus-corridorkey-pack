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
| `Q:\tools\ck-pack\` | this repo: app, scripts, installer script, manifest, licences, docs | yes; pushed to the private GitHub repo |
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

Copy to a second drive or the NAS:
- `Q:\tools\ck-pack-payload\` **without** `stage\` (it is rebuilt from
  `downloads\` in minutes, offline). Size: see `BUILD_INFO.json`
  (downloads ≈ 8.2 GB);
- `Q:\tools\ck-pack-payload\out\` (the finished installer, ≈ SIZE_OUT GB);
- the repo (or rely on the GitHub copy).

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

FILLED_IN_AFTER_TESTS
