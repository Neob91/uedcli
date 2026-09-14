"""Base-texture atlas assembly for `uedcli serve` (plan Task 3): packs `build_scene`'s
`texture_table` (`list[(w, h, rgb, mask)]`, the SAME cached solve the scene endpoint uses — never a
second decode path) into one RGBA image with a manifest keyed by table index.

Whether a poly alpha-tests against the atlas is decided PER-POLY by the scene payload's `masked`
flag, not baked here — a non-masked poly using a texture whose `mask` marks index-0 texels must
still render solid. The atlas therefore always carries every entry's real per-texel `mask` as its
alpha channel; the client's material split (Task 6) is what applies or ignores it."""
from __future__ import annotations

import io

_MAX_ATLAS_WIDTH = 2048


def _pack_rects(sizes: list[tuple[int, int]]) -> tuple[int, int, list[tuple[int, int]]]:
    """Shelf-pack `sizes` (w, h), left to right, wrapping at `_MAX_ATLAS_WIDTH` (or the widest
    single entry, if that alone exceeds it). Returns `(atlas_w, atlas_h, positions)`, `positions[i]`
    the `(x, y)` origin of `sizes[i]`. Not space-optimal — Slice 1 needs a correct index→rect
    mapping, not a dense pack."""
    if not sizes:
        return 0, 0, []
    max_w = max(w for w, _h in sizes)
    target_w = max(max_w, min(_MAX_ATLAS_WIDTH, sum(w for w, _h in sizes)))
    x = y = shelf_h = 0
    atlas_w = 0
    positions = []
    for w, h in sizes:
        if x and x + w > target_w:
            y += shelf_h
            x = 0
            shelf_h = 0
        positions.append((x, y))
        atlas_w = max(atlas_w, x + w)
        shelf_h = max(shelf_h, h)
        x += w
    return atlas_w, y + shelf_h, positions


def build_atlas(texture_table: list[tuple[int, int, bytes, bytes]]) -> tuple[bytes, dict, int, int]:
    """`texture_table` → `(png_bytes, manifest, width, height)`. `manifest` is `{tex_index: {x, y,
    w, h}}`, one rect per table entry (mesh-skin entries included — polys index into the same
    table). An empty table still returns a valid (1x1 transparent) PNG, never a crash on a level
    with no textured surfaces at all."""
    from PIL import Image

    sizes = [(w, h) for w, h, _rgb, _mask in texture_table]
    atlas_w, atlas_h, positions = _pack_rects(sizes)
    atlas_w, atlas_h = max(atlas_w, 1), max(atlas_h, 1)
    img = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))
    manifest: dict[int, dict[str, int]] = {}
    for idx, ((w, h, rgb, mask), (x, y)) in enumerate(zip(texture_table, positions)):
        manifest[idx] = {"x": x, "y": y, "w": w, "h": h}
        rgb_img = Image.frombytes("RGB", (w, h), rgb)
        alpha_img = Image.frombytes("L", (w, h), bytes(b * 255 for b in mask))
        rgba_img = rgb_img.convert("RGBA")
        rgba_img.putalpha(alpha_img)
        img.paste(rgba_img, (x, y))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue(), manifest, atlas_w, atlas_h
