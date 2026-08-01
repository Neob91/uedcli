# Spec — `stash apply` double-suffix + document `--at`

## Goal

1. A placed actor gets ONE random suffix, not two: `Pillar_abc123` → `Pillar_def456`, never
   `Pillar_abc123_def456`.
2. The `--at` flag help states what `--at` actually anchors (the bbox-min corner), not "Location".

## Current state

Double suffix — `uedcli/cli/placement.py:92-93`:

```
stem = a.name          # captured name — for a trunk member this ALREADY carries `_<rand>`
a.name = trunk.alloc_name(stem, existing_names)   # appends ANOTHER `_<rand>`
```

A trunk actor is stored as `<stem>_<rand>` (every `actor add`/generator add allocates one). Capture
keeps that name verbatim (`uedcli/cli/commands/stash.py`, trunk branch — names are unique so uniquify
does not touch them). Apply then feeds the full `Pillar_abc123` as the stem into
`trunk.alloc_name` (`uedcli/t3dtree.py:102-108`), which unconditionally appends `_<rand>` →
`Pillar_abc123_def456`.

- Suffix format: `_` + `_SUFFIX_LEN` (=6) chars from `_SUFFIX_ALPHABET` (`0123456789a-z`) —
  `uedcli/t3dtree.py:36-37, 98-99`.
- The SAME re-suffix pattern lives at `uedcli/cli/commands/actor/edit.py:434-436`, so
  `actor add -` and `actor duplicate` (`actor show X | actor add -`) double-suffix identically. See
  the scope question.
- The board example `Pillar_iisch_77db4m` shows a 5-char inner segment (`iisch`): it predates the
  current 6-char format or was a `--base-name` with an underscore. The mechanism is the same; the
  strip keys off the current `_SUFFIX_LEN` format.

`--at` doc gap — `uedcli/cli/parsers/_arguments.py:339`:

```
"world Location to place the set at (default: its captured origin)"
```

Wrong on both counts. Apply anchors the set's bbox-min CORNER, not the actor Location
(`placement.py:48-53`), and the no-`--at` default is the captured world ANCHOR (bbox-min), not the
origin. `docs/usage.md` already states the bbox-min contract correctly (lines 474-477 and 1264); only
the flag `-h`/`--help` text is stale.

Related stale help (bundle or note): `--folder` help (`_arguments.py:345-348`) says "absent --folder,
placed actors are unfoldered", but since the unify-T3D-trees change a member lands in its STORED
folder by default (`placement.py:44-46`, and `--folder` overrides).

## Design — the fix + recommendation

Add `trunk.strip_alloc_suffix(name)` beside `alloc_name` (`uedcli/t3dtree.py`, re-exported through
`trunk`): strip one trailing `_[0-9a-z]{SUFFIX_LEN}` if present, else return the name unchanged. Then
in `placement.py`:

```
stem = trunk.strip_alloc_suffix(a.name)
a.name = trunk.alloc_name(stem, existing_names)
```

Result: a captured `Pillar_abc123` → stem `Pillar` → single `Pillar_def456`. A `--base-name Pillar1`
(no alloc suffix) is unchanged → still `Pillar1_<rand>`, so the intent the current
`placement.py:92` comment protects is preserved.

Doc fixes (matching existing behavior — no new claims, allowed as tool-behavior docs):

- `--at` help → e.g. "world point to land the set's bbox-min CORNER on (default: the set's captured
  world anchor, its bbox-min)".
- `--folder` help → state the stored-folder default.

Recommendation: put the strip in the shared helper and apply it at BOTH stem sites (apply +
`edit.py:434-436`) so `apply`, `add -` and `duplicate` behave uniformly — leaving `duplicate`
double-suffixing while `apply` is fixed would be a new inconsistency. If the owner wants the minimal
change, apply-only. See the scope question.

## Edge cases & errors

- Name collisions: `alloc_name` still re-rolls against `existing_names` until unique
  (`t3dtree.py:105-108`), so two applies of one stash never collide — coordination-free identity is
  preserved (safety.md "Actor names carry a random suffix"). The strip only changes the cosmetic
  stem, never whether a suffix is added.
- Over-strip: an external-source name (or a `--base-name`) that coincidentally ends
  `_[0-9a-z]{6}` loses that segment. Harmless — a fresh suffix is still appended, so identity holds;
  only the stem's cosmetics change. Note it; do not add a guard for it.
- A captured name with NO alloc suffix (external T3D) → stem unchanged, single suffix appended.
- Empty apply source → existing `nothing to apply` exit 2 (`placement.py:37-38`), unchanged.

## Tests

- Capture a trunk `Pillar_<rand>`, apply, assert the placed name matches `^Pillar_[0-9a-z]{6}$` — a
  single suffix, not `Pillar_<rand>_<rand>` (inject `_rand` for determinism).
- Apply twice: two distinct single-suffix names, no collision.
- External-source name without an alloc suffix → single suffix.
- `strip_alloc_suffix` unit: strips exactly one trailing `_<6>`; leaves `Pillar1`, `Pillar`, and a
  name whose tail is not the alloc format untouched.
- `--at` `-h` text contains "corner" / "bbox-min" and not "Location" (guards the help from
  regressing). Same style for `--folder` if fixed.
- If scope includes add/duplicate: `actor show X | actor add -` yields a single suffix.

## Open questions

- `questions/suffix-strip-scope.md` — strip in `stash`/`prefab apply` only, or also in
  `actor add -` / `actor duplicate` (same double-suffix). Blocks the change's blast radius.
