"""Lightmap-atlas assembly for `uedcli serve`: packs every lit poly's baked lumel grid
(`build_scene`'s per-poly `lightmap` tuple, the SAME cached solve the scene/texture endpoints use)
into one RGB image, mirroring `textures.py`.

The baked lumel value is a MULTIPLIER against the base texel (`render.rs`: `final = base * value`,
clamped to 255), 1.0 = neutral, UNCLAMPED (overbright > 1.0 is common). An 8-bit atlas can't hold a
value above 1.0, so the whole atlas is scaled by one `intensity` = `max(1.0, global_max)`: each
lumel stores `value/intensity` in `[0, 1]`, and the client sets `lightMapIntensity = intensity`, so
`stored * intensity` recovers the value (three.js multiplies `map * (lightMapTexel * intensity)` —
the same product `render.rs` computes).

Each patch gets a 1-lumel edge-replicated gutter so nearest-sampling a UV just past the grid edge
clamps to the edge lumel (matching `render.rs`'s per-axis clamp) instead of bleeding into the
neighbouring patch. Polys sharing a surf share one packed patch (deduped by lightmap identity)."""
from __future__ import annotations

import io

from .atlas_pack import pack_rects


def _pad_edges(interior, w: int, h: int):
    """`interior` (a `w×h` PIL image) → a `(w+2)×(h+2)` image with the interior at `(1, 1)` and a
    1-pixel edge-REPLICATED border (not a solid fill), so nearest-sampling one texel past an edge
    clamps to the edge lumel."""
    from PIL import Image

    padded = Image.new("RGB", (w + 2, h + 2))
    padded.paste(interior, (1, 1))
    padded.paste(interior.crop((0, 0, 1, h)), (0, 1))                    # left column
    padded.paste(interior.crop((w - 1, 0, w, h)), (w + 1, 1))           # right column
    padded.paste(interior.crop((0, 0, w, 1)), (1, 0))                    # top row
    padded.paste(interior.crop((0, h - 1, w, h)), (1, h + 1))           # bottom row
    padded.paste(interior.crop((0, 0, 1, 1)), (0, 0))                    # corners
    padded.paste(interior.crop((w - 1, 0, w, 1)), (w + 1, 0))
    padded.paste(interior.crop((0, h - 1, 1, h)), (0, h + 1))
    padded.paste(interior.crop((w - 1, h - 1, w, h)), (w + 1, h + 1))
    return padded


def build_lightmap_atlas(polys: list[tuple]) -> tuple[bytes, dict, int, int, float]:
    """`build_scene`'s poly list (each tuple's last field is the lightmap `(origin, u_step, v_step,
    u_size, v_size, rgb)` or None) → `(png_bytes, manifest, width, height, intensity)`. `manifest`
    is `{poly_index: {x, y, w, h}}` — the INTERIOR rect (inside the gutter) of the poly's lumel
    patch, for every poly that has a lightmap. A level with no lit polys returns a 1×1 PNG,
    `intensity` 1.0, empty manifest (never a crash)."""
    from PIL import Image

    lit = [(i, poly[-1]) for i, poly in enumerate(polys) if poly[-1] is not None]

    global_max = 0.0
    for _i, lm in lit:
        rgb = lm[5]
        if rgb:
            global_max = max(global_max, max(rgb))
    intensity = max(1.0, global_max)

    # Dedup by lightmap identity: polys sharing a surf carry the SAME tuple object (build_scene's
    # `radiance_by_surf.get(i_surf)`), so one packed patch serves them all.
    unique: dict[int, int] = {}                          # id(lightmap) -> unique-patch index
    patches: list[tuple] = []                            # (u_size, v_size, rgb)
    poly_to_patch: dict[int, int] = {}
    for i, lm in lit:
        key = id(lm)
        patch_index = unique.get(key)
        if patch_index is None:
            patch_index = len(patches)
            unique[key] = patch_index
            patches.append((lm[3], lm[4], lm[5]))
        poly_to_patch[i] = patch_index

    padded_sizes = [(max(w, 1) + 2, max(h, 1) + 2) for w, h, _rgb in patches]
    atlas_w, atlas_h, positions = pack_rects(padded_sizes)
    atlas_w, atlas_h = max(atlas_w, 1), max(atlas_h, 1)
    img = Image.new("RGB", (atlas_w, atlas_h), (0, 0, 0))

    patch_rects: list[dict[str, int]] = []
    for (w, h, rgb), (gx, gy) in zip(patches, positions):
        w, h = max(w, 1), max(h, 1)
        data = bytes(_encode(v, intensity) for v in rgb) if rgb else bytes(3 * w * h)
        interior = Image.frombytes("RGB", (w, h), data)
        img.paste(_pad_edges(interior, w, h), (gx, gy))
        patch_rects.append({"x": gx + 1, "y": gy + 1, "w": w, "h": h})

    manifest = {poly_index: patch_rects[patch] for poly_index, patch in poly_to_patch.items()}
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue(), manifest, atlas_w, atlas_h, intensity


def _encode(value: float, intensity: float) -> int:
    """One lumel channel (a `value/intensity`-scaled multiplier) → an 8-bit byte, clamped to
    `[0, 255]`. `intensity >= global_max >= value >= 0`, so the clamp is a safety net, not a
    lossy crush of overbright (that's what `intensity` preserves)."""
    scaled = round(value / intensity * 255.0)
    return 0 if scaled < 0 else 255 if scaled > 255 else scaled
