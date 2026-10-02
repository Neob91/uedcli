+++
priority = "p2"
kind = "implement"
summary = "Confirm native mesh rendering holds on stock Unreal/UT99 meshes, not just Deus Ex"
depends-on = ["native-mesh-rendering-in-level-photo-native"]
+++

# Validate native mesh render against stock Unreal UT99 meshes

`native-mesh-rendering-in-level-photo-native` builds and validates against Deus Ex first
(`umesh.py`'s decoder is already substrate-generic: same code reads DX v68 8-byte verts and stock
Unreal/UT v69 packed verts, no flag). Owner direction: keep Unreal in mind in that item's
architecture so it needs no rework, but treat verifying it as separate, explicit tracked work
rather than an implicit footnote — this item is that tracker.

Scope: run the same mesh-instancing/rendering code path against Unreal or UT99 level + mesh content
(decorations/items/characters), same visual bar as the DX validation (correct shape/place/pose/skin
vs `--game`, no pixel-parity requirement). Close if it passes with no changes; if it surfaces a
DX-only assumption, fix it and record what broke.
