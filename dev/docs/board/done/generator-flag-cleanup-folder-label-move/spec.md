# Spec — generator-flag cleanup: `--folder`/`--label` move to the generators; ditch `--group`

**Status: BUILT 2026-07-24** (`22f82b8a8` code + `960275b0d` docs; suite green). Ephemeral per-feature
scratch — now superseded by the shipped code, `docs/usage.md`, and `direction.md`
("Folders"/"Labels"/"Generator pattern", reconciled); this file may be deleted. The durable record is
[`dev/docs/decisions.md`](../../../decisions.md) `2026-07-24 17:04 UTC`. **Date:** 2026-07-24.

**Why this spec exists.** It is the **coupled prerequisite** for the native `intersect`/`deintersect`
spec (`2026-07-24-intersect-deintersect-native-brushset.md` §7b): those verbs share `brush build`'s
output-flag set, which forced the question "what *is* that set." This spec pins the cross-cutting CLI
change to the **generators** so the shared set is well-defined. It touches `brush build`, `actor build`,
and `actor add` — wider than the intersect/deintersect work — so it stands alone and sequences **first**.

**Read first:** `cli.py:737` `_common_build_opts` (the `brush build` shared flags), `cli.py:455` `actor
build`, `cli.py:478` `actor add`, `model.py:44` `_FOLDER_CARRIER` / `labellib.py:29` `_LABELS_CARRIER`
(the on-the-wire carriers), `direction.md` "Folders"/"Labels"/"Generator pattern" (reconciled by this).

---

## 0. Goal

Make the **generator** the single place that sets an authored actor's identity — including its
organization (`folder`/`label`) — and make `actor add` a **pure carrier-consumer**. Three changes,
all decided at `decisions.md 2026-07-24 17:04`:

1. **Add `--folder <path>` and `--label <l>` (repeatable) to every generator** — `brush build` (all
   shapes, via `_common_build_opts`) and `actor build`.
2. **REMOVE `--folder`/`--label` from `actor add`.**
3. **Ditch `--group` from `brush build`** (`_common_build_opts`) → use `--prop Group=`.

This **reverses** the earlier rule that folder/label flags live on `actor add`, not the generators
(`direction.md`; decisions 2026-07-18 actor-folders / 2026-07-22 actor-labels) — already reconciled in
`direction.md`.

## 1. The mechanism (already in place)

`folder` and `label` are uedcli-side sidecars that ride the T3D wire as comment carriers the editor
strips silently: `// uedcli-folder: <path>` (`model._FOLDER_CARRIER`) and `// uedcli-labels: a,b,c`
(`labellib._LABELS_CARRIER`). Today the carriers are emitted in exactly ONE place — `query.actor_show_block`
(`query.py:308-316`, used by `actor show`) — and parsed back by `actor add` (`dispatch.py:1846`+). So the
*parsing* plumbing exists, but **generators emit NO carriers today — that is genuinely new emit code**, and
WHERE it goes is load-bearing (a wrong locus corrupts the trunk store):

- **Generator carrier emission MUST live in `emit.emit_actor_t3d` ONLY** (the shared single-actor generator
  stdout emitter — `emit.py:155`, written to stdout by `actor build`/`brush build` at `dispatch.py:3165`+,
  and by `brush intersect`/`deintersect` in the dependent spec — so BOTH verb families inherit it from one
  place, satisfying that spec's dependency). Emit the carriers there, gated on the actor having
  `folder`/`labels` set.
  - ⚠️ **DO NOT** add carriers to `emit.emit_actor` / `emit.emit_map` / `normalize.canonical_actor_t3d`:
    `canonical_actor_t3d` (`normalize.py:243`) writes the **stored trunk `actor.t3d` body** (`t3dtree.py:126`),
    whose INVARIANT is that it never contains a carrier line (`model.py:38-43`) — adding carriers there
    **corrupts the store** and makes `actor show` **double-emit**; `emit_map` feeds editor import
    (`writes.py:87`). Pin the emit at `emit_actor_t3d`, never the shared/canonical path.
  - **CLI:** `cli` adds `--folder`/`--label` args; they set `actor.folder`/`actor.labels` on the generated
    Actor (thread through `make_brush_actor` — which gains folder/labels params — and the `actor build`
    Actor construction), and `emit_actor_t3d` renders them. (`make_brush_actor` alone is NOT sufficient —
    `brush intersect`/`deintersect` build their Actor from CSG faces, not via `make_brush_actor`, so the
    carrier render must sit at the shared `emit_actor_t3d`, not in `make_brush_actor`.)
  - **Carrier helpers:** reuse `labellib.format_labels_carrier` (`labellib.py:51`) for labels; **extract a
    folder-carrier helper** from the hand-formatted line at `query.py:310` (none exists yet) and use it in
    both `query` and `emit_actor_t3d` — do NOT hand-format a second copy.
- **`actor add` side (change):** it KEEPS parsing carriers from the incoming T3D (unchanged) and just
  loses its own `--folder`/`--label` **override** flags. It persists exactly what the T3D carries.

## 2. Behavior details

- **No override, no second setter.** With the flags gone from `actor add`, there is exactly one setter
  (the generator/carrier) — no precedence rule to remember. To change folder/label *after* add, use the
  existing trunk verbs **`actor folder set|unset`** / **`actor label add|remove|set|clear`**.
- **Absent carrier = unfoldered / unlabelled** (unchanged default).
- **`--group` → `--prop Group=`.** `--group` set the plain `Engine.Actor.Group` Name prop with no
  abstraction, so it is redundant with the schema-validated `--prop Group=<name>`. The other
  `_common_build_opts` flags STAY (`--csg`/`--solidity`/`--texture`/`--rotate` each carry semantics beyond
  a raw prop; `--at`/`--base-name`/`--mover-class`/`--prop` are structural). `actor build` never had
  `--group` (already `--prop`), so the ditch touches only `brush build`.
- **`actor add` keeps `--order`** — trunk-sequence position is inherently an add-time concern (where in
  the LexoRank order to insert), not authored spatial/organizational identity, so it stays on the consumer.
- **`--label` grammar** matches the existing `actor label add` / `actor find --label` token rules
  (repeatable, OR at query time); `--folder` is a single dotted path like `actor folder set`.
- **`actor duplicate` and `stash/prefab apply` KEEP their `--folder`/`--label` (deliberate exception).**
  `actor add`'s flags are removed because it always follows a *generator* that could set them; but
  `duplicate` (`cli` dup parser, `dispatch.py:3695`) and `apply` (`cli.py:235`, `dispatch.py:899`) COPY
  already-stored actors with **no upstream generator** in the pipe, so their `--folder`/`--label` are the
  only setter available and STAY. The "single setter = the generator" principle is specifically about the
  `generator → actor add` path; `duplicate`/`apply` are copy-verbs, not that path.

## 3. Migration / backward-incompatibility (hard break)

- **`actor add --folder <p>` / `--label <l>` callers BREAK** (flags removed). Migration: set the
  folder/label on the **generator** that produced the T3D (`brush build … --folder <p> --label <l>`), or
  run `actor folder set` / `actor label add` after the add. Update every in-repo caller + doc + test.
- **Capability regression for NON-generator T3D sources (own it explicitly).** Hand-written T3D, and
  `stash show | actor add -` / `prefab show | actor add -` where the stored source lacks the wanted
  folder/label, can no longer be foldered/labelled *at add time* — and note stash/prefab entries **can't
  even carry** the carriers (they are rejected as trunk-only into a stash/prefab target, `dispatch.py:1865`).
  Recovery is a second piped verb: `… | actor add - | actor folder set --to X -` (works — `actor add` prints
  the allocated Names). This is a real ergonomic cost of the single-setter model; accepted, but documented.
- **`brush build … --group <g>` callers BREAK.** Migration: `--prop Group=<g>`.
- **Test migration (precise):** (a) `actor add --folder/--label` usages → port to generator-side or a
  follow-up `actor folder set`/`actor label`; the **override-precedence** tests (`test_folders.py:294`
  "override.path", `test_labels_verbs.py:212` "override") test the REMOVED behavior — **delete them / turn
  into argparse-rejection tests**, do NOT "port". (b) `--group`: there are **zero** `brush build --group`
  test usages — every `--group` hit in tests is `actor find`/`stash apply`/`prefab apply --group`, which
  **must NOT be touched**; do a targeted `build(... --group` search, never a blanket `--group` replace.
  (c) dead code after removal: `dispatch.py:3660` `labels_override = frozenset(args.label)` goes dead for
  `add` (survives via `getattr` but is unreachable) — remove it.

## 4. Tests

- **Generator emits carriers:** `brush build cube --folder a.b --label x --label y` → the emitted T3D block
  contains `// uedcli-folder: a.b` and `// uedcli-labels: x,y`; piped to `actor add -`, the trunk actor has
  folder `a.b` and labels `{x,y}`. Same for `actor build`.
- **`actor add` has no `--folder`/`--label`:** argparse rejects them (regression that they're gone).
- **`actor add` still persists carriers** from hand-written / `stash show` T3D (unchanged behavior).
- **`--group` gone from `brush build`:** argparse rejects `--group`; `--prop Group=club` produces
  `Group=club` in the emitted actor.
- **Round-trip:** `brush build --folder f --label l | actor add -` then `actor find --folder f` /
  `--label l` returns the actor.

## 5. Docs

`docs/usage.md`: move `--folder`/`--label` from the `actor add` reference to the generator (`brush build`/
`actor build`) reference; drop `--group` from `brush build` (note `--prop Group=`); note `actor add` is a
pure carrier-consumer (persists carriers; change later with `actor folder set`/`actor label`).
**`architecture.md`** (`:379`/`:382`/`:386` + the labels block ~`:427`) documents `actor add --folder`/
`--label` and the "`actor show` ↔ `actor add`" carrier mechanism as current-code — **update it** (CLAUDE.md
mandates `architecture.md` track the code). Check `docs/leveldesign/` for any `actor add --folder/--label`
walkthrough. `direction.md` is already reconciled (Folders/Labels/Generator-pattern sections cite
`2026-07-24 17:04`); the labels-section decision citation should also list the 17:04 entry (cosmetic).

## 6. Resolved (were open; closed before build per review)

- **Generator set is `brush build` shapes + `actor build`** (+ the new `brush intersect`/`deintersect`,
  which inherit via `emit_actor_t3d`). `stash`/`prefab` are stores, not generators; `actor duplicate`/`apply`
  are copy-verbs that KEEP their own flags (§2 exception). Set is exhaustive.
- **Hard removal, no deprecation window** — `uedcli` is a pre-1.0 internal tool with no external callers;
  all call sites are in-repo and migrated in this change. (The dependent intersect/deintersect build assumes
  the cleanup has landed, so a deprecation shim would only add noise.)

## 7. Decisions recorded

The load-bearing choices are in [`dev/docs/decisions.md`](../../../decisions.md) `2026-07-24 17:04 UTC` (generator-flag
cleanup). This spec is ephemeral; the ledger is durable.
