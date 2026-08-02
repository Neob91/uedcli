# Spec — `stash capture -` (stdin T3D)

## Goal

Let a T3D snippet on stdin be captured straight into a stash entry with a bare `-`, matching the
`build → add -` pipe convention, so `stash deintersect X | stash capture - --id baked` works without
`--from-t3d -`.

## Current state

Stdin capture ALREADY works today as `stash capture --from-t3d -`:

- Parser: `uedcli/cli/parsers/stash.py:14-23`. `names` (positional, subset filter) and
  `--from-t3d <FILE…|->` (`stash.py:18-21`); `-` is the stdin value.
- Reader: `uedcli/cli/ingest.py:33-39` (`read_t3d_files`: `-` is the sole value, files concatenate).
- Dispatch: `uedcli/cli/commands/stash.py:100-139`. External source is validated by
  `validate_ingest_actors`; else the trunk is the source. The `names` subset is filtered against the
  raw source Names (`stash.py:64-68`), then duplicates uniquified (`stash.py:71-77`).
- `--tree` + `--from-t3d` is already rejected as two sources (`stash.py:105-107`).

Convention precedent — `actor add`: a bare `-` positional (`file`) reads a T3D snippet from stdin
(`uedcli/cli/parsers/actor.py:262-264`, `uedcli/cli/commands/actor/edit.py:139-145`). Empty T3D there
is an error, exit 2 `no actors found in the T3D input` (`edit.py:375-376`) — NOT the name-list no-op.

So the item is an ergonomics + spelling change, not new capability.

## Design — the verb surface — DECIDED (owner, 2026-08-02)

Adopt the bare `stash capture - [names…]` form and **DROP `--from-t3d -`** (so `--from-t3d` is
files-only) per no-back-compat — one stdin spelling, not two. Empty stdin **exits 2** (matching
`actor add -`), not the name-list no-op. `conventions.md` (no back-compat alias):

```
stash capture [- [names…] | names…] [--from-t3d FILE…] [--tree KIND/NAME] [--id ID] [--force]
```

- A leading `-` positional = read T3D from stdin as the SOURCE. Remaining positionals stay the subset
  filter, preserving what `--from-t3d -` does today (`stash capture - Pillar1`). Actor names are never
  `-`, so a leading `-` is unambiguous.
- No leading `-` = source is the trunk (`--tree`/`$UEDCLI_LEVEL`) or `--from-t3d FILE…`; positionals
  are the subset.
- `-` is mutually exclusive with `--from-t3d` and `--tree` (each names a source) — same shape as the
  existing `--tree`+`--from-t3d` guard.
- `--from-t3d` keeps `FILE…` (multiple concatenate) but no longer accepts `-`.

Reuse `ingest.read_t3d_input("-")` for the read and the existing `_capture_from_t3d` path for
parse/subset/uniquify/normalize — the source token only decides where `text` comes from.

Empty stdin → exit 2 (existing `capture source has no actors`, `stash.py:69-70`), matching
`actor add -`. A T3D-snippet source that yields no actors is an error, not the name-list no-op.

## Edge cases & errors

| Case | Exit |
|-----------------------------------------------------|---
| `-` with `--from-t3d` or `--tree` (two sources) | 2, naming the conflict (mirror `stash.py:105-107`) |
| empty / whitespace-only stdin | 2 `capture source has no actors` — clean, not a traceback |
| `names` subset names an actor absent from the stream | 2 `actors not found in source: …` (`stash.py:66-67`) |
| duplicate Names in the stream | uniquified, none dropped (`stash.py:71-77`; safety.md "Ingest never collapses duplicates") |
| builder brush in the stream | dropped (`stash.py:54`) |
| unknown class / texture in the stream | 2 via `validate_ingest_actors` (`ingest.py:42-64`) |
| `--id` collision, no `--force` | 2 (safety.md); `--force` over a corrupt box → 2 (safety.md) |

## Tests

- `stash capture -` from a piped snippet stores all actors; stdout prints the id.
- `stash deintersect … | stash capture - --id baked` round-trips (or the nearest producer available).
- `stash capture - Name1` subsets the stream.
- `-` + `--from-t3d` → exit 2; `-` + `--tree` → exit 2.
- empty stdin → exit 2, no traceback (regression for the CLI "never a bare exception" rule).
- `--from-t3d -` (the removed spelling) is rejected — pin the removal so it can't creep back as a
  dual spelling.

## Docs to update in the same change

- `docs/usage.md` (`stash capture`): the bare `- [names…]` stdin-T3D source, `-` mutually exclusive
  with `--from-t3d`/`--tree`, `--from-t3d` now files-only, empty stdin exits 2.

## Notes

- Cross-verb asymmetry (accepted, out of scope here): after this change `stash capture` reads stdin
  T3D via a bare `-` and no longer via `--from-t3d -`, but `actor preview` still takes stdin T3D as
  `--from-t3d -` (`preview.py:52`). A tool-wide reconcile of the stdin spelling is filed as a SEPARATE
  follow-on board item; do not resolve it in this change.
