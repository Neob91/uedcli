# Spec — add the missing surface poly-flags to the settable set

## Goal

Make the five real `PolyFlags` bits that `kb/textures.md` documents but no verb can set settable via
`brush poly set --add-flag/--remove-flag` (and `brush build sheet --flag`), by adding them to
`query.PF_NAMES`. Reconcile the docs' "these are the settable names" claim with the widened set.

The five, by their kb spelling and bit:

| Name (lowercased) | Bit | UE1 flag | What it does |
|--------------------|-----------|----------------------|---
| `bigwavy` | `0x1000` | `PF_BigWavy` | large ripple render distortion |
| `smallwavy` | `0x2000` | `PF_SmallWavy` | small ripple render distortion |
| `lowshadowdetail` | `0x8000` | `PF_LowShadowDetail` | coarse per-surface lightmap resolution |
| `brightcorners` | `0x80000` | `PF_BrightCorners` | lightmap edge-brightening (kills dark seams) |
| `highshadowdetail` | `0x800000` | `PF_HighShadowDetail` | crisp per-surface lightmap resolution |

## Current state

- `query.py:17-22` — `PF_NAMES`: 16 `(bit, name)` pairs. None of the five above are present.
- `query.py:25-31` — `decode_flags`: names only `PF_NAMES` bits; any other set bit is emitted as a hex
  tail. So today these five decode to hex, not names (the overview's "can READ" means the bit survives
  in the int, not that it is named).
- `surface.py:34-49` — `_FLAG_BY_NAME` and `encode_flags` derive from `PF_NAMES`; `encode_flags`
  strictly rejects any unknown name.
- `cli/parsers/brush.py:409-410,429-434` — `--add-flag`/`--remove-flag` take `choices=flag_names`
  built from `PF_NAMES`; `196-202` — `brush build sheet --flag` the same.
- `dev/docs/unrealed/leveldesign/kb/textures.md:30-32,44-49` — claims uedcli "exposes 16 flag names",
  tags these five *(no `--add-flag`)*.

None of the five affects CSG or solidity: the native core reads only `PF_Semisolid`/`PF_NotSolid`/
`PF_Portal` (`uedcli-native/src/csg.rs:18-21`), so these are pure render/lightmap attributes. Per-poly
`PolyFlags` survive the paste path unchanged (`quirks.md` "Surfaces / polys"), so all five are
round-trip-clean and carry no build risk — they are plain authorable bits, distinct from every
existing `PF_NAMES` bit and from the editor-transient bits (`PF_Selected`/`PF_Memorized`) that must
never be settable.

## Design — CLI surface

Append the five pairs to `PF_NAMES`. No new flags, no help rewrite: `--add-flag`/`--remove-flag`/
`--flag` inherit the wider `choices=` automatically. The generic help lines stay accurate:

    --add-flag FLAG      repeatable; surface flag by name (case-insensitive), not bit value
    --remove-flag FLAG   repeatable; surface flag by name (case-insensitive), not bit value

Ordering in `PF_NAMES`: append by ascending bit, matching the existing rough order.

## Decisions

- **Add ALL five** — `bigwavy`, `smallwavy`, `lowshadowdetail`, `highshadowdetail`, `brightcorners`
  (owner, 2026-08-02). They are plain bits, round-trip-clean, CSG-neutral; the guiding goal is to
  expose every UnrealEd surface attribute as text. The "distortion / lightmap memory" side effects
  are deliberate author choices documented in the kb, not correctness risks. No subset held back.

## Edge cases & errors

- Unknown flag name → argparse `choices=` rejects at parse (exit 2); `encode_flags` also rejects,
  `ValueError` naming the bad name → exit 2. Already covered; the five simply widen the accepted set.
- `decode_flags` now names these bits instead of a hex tail — pin with an encode↔decode symmetry test.

## Tests

- `test_surface.py` — extend the encode/decode round-trip: every `PF_NAMES` name must
  `encode_flags` → `decode_flags` back to itself; assert the five new names set the expected bits.
- Catalog-agreement regression (overview asks for it): a test that the `PF_NAMES` name set equals the
  set of flag rows in `kb/textures.md` (parse the table's bits), so the two cannot drift again.
- Refresh `tests/fixtures/parser_baseline/{help.json,action_tree.json}` — `choices` widen.

## Docs

- `dev/docs/unrealed/leveldesign/kb/textures.md` — drop the five *(no `--add-flag`)* tags and change
  "exposes 16 flag names" → 21. **This is a `dev/docs` edit → needs the owner's explicit yes** (propose
  the exact diff; do not edit unasked).
- Check `docs/leveldesign/` and `docs/usage.md` (user-facing) for any "16 flags" / settable-set claim
  and update it in the same change (CLAUDE.md "Documentation"). Found:
  `docs/leveldesign/general/textures-and-surfaces.md:47` ("The 16 flags uedcli can set by name: …").
