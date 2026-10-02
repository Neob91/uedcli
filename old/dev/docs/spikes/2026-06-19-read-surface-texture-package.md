# Read a surface's bound texture PACKAGE (2026-06-19)

**Question.** A textured BSP surface holds its texture as a **resolved object
pointer**, so the editor knows which *package* the texture came from. But both
serialization paths drop it: `MAP EXPORT` and `EDIT COPY` emit a **bare**
`Texture=Area51Wall_A` (no package) — verified in
[`2026-06-19-t3d-package-qualification.md`](2026-06-19-t3d-package-qualification.md).
Is there **any OTHER way** to read, for a loaded/identified surface, the
**package-qualified** texture it actually bound (e.g.
`CoreTexMetal.Metal.Area51Wall_A` vs `Area51Textures.Metal.Area51Wall_A`)? This
decides whether uedcli can **recover** texture→package bindings from a loaded
`.dx`, not just from authored edits.

## Headline verdicts (all live-observed, exact bytes captured)

| Question | Verdict |
|---|---|
| Is there a read path that recovers a surface's bound **package**? | **YES** — `OBJ DEPENDENCIES PACKAGE=<levelpkg>` |
| Which verb + exact syntax | **`OBJ DEPENDENCIES PACKAGE=MyLevel`** (the loaded level's package is `MyLevel`). Prints to `Editor.log`. |
| Does it qualify (Package.Group.Name)? | **YES** — full three-part, e.g. `Texture CoreTexMetal.Metal.Area51Wall_A` |
| Does it distinguish the known collision? | **YES** — both `CoreTexMetal.Metal.Area51Wall_A` and `Area51Textures.Metal.Area51Wall_A` print distinctly, in the same dump |
| Granularity | **Per-brush, per-poly order.** One `Class Engine.Polys` block per brush; under it, each poly's bound texture in poly order. |
| Is the (name→package) map reconstructable from `OBJ LIST CLASS=Texture` for the non-colliding case? | **YES** — each loaded texture prints `Package.Group.Name`; a bare name unique among loaded packages resolves uniquely |
| `POLY TEXINFO` / `POLY TEXTURENAME` reveal the package? | **NO** — `TEXINFO` prints only UV scale; `TEXTURENAME` is a *setter*, prints nothing |
| `GET <topic>` / `CURRENTTEXTURE` / texture-browser reflection console-readable? | **NO** — the topic-handler `Get` API returns into a frontend buffer, not the log; no console verb reaches it |
| Surface selection state readable (which surf is selected / its texture)? | **NO** — surface state lives on derived BSP Surfs; `PF_Selected` and surf texture do not round-trip through `MAP EXPORT`/`EDIT COPY` |

**Bottom line.** uedcli **can** recover texture→package bindings from a loaded
`.dx` by driving the editor once: `OBJ DEPENDENCIES PACKAGE=MyLevel` walks the
level object graph and prints every brush's per-poly texture **package-qualified**,
disambiguating collisions. It is NOT forced to rely solely on authored per-poly
package data. (For the canonical store the recommendation in the prior spike still
stands — *persist* the package — but a one-time recovery read of an unsessioned
`.dx` is now possible.)

## Setup / reproduce

Ephemeral editor wired to the install content (the collision packages live there),
following the content-install spike
([`2026-06-18-deusex-content-install.md`](2026-06-18-deusex-content-install.md)):

1. Assemble a runtime dir `_scratch/texread/rt/` exactly like the entrypoint does:
   symlink the substrate binaries `Tools/uedcli/uned/UED22/*`, copy the `*.ini`,
   and rewrite `[Core.System] Paths` to **absolute** substrate-code +
   install-content lines (the relative `../Textures/*.utx` form does not resolve
   under UCC's cwd — the content-install spike's load-bearing fix). Add
   `Paths=/repo/_scratch/deusex/game/Textures/*.utx`.
2. Launch: `docker compose run -d --name uned-texread
   --entrypoint "/usr/bin/tini -- bash /repo/Tools/uedcli/uned/entrypoint.sh"
   -e UED_DIR=/repo/_scratch/texread/rt -v uned-wp-texread:/wineprefix uned`.
3. Drive console verbs via `wine_ctl.py exec` into the **Command box** (proven for
   `OBJ LIST`/`OBJ DEPENDENCIES`). The log is flush-laggy → snapshot
   `stat -c %s /opt/UED22/Editor.log` before the query, run a noisy command after
   (e.g. `OBJ LIST CLASS=Mesh NAME=zzz`), then `tail -c +<offset+1> | tr -d '\000'`.

The discriminator (from the prior spike): **`Area51Wall_A`** exists in BOTH
`CoreTexMetal` (128² grille) and `Area51Textures` (256² panel). A correct read
path must tell them apart; the bare name cannot.

## The winning lever — `OBJ DEPENDENCIES PACKAGE=MyLevel`

`OBJ DEPENDENCIES PACKAGE=<pkg>` (a core.dll `UObject::Exec` verb,
`Dependencies of %s:` → `Package %s references:` → `   %s` per ref) walks the
level package's reachable object graph and prints every referenced object's
**full name** (`Class Engine.Polys`, `Texture Package.Group.Name`, …).

A brush's `Engine.Polys` object is the authored `FPoly` array; each `FPoly` holds
a **resolved `Texture*`**, and the walker prints it qualified. Controlled cube
(6 faces; Top textured from `CoreTexMetal`, Bottom from `Area51Textures`, rest
`Engine.DefaultTexture`), loaded as the **first and only** level in a fresh editor:

```
Package MyLevel references:
   Class Engine.Polys
   Texture CoreTexMetal.Metal.Area51Wall_A      ← Top   (poly 0)
   Texture Area51Textures.Metal.Area51Wall_A    ← Bottom(poly 1)
   Texture Engine.DefaultTexture                ← North (poly 2)
   Texture Engine.DefaultTexture                ← South (poly 3)
   Texture Engine.DefaultTexture                ← East  (poly 4)
   Texture Engine.DefaultTexture                ← West  (poly 5)
```

The two `Area51Wall_A`s — bound to **different packages** — print **distinctly**,
in **poly order** matching the authored PolyList / `MAP EXPORT` order. The
collision is resolved.

### Per-brush separation (two-brush test)

A level with two brushes (BrushA→`CoreTexMetal`, BrushB→`Area51Textures`) yields
**two separate `Engine.Polys` blocks**, each with its own brush's per-poly textures:

```
Class Engine.Polys
   Texture CoreTexMetal.Metal.Area51Wall_A      ← BrushA
...
Class Engine.Polys
   Texture Area51Textures.Metal.Area51Wall_A    ← BrushB
```

So the dump is **per-brush** (one `Engine.Polys` block each) and **per-poly-ordered**
within a brush. Correlating block-order×poly-order with the `MAP EXPORT` brush/poly
order gives a per-surface package — uedcli knows both orders model-side.

### Confirmed on a REAL loaded `.dx`

`MAP LOAD 19_FMA.dx` (a real LUM map on base content) then
`OBJ DEPENDENCIES PACKAGE=MyLevel` emitted the level's actually-bound textures
fully qualified, including BOTH collision packages present in real content:

```
 92  HK_Helibase.Metal.Metal_A
 10  CoreTexStone.Stone.un_stonsign_c
  7  CoreTexMetal.Metal.Area51Wall_A
  7  Area51Textures.Metal.Area51Wall_A      ← collision distinguished in real content
  4  CoreTexMetal.Metal.waterfontn_a
  …
```

(The dump also lists editor-UI textures `Editor.*` / `Extension.*` — those are the
browser/sprite textures, trivially filtered: they are not level-content packages.)

### Caveats (load-bearing for using it)

- **`MAP NEW` / `MAP LOAD` does NOT immediately purge the previous level's objects**
  from the `MyLevel`/transient pool. Reusing one editor across loads → the dump
  accumulates **stale** textures from prior levels. **Recover in a FRESH editor that
  loads exactly one `.dx`** (which is uedcli's natural model — load → dump → tear
  down), or the result is polluted. Every clean per-level result above used a
  freshly-recreated container.
- **The textures surface from `Engine.Polys` (the authored brush PolyList), not from
  the BSP `Model` Surfs.** `CLASS=Model` narrowing showed only the Model's default
  surf texture, not the per-surf bound textures, in this build's walk. So this reads
  the **authored per-poly** binding (which is exactly what a `.dx`'s brushes carry),
  not a recomputed BSP-surf binding. For recovery that is the right object — the
  brush PolyList is the authored source the surface inherits from.
- **Log flush lag + walk latency:** the walk emits incrementally; read it only after
  a trailing noisy command and a short settle, or an early read catches a partial
  block (observed once: a partial two-brush dump showed only `DefaultTexture` before
  the qualified lines flushed).

## The (name→package) map from `OBJ LIST CLASS=Texture` (non-colliding case)

`OBJ LIST CLASS=Texture` prints every **currently-resident** texture as
`Log: Texture <Package>.<Group>.<Name>  <bytes> <bytes>` — fully qualified for
grouped install content. After demand-loading both collision packages, BOTH
`Area51Wall_A`s appear distinctly:

```
Log: Texture Area51Textures.Metal.Area51Wall_A   87945  87945
Log: Texture CoreTexMetal.Metal.Area51Wall_A     22369  22369
```

(Group-less builtins print two-part, e.g. `Texture Engine.DefaultTexture`.)

**Reconstruction verdict:** for the **non-colliding majority**, a bare surface name
resolves to its package by intersecting the bare name with the loaded packages'
texture tables from `OBJ LIST` — if exactly one loaded package exports that name, the
package is unique and recovered **without any per-surface read**. `OBJ LIST` only
covers what is **resident**, so the level's packages must be loaded first (which they
are after a `.dx` load + ensure-load). For the **colliding minority** (64 of 2392
install names; same bare name in 2+ loaded packages) `OBJ LIST` alone is ambiguous —
that is exactly where the per-brush `OBJ DEPENDENCIES` read is needed.

## Levers that did NOT work (tried, captured, ruled out)

- **`POLY TEXINFO`** — extracted format is `TEXINFO : U=%1.5f V=%1.5f` (UV scale
  only); no texture name, no package. Verdict: no.
- **`POLY TEXTURENAME`** — in the binary it sits among the poly **setters**
  (`Poly SetTexture` cluster, beside `TEXMULT`/`TEXPAN`/`TEXSCALE`); it *sets* a
  texture, prints nothing. Verdict: no.
- **`GET Polys TextureName` / `GET Texture CurrentTexture` / `CURRENTTEXTURE` /
  `GET Ed CurTex`** — the editor's topic-handler `Get` API
  (`PolysTopicHandler::Get` item `TextureName`/`Multiple Textures`,
  `TextureTopicHandler::Get` item `CURRENTTEXTURE`, `EdTopicHandler::Get` item
  `CURTEX`) IS what the Surface-Properties dialog / texture browser read — but it
  returns into a **frontend buffer**, not the output device. No console verb routes
  it to the log; typed into both the Command box and the Log-Window `>` console it
  produced **zero** output. Verdict: not console-readable.
- **Surface selection read-back** — `POLY SELECT MATCHING FLOORS/CEILINGS/...`
  followed by `POLY SETFLAGS` then `MAP EXPORT` showed **no** flag change in the
  export: surface flags/selection live on derived **BSP Surfs**, which do not
  round-trip through `MAP EXPORT` (only the authored brush PolyList does). Confirms
  the quirks-doc rule "you can't ask the editor which surface is selected." Verdict:
  no surface-level read channel via export/copy.
- **`MESH GETPROPERTIES`** — the only `GETPROPERTIES` verb in the build; dumps
  **mesh** props, not BSP. No generic object-property reflection verb exists in this
  UE1 build. Verdict: no.
- **`OBJ DEPENDENCIES PACKAGE=MyLevel CLASS=Model`** — narrows to the BSP Model
  object, which showed only `Engine.DefaultTexture`/`S_ZoneInfo` (the Model default),
  not per-surf textures. The per-poly textures live on the `Engine.Polys` object, so
  do NOT narrow with `CLASS=Model`; run the unfiltered `PACKAGE=` walk.

## Recommendation for the surface-texturing design

1. **Recovery is now possible — uedcli is no longer limited to authored package
   data.** To bootstrap texture→package bindings from an existing `.dx` that has no
   session/per-poly package field (e.g. importing a hand-authored level, or a merge
   from a foreign `.dx`), uedcli can: load the `.dx` in a **fresh** editor →
   ensure-load its package manifest → `OBJ DEPENDENCIES PACKAGE=MyLevel` →
   parse the `Engine.Polys` blocks → correlate block-order × poly-order with the
   `MAP EXPORT` brush/poly order → recover the qualified package per textured poly.
2. **Cheap common case first.** For the non-colliding majority, skip the per-poly
   read entirely: resolve each bare surface name against the loaded packages'
   `OBJ LIST CLASS=Texture` tables; a name unique among loaded packages is its
   package. Fall back to the `OBJ DEPENDENCIES` per-poly read only for the colliding
   minority (or whenever the cheap lookup is ambiguous).
3. **For the live store, the prior spike's recommendation is unchanged:** *persist*
   the package as authored per-poly data and emit qualified `Texture=` at
   materialize. Recovery is a **bootstrap/merge** convenience, not a substitute for
   storing the binding — the recovery read needs a live editor and a one-time drive,
   whereas the store must answer offline.
4. **Treat recovery as one-shot per `.dx`, in isolation.** Because the object pool
   accumulates stale textures across loads in a reused editor, a recovery read must
   run on a freshly-loaded single level (uedcli's `session start <dx>` already
   implies a fresh, per-session editor — a future `--recover-texture-packages` could
   ride that seam).

## Artifacts (`_scratch/texread/`, gitignored)

- `cube.t3d` / `cube_export.t3d` — the 6-face dual-qualified collision cube + its
  bare re-export.
- `twobrush.t3d` / `twobrush_export.t3d` — two brushes (A→CoreTexMetal,
  B→Area51Textures) + bare re-export.
- `deps_twobrush.txt` — the captured `OBJ DEPENDENCIES` dump showing the two
  separate `Engine.Polys` blocks with their qualified textures.
- `rt/` — the runtime dir with absolute install-content `Paths`.

## Cross-links

- Prior package-qualification spike (export strips, import honours):
  [`2026-06-19-t3d-package-qualification.md`](2026-06-19-t3d-package-qualification.md).
- Content install (the package-path wiring this depends on):
  [`2026-06-18-deusex-content-install.md`](2026-06-18-deusex-content-install.md).
- Surface flags + texturing design (the consumer of this verdict):
  `specs/2026-06-19-uedcli-surface-flags-texturing-design.md` (landed; spec deleted).
- Object-graph / surface-state quirks:
  [`../unrealed/quirks.md`](../unrealed/quirks.md) (`PF_Selected` does not
  round-trip; surface state is on derived BSP).
- Command vocabulary + extraction method:
  [`../unrealed/commands.md`](../unrealed/commands.md) (`OBJ` family),
  [`../unrealed/extracting-from-dll.md`](../unrealed/extracting-from-dll.md).
