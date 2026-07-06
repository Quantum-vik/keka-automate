"""
Generate the Auto-Keka app icon (teal rounded square + white clock).

    python packaging/make_icon.py <out.png|out.ico> [size]

Writes a PNG, or a multi-resolution ICO if the path ends in .ico (Windows).
Shared by the per-OS packaging scripts.
"""
import sys
from PIL import Image, ImageDraw


def make(size=1024):
    S = size
    c1, c2 = (0x14, 0xc2, 0xa5), (0x0a, 0x8d, 0x7b)   # design logo gradient
    grad = Image.new("RGB", (S, S))
    d = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / S
        d.line([(0, y), (S, y)], fill=tuple(int(c1[i] + (c2[i]-c1[i])*t) for i in range(3)))
    pad, r = int(S*0.088), int(S*0.205)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, S-pad, S-pad], radius=r, fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(grad, (0, 0), mask)
    dr = ImageDraw.Draw(icon)
    cx = cy = S // 2
    R, w = int(S*0.226), max(2, int(S*0.045))
    dr.ellipse([cx-R, cy-R, cx+R, cy+R], outline=(255, 255, 255, 255), width=w)

    def hand(dx, dy):
        dr.line([cx, cy, cx+dx, cy+dy], fill=(255, 255, 255, 255), width=w)
        dr.ellipse([cx+dx-w//2, cy+dy-w//2, cx+dx+w//2, cy+dy+w//2], fill=(255, 255, 255, 255))
    hand(0, int(-S*0.146))
    hand(int(S*0.109), int(S*0.043))
    dr.ellipse([cx-w//2, cy-w//2, cx+w//2, cy+w//2], fill=(255, 255, 255, 255))
    return icon


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "auto-keka.png"
    icon = make(1024)
    if out.lower().endswith(".ico"):
        icon.save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    else:
        icon.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
