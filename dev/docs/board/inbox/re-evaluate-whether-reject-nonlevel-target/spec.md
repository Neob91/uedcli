# Actor labels — flat, multi-valued cross-cutting classification

**Status:** spec (ephemeral — fold into `architecture.md` + `unrealed/t3d.md` on build, then this file
may be deleted). **Revised 2026-07-22** (first cold-review pass) and **re-reviewed 2026-07-24** (second
pass — stale `set`/char-class contradictions removed, box touchpoints + double-apply guard + flat
matcher/casefold folded in; §11.1 raises a scope-cut for Andrzej). Code refs are **symbol-anchored**
(line numbers drift as the tree changes concurrently — trust the symbol, not the coordinate).
**Decisions ledger:** [`decisions.md` 2026-07-22 20:49 UTC](../../../decisions.md). Every load-bearing
choice below is Andrzej's, recorded from the speccing Q&A; this spec compiles them.
**Sibling dimension:** board item `actor-folders-hierarchical-actor-organization`
— a label is the *flat, multi-valued* counterpart to the *single-path, hierarchical* `folder`. Both
are uedcli-side, never emitted to the built map, and both ride the one shared per-actor T3D-tree path.
**Pairs with** the sibling **copy-between-trees** spec (separate) — labels travel across trees the way
folders do, and that verb consumes the same inheritance rule.

---

## 1. Motivation & the concept

A build needs two *different* organizational axes:

- **`folder`** (already specced) — a single **hierarchical path** answering *"where does this live"*
  (`castle.tower.roof`). One per actor. A tree.
- **`label`** (this spec) — a flat, **multi-valued** set of tokens answering *"what is this about"*
  — cross-cutting concerns that ignore the geographic hierarchy: `lighting`, `flammable`, `hero`. An
  actor carries any number of them. This is the Gmail/GitHub-issue "labels" model: many labels per
  item, each label spanning the whole tree.

A single hierarchy can't express cross-cutting membership — a torch is at `castle.tower` (location)
*and* is `lighting` *and* is `interactive` at once, three independent axes the folder tree forces you
to collapse into one. Labels are that missing axis.

**Headline use — the duplicate handle.** `actor duplicate` mints one **fresh, unique** label
(`dup-<rand>`) and stamps it on every copy, so the whole batch is instantly re-addressable as a set
(`actor find --label dup-<rand> | …`) *after the pipeline ends* — something the stdout name list
can't give you. See §7.

### Naming: why `label`, and why it was free to take
"label" is the natural, widely-understood word for a multi-valued classification — but it collided
with two things, both now cleared:

- The engine `Actor.Tag` property (the obvious first choice, "tag") is a real UnrealScript field, matched
  today via `actor find --prop Tag=…`. Naming our dimension "tag" would sit a `--tag` filter right next
  to `--prop Tag=` — the exact overload `folder` was invented to avoid with `Group`. **Rejected: "tag".**
- "label" *was* taken by `actor preview`'s on-image text annotations (`--labels`). **Andrzej renamed that
  flag to `--annotate`** (`cli.py:137`, `dispatch.py:487`), freeing the word for the dimension where it
  fits best. (Follow-up, §13: the preview *internals* — `parse_label_spec`, `DEFAULT_LABELS`,
  `LabelSpec` — are still "label"-named; rename them to `annotation*` for clarity in a separate chore.)

### Relationship to `folder`, `Group`, `Tag` — all INDEPENDENT
A label is **not** derived from, absorbed into, or written to the `folder` sidecar, the engine `Group`
prop, or the engine `Tag` prop. It is a separate uedcli-side dimension, never emitted to the built
map. An actor may carry a folder, a `Group=`, a `Tag=`, and any number of labels; none interact.

---

## 2. Storage model — a per-actor `labels` sidecar

A label set is a **typed field on the model** and a **per-actor sidecar file in the trunk**, beside
`order_value` and `folder`:

```
<maps>/<level>/actors/<name>/
    actor.t3d       # unchanged (labels are NOT in here)
    order_value     # unchanged
    folder          # unchanged (single dotted path, if any)
    labels          # NEW — one label per line, SORTED, trailing "\n"; absent = no labels
```

- **Model:** `Actor.labels: frozenset[str]` — a typed field like `folder` (`model.py:82`), **not** a
  `props` entry. Empty set = unlabelled = no `labels` file. Because labels live on the model actor,
  the delta-write baseline (§3) is derived from `Actor.labels` directly — **no new tuple element**, so
  the `read_actor_tree` 4-tuple `(Level, ranks, bodies, folders)` and its unpack sites
  (`trunk.py:46`, `dispatch.py:1396`, `stashlib.py:157,216`) are UNCHANGED (see §3, §10).
- **One label per line, sorted.** Sorting makes the file canonical (stable git diffs). It *also*
  helps merges: because each label is its own line, two branches that `label add` **different** tokens
  to the same actor often merge cleanly (disjoint line insertions) where a single-line field would
  always conflict — but this is a *best-case tendency, not a guarantee* (git's 3-way merge still
  conflicts when both sides touch the same/adjacent hunk of a small file). Same-actor add-vs-remove of
  the same label still conflicts, exactly like a body conflict.
- **Multi-valued by definition** (Decision). The whole point is cross-cutting membership; a set, not a
  scalar. Contrast `folder` (single path) — the two dimensions are deliberately different shapes.

### Trunk I/O — the ONE shared path
Labels ride the same per-actor tree I/O as `folder`/`order_value` (`t3dtree.py`, the unify-T3D-trees
module), so trunk, stash, and prefab all read/write them through one code path:

- **read** (`read_actor_tree`): read `labels` (split on newline, strip, drop blanks → `frozenset`;
  absent/empty → `frozenset()`) into `Actor.labels`, alongside the `folder`/`order_value` reads. (The
  returned tuple shape is unchanged — labels arrive on the `Level`'s actors.)
- **write** (`write_actor_tree`): when `actor.labels` is non-empty, write the sorted one-per-line file
  **atomically via `tmp + os.replace`** (like `actor.t3d`/`folder`); when it is empty, **remove any
  existing `labels` file** (so `label clear`/`remove`-to-empty actually clears it). A lock-free reader
  never sees a torn file; a killed writer never wedges the level.

---

## 3. The delta-write diff MUST include labels — the critical trap ⚠️

**(New in the revision — the folder spec's central §2 trap, which the first draft missed.)**

`TrunkLevelSource.save` does a **delta write**: it recomputes the `changed` set from a content-diff vs
the load snapshot and writes ONLY those actors (`dispatch.py:1442-1454`):

```python
changed = {name for name, body in new_bodies.items()
           if body != self._loaded_bodies.get(name)
           or ranks[name] != self._ranks.get(name)
           or level.actors[name].folder != self._loaded_folders.get(name)}   # ← labels absent
```

A `label add`/`remove`/`clear` leaves the body, rank, AND folder byte-identical, so the touched
actor is **not** in `changed`, the write is dropped, and **the label change is silently lost** — a
correctness bug, not a nicety, symmetric for clear-to-empty (labels→∅ also leaves body/rank/folder
identical).

**Fix (required):**
1. Add a `_loaded_labels: dict[str, frozenset[str]]` baseline, built from `Actor.labels` on `load()`
   (`{n: level.actors[n].labels for n in level.actors}`) and re-derived on `save()` after the write
   (mirroring `self._loaded_folders = {name: actor.folder …}` at `dispatch.py:1458`). It is derived
   from the model, so no `read_actor_tree` signature change.
2. Add the fourth clause to the diff:
   `or level.actors[name].labels != self._loaded_labels.get(name, frozenset())`.
3. Update the `dispatch.py:1443-1445` comment to name labels as a sidecar-only delta too.

**Regression (both directions, §12):** a label-only `add` on an actor whose body/rank/folder are
unchanged persists to disk; a `clear` that empties an actor's labels persists (the file is removed).
Without the diff fix both silently no-op — this is the test that would have caught the bug.

---

## 4. Verb surface — `actor label <sub>`

`actor label` with sub-verbs. Shaped for a *set* (so `add`/`remove` exist, unlike single-valued
`folder`):

| Sub-verb | Grammar                                                 | Effect |
|----------|---------------------------------------------------------|--------|
| `add`    | `actor label add    <names…\|-> --label L [--label L…]` | UNION: add the given label(s) to each actor's existing set |
| `remove` | `actor label remove <names…\|-> --label L [--label L…]` | SUBTRACT: drop the given label(s); absent ones are a no-op |
| `clear`  | `actor label clear  <names…\|->`                        | remove ALL labels (delete the sidecar) |
| `get`    | `actor label get    <names…\|-> [--json]`               | print each actor's labels (query) |

- **No `set` sub-verb** (Decision, 2026-07-23). "Make the labels exactly `{X}`" is `clear` then
  `add` — derivable, so it is dropped for a leaner surface (`add`/`remove`/`clear`/`get` only).
- **Grammar — actors positional/`-`, label VALUES behind a repeatable `--label`** (Decision,
  2026-07-23). Resolves the two-positional-lists ambiguity exactly as `actor folder set --to <path>
  <names…>` does (value is a flag; the actors are the positional/stdin name-set, consistent with every
  mutating actor verb — `delete`/`rotate`/`prop`/`folder`), so `-` universally means "actors from
  stdin." `--label` is **repeatable** (each occurrence = one label). The flag is spelled **`--label`**
  on the mutation verbs too (same token as the `find --label` filter — same meaning "a label"; NOT a
  distinct `--to`-style flag). `-` is the sole stdin source (not mixable with inline names), empty
  stdin → clean no-op exit 0.
- **`get` output:** one line per actor in argument order, `Name<TAB>l1,l2,l3` (labels sorted,
  comma-joined; unlabelled → `Name<TAB>(none)`). `--json` → `{name: ["l1","l2"], …}` (unlabelled →
  `[]`). The Name-prefix (`Name<TAB>…`) is a DELIBERATE improvement over `folder get`, which prints the
  value only with no name (`dispatch.py:238-240`) — a multi-actor label dump needs the name to be
  parseable. The `--json` object shape mirrors `folder get --json`.
- **PRODUCER — the mutating label verbs echo touched names to stdout.** `add`/`remove`/`clear`
  print each touched actor Name to **stdout** (one per line), human summary to **stderr**, so
  mutations chain: `find … | label add - --label lit | prop set - Texture=Stone | move - --by 0,0,64`.
  This follows `actor rotate`/`delete` (`dispatch.py:3578,3611` — *"PRODUCER: rotated names to
  stdout"*). **NOTE — this is deliberately NOT a mirror of `actor folder set/unset`, which print
  NOTHING to stdout** (`dispatch.py:242-245`). Making the label verbs producers is the better,
  compose-friendly behavior; the resulting inconsistency with the silent folder verbs is a real wart.
  *Follow-up (board `inbox.md`): make `folder set/unset` producers too, for consistency.* (First draft
  wrongly called this "mirroring folder" — corrected.)
- **Validate-all-then-apply** (invariant D2): resolve every name and validate every label BEFORE any
  write; a bad name or malformed label leaves the whole tree untouched (clean exit 2 naming the value).

---

## 5. Query — `actor find --label`

Add to `actor find` (mirroring `--folder`):

- **`--label <glob>`** (repeatable) — match actors carrying a label matching `<glob>`. Matching is
  **flat `*`-globbing** — a `*` wildcard only, NOT globstar (`**` has no meaning; labels are flat) and
  **NOT** fnmatch `?`/`[…]` char-classes. `--label 'dup-*'` finds every duplication batch;
  `--label lighting` finds all lit actors.
- **Pattern syntax matches folder's conservative stance** (Decision, 2026-07-24 — char-class DROPPED).
  Like `folderlib.validate_pattern`, `--label` **rejects** `?` and `[`/`]` in a pattern (clean exit 2
  naming the value) rather than letting fnmatch leak unsanctioned semantics; only `*` is a wildcard.
  (Reuse/mirror the folder pattern validator.) This removes the earlier `--label`-vs-`--folder`
  asymmetry entirely — both now allow `*` (folder additionally `**`) and reject the rest.
- **Multiple `--label` OR together** (an actor matching ANY listed label), consistent with how
  repeated `--folder`/`--group`/`--class-exact` already OR within their filter (`query.py:164-215`).
  Across DIFFERENT filters, AND applies (`find --label lighting --folder castle.**`).
- **`--no-label`** — match only UNLABELLED actors; the sole way to query them. Mutually exclusive with
  `--label`, mirroring `--no-folder` (`cli.py:289`).

---

## 6. Setting labels at creation — `actor add --label` + the carrier

`actor add` gains **`--label L`** (repeatable), stamping the given label(s) on EVERY added actor —
mirroring `actor add --folder`. Per the generator pattern (labels are trunk state), the flag lives on
`actor add`, **not** on the generators (`brush build`/`actor build`). Precedence, identical to
`--folder`: an explicit `--label` **OVERRIDES** any `// uedcli-labels:` carrier in the input; absent
`--label`, the carrier sets the labels; absent both, the actor is unlabelled.

### The carrier — parsed in `model.parse_t3d`, NOT in labellib
For labels to round-trip through `actor show A | actor add -`, the `// uedcli-labels: l1,l2` comment
must be consumed where the folder carrier already is: **`model.parse_t3d`** reads `_FOLDER_CARRIER`
(`model.py:40,147`) into `Actor.folder`; add a parallel `_LABELS_CARRIER` read into `Actor.labels`
there. `labellib` provides the regex + `format_labels_carrier`; `query.actor_show_block` emits the
comment (alongside `// uedcli-folder:`) when the actor is labelled and its carrier gate is on;
`--t3d-only` suppresses BOTH carriers. Since `actor_show_block`'s existing `with_folder` param now
gates the labels carrier too, its meaning becomes "emit sidecar carriers" — **rename it
`with_sidecars`** (a deliberate rename, not a silent overload; update its callers).

---

## 7. `duplicate` integration — inherit + a fresh batch label

`actor duplicate` is thin sugar today: it renders `actor_show_block(with_folder=True)` per source and
re-ingests via the SHARED `_ingest_actor_t3d(verb="duplicate")` (`dispatch.py:3437`) — the same
function `actor add` uses (`dispatch.py:3420`), which applies `--folder` as an **override**
(`dispatch.py:1712,1741`). The label behavior duplicate needs is **different from add's override**, so
the shared path needs an explicit new channel — this is the subtle part the reviews flagged.

### 7.1 Labels: inherit + fresh handle (Decision (b))
Each copy's label set is a **UNION**, never a replace:

```
copy.labels = (inherited labels, from the source's carrier)  ∪  {dup-<rand>}  ∪  {explicit --label values}
```

- **The fresh `dup-<rand>` is ALWAYS minted** (Decision, 2026-07-23), regardless of whether `--label`
  is passed — so a duplicated batch is *always* isolable by a unique handle, and the "which flag names
  the batch" ambiguity is gone. `--label` on `duplicate` is **purely additive**: its value(s) are
  unioned IN ADDITION to the auto `dup-<rand>` (they do NOT replace it), so `duplicate X --label wing-b`
  yields copies carrying inherited labels + `dup-<rand>` + `wing-b`.
- **Inherited labels** arrive because `actor_show_block` now emits the `// uedcli-labels:` carrier
  (§6), so the shared ingest parses them into `Actor.labels` for free. A duplicated `lighting` torch
  therefore stays `lighting`.
- **Mechanism (required — do NOT route through add's override):** `_ingest_actor_t3d` gains a distinct
  **`labels_add: frozenset[str]`** union channel, SEPARATE from add's `--label` override channel. The
  duplicate handler passes `labels_add = {dup-<rand>} ∪ {explicit --label values}`; the ingest UNIONs
  it onto each actor's carrier-parsed set. `actor add` never sets `labels_add` (it uses the override
  path). (add = override, duplicate = union.)
- **`<rand>`** uses the collision-free suffix generator (`t3dtree._rand_suffix`, `t3dtree.py:98`),
  **re-rolled** until the token is not already a label anywhere in the target tree — so the auto
  handle is guaranteed to isolate the batch. (An explicit `--label` value carries no such guarantee —
  it may already exist elsewhere — but that never matters, because the always-present `dup-<rand>` is
  the guaranteed-unique handle.)
- **Accumulation caveat:** because copies inherit the source's labels, re-duplicating an
  already-duplicated actor carries its old `dup-<rand>` forward *plus* the new one, so `find --label
  'dup-*'` grows noisier over generations and a copy can match several batch handles. Acceptable (the
  newest handle still isolates the newest batch); flagged so it's a known property, not a surprise.
- The batch label is echoed to **stderr** (`duplicated 3 actors → label 'dup-a1b2c3'`); fresh **Names
  still print to stdout** unchanged (stdout chains *within* a pipeline; the label re-addresses *after*
  it).

### 7.2 Placement — `--by` / `--at` (removes the same-location footgun)
Today copies land ON their originals (overlap), forcing a second `| actor move -`. Add:

- **`--by DX,DY,DZ`** — translate every copy by the same per-actor delta from its original — the SAME
  meaning as `actor move --by` (`cli.py:467`, `dispatch.py:3345`), not a third invention. Multi-actor
  layout preserved trivially.
- **`--at X,Y,Z`** — anchor the set's bbox-min CORNER at the point (absolute); relative layout
  preserved.
- **Mechanism (corrected):** duplicate does **not** go through `_apply_set` — that path is only reached
  by stash/prefab apply (`dispatch.py:347,1007`) and implements only `--at` (no `--by`,
  `dispatch.py:744-750`). Duplicate goes through `_ingest_actor_t3d`, so the translate must be added
  there using the *same primitives* apply uses: `stashlib.translate` + `writes.union_bounds` (for the
  `--at` bbox-min anchor). (First draft claimed `--at` "reuses `_apply_set`" — corrected.)
- **Exactly one of `--by`/`--at` is REQUIRED** (an argparse REQUIRED mutually-exclusive group, like
  `actor move`'s `--to`/`--by`) — Decision 2026-07-24, **supersedes** the earlier warn-don't-error call.
  A bare `actor duplicate <names>` with no placement is a clean **exit 2** (`duplicate requires --by or
  --at`), so accidental invisible overlapping copies can't happen. The **explicit-overlap escape hatch
  is `--by 0,0,0`** (a deliberate zero delta) — for the duplicate-in-place-then-compute-a-move
  workflow, you state the overlap on purpose. (The old same-location default + the stacked-point overlap
  warning are therefore gone from `duplicate`.)

---

## 8. Cross-tree travel — a real `labels` channel, NOT free ⚠️

**(Corrected in the revision.)** Labels do **not** ride stash/prefab "for free." `read_stash`/`read_prefab`
re-serialize each actor to a canonical-T3D blob, which **drops every uedcli-side sidecar field**
(folder, and now labels). Folder solved this with a **separate `folders: name→folder|None` channel**
threaded through the wrappers; labels need the **identical parallel `labels: name→frozenset[str]`
channel**:

- `stash_register.read_stash`/`write_stash` (`stash_register.py:38-52`) — carry labels beside folders.
- `stashlib._level_from_blobs` / `write_prefab` / `read_prefab` (`stashlib.py:127-144,177,242`) — same.
- `_apply_set` (`dispatch.py:719-742`) — apply/copy-into-a-level re-attaches each member's stored
  labels as the placement DEFAULT (inherited), exactly as it re-attaches `folders`
  (`dispatch.py:727-728`). An explicit placement `--label` (if that verb offers one) is additive.

This spec does NOT design the copy-between-trees verb (its sibling spec does); it guarantees the
sidecar is carried through capture/read/write via this channel, and lists the touchpoints in §10.

---

## 9. Validation & matching

- **Label token charset:** a single flat segment `[A-Za-z0-9_+-]+`, non-empty, no `.` (labels are flat
  — the dot is the folder-path separator, meaningless here), no `/`/`\`/newline. **Shared with folder:
  export a public `folderlib.validate_segment(s)` (extracting the private `_SEGMENT`,
  `folderlib.py:24`) and have `labellib.validate_label` call it** — ONE charset definition, no
  duplicated regex. (Resolves the first draft's §8-says-reuse-folderlib vs §9-says-new-labellib
  contradiction.) Malformed → clean exit 2 naming the value.
- **Leading-`-` hazard:** the charset admits a leading `-`, so `--label -foo` risks argparse treating
  `-foo` as an option. The CLI already has a custom `_parse_optional` for the coordinate args
  (`cli.py:57`); either route `--label` through the same recognizer OR **disallow a leading `-` in a
  label token** (simplest — a label starting with `-` has no real use). Recommend the latter; state it
  in the validator.
- **Case:** stored as authored (case preserved), matched **case-insensitively** — identical to folder
  and to actor-name resolution. `Lighting` == `lighting`; the first-authored casing is stored.
- **Dedup:** adding a present label is a no-op; the sorted-set storage makes on-disk duplicates
  impossible.

---

## 10. Module shape / touchpoints

- **`uedcli/labellib.py`** (NEW) — `validate_label` (charset via `folderlib.validate_segment` PLUS its
  OWN leading-`-` guard on top: the shared segment regex `[A-Za-z0-9_+-]+` admits a leading `-` and
  folders depend on that regex, so the label-only "no leading `-`" restriction must layer in `labellib`,
  NOT inside `validate_segment`); `_LABELS_CARRIER` regex + `format_labels_carrier`; and a **FLAT match
  predicate** — reject `?`/`[`/`]` first, then match `*`-only, **case-insensitively via casefold-both +
  `fnmatchcase`** (the house pattern at `query.py:195`; bare `fnmatch.fnmatch` is case-SENSITIVE on
  Linux). This mirrors folder's *stance*, NOT `folderlib.validate_pattern`'s code (which is dotted /
  `**`-aware — wrong for a flat label). Sibling of `folderlib.py`.
- **`uedcli/folderlib.py`** — expose a public `validate_segment(s)` (shared single-segment charset;
  does NOT itself reject a leading `-` — that stays a labellib-layer concern so folder validation is
  unchanged).
- **`uedcli/model.py`** — `Actor.labels: frozenset[str]` field (default `frozenset()`);
  `parse_t3d` gains the `_LABELS_CARRIER` read into `Actor.labels` (mirroring `_FOLDER_CARRIER`,
  `model.py:147`).
- **`uedcli/t3dtree.py`** — read/write the `labels` sidecar in `read_actor_tree`/`write_actor_tree`
  (the ONE shared path; **no tuple-shape change** — labels ride on `Actor.labels`).
- **`uedcli/query.py`** — `list_actors` gains `labels`/`no_label` filters (flat `*`-only match per
  §5/§9, OR-within, empty set for `no_label`); `actor_show_block` emits the labels carrier.
- **`uedcli/dispatch.py`** — the label baseline + diff clause (§3, `_loaded_labels`, the
  `TrunkLevelSource.save` delta diff); `actor label add|remove|clear|get` handlers (producer stdout,
  validate-all-then-apply); `actor add`/`actor find` wiring; **`_ingest_actor_t3d` gains a
  `labels_override` param SET BY THE ADD HANDLER ONLY** (do NOT read `args.label` unconditionally inside
  `_ingest` — `duplicate` also has `--label`, so an unconditional read would apply it as BOTH an
  override and a union) **and a `labels_add` union param set by the DUPLICATE handler**
  (`{dup-<rand>} ∪ args.label`, with `labels_override=None`); + the `--by`/`--at` translate
  (`stashlib.translate` + `writes.union_bounds`, NOT `_apply_set`); `_apply_set` re-attaches stored
  labels (§8).
- **`uedcli/stashlib.py`, `uedcli/stash_register.py`** — the `labels: name→frozenset[str]` channel
  through `read_tree_box`/`write_tree_box` + `_level_from_blobs`/`write_prefab`/`read_prefab`/
  `read_stash`/`write_stash`, mirroring the `folders` channel's STANCE (§8). `read_tree_box` sources
  labels from `level.actors[n].labels` (the model field), NOT from a read-tuple element (labels never
  grew the tuple, §2).
- **`uedcli/dispatch.py` box sources** — `StashLevelSource.save`/`.load` and `PrefabLevelSource.save`/
  `.load` must compute + re-attach the `labels` channel exactly as they already do `folders`; without
  it a `label add --tree stash/x` (allowed below) silently drops on save — the §3 delta-trap, for boxes.
- **`uedcli/cli.py`** — the `label` sub-parser, `find --label`/`--no-label`, `add --label`,
  `duplicate --label`/`--by`/`--at`.
- **`--tree stash|prefab` reach (Decided — ALLOW, 2026-07-23):** every label surface accepts
  `--tree stash|prefab` — the per-actor sidecar slot exists in stash/prefab post-unify, and §8 carries
  labels through the `labels` channel, so a label set/query on a box is meaningful. The label surfaces
  deliberately do **NOT** call `_reject_nonlevel_target_for_folders` (the folder guard, `dispatch.py:169`),
  whose trunk-only premise ("flat boxes, no sidecar slot") is stale post-unify — un-staling folder to
  match is a separate board item.

---

## 11. Resolved design choices (2026-07-23, Andrzej)

All prior open sub-choices are now decided (nothing left open in this spec):

1. **Grammar** — actors positional/`-`, label values behind a **repeatable `--label`** flag (§4).
2. **No `set` sub-verb** — `add`/`remove`/`clear`/`get` only; replace-all = `clear`+`add` (§4).
3. **Mutation flag spelled `--label`** — same token as the `find --label` filter, not a distinct
   `--to`-style flag (§4).
4. **`--by`/`--at` land in THIS spec, and exactly one is REQUIRED** — the duplicate placement overhaul
   is part of this work; a bare `duplicate` with no placement is exit 2 (`--by 0,0,0` = explicit
   overlap). No same-location default (Decision 2026-07-24, §7.2).
5. **Label surfaces ALLOW `--tree stash|prefab`** — the sidecar exists there post-unify; the stale
   folder trunk-only guard is a separate board item (§10, §8).
6. **`--label` patterns are `*`-only** — `?` and `[`/`]` char-classes are REJECTED (clean exit 2),
   mirroring folder's stance (see §5; supersedes the earlier "char-class supported" note).

### 11.1 OPEN — scope cut raised in re-review (2026-07-24, needs Andrzej)

**Does the full stash/prefab `labels` plumbing (§8) + the `--tree stash|prefab` allowance (choice 5)
belong in THIS spec, or should it defer to the sibling copy-between-trees spec that actually consumes
it?** A cold re-review flagged §8 as the YAGNI-adjacent surface: it threads labels through
capture/read/write (`read_tree_box`/`write_tree_box`, both box `LevelSource.save`/`.load`,
`_apply_set`) purely so a not-yet-designed copy-between-trees verb can carry them — this spec itself
never moves a label between trees. **The clean cut:** keep THIS spec to **trunk + `duplicate`** (the
cohesive, self-contained core), and move §8 + choice 5 (the box channel + `--tree stash|prefab` on the
label verbs) into the copy-between-trees spec. Trade: `label`/`duplicate` land sooner and smaller; a
`label add --tree stash/x` would exit-2 "trunk only" (like folder) until the sibling spec lands.
**Recommend the cut** — it shrinks the build, removes the omitted-touchpoint risk, and pairs the box
plumbing with its only consumer. Andrzej: cut (defer §8) or keep?

---

## 12. Test strategy (host-native `bin/test`)

1. **DELTA-WRITE (the §3 trap, both directions) — the test that catches the critical bug.** `label add`
   on an actor whose body/rank/folder are unchanged persists across a fresh `load()` (assert the
   `labels` file on disk AND a re-read `Actor.labels`); `label clear` on a labelled actor removes the
   file and persists. Assert the precondition (baseline has the old set) before the mutation.
2. **Sidecar round-trip (the shared path):** write labels `{b,a,c}` → the file is sorted `a\nb\nc\n`;
   read back → `frozenset({a,b,c})`; empty set writes NO file; clearing removes an existing file.
   Assert trunk, stash, AND prefab all round-trip labels identically (extend
   `test_t3d_tree_consistency.py`) — proving the §8 `labels` channel works, not just the trunk.
3. **Verbs:** `add` unions; `remove` subtracts (missing = no-op); `clear` empties+deletes the file;
   `get` prints `Name\tl1,l2` sorted (+ `--json`); each is
   validate-all-then-apply (bad name / malformed label leaves ALL untouched, exit 2 naming the value);
   each echoes touched names to stdout, summary to stderr; `-` reads stdin, empty stdin → no-op exit 0.
4. **`find --label`:** flat `*`-only match (a `?`/`[` pattern → exit 2); case-insensitive; repeated
   `--label` ORs; ANDs with `--folder`/`--class`;
   `--no-label` finds only unlabelled and is mutually exclusive with `--label`.
5. **`actor add --label`** stamps every added actor; the `// uedcli-labels:` carrier round-trips through
   `show | add -` (via `model.parse_t3d`); explicit `--label` OVERRIDES the carrier; `--t3d-only`
   suppresses it.
6. **Duplicate:** copies inherit originals' labels (UNION) AND all carry ONE shared fresh `dup-<rand>`
   (matches `^dup-`, isolates exactly the batch via `find --label`); inject a colliding pre-existing
   `dup-…` label and assert a re-roll (this requires an injectable-randomness seam — `t3dtree._rand_suffix`
   is called directly, not via `alloc_name`'s `_rand` param, so expose/monkeypatch it); **`--label wing-b`
   is ADDITIVE — copies carry inherited ∪
   `dup-<rand>` ∪ `wing-b`, and the `dup-<rand>` is STILL present** (the regression that pins
   "always mint, `--label` never replaces"); the batch label is on stderr, new Names on stdout;
   `--by`/`--at` place the batch (relative layout preserved; `--at` anchors the set's bbox-min corner);
   **exactly one of `--by`/`--at` is REQUIRED — a bare `duplicate` with neither → exit 2; `--by 0,0,0`
   is the explicit-overlap escape.**
7. **Case-insensitive** match/store (`Lighting` == `lighting`, first casing stored); leading-`-` label
   rejected (§9).

Use artificial label values (`hero`, `flammable`, `dup-1337ab`) and realistic multi-actor sets.

## 13. Blast radius + docs / follow-ups

- **Docs (no doc left stale):** `docs/usage.md` (the `actor label` verbs, `find --label`/`--no-label`,
  `add --label`, `duplicate --label/--by/--at`); `docs/leveldesign/` (labels as the cross-cutting
  organization axis beside folders); `architecture.md` (the `labels` sidecar + `Actor.labels` field +
  the `_loaded_labels` delta baseline + `labellib.py` + the stash/prefab `labels` channel +
  `labellib`/`folderlib.validate_segment` in the module map); `unrealed/t3d.md` (labels are uedcli-side,
  never emitted — like folder).
- **Decisions ledger:** append the resolved choices (name `label`; multi-valued set; the freed-via-
  `--annotate` rename; inherit+fresh dup label as a UNION; grammar) to `decisions.md`.
- **Follow-up chores (board `inbox.md`):** (a) the preview annotation *internals* (`parse_label_spec`,
  `DEFAULT_LABELS`, `LabelSpec`) are still "label"-named after the `--annotate` flag rename — rename
  them `annotation*`. (b) make `folder set/unset` producers (echo touched names to stdout) for
  consistency with the label verbs (§4). (c) re-evaluate whether `_reject_nonlevel_target_for_folders`
  is stale post-unify (§11.4).
- **Sibling spec:** copy-between-trees (consumes the label inheritance rule + the §8 `labels` channel).
