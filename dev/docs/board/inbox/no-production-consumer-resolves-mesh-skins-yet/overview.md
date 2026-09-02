+++
priority = "p3"
kind = "implement"
summary = "Mesh skins are resolved only by two spike harnesses, so no test can render one end to end."
+++

# No production consumer resolves mesh skins yet

**Recorded while building board item `native-texture-decode`, whose spec required "one mesh-skin
case covered for every format this build adds". What was actually achievable is written below,
so the gap is visible rather than implied by a passing test.**

## What a mesh skin is, and who resolves one

A UE1 mesh does not carry its own pixels. It carries *skin* references — texture names like
`DeusExItems.Ammo10mmTex` — that a renderer looks up in the packages on the search path, decodes
to pixels, and maps onto the mesh's triangles.

**Nothing under `uedcli/` does that lookup.** The only two callers are spike harnesses:
`dev/docs/spikes/2026-07-25-native-mesh-decode/harness/render.py` and `render_class.py`.
`rules/spikes.md` makes a committed harness durable evidence rather than scratch, so they are
real surface — but they are scripts run by hand, they need a mesh package the offline suite does
not have, and the suite cannot import them.

## What IS covered

- Every pixel format the decoder now reads — P8, BC1, BC2, BC3 — resolves through a
  skin-shaped reference (`Package.Name`, with any Group segment dropped, which is exactly the
  string both harnesses build).
- An undecodable skin returns a typed error carrying the offending reference, which is what the
  harnesses print when they refuse.
- A static check that neither harness still treats the truthy error object as an image.

## What is NOT covered

An end-to-end render: mesh geometry plus a decoded skin plus a rasterized frame. It cannot be,
until something in the shipped tool resolves skins.

## When to close this

When the class-preview arm lands — `class preview --textured`, specced in board item
`unified-asset-catalog` — it becomes the first production skin consumer. Add the end-to-end
case then, and delete this item.
