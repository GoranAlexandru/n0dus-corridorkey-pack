# CorridorKey Pack — plan (Phase 0, read-only) — ends at STOP 1

Written 2026-10-29. Nothing has been built, downloaded into a payload, or
changed anywhere. `Q:\tools\CorridorKey2.0` (the REFERENCE) was only read.
The only file this phase created is this one.

**What the pack is:** a folder you copy to a colleague's PC. They double-click
`CorridorKey-Setup.exe`, no internet needed. When it finishes, the Start menu
has a "CorridorKey" entry that opens the same window you use today, and the
last page of the installer says whether the self-test passed.

Plain-language summary of the decisions you need to make is at the end
(**STOP 1 QUESTIONS**). Each has a recommended option, listed first.

## OWNER RULINGS AT STOP 1 (2026-10-29)

| Q | Ruling | What it means for the build |
|---|---|---|
| Q1 | **a** | Inno Setup, one folder with `CorridorKey-Setup.exe` + `CorridorKey-Setup-1.bin` |
| Q2 | **a** | Python and all packages pre-built at build time, copied as files, every file hash-checked |
| Q3 | **a** | NVIDIA driver 570.65 or newer, else a plain "update your driver" refusal |
| Q4 | **b, amended** | Refuse cards **under 6 GB**. **6 GB up to (not including) 8 GB: install, with a plain warning** that only small clips / small windows fit. 8 GB+: no warning |
| Q5 | **a** | `%LOCALAPPDATA%\Programs\CorridorKey`, or `C:\CorridorKey` when the user name is not plain ASCII; non-ASCII folders refused |
| Q6 | **c — owner's decision** | See "Licence decision" below |
| Q7 | **a** | Uninstall removes settings and logs too; upgrades keep them |
| Q8 | **a** | `%LOCALAPPDATA%\CorridorKey\install.json` |
| Q9 | **c** | Local git in `Q:\tools\ck-pack` **plus a PRIVATE GitHub repo `n0dus-corridorkey-pack`** (the owner creates it and supplies the URL). Pushed: code, docs, manifest only. **Never pushed: payload, weights, media, installers** |
| Q10 | **a** | gyan.dev ffmpeg 6.0 essentials (GPL); licence and matching source kept with the pack |

**Extra ruling:** once the payload is built and verified, report its total size
so the owner can archive `Q:\tools\ck-pack-payload\` and the finished installer
on a second drive or the NAS: the emergency copy if any upstream source
disappears.

### Licence decision (Q6 c), recorded as the owner's

> The owner has decided, on their own reading of the CorridorKey licence §2a,
> that the pack is used **studio-internally only**: handed only to people
> inside the company, never to freelancers, clients, partner studios or the
> public, never sold or charged for. **No email to Corridor Digital.** The
> CorridorKey name stays prominent (§4). The §3 revenue rule (US $20M,
> counted across the whole group) is the owner's to keep track of.
> Recorded 2026-10-29, also in `docs\owner.md`.

**Documented fallback (not built): "download CorridorKey's own code and weights
at install time."** If this decision ever needs revisiting, the pack can stop
carrying CorridorKey's own files. The installer would carry everything else
(Python, packages, ffmpeg, the NVIDIA/Microsoft/Google models, our app), and
fetch only CorridorKey's code (GitHub, commit `485f5e9`) and weights (Hugging
Face, revision `cf44a8d`) from Corridor's own official locations during
install. It would check them against the same SHA-256 pins. Then each
colleague downloads the tool from Corridor themselves, and the studio never
passes on Corridor's files. The cost: those installs need internet (~2.7 GB),
and they break if Corridor moves or removes the files. The full description
lives in `docs\owner.md`, "Fallback: CorridorKey fetched at install time".

> Note: the brief I was given was cut off in the middle of Q1 ("(b) the").
> I wrote the questions myself from what Phase 0 found; if your Q1 had
> other options in mind, tell me and I'll add them.

---

## 1. What is inside today's working setup (the ingredients)

Read from `SETUP_RECIPE.md`, every file in `app\`, the install logs, the
package list in the venv and the model files themselves.

### 1.1 Runtime ingredients

| # | Ingredient | Exact version / pin | Size | Official source |
|---|---|---|---|---|
| 1 | CorridorKey 2.0 code (`infer.py`, `corridorkey\`, `third_party\MoGe\`, `scripts\`, `LICENSE`, `THIRD_PARTY_NOTICES.md`) | git commit `485f5e9ab759ead6138cc990776184b59d6ea971` | ~1.5 MB | GitHub `nikopueringer/CorridorKey2.0` |
| 2 | CorridorKey weights `corridorkey_v2.safetensors` + `foundation_stats.safetensors` | HF revision `cf44a8db3f024bb49fd59daa408848ccf05f7477`; SHA-256 `c43596de…0436` / `924783ce…66af3` | 2.66 GB + 19 KB | Hugging Face `nikopueringer/CorridorKey2.0` |
| 3 | C-RADIOv4-SO400M (NVIDIA): `model.safetensors` + its config/`.py` files | HF revision `c0457f5dc26ca145f954cd4fc5bb6114e5705ad8`; SHA-256 `23e0c117…763c` | 1.72 GB | Hugging Face `nvidia/C-RADIOv4-SO400M` |
| 4 | MoGe-2 ViT-B (Microsoft) `model.pt` | HF revision `ca5f0e07ff01d3e5a364c1d954ed12ee1814b368`; SHA-256 `16b8110e…a5f6` | 419 MB | Hugging Face `Ruicheng/moge-2-vitb-normal` |
| 5 | RVM small (Google DeepMind) `pretrain_rvm_small16_256_204031069.npz` | MD5 (base64) `ZJb6kj8+tasiJbVeplXu7Q==`; SHA-256 to be recorded at first download | 270 MB | Google storage bucket named in upstream's `download_weights.py` (the publisher's own) |
| 6 | Private Python | CPython 3.11.18, python-build-standalone release `20261026` (MSVC 1944, Tk 8.6) | 78 MB installed | GitHub `astral-sh/python-build-standalone` |
| 7 | PyTorch + torchvision (CUDA 12.8 build) | `torch 2.9.1+cu128`, `torchvision 0.24.1+cu128` | wheel 2.86 GB; 4.3 GB installed | `download.pytorch.org/whl/cu128` |
| 8 | Other Python packages (34) | exact versions below | ~150 MB of wheels | PyPI (+ utils3d from GitHub, see note) |
| 9 | ffmpeg + ffprobe | today: 6.0 gyan.dev "full" build on PATH | ~200 MB | gyan.dev builds, GitHub `GyanD/codexffmpeg` (tag `6.0`) |
| 10 | Our app (`app\`: `ck_gui.py`, `ck_run.py`, `stills.py`, `vram_plan.py`, `gpu_win.py`, `ck_infer_shim.py`) | as of 2026-10-28 | ~80 KB | the reference folder (copied, then adapted, §9.3) |

The 34 other packages, exactly as installed in the working venv:
certifi 2026.10.23 · charset_normalizer 3.5.2 · colorama 0.4.6 · einops 0.8.2 ·
filelock 4.2.4 · fsspec 2026.9.0 · glcontext 3.1.0 · huggingface_hub 0.36.2 ·
idna 3.20 · jinja2 3.1.6 · markupsafe 3.0.3 · moderngl 5.13.0 · mpmath 1.3.0 ·
networkx 3.6.1 · numpy 1.26.4 · opencv-python 4.11.0.86 · packaging 26.3 ·
pillow 13.0.0 · pip 26.2.2 · pyyaml 6.0.3 · regex 2026.9.29 · requests 2.34.2 ·
safetensors 0.8.0 · scipy 1.17.1 · setuptools 79.0.1 · sympy 1.14.0 ·
timm 1.0.30 · **tkinterdnd2 0.7.0** · tokenizers 0.22.2 · tqdm 4.70.1 ·
transformers 4.57.6 · typing_extensions 4.16.0 · urllib3 2.8.0 · utils3d 1.7.

- **utils3d** is not on PyPI at this version. Upstream installs it from GitHub at
  commit `83bfa5bda008803f6521ce9547f94023b8afeddd`. The build script builds that
  one wheel once, from that commit, and records its hash like every other file.
- **The CorridorKey weights are not pinned upstream.** `download_weights.py`
  passes `revision=None`, which means "whatever is newest". The pack pins the
  revision the reference actually downloaded (`cf44a8d…`, read from the
  download metadata), so a later upstream update can't silently change a
  rebuilt pack.

**Totals:** installed ≈ **10.4 GB**; the installer itself ≈ **8–8.5 GB**.
Most of that is already-compressed data (the torch wheel and the model
weights), which won't shrink further.

### 1.2 What the app depends on (found by reading the code)

- `ck_gui.py` and `ck_run.py` find Python at `ROOT\venv\Scripts\python.exe` and
  CorridorKey at `ROOT` (the folder above `app\`).
- **`ck_run.py` calls `ffmpeg` and `ffprobe` by bare name**, i.e. from PATH
  (`retag`, `probe_clip`). It also never passes `--ffmpeg_bin` to upstream, so
  upstream's `require_ffmpeg` also finds ffmpeg on PATH. Today that is
  `C:\Users\goran\AppData\Local\ffmpegio\…\ffmpeg.exe`. On a colleague's PC
  it might be missing, or a different version. **This has to change** (§5).
- **Upstream encodes video with `libx264`** (default `--ffmpeg_codec libx264`).
  Only GPL ffmpeg builds include libx264. That decides the ffmpeg question (§8).
- **The mp4 colour-tag fix was measured against ffmpeg 6.0's automatic
  RGB→YUV conversion.** A different ffmpeg version may convert differently.
  So the pack pins 6.0, and changing that later means repeating the colour
  check in SETUP_RECIPE.md.
- `settings.json` and `logs\` live inside `app\`. They need to move so an
  upgrade can replace `app\` without losing them (§10).
- The runner reads `nvidia-smi --id=0`, i.e. GPU number 0 in nvidia-smi's
  order. PyTorch numbers GPUs "fastest first" unless told otherwise. On a
  PC with two different NVIDIA cards, the card measured and the card used
  could differ. The pack sets `CUDA_DEVICE_ORDER=PCI_BUS_ID` so both agree.
- Temp and caches already go inside the tool folder (`tmp\jobs`,
  `.cache\huggingface`, `HF_HUB_OFFLINE=1`). The pack keeps that and adds the
  NVIDIA shader cache (otherwise `%APPDATA%\NVIDIA\ComputeCache`) and
  `TEMP`/`TMP` for child processes.
- OpenCV (`cv2.imread`/`imwrite`) can't open non-ASCII paths on Windows. Temp
  EXRs are written inside the install folder, so **a non-ASCII install path
  would break every image and sequence job.** That is the concrete reason for
  the ASCII rule (§5).
- Longest file path inside the packages: 128 characters below
  `site-packages\`. To stay under Windows' 260-character limit without
  admin-only "long paths", the install folder path is kept to **90 characters
  or fewer**, and the installer refuses longer ones.

---

## 2. Installer technology

The payload is ~8 GB of data that won't compress. **Windows will not start
an .exe of about 4 GB or more.** Inno Setup's own changelog for 6.5.2 calls
"nearly 4 GB" "near the maximum Windows supports". So **a true single-file
installer is not possible for this payload with any tool**, Inno or 7-Zip.
The smallest honest shape is **one folder holding two files**.

| Option | What the colleague gets | Wizard, pre-checks, progress, last-page result | Uninstall in Windows "Apps" | Cost / risk |
|---|---|---|---|---|
| **A. Inno Setup 6.7 with disk spanning** (`DiskSpanning=yes`, `DiskSliceSize=max`) | `CorridorKey-Setup.exe` (a few MB) + `CorridorKey-Setup-1.bin` (~8 GB), one folder | Yes, all built-in; we already use Inno for N0DUS; 6.7.3 is installed on this PC | Yes, per-user, no admin | Lowest. Since 6.5.2 one slice can be any size, so it's exactly two files, not a dozen 2 GB pieces |
| B. Inno + a separate `payload.7z` that Inno unpacks itself (built-in 7-Zip since 6.4) | setup.exe + payload.7z, one folder | Yes | Yes | Same two files as A, plus a second hashing/packing step to keep in sync. No gain |
| C. 7-Zip self-extracting .exe + setup script | still two pieces (the .exe would be over 4 GB), or a small SFX + archive | No wizard: pre-checks, progress and the result page would all be hand-made (PowerShell/Python windows) | Hand-made | Most work, worst experience |
| D. NSIS / WiX (MSI) | NSIS: 2 GB hard limit, needs external data. MSI: 2 GB cabinets, per-user MSI is awkward | Yes | Yes | More work than A for nothing extra |

**Recommendation: A.** Colleagues copy one folder (e.g. from a network share
or a USB drive) and double-click `CorridorKey-Setup.exe`. The `.bin` must sit
next to it. If it's missing, Inno says so in plain words.

Compression: the big files (torch, weights) are stored without
recompression. Recompressing costs minutes and saves almost nothing. The small
things (Python, code, ffmpeg) use LZMA2. That keeps install time close to
disk-copy speed.

Not code-signed (signing certificates cost money; the rules say no paid
services). So Windows may show "Windows protected your PC" the first time:
**More info → Run anyway**. The colleague README says so up front.

---

## 3. Install-time design: how Python gets onto the target

The brief asks to rebuild the venv on the target with
`pip --no-index --find-links`. The reason given is that a venv's absolute
paths don't move. Phase 0 found a second way that avoids that problem
altogether. You choose (**Q2**).

**Option 1 — pre-built private Python, copied as files (recommended).**
At build time, install every package straight into the standalone Python's
own folder (no venv at all). python-build-standalone is built to be
relocatable, and packages installed into it carry no absolute paths. The
only exceptions are the little `.exe` launchers in `Scripts\` (e.g.
`pip.exe`), which the pack never uses; it always runs `python.exe -m ...`.
On the target, install is then a plain file copy.
- Every single installed file is listed with its SHA-256 in the manifest and
  checked after copying (~1 minute). Option 2 can only check the wheels.
- No pip, resolver or wheel-unpacking step runs on the colleague's PC: fewer
  things that can fail.
- The build proves relocation before it makes an installer. It installs into
  folder X, moves to folder Y, and the full self-test must pass there.

**Option 2 — rebuild with pip on the target (the brief's design).** The
installer copies Python + a wheel folder, then runs
`python -m pip install --no-index --find-links wheels --require-hashes -r requirements.lock`.
That's the reference's exact recipe, with hashes. It adds ~2–4 minutes and
needs ~3 GB of extra space during install (the wheels, deleted afterwards).

**Estimated install time** (SSD, typical studio PC):

| step | Option 1 | Option 2 |
|---|---|---|
| pre-checks | seconds | seconds |
| unpack ~8 GB (from local disk / from a 1 Gbit network share) | 1–2 min / 2–3 min | 1–2 min / 2–3 min |
| pip install | — | 2–4 min |
| verify hashes | ~1 min | ~1 min (non-wheel files) |
| self-test (first model load reads 4.8 GB from disk) | ~1 min | ~1 min |
| **total** | **~4–6 min** | **~6–10 min** |

Windows Defender scans every new file (torch alone is ~31,000 files). It can
add a few minutes on slower PCs, and there's no way around that without admin
rights.

---

## 4. Pre-checks: before anything is unpacked

All checks run when the installer starts, before the first wizard page
(the disk check runs on the folder page). Any failure shows one plain
message and the installer quits. Nothing has been written.

| Check | How | Rule | Message if it fails (draft) |
|---|---|---|---|
| Windows | OS build number | Windows 10 22H2 (build 19045) or Windows 11 (build 22000+), 64-bit | "CorridorKey needs Windows 10 (version 22H2) or Windows 11, 64-bit. This PC runs build NNNNN." |
| NVIDIA GPU present | runs `nvidia-smi` (installed with every NVIDIA driver, in `C:\Windows\System32`) | must run and list a GPU | "No NVIDIA graphics card (or no NVIDIA driver) was found. CorridorKey needs an NVIDIA RTX 30-series card or newer." |
| GPU generation | `nvidia-smi --query-gpu=name,compute_cap,driver_version,memory.total --format=csv,noheader` (tested on this PC: `NVIDIA GeForce RTX 3090, 8.6, 610.62, 24576 MiB`) | "compute capability" **8.6 or higher** = RTX 30-series (8.6), RTX 40 (8.9), RTX 50 (12.0) and the matching pro cards (RTX A-series, Ada). Refuses RTX 20 / GTX 16 (7.5) and older | "This PC's graphics card (NAME) is older than an RTX 30-series. CorridorKey needs RTX 30-series or newer." |
| GPU memory | same query | **Ruled (Q4 b):** under 6 GB refused; 6 GB up to (not including) 8 GB installs after a plain warning; 8 GB+ silent. The app's own planner says even a tiny clip needs ~4.8 GB *free* | refuse: "NAME has N GB of graphics memory; CorridorKey needs at least 6 GB." · warn: "NAME has N GB of graphics memory. CorridorKey will work, but only for small clips: larger clips will be refused or keyed with a smaller time window (softer edges). Continue?" |
| Driver | same query | **570.65 or newer**, which NVIDIA's CUDA 12.8 release notes give as the Windows minimum (CUDA 12.8 GA). RTX 50 cards need it anyway (**Q3**) | "The NVIDIA driver is version X. CorridorKey needs 570.65 or newer. Update it from nvidia.com or the NVIDIA app, then run this installer again." |
| Disk | free space at the chosen folder | Option 1: **12 GB** free (10.4 GB + room for temp). Option 2: **15 GB** | "The drive for C:\… has N GB free; CorridorKey needs 12 GB." |
| Folder | the chosen path | plain ASCII letters/digits/`\ : _ - .` and spaces only; 90 characters at most; not inside the old reference folder | "Please choose a folder whose path uses only plain English letters and numbers (no accents), e.g. C:\CorridorKey." |

If a PC has several NVIDIA cards, the check passes if card number 0 (the one
the app will use) qualifies. Otherwise it names the cards and stops.

---

## 5. Isolation on the target (the "Anaconda trap" and friends)

- **No .bat, no console window.** The Start-menu shortcut points straight at
  `<install>\python\pythonw.exe -I "<install>\app\ck_gui.py"`. `-I`
  ("isolated mode") makes Python ignore `PYTHONPATH`, `PYTHONHOME` and every
  other `PYTHON*` variable, and the user's own site-packages. It is the
  built-in form of what the brief asks for.
- **Every process the app starts gets a cleaned environment** (one small
  helper, used by the window and the runner). It removes `PYTHONPATH`,
  `PYTHONHOME`, `PYTHONSTARTUP`, `PYTHONUSERBASE` and `CONDA_*`; sets
  `PYTHONNOUSERSITE=1`; and also passes `-I` to every child Python. So the
  Anaconda problem from SETUP_RECIPE.md can't come back through a child
  process.
- **PATH is cut down for child processes** to Windows' own folders
  (`System32`, where `nvidia-smi` and `taskkill` live) plus the pack's Python.
  Nothing from Anaconda or another CUDA install on PATH can be picked up.
- **ffmpeg is the bundled copy, by full path, everywhere.** The runner calls
  `<install>\ffmpeg\bin\ffmpeg.exe` / `ffprobe.exe`, and passes
  `--ffmpeg_bin <full path>` to upstream's `infer.py` (it already has that
  option). PATH is never consulted.
- **Caches and temp stay inside the install folder:** `tmp\` (jobs, `TEMP`,
  `TMP` for child processes), `.cache\huggingface` (`HF_HOME`, offline
  flags already set), `.cache\nv` (`CUDA_CACHE_PATH`), `.cache\torch`
  (`TORCH_HOME`).
- **Default install path, plain ASCII:** `%LOCALAPPDATA%\Programs\CorridorKey`
  (per-user like N0DUS, no admin) when that path is plain ASCII and short. A
  Windows user name with an accent (e.g. "Jörg") would make it non-ASCII; then
  the default becomes `C:\CorridorKey` (normal users may create folders at the
  top of C: without admin) (**Q5**).

---

## 6. Post-install self-test

Runs automatically at the end of the install. It never needs the internet.

1. **Hash check:** every installed payload file against the manifest. Any
   mismatch = FAIL, naming the file.
2. **CorridorKey's own check:** `python -I scripts\smoke_test_runtime.py --load_model`
   (checkpoint format, then loads the full model onto the GPU). It must print
   `checkpoint ok` and `model ok`.
3. **A real key:** `python -I app\ck_run.py selftest\green_test.png --out_dir <install>\data\selftest`.
   It must exit 0. Then the result must exist **and actually be keyed**: the
   key PNG has an alpha channel; a known background corner averages alpha
   below 0.1; and the centre of the test subject averages above 0.9. "A file
   exists" alone could pass on a broken keyer; this can't.

**The test image is synthetic.** A small script in the repo draws it: a flat
chroma-green background, a grey/orange shape with a soft edge, ~1024×576.
The same script makes a blue-screen version and a short 48-frame clip for
our own testing. No company art. The image is made at build time and hashed
like everything else.

**Result:** the installer's last page shows **PASS** (green) or **FAIL**
(red) with one plain sentence, plus a button to open the log. The log is
`<install>\data\install\selftest.log`, next to Inno's own setup log (copied
there). A FAIL keeps the install, so the log can be read or sent to you. The
Start-menu entry still works, and the window shows "self-test failed, see
log" in its status line.

---

## 7. Discovery for a future N0DUS node: `install.json`

Proposal (**Q8**): the installer writes, after the self-test,

`%LOCALAPPDATA%\CorridorKey\install.json` — a fixed per-user place that
doesn't depend on where CorridorKey was installed:

```json
{
  "schema": 1,
  "product": "CorridorKey Pack",
  "pack_version": "1.0.0",
  "corridorkey_commit": "485f5e9ab759ead6138cc990776184b59d6ea971",
  "install_dir": "C:\\Users\\name\\AppData\\Local\\Programs\\CorridorKey",
  "python": "…\\python\\python.exe",
  "ck_run": "…\\app\\ck_run.py",
  "ffmpeg": "…\\ffmpeg\\bin\\ffmpeg.exe",
  "python_args": ["-I"],
  "installed_at": "2026-11-02T10:15:00Z",
  "self_test": "pass"
}
```

A N0DUS node would read it, run `python -I ck_run.py INPUT --out_dir DIR`, and
read the JSON event lines the runner already prints. That is the protocol
`ck_gui.py` uses today, so the node and the window behave identically.
Uninstall deletes the file only if it still points at the folder being
removed. The file is UTF-8, so a non-ASCII user folder in its own path is
harmless.

---

## 8. Licences: what each requires for studio-internal redistribution

*This is a plain reading, not legal advice.* Every licence text listed below
is stored in the repo's `licences\` folder and installed into
`<install>\licences\`. A `NOTICE.txt` collects the required attribution lines.
The build script also copies the licence file of every Python package
automatically from its wheel.

| Component | Licence | In plain words, for giving it to colleagues inside the company |
|---|---|---|
| **CorridorKey 2.0** (code + weights) | CC BY-NC-SA 4.0 **plus Corridor's additional terms** (read in full from the reference `LICENSE`) | Use on commercial projects is allowed (§1a), and the images/videos made are yours (§1b). **Watch §2a:** "You may not repackage, redistribute, sublicense, or sell this tool, in whole or in part, as a standalone product or as part of a competing product." My reading: installing the tool for your own staff, free, inside one company, isn't selling a product or giving it "to the public" (the CC licence's definition of sharing). But "repackage… redistribute" is close enough to what an installer does that **you** should decide (**Q6**). **§3, large organisations:** if the company *together with its parent/sister companies* had over **US $20M gross revenue last fiscal year**, every person who uses it needs a paid CorridorKey seat. **§4:** keep the name "CorridorKey" prominent; the pack does (product name "CorridorKey", Start-menu "CorridorKey"). |
| C-RADIOv4-SO400M (NVIDIA) | NVIDIA Open Model License (June 2024; read in full) | Commercial use and redistribution allowed. Whoever receives a copy must get **a copy of the licence** and a **"Notice" text file** containing exactly: *"Licensed by NVIDIA Corporation under the NVIDIA Open Model License"*. Rights end if the company sues claiming the model infringes. This version has no "guardrail" clause. |
| MoGe-2 (Microsoft) code + weights | MIT; the vendored DINOv2 part is Apache-2.0 | Keep the copyright notice and licence text (already in `third_party\MoGe\LICENSE`). |
| RVM (Google DeepMind) | Apache-2.0 (code) / CC BY 4.0 (weights) | Give credit: name, link, licence, "not modified". The NOTICE does it. |
| PyTorch / torchvision | BSD-3-Clause | Keep the copyright and licence text. The wheel also carries NVIDIA CUDA libraries (cuBLAS, cuDNN, …), whose licence allows passing them on as part of an application. Their notices ship inside the wheel and stay there. |
| tkinterdnd2 | MIT (the tkdnd binary inside: BSD-style) | Keep notices. |
| Python 3.11 (python-build-standalone) | PSF licence (+ OpenSSL, Tcl/Tk etc., licences included in the download) | Keep the licence files that come with it. |
| OpenCV (opencv-python wheel) | Apache-2.0; the wheel carries an LGPL FFmpeg DLL of its own | Keep notices (they ship inside the wheel). |
| **ffmpeg** | depends on the build | See below. |
| All other Python packages | MIT / BSD / Apache-2.0 / PSF; certifi is MPL-2.0 | Keep notices, collected automatically. |

**ffmpeg build type.** Upstream encodes with **libx264**, and only GPL builds
contain it. An LGPL build would mean switching the encoder (e.g. NVIDIA's
NVENC or OpenH264). Output would no longer match the measured reference, and
the colour checks would need redoing. **Recommendation: gyan.dev
"ffmpeg-6.0-essentials_build"** from GitHub `GyanD/codexffmpeg`, release tag
`6.0` (the same version and build family as the one verified today;
essentials = smaller, still has libx264, 25.9 MB as .7z). It is **GPLv3**. The
GPL's main duty when passing on copies is to offer the source code. Copies
made only for a company's own staff are generally not counted as
"distribution", but compliance is cheap anyway: the pack ships the licence
text and a SOURCE note, and the payload folder keeps the matching ffmpeg 6.0
source tarball (from ffmpeg.org, hashed). Anyone given the pack can get the
source.

---

## 9. Repo layout

```
Q:\tools\ck-pack\                (git; small files only)
  PACK_PLAN.md                   this file
  README.md                      for colleagues: what it is, how to install, SmartScreen note, what PASS/FAIL means
  docs\owner.md                  for you: how to rebuild the payload and the installer, how to release a new version
  docs\CHANGES_FROM_REFERENCE.md every change made to the app vs Q:\tools\CorridorKey2.0\app, and why
  app\                           our app, adapted (see 9.3)
  installer\corridorkey.iss      Inno Setup script
  scripts\build_payload.py       downloads every ingredient from its official source into the payload folder, checks hashes
  scripts\build_installer.py     verifies the payload against the manifest, then runs Inno's compiler
  scripts\verify.py              checks a payload folder OR an installed folder against the manifest (also used by the self-test)
  scripts\make_test_media.py     draws the synthetic green/blue test image and clip
  manifest\sources.json          WHAT to fetch: URL, version/revision, expected SHA-256
  manifest\payload.json          generated: every payload file + size + SHA-256
  manifest\requirements.lock     exact package versions with hashes
  licences\                      every licence text + NOTICE.txt
  tests\                         checks for the scripts (manifest, verify, test-media maths)
  .gitignore                     payload, build output, *.bin, *.exe, weights, media
```

```
Q:\tools\ck-pack-payload\        (NOT in git; rebuilt any time by build_payload)
  downloads\                     the original downloads, as fetched
  stage\                         the exact tree that goes into the installer
  out\                           CorridorKey-Setup.exe + CorridorKey-Setup-1.bin
```

### 9.1 Installed layout on a colleague's PC

It keeps the reference's layout (CorridorKey at the root, `app\` beside it),
so the app needs as few changes as possible:

```
<install>\  infer.py, corridorkey\, third_party\, scripts\, LICENSE   CorridorKey @ 485f5e9
            weights\, vfms\                                           models (4.8 GB)
            python\                                                   private Python (+ packages in Option 1)
            ffmpeg\bin\ffmpeg.exe, ffprobe.exe
            app\                                                      our app
            selftest\green_test.png
            licences\
            data\settings.json, data\logs\, data\install\, data\selftest\   (kept on upgrade)
            tmp\, .cache\                                             (emptied on upgrade/uninstall)
```

### 9.2 Hashes, everywhere

- `build_payload` refuses any download whose SHA-256 doesn't match
  `sources.json`. A brand-new pin (e.g. the RVM file's SHA-256) is recorded
  once on first download. You'll see that happen, and it's listed in the
  build log.
- `build_installer` re-hashes the whole stage folder against
  `payload.json` before compiling. One wrong byte and it refuses.
- The installer verifies the installed files against the same manifest
  (§6, step 1).

### 9.3 Changes the pack's copy of the app needs

Proposed now, made in Phase 1, each recorded in
`docs\CHANGES_FROM_REFERENCE.md` (the reference copy stays as it is):

1. Python path: `python\python.exe` instead of `venv\Scripts\python.exe`;
   child Pythons started with `-I`.
2. ffmpeg/ffprobe by full path; `--ffmpeg_bin` passed to upstream.
3. The cleaned environment for every child process (§5), plus
   `CUDA_DEVICE_ORDER=PCI_BUS_ID`.
4. `settings.json` and `logs\` move to `data\`.
5. **The window refuses an output folder inside the install folder.** An
   upgrade or uninstall replaces that folder, and your outputs must never be
   in the way.
6. A small "About / licences" link in the window (CorridorKey attribution
   lives where people look).
7. A single-instance marker so the installer can ask "please close
   CorridorKey first" during upgrade/uninstall (Inno's `AppMutex`).

The keying itself stays bit-identical to the reference. Phase 1 proves it on
the synthetic clip: pack output vs reference output, decoded frames compared.

---

## 10. Upgrade and uninstall

**Upgrade** (a newer pack run over an older one): the same Inno "AppId", so
Windows sees one product and the installer reuses the old folder.
`data\` is kept as-is: settings (remembered output folder, GPU memory choice,
tick boxes) and logs. Everything else is removed first and replaced (Python,
packages, CorridorKey, models, app, ffmpeg); `tmp\` and `.cache\` are emptied.
Then the self-test runs again. The installer asks the user to close
CorridorKey first if it's open.

**Uninstall** (Windows Settings → Apps, or the Start-menu uninstall entry)
deletes:
- the files it installed;
- the folders it created by name: `python\`, `tmp\`, `.cache\`, `data\` (settings
  and logs; see **Q7**);
- the Start-menu entry, the uninstall registration and `install.json`.

It **never deletes the install folder wholesale**. Only those named parts go,
and the folder itself is removed only if it's empty afterwards. Together with
change 9.3-5 (outputs can't be inside the install folder), that means
**uninstall can't reach the colleague's output files**, wherever they are.

---

## 11. What Phase 1 would do (after your rulings)

1. Create the repo here (`git init`), commit this plan, the layout, `.gitignore`,
   `sources.json` with all pins.
2. `make_test_media.py`, then `build_payload.py` → payload folder, every hash
   checked. Downloads ≈ 8.3 GB from the official sources only.
3. Adapt the app (9.3); prove keying is identical to the reference.
4. The Inno script with the pre-checks, the self-test page, upgrade and
   uninstall; build the two-file installer.
5. Test on this PC: install into a fresh folder → self-test PASS → key the
   synthetic clip from the Start-menu window → upgrade over it (settings
   kept) → uninstall (outputs untouched, folder gone). Also make each
   pre-check fail on purpose and confirm nothing was written. A different PC
   is the real test; if you can lend one, that's the step to do there.
6. Colleague README + owner doc. Then STOP 2 for you to try it.

---

## STOP 1 QUESTIONS

Answer with the letters, e.g. "Q1 a, Q2 a, …". Recommended option first.

**Q1. Installer type.** One file isn't possible: Windows won't start an .exe
of ~4 GB or more, and the payload is ~8 GB.
- **(a) Recommended:** Inno Setup (as for N0DUS). One folder, two files:
  `CorridorKey-Setup.exe` + `CorridorKey-Setup-1.bin`. A normal installer
  with all the checks and a PASS/FAIL page.
- (b) The same, but with a separate `payload.7z` instead of the `.bin`. Same
  experience, one more thing to keep in sync.
- (c) A 7-Zip self-extractor. Still two pieces at this size, and no proper
  installer pages.

**Q2. How Python and its packages get onto the colleague's PC.**
- **(a) Recommended:** pre-built at build time and copied as files. Faster
  (~4–6 min), nothing gets "installed by pip" on their PC, and every file is
  hash-checked. The build proves it works after being moved before it ships.
- (b) As the brief says: rebuild with pip from the bundled wheels during
  install. ~6–10 min, only the wheels get hash-checked.

**Q3. Minimum NVIDIA driver.**
- **(a) Recommended:** 570.65 or newer, NVIDIA's stated minimum for CUDA 12.8
  on Windows. Older drivers get a clear "update your driver" message.
- (b) Allow down to 528.33 (CUDA 12's general floor) with a warning. RTX 30/40
  cards would usually work; RTX 50 cards would not.

**Q4. Minimum graphics memory.**
- **(a) Recommended:** refuse cards under 8 GB (they can only key very small
  clips).
- (b) Install on 6 GB cards too, with a warning.
- (c) No memory check, generation only.

**Q5. Default install folder.**
- **(a) Recommended:** `%LOCALAPPDATA%\Programs\CorridorKey` (per-user, like
  N0DUS); automatically `C:\CorridorKey` if the user name has accents.
  Non-ASCII folders are refused either way.
- (b) Always `C:\CorridorKey`.
- (c) Always the per-user folder; refuse to install for users with accented
  names.

**Q6. The CorridorKey licence (needs your decision; I can't make it).**
Two facts only you know: (1) is the company, together with any parent or
sister companies, under US $20M revenue last fiscal year (or has it bought a
seat for each user)? (2) will the pack stay strictly inside the company (no
freelancers, clients or partner studios)?
- **(a) Recommended:** I build now; you confirm both facts before the first
  colleague gets it. Optionally you email contact@corridordigital.com to
  confirm an internal installer is fine under §2a (the email is yours to
  send; I don't contact anyone).
- (b) Pause the build until Corridor answers in writing.
- (c) Build and hand out on your own reading of §2a, no email.

**Q7. On uninstall, the colleague's CorridorKey settings and logs**
(remembered output folder, GPU choice; not their output files):
- **(a) Recommended:** removed too, a clean uninstall. Upgrades always keep
  them.
- (b) Kept, in case CorridorKey is reinstalled later.

**Q8. Discovery file for the future N0DUS node.**
- **(a) Recommended:** `%LOCALAPPDATA%\CorridorKey\install.json` as in §7.
- (b) A registry entry under `HKCU\Software\CorridorKey` instead.
- (c) Both.

**Q9. Where the pack repo lives.**
- **(a) Recommended:** `Q:\tools\ck-pack\` (where this plan is), local git
  only. The payload goes in `Q:\tools\ck-pack-payload\`.
- (b) The same folders, and also pushed to a private project on the studio's
  own GitLab.
- (c) Somewhere else: tell me where.

**Q10. ffmpeg.**
- **(a) Recommended:** the gyan.dev 6.0 "essentials" GPL build, the same
  version the colour fix was measured with. The licence and source are kept
  with the pack.
- (b) An LGPL build with a different video encoder. That changes the output,
  so the colour and quality checks would need redoing.
