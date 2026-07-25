# Spec: trunk write safety — atomic `order_value`, illegal empty rank, same-actor lost-update detection

**Status:** specced, **review-gated** (rounds 1–2 resolved — 4 cold reviewers each; this file is the
post-round-2 revision. A fresh round follows). This changes an on-disk write invariant AND its failure
mode is silent, so it stays at 4 reviewers. Round 2 verified every code premise correct and the D3
concurrency argument airtight; the changes below are spec-completeness and test-plan fixes.
**Requested by:** Andrzej (2026-07-25, session `uedctl:review`) — from a codebase review that surfaced
the non-atomic `order_value` write; he then added the illegal-empty gate ("error rather than corrupt
data") and asked for same-actor lost-update detection ("Add lost-update detection").
**Ephemeral:** scratch for designing the work; deleted once it lands. The durable record afterwards is
`decisions.md` (choices + rejected alternatives), `architecture.md` (what the code does), and the
regression tests named in §5.

**This document is SELF-CONTAINED.** Everything needed to build the work — the binding decisions and
their rejected alternatives, the exact code seams, the concurrency argument, and the house rules that
constrain it — is stated here. Source may be read; no other document needs to be opened.

---

## 0. Terms (for a reader with no context)

- **T3D trunk** — the git-tracked source of truth for a level: one directory per actor,
  `maps/<level>/actors/<name>/{actor.t3d, order_value[, folder][, labels]}`. `actor.t3d` is the
  actor body; `order_value` is a **per-actor LexoRank string** (a sortable token) that fixes the
  actor's position in export / CSG-precedence order; `folder`/`labels` are uedctl-side organization
  sidecars.
- **Shared tree format** — the same per-actor layout is used by all three on-disk T3D trees (git
  **trunk**, machine-local **stash**, git-committed **prefab**), read and written through ONE code path
  (`t3dtree.read_actor_tree` / `t3dtree.write_actor_tree`). (Invariant, `direction.md`.)
- **Delta write** — a trunk save writes only the actors whose body/rank/folder/labels differ from the
  saving process's own load snapshot, and prunes only the actors that process itself deleted, so
  disjoint concurrent edits compose. (`decisions.md` 2026-07-18.)
- **Per-level flock** — `TrunkLevelSource.save` serializes savers with an exclusive `flock` on
  `<maps-dir>/.locks/level-<level>.lock` (`dispatch.py`, the `with open(lock) … fcntl.flock(lf,
  LOCK_EX)` block wrapping `trunk.write_level`). **Loads take no lock** (`TrunkLevelSource.load` →
  `read_actor_tree`; reads are point-in-time, by design).
- **Load snapshot** — the four dicts `TrunkLevelSource` captures at `load()`: `self._loaded_bodies`
  (name → **raw stored `actor.t3d` text**, verbatim — `bodies[name] = body.read_text()`), `self._ranks`
  (name → order_value), `self._loaded_folders`, `self._loaded_labels`. `self._ranks` is left
  **un-mutated until after the write**, so it is the true load baseline at the D3 check point. The
  existing delta-write `changed` diff already compares against these four.

The three problems below all live at the trunk write/read seam and share the same regression surface,
so they are specced and built as one batch.

---

## 1. Problem

**P1 — `order_value` is written non-atomically, alone among its siblings.**
In `t3dtree.write_actor_tree`, `actor.t3d`, `folder`, and `labels` each land via tmp-file + `os.replace`;
`order_value` is the one sidecar still written with a bare `(d/"order_value").write_text(rank + "\n")`.
A lock-free reader (`read_actor_tree`) can hit the truncate-then-write window and read an empty/partial
rank; an empty rank (`str.strip()` → `""`) sorts that actor to the front of the `(order_value, name)`
order and can spuriously trip the "shared order_value" duplicate-rank warning.

**P2 — an empty `order_value` is silently tolerated, not rejected.**
`read_actor_tree` reads `ranks[name] = rv.read_text().strip() if rv.is_file() else ""` — both a missing
and an empty file yield `""`, sorting the actor to the front with no error; `save` preserves a stored
empty rank by a membership test. Corrupt state (an empty rank on a valid body — producible by P1's crash
window or manual tampering) flows through silently. Andrzej: make it **illegal**.

**P3 — same-actor concurrent edits are a silent lost update.**
The per-level flock serializes the atomic write phase but not the read→edit→write cycle. Two processes
that both `load()`, both edit the same actor *X*, then both `save()`: the second writer's `changed` set
fires on *X* (differs from its own stale baseline), so it overwrites the first writer's *X* with **no
error**. (Disjoint-actor edits already compose and must keep doing so.) Andrzej: detect it and error.

---

## 2. Decisions (each recorded in `decisions.md` on build; rejected alternatives kept here)

**D1 — `order_value` writes atomically (tmp + `os.replace`), like its three sibling sidecars.**
In `write_actor_tree`, replace the bare `write_text` with the tmp-file + `os.replace` pattern the
`folder`/`labels` writes use (same `os.getpid()` temp-name convention), preserving the existing
**rank-before-body** write order (the reader's admission gate is the body, so a rank written first is
always visible by the time the body admits the dir; a rank written last would be racily empty).
*Rejected: keep the bare `write_text`* — the direct cause of P1's torn read. **D1 is a prerequisite for
D2** (so an empty rank is unambiguous corruption, not a live race) **and for D3's "the re-read never sees
a torn file" claim.** (Only the `folder`/`labels` blocks carry the "loads take no flock…truncated first
line" comment verbatim; `actor.t3d` carries a shorter "atomic" comment plus the module docstring — D1
brings `order_value` to the same standard.)

**D2 — an empty or missing `order_value` on an actor that has a valid `actor.t3d` is ILLEGAL; the shared
reader raises a named error that reaches the CLI as a clean exit-2, never a traceback.**
When an actor directory passes the body-admission gate (`actor.t3d` present and non-empty) but its
`order_value` is missing, empty, or whitespace-only, raise a **named low-layer exception** —
`CorruptTreeError(ValueError)` defined in `t3dtree` — identifying the offending actor and tree
path (e.g. `corrupt T3D tree: actor 'Foo' in <dir> has no order_value (crashed write?)`), instead of
defaulting the rank to `""`. (Exactly where this raise sits relative to the D3 re-read is specified in §3
— it must NOT fire during the D3 conflict re-read.)
- **Error surfacing (specified concretely — the trunk path currently leaks).** `t3dtree` is a low layer
  and cannot import `dispatch._SelectionExit` (circular). `dispatch()`'s top-level handler does NOT catch
  bare `ValueError`, and `TrunkLevelSource.load` (unlike `StashLevelSource.load`/`PrefabLevelSource.load`,
  which catch `(OSError, ValueError)` → `_SelectionExit`) has **no try/except**. So the fix has two
  required halves: (a) `CorruptTreeError` subclasses `ValueError`; (b) **add a try/except to
  `TrunkLevelSource.load` mirroring the stash source** — `except (OSError, ValueError) as e: raise
  _SelectionExit(...)`. The single trunk **read** chokepoint is `TrunkLevelSource.load` (all ~30
  `src.load()` sites funnel through it; `trunk.read_level` has no non-test callers). **Also note the
  write-side path:** `stashlib._read_ranks_if_present` → `read_actor_tree` runs during a stash/prefab
  *rewrite* (`write_tree_box`), so D2's raise can fire there too; every such caller is already wrapped
  (`stash capture --force` and `stash promote --force --as <prefab>` — promotion is a `stash` subverb, not
  a `prefab` one — catch `(…, ValueError)`), so no traceback escapes — but the test plan pins it (§5)
  rather than leaving it to luck. The plain read verbs (`stash show/apply/preview`,
  `prefab show/apply/preview`) are likewise already covered (the stash pre-flight `except (OSError,
  ValueError)`; `_read_prefab_or_exit`); `StashLevelSource.save`/`PrefabLevelSource.save`'s `force=True`
  rewrite reads are unreachable-corrupt in practice (their own `load()` gates the box first), so they need
  no new wrap — noted so a future refactor does not unknowingly expose them.
- **A deliberate consequence of D2 on `--force`:** because `write_tree_box` re-reads the *existing* box
  before swapping, `stash capture --force` / `stash promote --force` **over an already-corrupt box** now
  exit 2 instead of clobbering it — recovery is `rm` the corrupt dir, not `--force`. Accepted: boxes are
  git-recoverable / throwaway, and silently clobbering corruption is worse than naming it.
- **Scope: the shared reader**, so the gate covers trunk, stash, and prefab uniformly (every writer
  supplies a non-empty rank for every actor: trunk via override / preserved `self._ranks` / `append_rank`;
  stash+prefab via `stashlib._ranks_for` → `append_rank`). A well-formed tree never trips it (empirically:
  0 of 13,679 on-disk `actor.t3d` have a missing/empty rank on a valid body).
- **Dead code removed in the same change (no-back-compat-cruft rule).** After D2 no reader can produce an
  empty rank in `self._ranks`, so three now-unreachable pieces are DELETED, not left:
  (i) the save-loop's **empty-rank tolerance** — the *rationale clause* "so a legit empty stored rank is
  preserved not re-minted" goes; **the membership test itself stays** (`if name in self._ranks` still
  distinguishes preserve-rank from mint-rank — load-bearing, do not remove);
  (ii) `doctor.check_duplicate_order`'s dedicated **empty-`order_value` branch** ("have no order_value
  (empty sidecar)") and its test `test_doctor.py::test_it_flags_actors_with_no_order_value_distinctly` —
  `level doctor`/`status` reach that branch via `src._ranks`, which is post-read, so an empty rank can
  never arrive (a corrupt tree exits 2 at `load` first); and
  (iii) `test_level_source.py::test_trunk_source_preserves_an_empty_stored_rank`, which seeds an empty
  `order_value` on a valid body and asserts `load()` *preserves* it — the exact behavior D2 abolishes, so
  after D2 it fails at the `load()` line. Delete it (or rewrite it to assert the new named exit-2). These
  two tests (`test_doctor.py`, `test_level_source.py`) are the ONLY two that seed an empty rank on a valid
  body, so the enumeration is now complete.
- **One-time consequence (deliberate, not a regression):** a pre-existing on-disk tree with an
  empty/missing rank on a valid body turns from a silently mis-sorted read into a hard exit-2. Trees are
  git-tracked / regenerable; failing loud is the intent.
- *Rejected: keep defaulting to `""`* (the P2 corruption); *rejected: auto-repair by minting a rank on
  read* (a read must not mutate; renumbering hides the crash).

**D3 — same-actor lost updates are detected by compare-and-abort under the per-level flock (trunk only).**
In `TrunkLevelSource.save`, after acquiring the flock and before `write_level`, run the check below and,
on any conflict, raise `_SelectionExit` (top-level-caught → exit-2) listing the conflicting name(s) and
write **nothing**. Message: `actor(s) changed on disk since this edit was loaded: <names> — another
writer committed concurrently; reload and re-apply`.

**The normative rule (the ONLY normative statement; the case list and §4 illustrate it, they do not
narrow it):**
> For every actor name in this save's `changed ∪ deleted` set, re-read its **current on-disk state** —
> the raw `actor.t3d` bytes (or *absent*), `order_value`, `folder`, `labels` — and compare it, dimension
> by dimension, against this process's **load snapshot** for that name (`self._loaded_bodies.get(name)`
> as raw text or `None`, `self._ranks.get(name)`, `self._loaded_folders.get(name)`,
> `self._loaded_labels.get(name, frozenset())`). **Absence is a comparable value** (snapshot-absent →
> body `None`; disk-absent → body `None`). The baseline is ALWAYS the load snapshot — **never** the
> resolved-to-write value. It is a **conflict** iff current-on-disk state ≠ load-snapshot state, with
> exactly one carve-out: **a name in `deleted` that is now absent on disk is NOT a conflict** (its
> end-state — gone — is already achieved; skip its prune and continue).

Why each case falls out of the one rule (do NOT special-case beyond the delete carve-out):
- **Plain `actor add`** (in `changed`, snapshot-body `None`, disk-body `None`): equal → no conflict.
- **Concurrent same-name add** (snapshot-body `None`, disk-body present): differ → conflict. *(The "side
  benefit": two concurrent adds of the same fresh name collide-detect.)*
- **Edit under us** (snapshot-body `X`, disk-body `X'`): conflict. Same for a **folder-only** or
  **label-only** concurrent edit — the four-dimension compare catches it even when the body is unchanged.
- **Edit vs concurrent delete** (in `changed`, snapshot-body present, disk-absent): `X ≠ None` → conflict
  — this is what prevents a delete from being silently resurrected. (Do NOT generalize the delete
  carve-out to `changed` names.)
- **Clean edit / clean delete** (disk equals snapshot on all four dims): no conflict → proceed.
- **Delete vs concurrent edit** (in `deleted`, disk differs from snapshot): conflict.
- **Identical concurrent delete** (in `deleted`, disk absent): the carve-out → not a conflict.

**Why it is airtight (the 100% claim):** `load()` is lock-free, but the compare *and* the write both
happen inside the flock, and **every writer of an existing actor holds that flock** (see the
`_level_create` carve-out). If the re-read equals the snapshot, nothing changed our targets since our load
*and* nothing can before our write completes — a compare-and-swap with no window. Per-actor writes are
atomic (`os.replace`, and `order_value` too after D1), so the re-read never sees a torn file. The body
dimension is a **raw-bytes compare** against `self._loaded_bodies` (verbatim stored text); an unchanged
file is byte-identical, so no `load_actor_body`/`dump_actor_body` round-trip is needed — this is
**more** robust than the existing `changed` diff (which relies on dump∘load idempotence).

- **`_level_create` carve-out.** `_level_create` (`dispatch.py`) is the one trunk writer that calls
  `trunk.write_level` outside the flock. It refuses a populated level (`any(actors_dir.iterdir())` →
  error) and only scaffolds a fresh `LevelInfo`, so its actor set is disjoint from any concurrent editor's
  by construction — it cannot participate in a same-actor lost update. (Alternative: bring it under the
  flock — rejected as unnecessary given the guard, and the lock dir may not exist at create time.)
- **Semantics: abort, do not merge.** The losing process re-runs against fresh state; uedctl is stateless
  per invocation, so an abort writes nothing and the re-run recomputes — no in-memory work is stranded.
  Git is the merge engine. *Rejected: accept + document last-writer-wins* (Andrzej chose detection);
  *rejected: in-`save` three-way merge* (git's job).
- **Disjoint edits unaffected:** a process checks only its own `changed ∪ deleted` against its own
  snapshot, so an actor another process touched but this one did not is never checked, written, or pruned.
- **Scope: `TrunkLevelSource.save` only.** `StashLevelSource.save` keeps its whole-tree atomic
  `force=True` swap (throwaway, machine-local, single-writer); no lost-update check.

---

## 3. Code seams (where each change lands)

- **D1** — `t3dtree.write_actor_tree`: `order_value` write → tmp + `os.replace`.
- **D2 + the shared read helper — RAISE PLACEMENT is specified to avoid a divergent build.** Factor the
  per-actor read (body-admission + `order_value` + `folder` + `labels`) into ONE shared helper used by
  both `read_actor_tree` and the D3 re-read. **The shared helper reads and RETURNS the raw rank (empty
  string / `None` for absent) and NEVER raises.** It returns the **folder normalized to `None`-if-absent**
  and **labels as a `frozenset`**, so both callers compare in the one representation the snapshot dicts use
  (`_loaded_folders` = `folder or None`; `_loaded_labels` = a `frozenset`) — otherwise the D3 re-read would
  false-conflict on an unfoldered/unlabeled actor (raw `""` vs snapshot `None`). The D2 corruption check
  lives in **`read_actor_tree`**,
  applied to the helper's returned rank (raise `CorruptTreeError` when the body was admitted but the
  returned rank is empty/missing). The **D3 re-read calls the helper directly and does NOT apply the D2
  check** — it treats an empty/absent on-disk rank as a plain comparable value, so a rank that a
  concurrent git-checkout / branch-switch / manual edit emptied between this process's `load()` and its
  flock'd re-read simply compares unequal to the (non-empty) snapshot rank → a clean `_SelectionExit`
  conflict exit-2, never a `CorruptTreeError` traceback. This resolves the "raises for one caller, not the
  other" tension with one un-flagged helper. Define `CorruptTreeError(ValueError)`; add the
  `except (OSError, ValueError) → _SelectionExit` wrap to `TrunkLevelSource.load`.
- **D3** — `dispatch.py` `TrunkLevelSource.save`: inside the flock block, before `trunk.write_level`, run
  the §2 D3 rule via the shared per-name helper over `changed ∪ deleted` only (NOT a full
  `read_actor_tree`; keep the cost `O(|changed ∪ deleted|)`). On conflict raise `_SelectionExit`.

## 4. Interactions the reviewers must check

- **The D3 comparison baseline is the LOAD SNAPSHOT (`self._ranks` etc.), never the resolved-to-write
  rank** — else a single-writer `actor order` (which puts a new rank in `resolved`/`changed`) self-aborts.
- **Absence handling:** snapshot-absent ∧ disk-absent is NOT a conflict (plain add); snapshot-present ∧
  disk-absent IS (edit-vs-delete resurrection guard); the delete carve-out applies only to names in
  `deleted`.
- **The `read_actor_tree` return contract is unchanged** (`(Level, ranks, bodies, folders)`); D2 only adds
  an error path.
- **No verb saves twice per process** (save-sites are mutually-exclusive branches), so the post-save
  snapshot refresh never defends a second in-process save.

## 5. Test plan (regressions — `test_t3dtree.py` / `test_driver.py` / new `test_trunk_concurrency`)

1. **D1 atomic** — the `order_value` write goes through `os.replace` (assert by intercepting `os.replace`
   and checking the `order_value` destination passes through it, the same way `folder`/`labels` atomicity
   is shown — an "observable" assertion, not a source grep).
2. **D2 gate, trunk path** — a trunk tree with a valid `actor.t3d` but empty/missing `order_value` makes
   an ordinary mutating verb (`actor prop set`) exit **2 with the named message, NOT a traceback** (drive
   it through the real `dispatch()` boundary so the `_SelectionExit` translation runs). A well-formed tree
   does not trip it.
3. **D2 gate, rewrite paths** — the shared-raise's other blast-radius entry points: a **`stash capture
   --force`** over a pre-corrupted stash (routes through `_read_ranks_if_present` → `read_actor_tree`) and
   a **`stash promote --force --as <existing-prefab>`** over a pre-corrupted prefab (promotion is a `stash`
   subverb, not a `prefab` one) both exit **2, not a traceback** (an ordinary `--tree stash/<id>` edit exits
   at `StashLevelSource.load` first, so it does not exercise this path).
4. **D3 lost update** — two `TrunkLevelSource`s load the same level; both edit *X*; first saves; second's
   save exits **2 with the conflict message and writes nothing** (on-disk *X* stays the first writer's).
5. **D3 compose preserved** — two *different* actors edited; both saves succeed; tree has both.
6. **D3 plain add survives** — a lone `actor add` (absent in snapshot and disk) saves cleanly.
7. **D3 override single-threaded** — a single-writer `actor order` (rank override, no concurrency)
   succeeds (guards the resolved-rank self-trip).
8. **D3 concurrent same-name add** — a concurrent same-name `actor add` aborts.
9. **D3 delete vs folder-only edit** — B `actor folder set X` (body/rank unchanged), A `actor delete X`;
   A's save aborts.
10. **D3 delete vs LABEL-only edit** — B `actor label add X …` (body/rank/folder unchanged), A
    `actor delete X`; A's save aborts (pins the labels dimension of the compare specifically).
11. **D3 edit vs concurrent delete (resurrection guard)** — A `actor prop set X`, B `actor delete X`
    commits first; A's save exits 2 and X stays deleted (guards against a wrong impl generalizing the
    delete carve-out to `changed` names and resurrecting X).
12. **D3 identical delete** — two `actor delete X`; the second succeeds (the delete carve-out), no
    spurious abort.
13. **D3 CHANGED-side sidecar conflict** — A `actor label add X foo` (X enters A's `changed` via the labels
    dim, body+rank unchanged); B `actor folder set X bar` commits first; A's save aborts. This pins the
    four-dimension compare on the `changed` side (not just the `deleted` side) — a wrong impl that compares
    only body+rank for `changed` names would silently lose B's folder edit yet pass tests 4–12.
14. **D3 CHANGED-side rank conflict** — A `actor order X --after REF` and B a concurrent `actor order X …`
    committing first; A's save aborts (the rank dimension conflicts on a `changed` name; complements test 7's
    no-false-positive by pinning the true-positive).

*(The "compare and write both inside the flock" placement is asserted by build-review inspection, not by a
regression — the sequential in-process tests above would also pass a TOCTOU-outside-the-lock impl.)*

## 6. Out of scope (logged, not done here)

- **Whole-save abort granularity / theoretical livelock** — a large batched pipeline aborts the whole save
  if one target raced; recoverable (stateless re-run) but coarse. **Logged to `inbox.md`** as a known
  tradeoff. A finer "write the non-conflicting subset, report conflicts" mode is a possible future refine.
- Three-way merge (git's job); locking reads (stay lock-free); the other review findings (chore batch +
  Spec C).
