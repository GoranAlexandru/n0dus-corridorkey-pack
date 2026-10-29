# The pack's app vs the reference app

Baseline: `Q:\tools\CorridorKey2.0\app\` as of 2026-10-28, committed unmodified
as commit "Copy the app verbatim from the reference" so every change below is
its own diff (`git diff 67c4bcb -- app/`). The reference itself is never
touched. **Nothing in how CorridorKey keys changed**: same upstream `infer.py`,
same flags, same window choice, same colour-tag fix.

| # | Change | Files | Why (PACK_PLAN.md) |
|---|---|---|---|
| 1 | Private Python is `python\python.exe` (no venv); every child Python starts with `-I` (isolated: ignores `PYTHONPATH`, `PYTHONHOME`, user site-packages) | `ck_run.py`, `ck_gui.py`, `ck_env.py` | §3 ruling Q2 a, §5 |
| 2 | ffmpeg / ffprobe by full path to the bundled copy; `--ffmpeg_bin <full path>` passed to upstream `infer.py` (it already had the option) | `ck_run.py`, `vram_plan.py` | §1.2: the reference used whatever ffmpeg was on PATH |
| 3 | `ck_env.apply()` cleans the environment of the window and the runner before anything starts, so every child inherits it: removes `PYTHON*`/`CONDA_*`/`VIRTUAL_ENV`/`PIP_*`, `PYTHONNOUSERSITE=1`, PATH cut to Windows' folders + the private Python, `TEMP`/`TMP`/HF/torch/NVIDIA caches inside the install, offline flags, `CUDA_DEVICE_ORDER=PCI_BUS_ID` | new `ck_env.py`; called from `ck_run.py`, `ck_gui.py`, `selftest.py` | §5; the Anaconda trap (SETUP_RECIPE.md "Install" step 2) |
| 4 | `nvidia-smi` / `taskkill` by full path (System32) | `gpu_win.py`, `ck_gui.py` | §5 (PATH not trusted) |
| 5 | `settings.json` and `logs\` moved from `app\` to `data\` | `ck_run.py`, `ck_gui.py`, `ck_env.py` | §10: upgrades replace `app\` and keep `data\` |
| 6 | Output folder inside the install folder is refused, by the runner (error `output_inside_install`) and by the window (Browse and Start) | `ck_run.py`, `ck_gui.py` | §9.3-5: uninstall/upgrade can never reach the user's outputs |
| 7 | "About" button: version, CorridorKey attribution, studio-internal note, self-test result, opens the licences folder; the status line says so if the install self-test failed | `ck_gui.py` | §8 (attribution where people look), §6 |
| 8 | Named mutex `CorridorKeyPack.App`, held by the window and the runner, so the installer can ask "please close CorridorKey" during upgrade/uninstall | `ck_env.py`, `ck_run.py`, `ck_gui.py` | §9.3-7 |
| 9 | Installer self-test + `install.json` discovery file | new `selftest.py` (+ `verify.py` copied in from `scripts\` at build) | §6, §7 |

Not carried over from the reference: `Start CorridorKey.bat` (the Start-menu
shortcut starts `pythonw.exe -I app\ck_gui.py` directly; no console window),
`settings.json` (the owner's own), `logs\`.

Left out of the install from upstream CorridorKey (no code changed):
`CorridorKey_DRAG_CLIPS_HERE.bat` / `.sh`. Without a `venv\` folder they fall
back to whatever `python` is on PATH, exactly what the pack exists to avoid.
The Start-menu window replaces them. Every other upstream file is installed
byte-for-byte.

## Proof that keying is unchanged

`tests/equivalence.py` keyed the synthetic still and 48-frame clip with the
reference install's own Python + upstream `infer.py`, and with the installed
pack's runner (same window), using the same ffmpeg. Result 2026-10-29: still
key/alpha pixel-identical, clip fg/alpha decoded frames identical (all 48).
See `docs/owner.md` §7.
