# Plan: add the five missing surface poly-flags

Build in a feature worktree (`andrzej/p3/missing-poly-flags`), one squash-merged commit. Everything
downstream of `PF_NAMES` derives the set automatically, so the code change is one list edit.

## Slice 1 — widen `PF_NAMES`

- Append the five `(bit, name)` pairs to `query.PF_NAMES` (`query.py:17-22`), ascending by bit:
  `(0x1000,"bigwavy")`, `(0x2000,"smallwavy")`, `(0x8000,"lowshadowdetail")`,
  `(0x80000,"brightcorners")`, `(0x800000,"highshadowdetail")`.
- No other code edit: `surface._FLAG_BY_NAME`/`encode_flags` (`surface.py:34-49`), the
  `--add-flag`/`--remove-flag` choices (`cli/parsers/brush.py:409-434`), and `brush build sheet
  --flag` (`:196-202`) all derive from `PF_NAMES`. `decode_flags` now names these bits instead of a
  hex tail — a behavior change to pin, not code to write.

Tests (`tests/test_surface.py`):
- Extend the encode/decode round-trip: every `PF_NAMES` name `encode_flags` → `decode_flags` back to
  itself; assert the five new names map to the expected bits (`bigwavy`→`0x1000`, etc.).
- Assert `decode_flags(0x1000) == ["bigwavy"]` (was `["0x1000"]` before) for each of the five.

## Slice 2 — catalog-agreement regression

- New test (`tests/test_surface.py` or a small `tests/test_flag_catalog.py`): parse the flag-bit
  table in `dev/docs/unrealed/leveldesign/kb/textures.md` and assert its `PF_*` bit set equals
  `query.PF_NAMES`'s bit set, so the doc and the settable set cannot drift again.

## Slice 3 — refresh parser baselines

- Regenerate `tests/fixtures/parser_baseline/{help.json,action_tree.json}` — the `--add-flag`/
  `--remove-flag`/`--flag` `choices` widen by five.

## Slice 4 — docs

- **`dev/docs/unrealed/leveldesign/kb/textures.md` (owner-approval-gated — do NOT edit unasked).**
  The needed diff: `:30` "exposes 16 flag names" → 21; drop the five *(no `--add-flag`)* tags and the
  `:31-32` "not in that set (they need a raw bit write)" sentence; drop the *(no `--add-flag`)* tags
  on the five table rows (`:44-49`). Propose the exact diff to the owner and wait for a yes before
  touching it. The catalog-agreement test (Slice 2) fails until this lands, so sequence the doc edit
  with the code in the same merge.
- **User-facing (no approval needed — tool-behavior):** `docs/leveldesign/general/textures-and-surfaces.md:47`
  "The 16 flags uedcli can set by name: …" → 21, listing the five new names. Grep `docs/usage.md`
  and `docs/leveldesign/` for any other "16 flags"/settable-set claim; none found beyond that line,
  but re-check at build time.

## Verify

- `bin/test -k "surface or flag or cli"` green; formatter/linter/type-checker on touched files.
- Exercise live: `brush build sheet --width 128 --height 128 --flag brightcorners | actor add -`,
  then `brush poly find … | brush poly set - --add-flag highshadowdetail --remove-flag lowshadowdetail`,
  then `brush poly list` shows the names decoded (not a hex tail).
- One subagent reviews `git diff base...HEAD` (must read `dev/docs/direction/conventions.md`,
  `dev/docs/unrealed/t3d.md` "Polygon sub-fields", `CLAUDE.md`); fix confirmed findings; re-test.
- **Blocking gate:** the `kb/textures.md` edit needs the owner's explicit yes — do not merge until it
  is granted, since the agreement test depends on it. If not yet granted at build time, park via
  `bin/board new inbox '[OWNER — confirm] kb/textures.md poly-flag count 16→21'` with the diff.
- `git mv` to `done/`, cut `overview.md` to one line, squash-merge.
