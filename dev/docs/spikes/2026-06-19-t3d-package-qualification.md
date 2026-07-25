# T3D package qualification spike (2026-06-19)

**Question.** `MAP EXPORT` writes `Texture=` and actor `Class=` as a **bare
name** (no package) — verified across the real Deus Ex level exports under
`Temp/*.t3d` (e.g. `Begin Polygon … Texture=Backdrop`). A bare name is
**ambiguous** when two loaded packages both export a resource of that name. Does
UnrealEd export a **fully-qualified** `Texture=Package.Name` when the bare name
is ambiguous? Does **IMPORT** accept and correctly bind an explicit qualified
`Texture=Package.Name` / `Class=Package.ClassName`? The answer decides whether
uedctl can store the package *inside* the T3D, or must track packages as
separate declared data.

## Verdicts (all observed live, exact bytes captured)

| Question | Verdict |
|---|---|
| Does EXPORT qualify `Texture=` under ambiguity? | **NO** — always bare, ambiguous or not |
| Does IMPORT accept qualified `Texture=Package.Group.Name`? | **YES** — and it **demand-loads** the named package |
| Does the qualified import bind the **correct** package? | **YES** — wrong-package qualifier → **no bind at all** (no silent fallback) |
| Does EXPORT qualify `Class=`? | **NO** — always bare |
| Does IMPORT accept qualified `Class=Package.ClassName`? | **YES**, but the package part is **ignored** — class resolves by global name |

**Bottom line for the spec:** the package round-trips through the editor in
*neither* direction — EXPORT strips it, so you can never read it back out of a
plain export; but IMPORT *honours* it for textures (it is the lever that picks
the right package). So uedctl **can put the package into the `Texture=` field of
the T3D it feeds the editor at materialize**, and **must track the package
separately as authored data** in the store (a `Texture` poly field's
package, or a name→package index), because no export will ever tell it the
package again. See "Recommendation".

## Setup / reproduce

Ephemeral editor (the persistent `dx-lum-uned`'s `/opt/UED22` symlinks are stale
→ dangling, and the baked entrypoint path is stale), wired to the install
content per the content-install spike
([`2026-06-18-deusex-content-install.md`](2026-06-18-deusex-content-install.md)):

1. Build a runtime dir `_scratch/pkgqual/rt/` = symlinks to the real substrate
   `Tools/uedctl/uned/UED22/*` (binaries) + copied inis, with the
   `[Core.System] Paths` rewritten to **absolute** substrate-code +
   install-content lines (the relative `../Textures/*.utx` form does not resolve
   under UCC's cwd — the content-install spike's load-bearing fix).
2. Start the editor with `UED_DIR=/repo/_scratch/pkgqual/rt` and the entrypoint
   override (the baked image path is stale):
   ```
   docker compose run -d --name uned-pkgqual \
     --entrypoint "/usr/bin/tini -- bash /repo/Tools/uedctl/uned/entrypoint.sh" \
     -e UED_DIR=/repo/_scratch/pkgqual/rt \
     -v uned-wp-pkgqual:/wineprefix  uned
   ```
3. Drive with `docker exec uned-pkgqual python3 /repo/Tools/uedctl/uned/wine_ctl.py exec "<VERB>"`.
   `OBJ LIST` lands in `/opt/UED22/Editor.log` (flush-laggy → follow with a noisy
   command, then `grep -a`; the log is a binary file, so `grep -a`).

Enumerate texture names per package with `UCC batchexport <pkg>.utx Texture pcx`
(its `Exported Texture <Package>.<Group>.<Name>` log lines are the name table).

## The collision found

Across all **57** install texture packages (2392 distinct bare names, **64**
colliding bare names), the cleanest collision used:

- **`Area51Wall_A`** exists as **`CoreTexMetal.Metal.Area51Wall_A`** AND
  **`Area51Textures.Metal.Area51Wall_A`** — same Group (`Metal`), same Name,
  two packages. The two are genuinely different images: `CoreTexMetal`'s is a
  128×128 vent grille; `Area51Textures`'s is a 256×256 octagon-framed panel
  (distinct `md5`, distinct dimensions — a clean discriminator).

(Other 2-package collisions: `ClenWoodPanel_A` in `Catacombs`/`CoreTexWood`;
`NYskybox1Mbs` in `BatteryPark`/`UNATCO`; the whole `ClenRckt*` family in
`Rocket`/`TITAN`; many `NYC*` in `NYCBar`/`NewYorkCity`.)

## Test 2 — EXPORT under ambiguity: BARE, always

Hand-authored a 256³ cube with two faces carrying the **qualified** colliding
texture (Top→`CoreTexMetal.Metal.Area51Wall_A`, Bottom→`Area51Textures.Metal.
Area51Wall_A`), rest `Engine.DefaultTexture`. Loaded **both** packages,
`MAP IMPORTADD`, then `MAP EXPORT`. Exact exported bytes:

```
Begin Polygon Item=Top Texture=Area51Wall_A Link=0          # was CoreTexMetal.Metal.Area51Wall_A
Begin Polygon Item=Bottom Texture=Area51Wall_A Link=1       # was Area51Textures.Metal.Area51Wall_A
Begin Polygon Item=North Texture=DefaultTexture Link=2
…
```

Both faces — bound to **different packages** — export as the **same bare**
`Texture=Area51Wall_A`. The package qualification is **lost on export**, even
under direct ambiguity.

Control (no ambiguity): with only `CoreTexMetal` loaded, a **bare**
`Texture=Area51Wall_A` import re-exports `Texture=Area51Wall_A` — identical.
So bareness is **universal**, not an ambiguity artifact; the editor never
qualifies a `Texture=` on export.

## Test 3 — IMPORT a qualified ref: ACCEPTED, demand-loads, binds correctly

- **Accepted + demand-load.** With **only `Area51Textures`** loaded, importing a
  brush face `Texture=CoreTexMetal.Metal.Area51Wall_A` caused the editor to
  **auto-load the entire `CoreTexMetal` package** (the log went from 0 to 171
  `CoreTexMetal.Metal.*` textures resident). With **nothing** preloaded, the
  dual-qualified cube auto-loaded **both** `CoreTexMetal` (171) **and**
  `Area51Textures` (80) and both faces bound. ⇒ the package qualifier in
  `Texture=` is parsed and the named package is demand-loaded at import.

- **Correct package, strict — no fallback.** A face qualified
  `Texture=CoreTexWood.Area51Wall_A` (a real package that does **not** contain
  `Area51Wall_A`) imported with **no texture binding at all** — the export was
  `Begin Polygon Item=Top Link=0` (no `Texture=`). The editor did **not** fall
  back to some other package's same-named `Area51Wall_A`. So the qualifier is
  resolved **strictly against the named package**: right package → binds; wrong
  package → unbound.

- **Working syntax:** `Texture=<Package>.<Group>.<Name>` (the full three-part
  form, e.g. `CoreTexMetal.Metal.Area51Wall_A`) is what was tested and works.
  (The two-part `Package.Name` form was not separately needed — every install
  texture lives in a Group, so the natural qualified form is three-part. If a
  texture is group-less, `Package.Name` is the expected form; not exercised
  here.)

## Test 4 — actor `Class=`: bare on export; qualifier accepted but ignored

- **EXPORT bare.** `Class=Engine.Light` and bare `Class=Light` both import and
  both export as bare `Class=Light`. Same as textures — package dropped.

- **IMPORT accepts qualified, but resolves by global class name, ignoring the
  package.** Three actors in one import:
  - `Class=Engine.Light` (correct package) → imported as `Light` ✓
  - `Class=Editor.Light` (**wrong** package — `Light` lives in `Engine`, not
    `Editor`) → **still imported as `Light`** ✓ — the wrong package qualifier was
    **not** rejected.
  - `Class=Engine.NoSuchClassXyz` (nonexistent class) → **dropped** (absent from
    the export).

  So `Class=` resolution is by the **class NAME globally**, unlike `Texture=`
  which resolves **within the named package**. UE1 class names are effectively a
  global namespace at actor-spawn lookup. (Caveat: this substrate's loaded code
  packages — `Core`/`Engine`/`Editor`/the BrushBuilder packages/drivers, 308
  distinct classes — have **zero class-name collisions**, so a *true* colliding-
  class bind-correctness test couldn't be run. The wrong-package-still-binds
  result indicates the package part is ignored; with a real class collision the
  qualifier would likely not disambiguate. This matches the known gap that the
  class package can't be derived from an unqualified `Class=`.)

## Recommendation for the surface-texturing spec

**Store the package, and put it into the `Texture=` field at materialize.**

1. **The package is authored data uedctl must own.** Because EXPORT strips it,
   no read of a `.dx`/T3D ever recovers the package. uedctl must carry, per
   textured poly, **which package** the texture came from — as a field on the
   model `Polygon` (a `texture_package`, beside the existing bare `Texture`), or
   an equivalent name→package binding resolved from the `main/packages` manifest.
   This is the same shape as the existing **`packages` manifest** (the third
   state-tree file) — the package set already lives in the store; the texturing
   work adds the *per-poly* binding so an ambiguous name picks the right one.

2. **Emit the qualified `Texture=Package.Group.Name` into the materialize T3D.**
   At `level apply`/`level preview` (the FULL RE-IMPORT seam), `emit` should
   write the **qualified** three-part form for any poly whose package is known.
   This is exactly the lever the editor honours: it demand-loads the package and
   binds the correct texture even under a name collision. (The package must also
   be on the ensure-load `Paths` — which apply already does from the manifest —
   so the demand-load resolves to a file.) Emitting bare would let the editor
   bind whichever same-named texture happens to be loaded first → wrong image
   under a collision.

3. **The canonical store T3D can stay bare *if* the package is a sibling field**,
   but the simpler, self-describing choice is to **store the qualified form in
   the `Texture=` field itself** and only down-convert if some consumer needs
   bare. Either way the package must be persisted; it cannot be recomputed.

4. **Merge implication (important).** A **raw `.t3d` without its owning `.dx`/
   session has no import table** — and since EXPORT writes bare names, a raw
   export carries *no package information whatsoever*. So a `.t3d` is not a
   self-sufficient merge/transport unit for textured geometry: the package
   binding lives only in the store's per-poly data + `packages` manifest. This
   reinforces the store-centric invariant — the `.dx` is a build artifact, the
   **store** (with its qualified texture bindings + manifest) is the source of
   truth. Promote/stash/prefab transport must carry the package binding
   alongside the geometry (the prefab `.json` sidecar's `packages` already does
   this at the package-set level; per-poly bindings ride in the `.t3d` blob if
   we store the qualified form there).

5. **`Class=` is a non-issue for surface texturing** but confirms the known gap:
   the actor's class package can't be derived from `Class=` (export bare; import
   ignores the qualifier). uedctl must likewise track an actor's class package as
   authored data if it ever needs it (it lives in the `packages` manifest today).

## Artifacts (`_scratch/pkgqual/`, gitignored)

- `objlists/*.log` — per-package `Exported Texture …` name dumps (the collision
  search input).
- `qual_brush.t3d` (dual-qualified cube), `bare_brush.t3d`, `qual_bad.t3d`
  (wrong-package), `class_probe.t3d`, `light_qual.t3d` — the import probes.
- `*_export.t3d` — the captured EXPORT bytes (`after_import`, `nopreload`,
  `bare`, `bad`, `class_probe_export`, `light_export`).
- `cmp_core_A51WallA.png` / `cmp_a51_A51WallA.png` — the two distinct
  same-named textures (128×128 grille vs 256×256 panel).

## Cross-links

- Content install (the package path wiring this depended on):
  [`2026-06-18-deusex-content-install.md`](2026-06-18-deusex-content-install.md).
- Surface flags + texturing design (to be written):
  `2026-06-19-uedctl-surface-flags-texturing-design.md` — this spike's verdict
  is its input for the package side.
- T3D format/quirks: [`../unrealed/quirks.md`](../unrealed/quirks.md) (surfaces,
  the paste path that preserves per-poly `Texture=`).
