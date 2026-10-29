# CorridorKey — how to install it

CorridorKey is an AI keyer: give it green- or blue-screen footage or images and it
gives back the subject with a clean alpha (transparency). This pack installs it
on your PC with everything it needs. **No internet, no admin rights.**

**Studio-internal only.** Please don't pass the installer to anyone outside the
company.

## What you need

- Windows 10 (version 22H2) or Windows 11
- An NVIDIA graphics card, **RTX 30-series or newer** (RTX 3060, 4070, 5080, RTX A4000…),
  with at least 6 GB of graphics memory. 8 GB or more is recommended; with
  6–8 GB only small clips fit.
- An NVIDIA driver from 2025 or later (version 570.65 or newer)
- About **12 GB free** disk space

If any of these is missing, the installer says so in plain words and installs
nothing.

## Install

1. Copy the whole **CorridorKey Pack** folder to your PC (or open it from the
   share). It holds two files that must stay together:
   `CorridorKey-Setup.exe` and `CorridorKey-Setup-1.bin`.
2. Double-click **CorridorKey-Setup.exe**.
   - If Windows says *"Windows protected your PC"*, click **More info**, then
     **Run anyway**. (The installer isn't code-signed; that's normal for our
     internal tools.)
3. Accept the note, keep the suggested folder (or choose another one with a
   plain-English path), click **Install**. It takes about 5 minutes.
4. At the end the installer tests CorridorKey on your graphics card. The last page
   says **PASSED** or **FAILED**.
   - **FAILED?** Tick "Show the self-test log" and send that log to whoever gave
     you the installer.

## Use

Start menu → **CorridorKey**. Drop clips (`.mp4`, `.mov`), images (`.png`, `.jpg`)
or a folder of numbered frames onto the window, choose an output folder, click
**Start**.

- Videos give `<name>_fg.mp4` + `<name>_alpha.mp4`; images give `<name>_key.png`
  (with transparency) + `<name>_alpha.png`.
- The output folder can't be inside CorridorKey's own install folder: updates
  and uninstalling replace that folder.
- **About** shows the version, the self-test result and all licences.

## Update or remove

- **Update:** run a newer installer. It keeps your settings (output folder, GPU
  memory choice) and replaces everything else.
- **Remove:** Windows Settings → Apps → CorridorKey → Uninstall. This removes
  CorridorKey and its settings. **Your output files are never touched.**
