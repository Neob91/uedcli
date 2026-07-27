+++
priority = "p1"
kind = "implement"
summary = "Decode every UE1 texture layout natively, reading the layout off the DATA rather than a format table."
spikes = ["dev/docs/spikes/2026-07-26-ucc-texture-fixture/"]
+++

# Native texture decode for any UE1 package

Plan: [`../../../plans/2026-07-25-native-texture-formats-plan.md`](plan.md).
Spec: board item `three-design-calls-the-native-texture-formats`.

**These two files are SELF-CONTAINED — read them and build. No other document needs opening.**
They inline the binding decisions with their rejected alternatives, the on-disk `UTexture`/
`FMipmap` byte layout, the house rules (test command, commit conventions, no-back-compat,
no-silent-half-answers), every corpus path with its committed/not status, and every measured
number with the root it was measured against. Provenance pointers are for the record only.

**Why it matters here and now:** `utexture.py` decodes one layout (`fmt==0`), so a `UTexture`'s
second mip array (`CompMips`) makes the body parse overrun — **30 textures in the project's own
`LUM/Textures/LUM_CoreTex.utx` are invisible to uedcli today** and render as a checkerboard.
This is a live bug on this substrate, not generic-UE1 hygiene.

**STATUS 2026-07-26: BUILDABLE.** Both escalations from the plan reviews are resolved — the
`repo_texture_root()` propagation (that directory left this repo when uedcli split out; the offline
criterion is now a committed synthesized fixture and the live `LUM_CoreTex.utx` 30 → 0 count is
integration-tier), and the decode oracle (spike
[`../../../spikes/2026-07-26-ucc-texture-fixture/`](../../../spikes/2026-07-26-ucc-texture-fixture/findings.md)
builds the fixture's P8 half with the game's own `ucc make` — byte-exact — and its DXT1 half with
Pillow, so the cross-check stays independent with no copyrighted content). That spike also **refuted
the plan's own ≤8/255 discrimination claim**: an index bit-offset bug scores 4.801 and PASSES, so
S4 now carries a second byte-exact pin.

**SCOPE WIDENED 2026-07-26 (owner ruling)** — a new slice `S2b` adds the two accessors
`actor preview --faces textured` needs (a mip pyramid, and `bMasked` carried on S2's typed result — **not** a `texture_has_bMasked` predicate, which `conventions.md`'s predicate rule forbids), so the texture
API changes once rather than twice. **The plan therefore re-enters the plan-review round
before building.** See `../../../specs/2026-07-26-actor-preview-textured-faces.md` §12.

**Nine slices:** `S1` CompMips + fixture builder → `S2` typed error results → `S3` layout
detection → `S4` BC1 → `S5` BC2/BC3 → `S6` integration sweep + engine-fact pins → `S7` docs/board.

**Gates** slice `S8a` of board item `unified-asset-catalog`. Land it **before any texture is
classified**: catalog shards are named `sha256(w,h,RGB)`, a frozen identity, so a later decode
change silently re-keys and orphans them.

**Two items were builder-decided under delegation ("do whatever it takes") and are reversible:**
a data-vs-`Format` disagreement is a named `format-disagreement` error rather than a note
(measured to fire on 0 of 18,176 exports today), and decode emits the mask the data carries
without consulting `bMasked`/`bAlphaTexture` (which `Engine.Texture` defaults to `False`, so
gating on them would silently switch block alpha off corpus-wide).
