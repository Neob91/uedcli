+++
priority = "p1"
kind = "bug"
summary = "`pkgref.build_texture_group_index` globs `*.utx` only, so a texture that lives inside a CODE package (`*.u`) never gets its group re-attached: native materialize emits the 2-part import `DeusExItems.BlackMaskTex` where the editor and the original shipped map both emit `DeusExItems.Skins.BlackMaskTex`. Live-measured on `DX.dx` (26/26 surfs). Wrong import path in shipped output, the exact 'Can't find Texture in file' failure the index exists to prevent."
+++

# `build_texture_group_index` never scans `.u` packages, so their textures ship group-less

Found while measuring `texture_ref` semantic identity (round 8 of
`texture-ref-i-actor-divergence-traced-to-golden`). Not fixed there — out of that round's mandate.

## The bug

`uedcli/native/pkgref.py`, `build_texture_group_index` iterates `dp.glob("*.utx")`. UE1 also stores
textures inside CODE packages (`.u`) — actor skins, in particular. `DeusExItems.u` holds an
`Engine.Texture` export `BlackMaskTex` under group `Skins` (verified by parsing the package).

The trunk stores the 2-part form the T3D `Texture=` field carries
(`Texture=DeusExItems.BlackMaskTex`); `Resolver.object_ref` is supposed to re-attach the group from
this index. With `.u` unscanned there is no index entry, so native emits an import whose outer chain
is the package itself:

- native: `DeusExItems.BlackMaskTex`
- self-built UED22 golden: `DeusExItems.Skins.BlackMaskTex`
- the ORIGINAL shipped `DX.dx` import table: `DeusExItems.Skins.BlackMaskTex`

Both references agree, native is the outlier. This is real `level materialize` output, not a
harness artifact — the failure mode `build_texture_group_index`'s own docstring names ("an import
MUST carry that group in its outer chain (the editor emits it) or the game raises 'Can't find
Texture in file'").

## Scale

All 26 surfs of `DX.dx` (its only texture). Zero on `03_NYC_UNATCOHQ` and zero of this kind on
`02_NYC_Bar` — both those levels' textures come from `.utx` files, so the index covers them. So it
only bites levels that dress world geometry in a skin texture from a code package; unmeasured across
the rest of the corpus.

## Not fixed — what a fix needs

Widening the glob to `*.u` is one line but is not obviously free: the `System/` dir holds ~40 `.u`
packages including multi-MB ones (`DeusEx.u`, `DeusExCharacters.u`), and the index is built on every
materialize. Needs a measurement of the added parse cost and a check that no `.u` texture name
collides with a `.utx` one in a way that changes an existing level's resolution (the index is
first-hit-wins over the search path). Also worth deciding whether other content kinds (Sound, Music,
Mesh) have the same hole.

Verification for a fix: `DX.dx`'s 26 `texture_ref` resolved-identity diffs (visible in
`parity_report.py` since round 8) must go to 0, and no other level's count may rise.
