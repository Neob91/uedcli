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

- New test (`tests/test_surface.py` or a small `tests/test_flag_catalog.py`), **directional (subset),
  not equality**: parse the flag-bit table in `dev/docs/unrealed/leveldesign/kb/textures.md` and
  assert every kb-table `PF_*` bit is in `query.PF_NAMES`'s bit set — a documented flag is always
  settable. Equality would fail: `PF_NAMES` carries `invisible` 0x1, `notsolid` 0x8, `semisolid` 0x20,
  which the kb table omits. The subset test passes with the Slice-1 code alone, so it does **not**
  depend on the owner-gated Slice-4 doc edit.
- NOTE: a stale, conflicting `PF_*` table exists at `dev/docs/spikes/bspspike/flags.py:29-31` (e.g.
  `PF_HighShadowDetail=0x10000`, `PF_BrightCorners=0x4000000`). Parse only `kb/textures.md`, never that
  file; it is a grep hazard, not the source of truth.

## Slice 3 — refresh parser baselines

- Regenerate the parser-baseline fixtures with `python -m uedcli.tests.parser_baseline` and commit
  `tests/fixtures/parser_baseline/{action_tree.json,help.json,argv_corpus.json}` — any parser-surface
  change (here the `--add-flag`/`--remove-flag`/`--flag` `choices` widen by five) reddens
  `test_action_tree_matches_baseline` / `test_help_screens_match_baseline` (`test_parser_baseline.py`)
  otherwise.

## Slice 4 — docs

- **`dev/docs/unrealed/leveldesign/kb/textures.md` (owner-approval-gated — do NOT edit unasked).**
  The needed diff: `:30` "exposes 16 flag names" → 21; drop the five *(no `--add-flag`)* tags and the
  `:31-32` "not in that set (they need a raw bit write)" sentence; drop the *(no `--add-flag`)* tags
  on the five table rows (`:44-49`). Propose the exact diff to the owner and wait for a yes before
  touching it. This is **no longer a test dependency** — the directional Slice-2 test passes on the
  code alone — so it is a correctness follow-up, not a merge blocker; land it in this merge if the yes
  is in hand, otherwise park it (see Verify).
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
- The `kb/textures.md` edit needs the owner's explicit yes, but it does **not** block this merge (the
  directional agreement test passes without it). If the yes is in hand, land the doc edit here;
  otherwise park it via `bin/board new inbox '[OWNER — confirm] kb/textures.md poly-flag count 16→21'`
  with the diff and merge the code without it.
- `git mv` to `done/`, cut `overview.md` to one line, squash-merge.
