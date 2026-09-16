+++
priority = "p?"
kind = "unknown"
summary = "GUI shading modes omit UnrealEd's Zones view mode"
+++

# GUI shading modes omit UnrealEd's Zones view mode

Filed from a UED22-vs-GUI-spec gap audit (2026-09-15) of `dev/docs/board/to-plan/uedcli-human-gui/
spec.md` and `dev/docs/board/to-build/gui-slice-2-quad-layout-ortho-views-matching/spec.md`.

## UED22 fact

`dev/docs/unrealed/rendering.md` "Render modes (`RendMap`/`REN=`/`RMODE`)" documents the real,
numeric per-viewport render-mode enum (shared by `[U2Viewport*] RendMap`, `RMODE <n>`, and
`CAMERA … REN=`): `1`=Wire, `2`=Zones, `3`=Polys, `5`=DynLight, `6`=PlainTex (textured fullbright),
`13/14/15`=Orth XY/XZ/YZ, `16`=TexView, `17`=TexBrowser, `18`=MeshView. Of the five real level-editing
view modes (excluding the orthographic-projection and browser/utility entries), **`Zones` (`2`) is a
first-class UnrealEd view mode** — it color-codes the built level by zone membership, alongside
Wire/Polys/DynLight/PlainTex. `dev/docs/board/to-spec/zones/spec.md` independently confirms zones are
a real, load-bearing UnrealEngine-1 concept (`ZoneInfo` actors, `PF_Portal` surfaces, a 64-zone cap,
`BSP REBUILD ZONES`) that this project is actively scoping authoring support for.

## What the GUI spec says

The main spec's "Shading & actor representation" section claims: "**Full UnrealEd-like view modes
per viewport**: textured+lit (native lightmap bake) / textured-unlit / flat / wireframe." Four modes,
described as "Full." `gui-slice-2-quad-layout-ortho-views-matching/spec.md` section 3 repeats the
same four-mode set with no addition.

## The gap

Four modes is not the full real set. UnrealEd's `Zones` mode has no counterpart in the GUI's design
at all — none of wireframe/textured-unlit/flat/textured+lit color-codes by zone membership, and no
GUI spec text (including the "Also open" flat-mode caveat, which only flags "flat" as undefined, not
"a mode is missing") acknowledges a fifth real editing view exists. This is a real information gap,
not just an undersold "Full" claim: zone boundaries are otherwise invisible in the GUI (no folder/
label facet captures zone membership either — zones are computed from the built BSP + portal flood,
not an authored per-actor property the org panel's existing facets could show).

## Why this matters

The whole point of P1 is to let a person navigate and audit a level visually. Zone membership is a
real, gameplay-relevant structure (sound propagation, visibility, water/gravity zones) that a
level-designer using the real editor could always see via `RMODE 2`; the GUI's audit/navigation
surface has no equivalent, and the zones scoping item's own "Current state" section notes native
zone resolution is unreliable today — a real caveat for whether/how this could be built, not a reason
the gap isn't real.

## Not filed as an implement task

This finding doesn't propose a mechanism (a client-side zone-color computation depends on the level
already having a resolved zone graph — currently only available via the editor path, since native
zone resolution is a known-broken area per `dev/docs/board/to-spec/zones/spec.md`'s "Current state").
Left for triage/spec; the zones scoping item is the natural place to fold in "does zones v1 include a
GUI visualization" as an open question.
