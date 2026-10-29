"""Draw the pack's synthetic test media. No company art: everything is generated.

  green_test.png  1024x576 chroma-green screen, a lit grey/orange "figure"
                  (head + shoulders + arm) with soft edges and light grain.
  blue_test.png   the same figure on a chroma-blue screen.
  green_clip.mp4  48 frames, 24 fps: the figure sways left/right (only with --clip,
                  needs ffmpeg: --ffmpeg PATH).
  regions.json    boxes the self-test checks (x0, y0, x1, y1; image coordinates,
                  origin top-left): "background" must key to alpha ~0, "subject"
                  to alpha ~1.

Deterministic (fixed seed), so the same script always draws the same pixels.

    python make_test_media.py OUT_DIR [--clip --ffmpeg ffmpeg.exe]
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1024, 576
GREEN = (0.12, 0.70, 0.24)    # a typical lit chroma-green, sRGB 0..1
BLUE = (0.07, 0.20, 0.82)     # a typical chroma-blue
REGIONS = {"background": [16, 16, 112, 112], "subject": [472, 300, 552, 380]}


def figure_mask(dx: float = 0.0) -> np.ndarray:
    """Soft-edged coverage 0..1 of the figure, shifted dx pixels horizontally."""
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    cx = W / 2 + dx
    d.ellipse([cx - 70, 110, cx + 70, 270], fill=255)                     # head
    d.rounded_rectangle([cx - 150, 250, cx + 150, H + 40], 60, fill=255)  # shoulders/body
    d.polygon([(cx + 140, 300), (cx + 260, 210), (cx + 285, 235), (cx + 160, 350)], fill=255)  # arm
    m = m.filter(ImageFilter.GaussianBlur(2.2))   # soft edge, like real footage
    return np.asarray(m, dtype=np.float32) / 255.0


def figure_colour(dx: float = 0.0, seed: int = 7) -> np.ndarray:
    """A lit figure: grey body, orange top, vertical light falloff, light grain."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.empty((H, W, 3), np.float32)
    base[...] = (0.55, 0.55, 0.57)
    top = yy < 280
    base[top] = (0.86, 0.52, 0.30)
    light = 1.05 - 0.35 * (yy / H) + 0.08 * np.cos((xx - W / 2 - dx) / 180.0)
    rng = np.random.default_rng(seed)
    grain = rng.normal(0.0, 0.012, (H, W, 1)).astype(np.float32)
    return np.clip(base * light[..., None] + grain, 0.0, 1.0)


def screen(colour, seed: int = 11) -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vign = 1.0 - 0.10 * (((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2) * 4
    rng = np.random.default_rng(seed)
    grain = rng.normal(0.0, 0.008, (H, W, 1)).astype(np.float32)
    return np.clip(np.array(colour, np.float32) * vign[..., None] + grain, 0.0, 1.0)


def frame(colour, dx: float = 0.0) -> np.ndarray:
    a = figure_mask(dx)[..., None]
    img = figure_colour(dx) * a + screen(colour) * (1.0 - a)
    return (np.rint(img * 255.0)).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--clip", action="store_true")
    ap.add_argument("--ffmpeg", default=None)
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame(GREEN)).save(out / "green_test.png", optimize=False)
    Image.fromarray(frame(BLUE)).save(out / "blue_test.png", optimize=False)
    (out / "regions.json").write_text(json.dumps(
        {"image": "green_test.png", "size": [W, H], **REGIONS,
         "note": "x0,y0,x1,y1 in image pixels, origin top-left"}, indent=1) + "\n")
    if a.clip:
        if not a.ffmpeg:
            raise SystemExit("--clip needs --ffmpeg PATH (the pack never uses ffmpeg from PATH)")
        n = 48
        raw = b"".join(frame(GREEN, 60.0 * np.sin(2 * np.pi * i / n)).tobytes() for i in range(n))
        cmd = [a.ffmpeg, "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{W}x{H}", "-r", "24", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-crf", "16", "-preset", "medium", "-bitexact", str(out / "green_clip.mp4")]
        subprocess.run(cmd, input=raw, check=True)
    print(f"test media written to {out}")


if __name__ == "__main__":
    main()
