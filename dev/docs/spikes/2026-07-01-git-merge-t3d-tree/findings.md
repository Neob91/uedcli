# Spike: can plain `git merge` replace uedcli's custom 3-way merge for T3D trees?

**Date:** 2026-07-01
**Question:** Can plain `git merge` replace uedcli's custom per-actor 3-way
merge for T3D trees, enabling parallel work via branches?
**Kind:** offline, no editor / no container. Pure git.

Harness (committed alongside this file):

- `build_tree.sh` — writes a realistic uedcli T3D-tree fixture (8 actors: 6
  point actors + 2 brush actors carrying `Begin Brush ... End Brush` polylists,
  plus `order` / `packages` / `name`). Properties one-per-line, sorted, to model
  canonical/deterministic emission.
- `run_spike.sh` — trunk -> branchA (edit + add) -> branchB (disjoint edit + add)
  -> `git merge`; then a forced same-actor conflict; then a reorder-vs-edit case.
- `probe_order.sh` — isolates *why* `order` conflicts (tail-adjacency vs.
  inherent) and demonstrates a per-actor ordering-key alternative.

Throwaway git repos land under `_scratch/git-merge-spike/` (gitignored).

---

## VERDICT

**Git-merge is viable as the session-merge mechanism — with one required change:
kill the shared `order` file.** The per-actor file layout is what makes this
work. Git's default `ort` strategy resolves disjoint per-actor work perfectly
(edits to different actors + additions of new actors), and same-actor conflicts
surface with clean, human/LLM-resolvable markers. The *only* systematic failure
is the shared `order` file, and it is a pure artifact of a shared line-based file
— not fundamental to CSG ordering.

Two conditions must hold:

1. **Ordering must not live in a single shared, tail-appended file.** Move CSG
   precedence to a per-actor ordering key (see caveat below). Otherwise every
   "add an actor" merge conflicts.
2. **Emission must be canonical and stable.** Non-canonical property order turns
   semantic-noop edits into spurious text conflicts (Scenario 6). uedcli already
   emits sorted/normalized — keep that invariant; it is load-bearing for merge.

If those hold, uedcli's custom per-actor 3-way replay merge is not needed for the
common case. It may still be wanted as a *fallback resolver* for same-actor
conflicts (semantic property-level merge instead of hunk text merge), but that is
an optimization, not a requirement.

---

## Results

### Scenario 1-4: disjoint work, then merge (`run_spike.sh`, repo `disjoint`)

branchA: edit `Light0` + `Computer0`, add `Datacube0`, append to `order`.
branchB: edit `Light1`, add `Barrel0`, append to `order`.

- **Disjoint actor edits + adds auto-merge cleanly.** After the merge, all edits
  to `Light0`/`Computer0`/`Light1` are present and both new actors
  (`Datacube0`, `Barrel0`) exist. Zero conflict on any `actors/*.t3d`. Because
  each actor is its own file, git treats disjoint actor work as disjoint files —
  the ideal case.
- **`order` is the sole conflict.** Both branches appended a different name to
  the last line, so git sees overlapping edits at the file tail:

  ```
  Trigger0
  <<<<<<< HEAD
  Datacube0
  =======
  Barrel0
  >>>>>>> branchB
  ```

  `git status` shows `A actors/Barrel0.t3d`, `M actors/Light1.t3d`, `UU order` —
  i.e. everything auto-merged except `order`.

### Scenario 5: same-actor conflict (`run_spike.sh`, repo `same_actor`)

Both branches edit `Light0` `LightBrightness` to different values. Merge yields:

```
    Location=(X=512.000000,Y=512.000000,Z=256.000000)
<<<<<<< HEAD
    LightBrightness=255
=======
    LightBrightness=64
>>>>>>> editB
    LightHue=40
```

**Cleanly resolvable.** The conflict is scoped to the single changed property
line, with full surrounding context intact. A human or LLM can pick a side (or
compute a value) trivially. This is the failure mode uedcli's custom merge is
designed to handle better — but even the raw git hunk is legible.

### Scenario 6: non-canonical emit -> spurious conflict (`run_spike.sh`, repo `reorder`)

Branch `reorderA` shuffles two adjacent property lines of `Light1` (semantic
no-op, as a non-canonical emitter might). Branch `editHue` makes a real hue edit
in canonical order. Merge **conflicts** even though the two changes don't
semantically overlap, because the reorder rewrote the same text region:

```
<<<<<<< HEAD
    LightHue=120
    LightBrightness=140
=======
    LightBrightness=140
    LightHue=200
>>>>>>> editHue
```

**Canonical emit is necessary.** Stable line order is what keeps disjoint
property edits from colliding. This is a strong argument for keeping uedcli's
deterministic emission as an enforced invariant, not a nicety.

### Order-file probe (`probe_order.sh`)

- **Test A — tail-append vs tail-append: CONFLICT.** The real "add an actor"
  flow (append name to end of `order`) conflicts every time, because both sides
  touch the same final line. This is why Scenario 1-4 conflicted.
- **Test B — insertions at well-separated lines: CLEAN.** Inserting near the top
  on one branch and near the bottom on the other merges with no conflict. Proves
  the `order` conflict is **textual adjacency, not inherent to ordering.**
- **Test C — per-actor `OrderKey`, no shared `order` file: CLEAN.** Store CSG
  precedence as a sortable key inside each actor file and drop `order` entirely.
  Adding an actor writes only that actor's file -> disjoint files -> no shared
  merge surface. Post-merge order is recovered by sorting on the key. Both adds
  landed with zero conflict.

---

## Caveats

### The `order` file is the merge hotspot — and a per-actor key fixes it

The shared, newline-delimited `order` file is the single thing that breaks clean
merges in the common workflow. Every branch that adds an actor appends to the
same last line, guaranteeing a conflict on merge (Test A). The conflict is
trivial for a human to resolve (concatenate both new names), but it means *no
add-actor merge is ever fully automatic* under the current layout — which
defeats the point of leaning on `git merge`.

**Recommended fix: per-actor ordering key.** Store CSG precedence as a sortable
attribute inside each `actors/<name>.t3d` (Test C). Adds become disjoint-file
adds; order is reconstructed by sorting. Caveats of the key approach:

- **Reordering existing actors still touches multiple files.** Moving an actor
  earlier/later means rewriting keys on several files; two branches reordering
  overlapping ranges will conflict per-file. But that is *reordering*, a rarer
  and genuinely-conflicting operation — appropriate to surface. Adds (the common
  case) stay clean.
- **Sparse keys (010, 020, ...) buy insertion room** without renumbering, but
  can exhaust; occasional renumber passes needed. A rational/float or
  fractional-index key (LexoRank-style) avoids renumbering at the cost of key
  churn.
- Whatever key scheme, the on-disk key must be part of canonical emission so it
  doesn't itself become a spurious-diff source.

An alternative that keeps a shared `order` file but avoids conflicts is a custom
git merge driver (`.gitattributes` + `merge=union` or a set-union driver) for
the `order` path. `merge=union` would concatenate both appends without conflict,
but produces duplicate/unordered results on non-append edits and can't express
precedence intent — weaker than the per-actor key. Prefer the key.

### Canonical emit is sufficient *and* required

With stable, sorted, one-property-per-line emission, disjoint property edits to
the same actor merge cleanly and only genuine same-property edits conflict.
Without it (Scenario 6), semantic no-ops conflict. Canonical emit is therefore
both sufficient for clean merges and a hard prerequisite — it must be enforced,
not assumed.

### Brush actors

The two brush actors (with `Begin Brush ... End Brush` polylists) behaved
identically to point actors in these scenarios — they are just larger text
blocks in their own files. Not separately stressed here: two branches editing
different polygons of the *same* brush would conflict at the hunk level like any
other same-file edit; whether that resolves sanely depends on how far apart the
edited polygons are in the file. A follow-up could probe intra-brush concurrent
edits, but it does not change the verdict.

### Same-actor semantic merge

Git resolves same-actor conflicts at the text-hunk level, not the property
level. For adjacent-but-different properties this is fine (they don't conflict).
For the *same* property edited two ways, git can't decide — nor could a naive
custom merge without a resolution policy. uedcli's per-actor 3-way replay could
add value here as a *conflict resolver* (property-level 3-way), but it is not
required to make branch-based parallel work function.
