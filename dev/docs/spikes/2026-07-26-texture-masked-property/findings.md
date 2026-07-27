# Spike — the TEXTURE-side `Masked` property

**Date:** 2026-07-26 · **Status:** complete · **Unblocks:**
board item `four-actor-preview-faces-rulings-need-a-durable` §11

## The question

`unrealed/quirks.md` established (🔬, owner 2026-07-26) that `Masked` is a property of the **texture**,
set at import, and that a texture's flags are OR'ed into every surface using it — but recorded the
property as *"not yet probed to the stored property name/offset on the export."*

`actor preview --faces textured` renders a face's real texture, so it must decide **per face**
whether palette index 0 is a cut-out or an ordinary colour. Without the texture-side half of that
gate it cannot be correct. Spec review round 1 parked the spec as structural on exactly this point.

Terms, defined once. A **P8** texture stores one byte per texel, an **index** into a 256-entry
**palette**. **Index 0** is conventionally a transparency key, but only on a face the engine draws
masked. `PF_Masked` (`0x2`, `query.PF_NAMES`) is the **per-poly** surface flag; this spike is about
the separate **per-texture** property.

## Harness

`harness/probe_masked.py` — reads the property block of every `Texture` export without decoding
mips (fast), and correlates it with actual index-0 usage.

```
probe_masked.py --known     # the ground-truth set + property frequency
probe_masked.py --sweep     # corpus-wide blast radius
```

Point it elsewhere with `$UEDCLI_SPIKE_TEXTURES`. It needs the game's `.utx` packages, which are
user-supplied and gitignored, so it is not a test — the pins are in `test_engine_facts.py` (§5).

## Finding 1 — the property is `bMasked`, stored PRESENCE-ONLY

Dumping every property across the packages touched leaves exactly one candidate that varies with
masking:

```
   610  Palette / UBits / VBits / USize / VSize / UClamp / VClamp / MipZero / InternalTime
   295  DetailTexture
   122  AnimNext
    92  bMasked              True×92        <- the only masking-related property, and never False
```

`bMasked` is a UE1 bool (`_PT_BOOL`), which `utexture._read_props` already decodes — the value rides
in the info byte's high bit, so no new parser is needed. **Across the whole 2,669-texture corpus, 191
textures carry `bMasked` and every one of them is `True`.**

That is UE1's property-serialisation rule, not a coincidence: a property equal to its class default
is omitted, and `UTexture.bMasked` defaults False. So:

> **`bMasked` present ⇒ the texture is masked. `bMasked` absent ⇒ it is not.**
> A stored `bMasked=False` does not occur.

**The gate `--faces textured` needs is therefore:**

```
masked = bool(poly.flags & 0x2) or texture_has_bMasked(ref)
```

Both halves are load-bearing. Gating on the poly flag alone misses `CoreTexMetal.ladder_a` — 66 % of
its texels are index 0, it carries `bMasked`, and on the ContainerYard containers it was painted on a
face whose polys decode to `flags: none`. That is precisely the "you look straight through two solid
containers" bug.

## Finding 2 — ungated masking would be catastrophic, and here is the number

Corpus sweep (`--sweep`, 57 packages, mip 0):

| | count | share
|---|---|---
| textures scanned | 2,669 | —
| carry `bMasked` | 191 | 7.2 %
| use index 0 **and** carry `bMasked` | 181 | genuine cut-outs
| **use index 0 and do NOT carry `bMasked`** | **464** | **17.4 % — false holes if ungated**

The worst offenders are flat colour swatches that are **100 %** index 0 — `LUM_CoreTex.White`,
`.Red`, `.Yellow`, `.SILVER`, `.NAVY`, and eight more. Under the spec's original unconditional
masking, a face textured with any of them would have rendered as **nothing at all**: every texel
skipped, no depth written, the geometry behind showing through a face-shaped hole.

`LUM_InfoPortraits.ArthurCallaway` is the committed counter-example used by the regression test: no
`bMasked`, palette[0] is real black `(0,0,0)` rather than the reserved key, 2.2 % of texels.

## Finding 3 — reserved magenta at palette[0] does NOT mean masked

A tempting shortcut is "index 0 is magenta ⇒ it is a transparency key". It does not hold:

| texture | `bMasked` | index-0 use | palette[0]
|--------------------------------|-----------|-------------|---
| `CoreTexMetal.ladder_a` | **True** | 66.19 % | (255, 0, 255)
| `CoreTexMetal.ClenChainlink_B` | **True** | 58.63 % | (255, 0, 255)
| `Paris.pa_gate_a` | **True** | 61.42 % | (255, 0, 255)
| `CoreTexMisc.DangDoNoEnter_A` | **True** | 27.34 % | (255, 0, 255)
| `CoreTexMetal.ShipGrayMetal_A` | False | 0.00 % | (255, 0, 255)
| `CoreTexWater.dirtywater` | False | 0.00 % | (255, 0, 255)
| `MolePeople.WirePanel` | False | 0.00 % | (255, 0, 255)
| `LUM_InfoPortraits.ArthurCallaway` | False | **2.22 %** | (0, 0, 0)

Three unmasked textures park magenta at index 0 and never use it — the key colour is a **palette
convention**, not a flag. And the one texture that genuinely needs protecting from a false hole
(`ArthurCallaway`) does not use magenta at all. `bMasked` is the only reliable signal.

## Finding 4 — two claims in the friction log are contradicted by the texture data

[`spikes/levelbuild-friction/agent-reports.md`](../levelbuild-friction/agent-reports.md) is
render-observation evidence and was the starting ground truth for this spike. Two of its inferences
do not survive contact with the packages. Recorded because both are cited elsewhere as fact:

1. **`Paris.pa_gate_a` — "flagging it turned out to be a no-op, its gaps are painted, not index 0."**
   The texture is **61.42 % index 0** and carries `bMasked`. The observation (adding `PF_Masked`
   changed nothing) was right; the explanation was wrong. Adding the *surface* flag was a no-op
   because the **texture already masks by itself** — the OR in the gate was already satisfied. This
   is a much better illustration of the engine rule than the log's own examples.

2. **`MolePeople.WirePanel` — "`--add-flag Masked` fixed it outright", with before/after shots.**
   `WirePanel` carries **no** `bMasked` and uses index 0 for **0.00 %** of its texels (its palette
   parks unused magenta there). Masking that face cannot have changed a pixel. Note also that **no
   texture in the entire `MolePeople` package carries `bMasked`** (0 of 88). Whatever produced the
   reported before/after, it was not index-0 masking. **Left open** — it is a claim about a past
   render this spike cannot re-run, and it does not affect the gate.

## Finding 5 — decoder gotcha worth one line

`TextureObj.palette_ref` is an **object ref**, not an export index. Passing it straight to
`decode_palette` raises `ValueError: palette body not at EOF`. It must go through
`utexture.export_index_of_ref(pkg, ref)`. This cost a false "decoder bug" during the spike and is now
noted in `quirks.md` and in the harness.

## Pins (per `rules/spikes.md`)

Two regressions in `uedcli/tests/test_engine_facts.py`, both offline against **committed** fixtures
(the game `.utx` corpus is user-supplied and gitignored, so it cannot be the pin):

- `test_utexture_bmasked_is_stored_presence_only_and_never_as_false` — a decoder change that started
  materialising `bMasked=False` would invert the gate; this trips first.
- `test_index_zero_is_an_ordinary_colour_on_an_unmasked_texture` — pins `ArthurCallaway` as an
  unmasked texture with real-black palette[0] and ~2.2 % index-0 usage, i.e. the exact false-hole
  case. Also pins the `export_index_of_ref` requirement from finding 5.

The corpus-wide numbers in findings 2-3 are reproducible with `probe_masked.py --sweep` wherever the
game content is installed; they are evidence, not a test.

## What this unblocks

board item `four-actor-preview-faces-rulings-need-a-durable` §4.3a is now implementable as written. The
predicate is a small addition to `utexture` — read the export's property block, return
`"bMasked" in props` — and needs no new decoding.
