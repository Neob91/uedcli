"""Base-texture atlas assembly for `uedcli serve` (plan Task 3): packs `build_scene`'s
`texture_table` (`list[(w, h, rgb, mask)]`, the SAME cached solve the scene endpoint uses — never a
second decode path) into one RGBA image with a manifest keyed by table index.

Whether a poly alpha-tests against the atlas is decided PER-POLY by the scene payload's `masked`
flag, not baked here — a non-masked poly using a texture whose `mask` marks index-0 texels must
still render solid. The atlas therefore always carries every entry's real per-texel `mask` as its
alpha channel; the client's material split (Task 6) is what applies or ignores it."""
from __future__ import annotations

import io
from dataclasses import dataclass

from .atlas_pack import pack_rects


@dataclass(frozen=True, kw_only=True)
class AtlasRect:
    """One packed atlas entry -- `web/src/api.ts`'s `AtlasRect` TS interface is the contract, same
    field names/types. `name` is the real `Package.Group.Name` (or `Package.Name` when the export
    has no group) for a brush-poly entry (`preview_native.py`'s `_TextureTable.index_for`, real
    export-backed) -- `None` for a mesh-skin entry (`index_for_decoded`, no export index) or when no
    `groups` value was supplied for this index at all."""
    x: int
    y: int
    w: int
    h: int
    name: str | None


def build_atlas(texture_table: list[tuple[int, int, bytes, bytes]],
                groups: list[str | None]) -> tuple[bytes, dict[int, AtlasRect], int, int]:
    """`texture_table` → `(png_bytes, manifest, width, height)`. `manifest` is `{tex_index:
    AtlasRect}`, one rect per table entry (mesh-skin entries included — polys index into the same
    table). An empty table still returns a valid (1x1 transparent) PNG, never a crash on a level
    with no textured surfaces at all.

    `groups` is parallel to `texture_table` (`_TextureTable.group_for(i)` for each index, the
    caller's own texture-resolution pass) and becomes each rect's `name` — `None` for an index
    `groups` doesn't cover (a mesh-skin entry, or `groups` shorter than `texture_table`)."""
    from PIL import Image

    sizes = [(w, h) for w, h, _rgb, _mask in texture_table]
    atlas_w, atlas_h, positions = pack_rects(sizes)
    atlas_w, atlas_h = max(atlas_w, 1), max(atlas_h, 1)
    img = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))
    manifest: dict[int, AtlasRect] = {}
    for idx, ((w, h, rgb, mask), (x, y)) in enumerate(zip(texture_table, positions)):
        name = groups[idx] if idx < len(groups) else None
        manifest[idx] = AtlasRect(x=x, y=y, w=w, h=h, name=name)
        rgb_img = Image.frombytes("RGB", (w, h), rgb)
        alpha_img = Image.frombytes("L", (w, h), bytes(b * 255 for b in mask))
        rgba_img = rgb_img.convert("RGBA")
        rgba_img.putalpha(alpha_img)
        img.paste(rgba_img, (x, y))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue(), manifest, atlas_w, atlas_h
