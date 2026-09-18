"""Report distinctly-coloured (non-grey) pixels in a screenshot region, grouped into clusters.
Used to locate brush wireframes and the pivot marker in the editor's ortho panes."""
import sys
from collections import defaultdict
from PIL import Image

path = sys.argv[1]
x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6])
im = Image.open(path).convert("RGB")
px = im.load()
buckets = defaultdict(list)
for y in range(y0, y1):
    for x in range(x0, x1):
        r, g, b = px[x, y]
        if max(r, g, b) - min(r, g, b) < 25:      # grey-ish chrome/grid
            continue
        buckets[(r, g, b)].append((x, y))
for col, pts in sorted(buckets.items(), key=lambda kv: -len(kv[1]))[:14]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    print(f"{col}  n={len(pts):5}  x[{min(xs)}..{max(xs)}] y[{min(ys)}..{max(ys)}]")
