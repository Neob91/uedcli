# `mover key` keyframe model: `count` owns `NumKeys`, `move`/`rotate` edit + required frame

**Status:** SPEC (not built). Brainstormed with Andrzej 2026-07-20; grounded by the live spike
`spikes/2026-07-20-mover-numkeys-trailing-zero/`. This is the **final** model; it supersedes this
spec's two earlier drafts (a `--from-base` opt-in flag; then "index-addressed create-or-edit"). The
net design and its rejected alternatives are below.

Decisions (+ rejected alternatives) live in [`decisions.md`](../decisions.md) 2026-07-20; this spec
is ephemeral scratch (fold what ships into `architecture.md` / `usage.md`).

## Background: the mover keyframe data model

A `Mover` keeps its **base pose** in the ordinary `Location`/`Rotation` fields (key 0). Movement
keyframes are 0-based: **key 0 is the base pose** (no `KeyPos`/`KeyRot` line — it *is* where the mover
sits); keys 1 … `NumKeys-1` are stored as offsets **from base** in the fixed-size arrays
`KeyPos[8]`/`KeyRot[8]`. Two distinct props:

- **`NumKeys`** — the *runtime count* of active waypoints (the mover interpolates through keys
  0 … `NumKeys-1`). It is authoritative: the engine cannot infer the count from which `KeyPos` lines
  exist, because a key at the base pose stores no line yet is still a real waypoint. **Live-verified**
  (`spikes/2026-07-20-mover-numkeys-trailing-zero/`): the editor preserves an authored `NumKeys`
  through `MAP IMPORTADD` + `MAP REBUILD` even when every movement key is at base — it never
  auto-decrements. `KeyPos`/`KeyRot` are a fixed `[8]` array, so `NumKeys` is meaningful only in
  `2 … 8` (`MIN_KEYS`/`MAX_KEYS`).
- **`KeyNum`** — the editor's *view selector* (which keyframe is displayed); pure editing-time state,
  which uedctl canonicalizes to 0 on ingest. Not authored here.

## Problems being solved

1. **No way to author the base-relative offset directly.** Today `mover key move/rotate` take
   world-absolute targets and subtract the base, so `--to 0,0,0` means the world origin, not the
   mover's own position; a forgotten-frame `--to` silently misauthors (`--to 0,0,90` meaning "up 90"
   yields `(0,0,90) − Location`, no error).
2. **`mover key add`'s "next slot" is ambiguous.** It finds the slot by the lowest index with no
   stored `KeyPos`/`KeyRot` line — but a key deliberately at the base pose has no line, so it looks
   free and the next `add` overwrites it.
3. **`NumKeys` itself is not directly settable** (hard-rejected from `actor prop`), so there is no way
   to set a mover's waypoint count as a first-class operation (the editor's own authoring flow is "set
   NumKeys, then position each key").

## Design

Verb set (of `mover key`): **`count`** (new), **`move`**/**`rotate`** (reworked), **`remove`**/
**`list`** (unchanged). **`add` is removed.**

### `mover key count <name> [<n>]` — get/set `NumKeys`

- No `<n>`: **print** the current `NumKeys` to stdout.
- With `<n>`: **set** `NumKeys = n`. **Non-destructive** — it only changes the count; it never clears
  key values. Lowering the count leaves the now-inactive keys' `KeyPos`/`KeyRot` lines in place
  (dormant), so `count 2` then `count 6` restores them. Raising it activates keys that default to the
  base pose (no line) unless they already carry a dormant value.
- **Bounds `2 … 8`** (`MIN_KEYS`/`MAX_KEYS`); out of range is a clean error naming the value.
- **Exactly equivalent to `actor prop set <name> NumKeys=<n>`** (see below) — same underlying setter,
  same validation, no `count`-specific side effects. `count`'s only extras are the **getter** and
  living in the discoverable `mover key` namespace.

`NumKeys` therefore comes **off** the `actor prop` hard-reject list (`propedit.HARD_REJECT`): both
`mover key count <name> <n>` and `actor prop set <name> NumKeys=<n>` set it, routed through one
shared setter that enforces `2 … 8` (naming the offending value) and preserves the editor's
omit-when-default(2) canonical form. `KeyPos`/`KeyRot`/`KeyNum` **stay** hard-rejected (author
keyframe geometry with `move`/`rotate`; `KeyNum` is canonicalized away).

### `mover key move <i>` / `rotate <i>` — edit an existing key, with a required frame

- **Edit-only:** `i` must be an existing movement key, `1 ≤ i < NumKeys`. They do **not** grow
  `NumKeys` (raising the count is `count`'s job). `i == 0` → error (base pose — use `actor
  move`/`actor rotate` on the mover); `i ≥ NumKeys` → error naming the fix ("no key `i`; raise the
  count first with `mover key count <name> <n>`").
- **Required coordinate frame on `--to`** (a mutually-exclusive pair, exactly one required when
  `--to` is given):
  - `--from-base` — coords are the offset from the base pose; written straight into
    `KeyPos`/`KeyRot` (base-subtraction skipped). `--to 0,0,64 --from-base` = 64uu above base.
  - `--from-world` — world-absolute (today's math): `KeyPos = to − Location`,
    `KeyRot = subtract_uu(to, base)`; for rotation, an absolute orientation.
  - No frame flag with `--to` → error ("choose --from-base or --from-world"), removing the
    silent-misauthoring footgun.
- `--by DX,DY,DZ` (delta on the *current* stored offset) takes **no** frame and rejects one (a delta
  is frame-agnostic — `KeyPos` is world-additive, not base-rotated; 2026-06-25 mover spike). `--to`
  and `--by` remain a required mutually-exclusive group.

### `mover key remove <i>` / `list` — unchanged

- `remove <i>` deletes key `i` and compacts (shifts higher keys down, `NumKeys--`) — the surgical,
  renumbering delete, distinct from `count`'s non-destructive count change.
- `list` prints one row per key `0 … NumKeys-1` (key 0 tagged `(base)`, world pose + stored offset);
  it remains the natural way to see all keys. (`count` with no arg is the direct scalar read.)

## Per-verb reference (post-change)

```
mover key count  <name> [<n>]                                       # print / set NumKeys (2..8), non-destructive
mover key move   <name> <i> ( --to X,Y,Z (--from-base|--from-world) | --by DX,DY,DZ )   # edit existing key i (1<=i<NumKeys)
mover key rotate <name> <i> ( --to P,Y,R (--from-base|--from-world) | --by DP,DY,DR )
mover key remove <name> <i>                                         # delete key i + compact (NumKeys--)
mover key list   <name> [--json]
# mover key add — REMOVED
```

Workflow — a 4-stop elevator: `mover key count lift 4`, then `mover key move lift 1|2|3 --from-base
--to …` (in any order — all keys exist). Reset to a plain door: `mover key count lift 2` (keeps the
stored key-2/3 offsets dormant in case you raise it again).

## Scope of change

`uedctl/cli.py`
- **Add** the `count` subparser: `name`, optional `n` (int), `_target_flag`. Help explains the
  non-destructive get/set and the `2..8` bound.
- **Remove** the `add` subparser (`mka`) and its `--at`/`--rot`.
- `move`/`rotate`: keep the `--to`/`--by` required mutually-exclusive group; add the frame pair
  `--from-base`/`--from-world` (own group, enforced in dispatch — see Validation). Update `--to`/subparser
  help off the unconditional "absolute world" wording.

`uedctl/dispatch.py` `_dispatch_mover_key`
- **Add** `keysub == "count"`: is-mover guard; no `n` → print `movers.num_keys(actor)`; with `n` →
  set via the shared NumKeys setter (bounds + canonical form).
- **Delete** the `add` branch.
- `move`/`rotate`: index guard `1 ≤ i < num_keys` (reject `0`, reject `≥ num_keys` with the
  raise-count hint); frame gating on `--to` (`--from-base` writes the triple directly; `--from-world`
  the base-subtracted math); reject a frame flag with `--by`; reject `--to` with no frame. Guards
  before any mutation.

`uedctl/propedit.py`
- Remove `"numkeys"` from `HARD_REJECT` (keep `name`, `brush`, `keypos`, `keyrot`, `keynum`).
- Route a `NumKeys` set through the shared setter that enforces `2 … 8` (error names the value) and
  keeps the omit-when-2 canonical form — so `actor prop set NumKeys=` and `mover key count` are
  byte-identical in effect.

`uedctl/movers.py`
- Add `set_num_keys(actor, n)` (the shared setter: validate `2 ≤ n ≤ 8`, write via `_set_numkeys`
  for omit-at-2). `num_keys` already reads it.
- Remove `next_key_index` (its only caller, `add`, is gone). `set_key_pos`/`set_key_rot` unchanged
  (they only grow `NumKeys`, but `move`/`rotate` now pass existing indices so they never grow it).

## Validation / error handling (all `_SelectionExit`, non-zero, never a traceback; name the value)

- `count`: `n` outside `2 … 8` → error ("NumKeys must be 2..8, got 9"). Same message via `actor prop
  set NumKeys=9`. Non-mover `NumKeys` set is already rejected by schema (prop not in the class).
- `move`/`rotate`: `i == 0` → base-pose error; `i ≥ NumKeys` → "no key i; raise the count first";
  `--to` without a frame → error; frame flag with `--by` → error. Frame/`--by` checks **before** the
  index check.
- Existing mover-class guard unchanged.

## Tests (`tests/`, offline)

- `count <name> 6` sets `NumKeys=6`; bare `count <name>` prints it; `count <name> 9` and `actor prop
  set NumKeys=9` **both** error identically (assert the full error object). `count 2` after keys were
  set leaves the `KeyPos`/`KeyRot` lines intact (non-destructive — assert the stored props survive).
- `actor prop set NumKeys=4` works (NumKeys off the reject list); `KeyPos`/`KeyRot`/`KeyNum` still
  rejected (guard test).
- `move 1 --to 0,0,64 --from-base` on a mover with non-zero `Location` (`512.5,-256.25,96.0`) writes
  `KeyPos(1)=(0,0,64)` (not `− Location`); `--from-world` writes `to − Location`. `rotate` analogs
  (`--from-world` uses the distinct `subtract_uu` path — own regression).
- `move`/`rotate` are edit-only: `move 3` on a 3-key mover (`i == NumKeys`) → "raise the count" error;
  `move 0` → base error.
- `move --to` with no frame → error; `move --by … --from-base` → error; full error objects.
- No-auto-decrement engine fact: `test_it_keeps_numkeys_when_a_key_is_zeroed` (already committed with
  the spike).
- `mover key add` gone: argparse unknown-subcommand (guard test so the removal is deliberate).
- Update the `--help`/CLI-consistency sweep for `count`, the frame flags, and the dropped `add`.

## Docs

- `usage.md` — the verb set; `count` (get/set, non-destructive, == `actor prop set NumKeys`); the
  required `--from-base`/`--from-world` frame vs `--by`; that you *raise the count then edit keys*
  (no `add`). Point authors at the timing props (`MoveTime`/`DelayTime`/`StayOpenTime`/`OtherTime`)
  and behavior enums (`MoverGlideType`/`MoverEncroachType`/`BumpType`) — all plain `actor prop set` —
  as the rest of the mover surface.
- **Tilted-base rotation caveat** — `rotation.subtract_uu`/`compose_uu` are per-component FRotator
  arithmetic, geometrically naive for a non-cardinal base; for a tilted base `Rotation`,
  `--from-world` and `--from-base` are not a simple additive re-basing.
- `architecture.md` — the keyframe verb model (count owns `NumKeys`; move/rotate edit-only + frame;
  `NumKeys` settable, other keyframe props `mover key`-only) and that it mirrors the editor's
  authoritative-`NumKeys` semantics (cite the spike).

## Rejected alternatives

- **Keep `mover key add`.** Its implicit slot pick can't tell a deliberately-base key from an empty
  one (zero offsets store no line). Replaced by explicit `count` (set the count) + index-addressed
  `move`/`rotate` (edit).
- **`move`/`rotate` auto-grow `NumKeys` (create-or-edit, contiguous).** An earlier draft; dropped in
  favor of `count` owning the count and `move`/`rotate` being edit-only (cleaner separation —
  Andrzej's call).
- **World as an implicit default frame.** Rejected for a *required* explicit frame — the world-default
  path silently misauthors the common relative case.
- **A separate `clear`/truncate verb.** Unneeded: `count <lower>` is the non-destructive reduce, and
  `remove <i>` the destructive delete. (Note `count 2` is *not* a clear — it keeps values.)
- **`NumKeys` as a raw unbounded byte.** Rejected — `KeyPos[8]` is fixed and a mover needs ≥ 2 keys,
  so `2 … 8` is enforced on both set routes (a `>8` mover reads out of bounds).
- **`--offset` arg / `--frame world|base` value / auto-decrement `NumKeys`.** As in prior drafts —
  the frame-flag pair reads best; the editor doesn't auto-decrement, so uedctl doesn't either.
