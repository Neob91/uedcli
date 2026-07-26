# Spike 6 — does native `.dx` write eliminate stubbing? (the thesis payoff)

**Status: RESOLVED (analysis) — YES. Native read+write removes the *entire* stub
pipeline, and with it UCC `make`/`batchexport class` and `umodel`.**

## Why stubs exist today (the two real reasons — neither is v68/v69)

The stub pipeline (`stub.py` + `uscript_rewrite.py` + `stub_cache.py`) converts a
DeusEx v68 **code** package into a UED22-loadable v69 "stub": UCC decompiles the
classes, function/state bodies are stripped, umodel re-encodes meshes, UCC `make`
recompiles. Its sole purpose is to let **the UT-lineage UED22 editor load DeusEx
code**. The two things that make raw DeusEx code unloadable by that editor:

1. **`Engine.u`/`Core.u` divergence** — DeusEx classes inherit from / call into a
   DeusEx-flavored Engine & Core whose class graph and natives differ from UT's; the
   v469 UCC can't link decompiled DeusEx bodies against UT's DLLs (hence body
   stripping). *(decisions.md 2026-06-21/22; confirmed there.)*
2. **Mesh format** — DeusEx `FMeshVert` is 8-byte int16, UT expects 4-byte packed
   (**Spike 2**), so meshes must be re-encoded (umodel).

Both are *content/class-graph* problems, **not** a package-version problem — UED22's
UCC reads v68 fine (decisions.md 2026-06-22). Andrzej's hypothesis: confirmed.

## Why native write removes all of it

Stubbing is a **load-into-the-UT-editor** workaround. The native-write thesis never
loads DeusEx code into any editor:

- **Geometry build** is the offline BSP engine (D2) — no editor CSG.
- **Class/texture qualification** is native (Spike 4) — no editor `OBJ DEPENDENCIES`.
- **The `.dx` is serialized natively** (Spike 3) — no editor `MAP SAVE`.
- **Reading DeusEx classes/props/textures/meshes** is done from the **real v68
  install** natively (Spikes 1, 2; property schema already mandated to read the real
  `.u`, never a stub — decisions.md 2026-06-26 14:10).

With no editor in the materialize loop, **nothing ever needs a v69 DeusEx package.**
So:

| Eliminated | Was for |
|---|---|
| `stub.py` / `uscript_rewrite.py` / `stub_cache.py` / `stub_closure.py` | making DeusEx code editor-loadable |
| `UCC.exe batchexport class uc` (decompile) | stub source |
| `umodel.exe` (mesh re-encode) | stub meshes |
| `UCC.exe make` (recompile) | stub build |
| the ephemeral build container | running the above |
| (even the committed v69 DeusEx`*`.u substrate) | only there so the editor loads DeusEx — unneeded by the native path |

This is the largest single subsystem the de-containerization deletes, and it falls out
*for free* once Spikes 1–4 + D2 land — no separate work.

## Net binary-elimination tally (with Spikes 1–4 + this)

| Binary | Status after native read+write |
|---|---|
| `UCC.exe` | **eliminated** — texture decode native (S1), `.dx`→model native (S3/S4 read), no decompile/`make` (stubs dead) |
| `umodel.exe` | **eliminated** — only fed stubbing; native mesh decode (S2) covers any residual catalog/preview need |
| ImageMagick `convert` | **eliminated** — native PNG (S1) + stdlib PNG writer |
| `unrealed.exe` | **reduced to OPTIONAL** — geometry/qualify/write all native; only lighting & paths remain (Spike 5) |

Docker/wine/X11/VNC exist only to host those binaries; once the editor is optional,
**the day-to-day loop is container-free.**
