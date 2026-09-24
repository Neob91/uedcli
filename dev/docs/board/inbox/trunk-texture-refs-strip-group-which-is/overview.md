+++
priority = "p0"
kind = "bug"
summary = "trunk texture refs strip Group, which is sometimes real identity not decoration"
+++

# trunk texture refs strip Group, which is sometimes real identity not decoration

Owner ruling (2026-09-22): the group-stripping convention was wrong. Filed while designing an
Inspector feature that wanted to display a texture's real `Package.Group.Name`.

## The bug

`model.strip_texture_group` (`uedcli/model.py:130`) actively collapses any qualified texture ref
to `Package.Name` — including a ref read back from a live editor's own `OBJ DEPENDENCIES` output,
which is documented as deliberate: "uedcli convention: NEVER store a group in a qualified texture
name ... including refs read back from the editor's own output." `surface.py::parse_texture_ref`
and `dev/docs/unrealed/quirks.md`'s "T3D format" section (lines 287-298) codify the same convention
for every writer (`brush poly set --texture` etc.): always construct `Package.Name`, never the
group, "even when one exists."

The convention's own justification is a SINGLE confirmed-live test case
(`CoreTexMetal.Area51Wall_A`, 2026-06-20): the bare 2-part ref bound the same object the 3-part
form did, so the rule was generalized to "group is display/organizational only" for every texture,
everywhere. That test only proves `Area51Wall_A` doesn't collide with anything else named
`Area51Wall_A` in `CoreTexMetal` — it says nothing about whether SOME OTHER name does.

## Why it's wrong

`Package.Name` is not always unique within a package. The on-disk export format ties uniqueness
to `(Outer, Name)`, not `Name` alone (`u-format.md`'s export record: `Outer` and `Name` are
independent fields; `upackage.object_path` walks the Outer chain to build an identity) — nothing
stops two different `Texture` exports sharing a Name under two different Groups, structurally, the
same way two files can share a filename in different directories.

Confirmed empirically against the real substrate (`dev/games/substrate-deusex`, 94 packages, 4375
texture exports, 64 packages carrying at least one Texture export): **8 real intra-package
same-name, different-group collisions**, e.g. `CoreTexCeramic.CermTileFloor_A` (groups `Tiles` and
`Ceramic` — two DIFFERENT textures), `CoreTexMisc.BW_SatPic_A02`/`BW_SatPic_B00`/`BW_SatPic_A03`/
`BW_SatPic_A01`/`BW_SatPic_A00`/`BW_LG_SatPic_B`/`BW_LG_SatPic` (each split between group `Glass`
and ungrouped). Zero same-name-*same*-group cases (UE1 forbids that — consistent).

For any of these 8 names, a trunk-stored `Package.Name` ref is ambiguous: whichever the resolving
search (editor or native) happens to land on first is what gets bound — not necessarily the one
the level author actually selected when they set the texture. This is silent, not surfaced
anywhere — a poly could render the wrong texture with no error.

Aside, not the main finding: `dev/docs/direction/asset-catalog.md` cites `CoreTexMetal.LadrBrwnMetal`
as its own canonical stripped-group example; in this substrate copy that name is single/non-colliding
(group `Ladder`). Possibly stale against this asset version — worth the owner's eye, not acted on
here (`direction/` needs an explicit yes to edit).

## What needs fixing (not scoped/estimated here — that's the next step)

- `model.strip_texture_group` and its callers (`qualify.py`, `surface.py::parse_texture_ref`,
  `dev/docs/unrealed/quirks.md`'s convention text) all need to stop discarding the group.
- Existing trunk content already has group stripped for any texture ref set through uedcli since
  this convention was adopted — a scan of real trunks against the catalog for ambiguous names would
  say how much content is actually at risk vs. theoretical.
- `uedcli/utexture.py::package_texture_refs` already has the right disambiguation logic (2-part
  when safe, 3-part when the name collides within the package) — the fix is likely "use this
  instead of always stripping," not new machinery.

## Evidence

- `uedcli/model.py:130` (`strip_texture_group`), `uedcli/qualify.py`, `uedcli/surface.py:95`
  (`parse_texture_ref`), `dev/docs/unrealed/quirks.md:287-298`.
- `dev/docs/unrealed/unrealscript/u-format.md:46` (export record: `Outer`/`Name` independent),
  `uedcli/upackage.py`'s `object_path` (outer-chain identity).
- Corpus scan: fork spike this session, `dev/games/substrate-deusex` (System + Textures), 94
  packages / 4375 Texture-classed exports scanned, 8 confirmed collisions, 0 same-name-same-group
  anomalies.
