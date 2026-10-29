"""Draw the pack's icon (no company art): a green rounded square with a white
key-hole silhouette, as a multi-size .ico.

    python make_icon.py OUT.ico
"""
import sys

from PIL import Image, ImageDraw


def draw(size: int) -> Image.Image:
    s = 256
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([8, 8, s - 8, s - 8], 48, fill=(31, 160, 72, 255))
    d.ellipse([88, 52, 168, 132], fill=(255, 255, 255, 255))        # key-hole head
    d.polygon([(110, 118), (146, 118), (164, 204), (92, 204)], fill=(255, 255, 255, 255))
    return im.resize((size, size), Image.LANCZOS)


def main():
    out = sys.argv[1]
    big = draw(256)
    big.save(out, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"icon written to {out}")


if __name__ == "__main__":
    main()
