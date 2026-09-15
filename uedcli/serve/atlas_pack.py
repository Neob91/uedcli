"""Shelf rect-packer shared by `textures.py` (base-texture atlas) and `lightmap.py` (lightmap
atlas) — the two were byte-identical copies (review finding); the "kept separate so the two
atlases can size independently" rationale doesn't hold since the function is already pure and
parameterized by its caller's own `sizes`."""
from __future__ import annotations

MAX_ATLAS_WIDTH = 2048


def pack_rects(sizes: list[tuple[int, int]], *, max_width: int = MAX_ATLAS_WIDTH
               ) -> tuple[int, int, list[tuple[int, int]]]:
    """Shelf-pack `sizes` (w, h) left to right, wrapping at `max_width` (or the widest single entry,
    if that alone exceeds it). Returns `(atlas_w, atlas_h, positions)`, `positions[i]` the `(x, y)`
    origin of `sizes[i]`. Not space-optimal — callers need a correct index→rect mapping, not a dense
    pack."""
    if not sizes:
        return 0, 0, []
    max_w = max(w for w, _h in sizes)
    target_w = max(max_w, min(max_width, sum(w for w, _h in sizes)))
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
