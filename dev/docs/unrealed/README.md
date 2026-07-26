# UnrealEd 2.2-under-wine — knowledge base

The hard-won, verified facts about driving UnrealEd 2.2 headless (the `dx-lum-uned` container:
UED22 under wine on Xvfb `:99` + fluxbox, driven by `wine_ctl.py` over `docker exec`).
Public docs are nearly nonexistent and rediscovery is expensive, so **document new findings
here** (per `../../CLAUDE.md`). Evidence lives in `../spikes/`.

| Doc | What's in it |
|---|---|
| [`commands.md`](commands.md) | Console-verb reference: how `wine_ctl` drives the editor + every exec family (`MAP`/`BRUSH`/`ACTOR`/`CAMERA`/`RMODE`/`MODE`/`BSP`/`LIGHT`/`PATHS`/`OBJ`/…) with subcommands, args, and the engine-level verbs. Confidence-tagged. |
| [`t3d.md`](t3d.md) | The T3D **on-the-wire text format** (`MAP EXPORT`/`MAP IMPORTADD`): block nesting, property line forms (scalar `Key=Value` and indexed `Foo(N)=<value>`), winding-defines-the-face, fractional vertices, what T3D can't carry, authored-vs-computed taxonomy. NOT the T3D tree directory form used by the session store. |
| [`package-format.md`](package-format.md) | The **binary package format** (`.u`/`.dx`/`.utx`/`.uax`/`.umx`) and the answer to "is a Deus Ex package different from an Unreal/UT one, and is v68-vs-v69 a compatibility gate?" — **no** (format identical; the version is a red herring; the real code-load blocker is `Engine`/`Core` class-graph divergence + mesh format). |
| [`quirks.md`](quirks.md) | The weird, surprising **gotchas** — `MAP IMPORTADD` grid-snap, `Texture=` demand-load, selectability (paste vs IMPORTADD), `SELECTNAME`, CSG model, paste drift, no coplanar merge, etc. |
| [`rendering.md`](rendering.md) | Getting pixels out — GL/device setup, render modes, the stale-framebuffer trap, black-viewport causes, building lighting, and `CAMERA OPEN` as the clean shaded-shot path. |
| [`extracting-from-dll.md`](extracting-from-dll.md) | How this knowledge is mined from the binaries (UTF-16LE wide-string extraction of the exec grammar) and verified live. |
| [`leveldesign/`](leveldesign/README.md) | The other axis — **level-design craft** (what makes a good, buildable level): the comprehensive dev reference is [`leveldesign/kb/`](leveldesign/kb/README.md) (geometry/BSP, zoning, lighting, textures, movers, actors/collision/pathing, the DX class catalog, NPC AI, human scale, design craft), binary-fact-checked. The reader-facing user cut is at [`../../leveldesign/`](../../../docs/leveldesign/README.md). |

The docs above are about **driving** UnrealEd headless; [`leveldesign/`](leveldesign/README.md)
is about **designing levels** in it. They cross-reference where they overlap (the CSG model).

Related (one level up): [`../architecture.md`](../architecture.md) (uedctl layers / write pattern),
[`../parallel-editors.md`](../parallel-editors.md) (driving many ephemeral editors at once).
