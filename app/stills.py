"""Still images and numbered frame folders for ck_run.py.

CorridorKey reads a frame FOLDER (never a single image): every *.exr/*.png/
*.jpg/*.jpeg in it, in plain sorted() order, through cv2.imread(IMREAD_COLOR)
-- 8-bit RGB, alpha dropped, 16-bit reduced to 8-bit -- treated as sRGB
exactly like video frames. Its only lossless output is a scene-linear EXR
sequence. So: a single image becomes a 1-frame folder; a folder is passed
through as-is when CorridorKey would read exactly our sequence in our order,
otherwise an ordered copy is staged; the EXRs are converted to PNG here.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

IMAGE_EXT = {".png", ".jpg", ".jpeg"}
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
CK_READS = {".exr", ".png", ".jpg", ".jpeg"}   # what CorridorKey's frame_paths() globs
FRAME_RE = re.compile(r"^(.*?)(\d+)\.(png|jpe?g)$", re.IGNORECASE)


class StillError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def classify(path: Path) -> str:
    if path.is_dir():
        return "sequence"
    ext = path.suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    return "unsupported"


def probe_image(path: Path) -> dict:
    from PIL import Image
    try:
        with Image.open(path) as im:
            w, h = im.size
            bands = im.getbands()
            mode = im.mode
            has_alpha = "A" in bands or (mode == "P" and "transparency" in im.info)
            transparent = False
            if has_alpha:
                a = (im.convert("RGBA") if mode == "P" else im).getchannel("A")
                lo, hi = a.getextrema()
                transparent = lo < 255  # any pixel not fully opaque
    except Exception as e:
        raise StillError("input_unreadable", f"Cannot read image {path.name}: {e}")
    return {"width": w, "height": h, "mode": mode, "has_alpha": has_alpha, "transparent": transparent}


def scan_sequence(folder: Path) -> dict:
    """Validate a folder of numbered frames; numeric order, one prefix/extension."""
    entries = [p for p in folder.iterdir() if p.is_file()]
    images = [p for p in entries if p.suffix.lower() in IMAGE_EXT]
    if not images:
        vids = [p.name for p in entries if p.suffix.lower() in VIDEO_EXT]
        hint = f" It holds videos ({', '.join(vids[:3])}); drop those as files." if vids else ""
        raise StillError("no_frames", f"No .png/.jpg frames in folder {folder.name}.{hint}")
    parsed, unnumbered = [], []
    for p in images:
        m = FRAME_RE.match(p.name)
        if m:
            parsed.append((m.group(1), int(m.group(2)), m.group(2), m.group(3).lower().replace("jpeg", "jpg"), p))
        else:
            unnumbered.append(p.name)
    if unnumbered:
        raise StillError("not_a_sequence", f"{folder.name}: frames must be numbered (name_0001.png); "
                                           f"not numbered: {', '.join(unnumbered[:3])}")
    kinds = {(pre, ext) for pre, _, _, ext, _ in parsed}
    if len(kinds) > 1:
        raise StillError("mixed_sequence", f"{folder.name} mixes sequences or formats: "
                                           + ", ".join(f"{pre}####.{ext}" for pre, ext in sorted(kinds)[:4]))
    parsed.sort(key=lambda x: x[1])
    nums = [n for _, n, _, _, _ in parsed]
    if len(set(nums)) != len(nums):
        raise StillError("duplicate_frames", f"{folder.name}: a frame number appears twice")
    prefix = parsed[0][0]
    name = prefix.rstrip("._- ") or folder.name
    files = [p for *_, p in parsed]
    gaps = [b for a, b in zip(nums, nums[1:]) if b != a + 1]
    # Pass through only if CorridorKey's own glob+sorted() reads exactly these, in this order.
    ck_list = sorted(str(p) for p in entries if p.suffix.lower() in CK_READS)
    direct = ck_list == [str(p) for p in files]
    return {"name": name, "files": files, "numbers": nums, "pad": max(4, max(len(s) for _, _, s, _, _ in parsed)),
            "ext": parsed[0][3], "gaps": gaps, "direct": direct}


def check_sequence_frames(files: list[Path]) -> dict:
    """Size of every frame (header only) must match; alpha checked on a sample."""
    first = probe_image(files[0])
    from PIL import Image
    for p in files[1:]:
        with Image.open(p) as im:
            if im.size != (first["width"], first["height"]):
                raise StillError("frame_size_mismatch", f"{p.name} is {im.size[0]}x{im.size[1]}, "
                                                        f"the first frame is {first['width']}x{first['height']}")
    step = max(1, len(files) // 11)
    sample = sorted(set(files[::step]) | {files[-1]})
    transparent = [p.name for p in sample if probe_image(p)["transparent"]]
    return {**first, "transparent_frames": transparent, "alpha_sampled": len(sample)}


def stage_sequence(files: list[Path], ext: str, dst: Path):
    """Ordered COPY CorridorKey can read: 000000.png, 000001.png, ... A copy, never a
    hardlink, so nothing downstream can ever reach the original's bytes."""
    dst.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(files):
        shutil.copyfile(p, dst / f"{i:06d}.{ext}")


def linear_to_srgb(x):
    """IEC 61966-2-1, the same equations as corridorkey.color_utils.linear_to_srgb."""
    import numpy as np
    x = np.maximum(x, 0.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.maximum(x, 0.0031308), 1 / 2.4) - 0.055)


def exr_to_png(fg_exr: Path, alpha_exr: Path, key_png: Path, alpha_png: Path, bits: int = 8):
    """fg (scene-linear EXR) -> sRGB, the video route's own conversion (clamp >= 0,
    IEC sRGB, clip [0,1]); RGBA PNG with STRAIGHT alpha (fg is not premultiplied).
    The alpha matte is written as-is: it is coverage, not colour, so no transfer."""
    import cv2
    import numpy as np
    fg = cv2.imread(str(fg_exr), cv2.IMREAD_UNCHANGED)
    a = cv2.imread(str(alpha_exr), cv2.IMREAD_UNCHANGED)
    if fg is None or a is None:
        raise StillError("exr_unreadable", f"cannot read {fg_exr.name} / {alpha_exr.name}")
    if a.ndim == 3:
        a = a[..., 0]
    srgb = np.clip(linear_to_srgb(fg.astype(np.float32)), 0.0, 1.0)   # BGR order, as read
    a = np.clip(a.astype(np.float32), 0.0, 1.0)
    scale, dtype = (255.0, np.uint8) if bits == 8 else (65535.0, np.uint16)
    q = lambda v: np.rint(v * scale).astype(dtype)
    bgra = np.dstack([q(srgb), q(a)])
    for img, path in ((bgra, key_png), (q(a), alpha_png)):
        part = path.with_name(path.name + ".part.png")
        if not cv2.imwrite(str(part), img):
            raise StillError("png_write_failed", f"could not write {path}")
        os.replace(part, path)
