"""Print a small ASCII map of a screenshot region, marking pixels of a given RGB.
Used to see the pivot marker's exact plus/dot shape."""
import sys
from PIL import Image

path, cx, cy = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
col = tuple(int(v) for v in sys.argv[4].split(",")) if len(sys.argv) > 4 else (255, 63, 63)
rad = int(sys.argv[5]) if len(sys.argv) > 5 else 10
im = Image.open(path).convert("RGB")
px = im.load()
print(f"{path} around ({cx},{cy}) marking {col}")
hdr = "     " + "".join(str((cx + dx) % 10) for dx in range(-rad, rad + 1))
print(hdr)
for dy in range(-rad, rad + 1):
    row = "".join("#" if px[cx + dx, cy + dy] == col else "." for dx in range(-rad, rad + 1))
    print(f"{cy + dy:4} {row}")
