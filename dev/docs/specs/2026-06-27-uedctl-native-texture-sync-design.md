# Native `texture sync` — drop the UCC/PCX/container seam (design)

**Ephemeral spec.** Phase A (item 1) of the de-containerization roadmap
(`2026-06-27-uedctl-decontainerization-roadmap-design.md`). Q0-INDEPENDENT: doesn't depend
on the offline-BSP (D2) decision, so it can land first. Built on the proven native texture
decoder (`spikes/2026-06-27-decontainerize-uedctl/01-native-texture-decode.md`, pixel-exact
vs UCC on the whole corpus). **Revised after two cold reviews** — the load-bearing risk is
not decode (proven) but **manifest-identity stability across the cutover**. Written for a
reader with no prior context.

## Problem

`texture sync` is documented "session-free, fully offline" but isn't: its one container
dependency is `texture.batchexport_textures` — `docker exec <c> wine UCC.exe batchexport
<pkg> Texture pcx Z:\work\…` → `cp_out` each PCX. `texture_catalog.sync_package` then calls
the private `_decode_exported(pcx_paths, …)`, which `Image.open(pcx)`s each and derives
`width/height/image_hash/colors` + writes a PNG. So `sync` needs Docker + wine + UCC + the
`/work` exchange; the rest of `texture_catalog.py` (hashing, named colors, manifest,
reconcile, atomic+flock writes) is already pure host-side Python.

## The actual seam (verified against the code)

`sync_package(…, batchexport, …)` (texture_catalog.py ~386) injects
`batchexport(container, package, host_dir) -> list[pcx_path]` (default
`texture.batchexport_textures`, wired at `dispatch.py:555`); `sync_package` then itself
calls `_decode_exported(pcxs, images_dir)` which hardcodes `Image.open(pcx)`. **So the swap
is NOT a one-line replacement of the injected `batchexport`** — the native producer yields
in-memory RGB with no PCX file, so it replaces the `batchexport` + `_decode_exported` pair.

## Change: a native `ExportedTexture` producer

Promote the spike decoder to **`uedctl/utexture.py`** (`load_package`, `decode_texture`,
`decode_palette`, `mip0_to_rgb`, version-aware `FMipmap`; **add an `Outer`/group accessor** —
the harness `Package` stores the export `outer` index but exposes no name for it yet; that
is net-new code this spec owns). Refactor `sync_package` to take an injected
**producer `produce(package, package_file) -> list[ExportedTexture]`** (default the native
one) in place of the `batchexport`+`_decode_exported` pair:

```
for each Texture export i in load_package(package_file):
    t = decode_texture(pkg, i)
    if t.fmt != 0:  handle per "Non-P8" below (NOT a silent skip)
    rgb = mip0_to_rgb(t.mips[0], decode_palette(pkg, t.palette_ref))    # mip-0 only
    img = PIL.Image.frombytes("RGB", (w, h), rgb)   # feeds the EXISTING hash/colors/PNG layer
    group, name = native_group_name(pkg, i)         # see "Manifest-KEY stability"
    write mip-0 PNG to .uedctl/textures/<package>/<stem>.png  (same path convention as today)
    yield ExportedTexture(group, name, w, h, image_hash(img), derive_colors(img))
```

`image_hash`, `derive_colors`, the PNG write, `reconcile`, `assign_refs`, atomic+flock
writes, `colors_source` provenance, the `package_hash`/`force` fast-path — all reused
**unchanged** (the seam is cleanly factored, confirmed by review). The container/`/work`
plumbing inside `sync_package` is deleted.

## Manifest-KEY (stem) stability — THE migration risk (must be proven, not assumed)

The manifest is **keyed by the PCX stem** `Group.Name` (`Manifest.textures: dict[stem,…]`;
`parse_pcx_stem` = `rpartition(".")`). Today the stem comes from UCC's group-prefixed PCX
**filename** (`Metal.Foo.pcx` → group `Metal`, name `Foo`). Natively it must be
reconstructed from the package object graph (the texture export's `Outer` chain). **If the
native stem differs from UCC's in ANY way, the manifest KEY changes** — which is NOT a
`stale` mark but a *new* + *removed* pair, risking orphaned `tags`/`description`/`colors`
classification (the `image_hash`-carries-across-rename path only rescues it if reconcile
pairs them, capped at one successor). The spike proved **pixel** equality (175/175 …) — it
**never validated the stem/group**, and `tex_compare.py` compared *bare* names only.

Risks to close:
- **`Outer` ≠ UCC's full dotted prefix for nested groups.** One `Outer` hop gives the
  immediate parent (`Skins`); UCC may write a multi-level prefix (`Skins.Sub`). The native
  group must reproduce UCC's exact stem, including the bare-vs-grouped boundary and any
  multi-level join.
- **Acceptance gate (required):** over the real install corpus, for every package assert
  `sorted(native_stems) == sorted(UCC_pcx_stems)` (extend `tex_compare.py` to compare
  **stems**, not just pixels). Ship only on byte-for-byte parity.
- **One-time key migration (fallback):** if parity can't be guaranteed everywhere, the first
  native `sync` runs a deterministic migration — match old→new entries by `image_hash`,
  rewrite keys, preserve all classification — rather than letting `reconcile` mass-`stale`.
  Spec which path is taken based on the parity result.

## `image_hash` byte-layout stability (so manifests don't churn)

`image_hash` = `sha256(img.convert("RGB").tobytes() + "WxH")`. The cutover keeps hashes
stable **only if `mip0_to_rgb`'s byte layout is identical to `Image.open(pcx).convert("RGB")
.tobytes()`** — same row order (top-down), same channel order (RGB), no stride/padding. The
spike proved *pixel* equality by comparing both via `convert("RGB").tobytes()`; the
production native path skips Pillow's PCX decode, so this is a **distinct invariant to pin +
test** (not something the spike exercised). Acceptance: for the corpus, assert
`image_hash(Image.frombytes("RGB",(w,h),native_rgb)) == image_hash(Image.open(ucc_pcx))`.
(`mip0_to_rgb` already emits row-major top-down RGB, so this is expected to hold — but it is
an implementation invariant, asserted by test, not assumed.)

## Non-P8 formats (resolve the dropped-`format` tension; conform to error conventions)

DeusEx content is 100% `P8` (corpus sweep), so this is dead code on the DeusEx substrate and
only matters for the generic-UE1/UT direction. Two constraints the spec must honor:
- **`format` was deliberately DROPPED from the manifest** (decisions.md 2026-06-22, "a
  constant carrying nothing"). So we do NOT re-add a `format` field without a NEW recorded
  decision. A non-P8 texture is **skipped with a warning during `sync`** (named:
  ``"Texture `Pkg.Name` format RGBA7 not yet decodable (only P8) — skipped"``) and is
  **excluded from reconcile's removed-set** (so it never silently marks an existing
  classification `removed`) — i.e. `sync` treats it as "not produced this run", not "gone".
  A consumer that later needs its image (`poly set --texture`) hard-errors naming the value.
- Never let an exception reach the user; one non-P8 texture must not abort the package sweep
  (matches today's textureless-package non-crash). Adding per-format decoders
  (`RGBA7`/`DXT1`/`RGB8`/`RGBA8`) is future work behind the `Format` the decoder already reads.

## `--container` and dispatch messaging — STAGE the removal

Land in two commits to de-risk:
1. **Native decode behind the existing signature** — `sync_package` keeps accepting
   `container` (now unused); prove corpus parity (stems + hashes) first.
2. **Drop the now-dead flag** — remove `texture sync --container` (cli.py/dispatch.py/
   signature/tests) per the generic-tool direction, OR keep it accept-and-ignore with a
   deprecation note if other docs/scripts depend on it (grep first). Also fix the dispatch
   "discovered N, none produced textures (none on the container Paths)" branch
   (dispatch.py ~562) — there is no container `Paths` gate natively; a host file either
   decodes or doesn't. `texture sync` then needs **no container at all** and becomes truly
   offline.

## PNG path / mip contract (unchanged, pin it)

The native path still writes **one mip-0 PNG per texture** at the existing convention
`.uedctl/textures/<package>/<stem>.png` (derived, not stored — consumers existence-check and
error "run `texture sync`"). Decode exposes all mips, but the catalog writes mip-0 only, so
the path/existence contract and the deferred web viewer are unaffected.

## Host-file-resolution semantic shift (note)

Today UCC resolves the bare package name via the container `Paths`; natively, the
host-resolved `package_file` from `enumerate_substrate_packages` is **decoded directly**, so
the enumerate "one file per bare name" dedup now determines exactly which file is read. Same
file set, but the choice becomes load-bearing — state it.

## Testing
- **Offline unit:** a small **synthetic** `.utx`-shaped fixture *builder* (emit a valid
  header + name table incl. `None`/`Texture`/`Palette`/`Format` + a tiny P8 Texture export +
  a 256-entry Palette, with a correct `FMipmap` `WidthOffset`) → assert
  `decode_texture`/`mip0_to_rgb`/group-name → known pixels + stem. (No copyrighted assets
  committed; the builder is ~60 lines — its own small task, not a one-liner.) Cover the
  v61-vs-v68 `FMipmap` variants.
- **Integration (`integration`-gated, real install present):** extend `tex_compare.py` to
  assert (a) pixel parity, (b) **stem parity** (native vs UCC PCX stems), (c) **`image_hash`
  parity** — the three cutover guarantees — across the corpus.
- Existing `texture_catalog` tests stay; only the producer fixture changes from "PCX bytes"
  to "native `ExportedTexture`".

## Doc updates required on landing (per dx_lum CLAUDE.md "after every change")
- `architecture.md` "Texture catalog" (drop "UCC-batchexports … PCX … cp_out" → native decode).
- `unrealed/commands.md` "Texture → PNG" recipe (keep as an editor fact; note uedctl uses
  native decode).
- `texture.py` docstring (it asserts "UCC batchexport is the only working path" — now false;
  module removed/emptied).
- New `decisions.md` entry: the seam-swap + the non-P8/`format` resolution + the `--container`
  staging.
- Promote the spike's `UTexture`/`FMipmap`/`UPalette`/`FPropertyTag` format facts into a
  durable topic doc (`unrealed/` or `architecture.md`), cited from the spike.

## Refs
`spikes/2026-06-27-decontainerize-uedctl/01-native-texture-decode.md` +
`harness/{utexture_decode,tex_compare}.py`; `uedctl/texture_catalog.py` (`sync_package`,
`_decode_exported`, `parse_pcx_stem`, `assign_refs`, `image_hash`, `derive_colors`,
`reconcile`); `uedctl/texture.py` (seam removed); `dispatch.py:555`; `packages.py`
(`enumerate_substrate_packages`); `decisions.md` 2026-06-22 (texture-catalog: stem identity,
`colors_source`, `image_hash`-over-pixels, `format`-dropped, atomic/flock).
