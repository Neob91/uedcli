"""Burn an N/E/S/W compass into a top-view diagram's corner. TOP view:
+X -> screen-right = East, +Y -> screen-down = South
(dev/docs/unrealed/rendering.md's documented ortho convention)."""
from PIL import Image, ImageDraw, ImageFont

def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def add_compass(path):
    im = Image.open(path).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cx, cy = 62, 78
    r = 34
    d.ellipse([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6], fill=(10, 11, 8, 200))
    f = _font(15)
    pts = {"N": (cx, cy - r), "S": (cx, cy + r), "E": (cx + r, cy), "W": (cx - r, cy)}
    for _, (x, y) in pts.items():
        d.line([cx, cy, x, y], fill=(224, 194, 116, 255), width=2)
    for label, (x, y) in pts.items():
        bbox = d.textbbox((0, 0), label, font=f)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx, ty = x, y
        if label == "N": ty -= 16
        if label == "S": ty += 2
        if label == "E": tx += 4
        if label == "W": tx -= w - 4
        d.text((tx - w / 2, ty - h / 2), label, font=f, fill=(255, 245, 220, 255))
    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(224, 194, 116, 255))
    Image.alpha_composite(im, overlay).convert("RGB").save(path)
