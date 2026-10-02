# Spec — scope the mover-resolver requirement back per verb

DRAFT. Surfaces the owner decision; the scoping set is the owner's call (see `questions/`).

## Goal

Making `movers.is_mover` schema-aware (decisions.md 2026-07-25 10:18) propagated a class-resolver
requirement — a project **and** `~/.uedcli/config.toml` — to every call site. Seven verbs plus the
`*preview` path now exit 2 without one, a wider narrowing than the owner sanctioned (only `level
doctor`). Decide, per call site, whether the mover question is load-bearing; a call site that asks
only for a warning or a cosmetic touch can stop asking and drop its requirement.

The only sanctioned fix is **scoping** (decisions.md 2026-07-25 10:18 ruled out a name-suffix
fallback, an optional silently-degrading resolver, and a second predicate). This spec proposes which
call sites keep the question, which drop it, and which keep it but ask it only in the rare case.

## Current state — the eight call sites

`is_mover(actor, index)` answers-or-raises; `index` is a `classindex.ClassIndex` built from the
composed `.u` path (`resources.mover_index` / `class_index`, `cli/resources.py:218-248`). It raises
`ClassRefError` (→ exit 2) whenever the answer is not knowable: no resolver (`movers.py:74-75`), the
actor's class is off the search path (`movers.py:80-83`), a truncated ancestry (`movers.py:44-48`),
or a bare-name collision that disagrees (`movers.py:91-94`). That last set is the item's **second
flag**: a trunk ingested from a retail `.dx`, or a mod actor whose `.u` sits elsewhere, now fails
these verbs. A verb that stops asking drops that failure too.

| Verb | Site | Asks mover-ness FOR | If it did not ask | Class |
|--------------------------|-----------------------------------------|--------------------------------------------------------|--------------------------------------------------|---
| `mover key` | `cli/commands/mover.py:36` | refuse keyframe ops on a non-mover | would write `KeyPos`/`KeyRot` to any actor | (b) correctness guard |
| `level doctor` | `doctor.py:132,482` | watertight check = closed-solid set is `Brush` or Mover | would mis-skip or mis-check mover brushes | (b) correctness — owner-sanctioned |
| `brush apply-transform` | `cli/commands/brush/edit.py:331` | refuse to bake a Mover (bake rewrites `PrePivot`, desyncs keys) | would silently corrupt a mover's swing axis | (b) correctness guard |
| `brush intersect`/`deintersect` | `cli/commands/brush/edit.py:108` → `brushcsg.check_all_csg_brushes` (`brushcsg.py:102`) → `native/materialize.py:110` | refuse a Mover from a world-CSG merge | a mover's brush merges as an additive → wrong plug | (b) correctness, but bites all-brush sets (below) |
| `stash capture` | `cli/commands/stash.py:60` (`canonicalize_mover`) | fold an ingested `KeyNum≠0` mover to base pose | an external mover round-trips non-canonical | (b) correctness, fires only on `KeyNum≠0` |
| `event graph` | `eventgraph.py:111` (`build_graph`) | make a tagless mover a visible NODE | a mover with no `Event`/`Tag` gets no isolated node | (c) completeness |
| `brush scale` | `cli/commands/brush/edit.py:255,288` | WARN "keyframe travel does not scale" | the warning is lost; the scale is unchanged | (c) warning |
| `*preview` (actor/stash/prefab) | `preview.classify_brush` (`preview.py:361`), `cli/rendering.preview_movers` (`rendering.py:526`) | filled: subtract-cull escape + mover colour; wire: mover colour only | filled: wrong fill; wire: wrong colour on a name-miss | filled (b) already requires index; wire (c) cosmetic |

Two mechanics that shape the scoping:

- **`is_mover` validates the index first** (`movers.py:74`), so even an all-classless-`Brush` set —
  the normal `brush build … | brush intersect -` pipe — trips the resolver requirement, though none
  of those actors could ever be a mover. The requirement bites the common case, not just the rare
  one.
- **`canonicalize_mover` mutates only when `KeyNum≠0`** (`movers.py:214-217`); a trunk capture (the
  normal case) holds canonical `KeyNum=0` movers, so the index is consulted but changes nothing.

## Design

Two kinds of change, kept distinct:

**A. Drop the question (observable behaviour change — the owner's call).**

- `brush scale` — the mover check only prints a warning (`edit.py:256,289`). Dropping it makes
  `brush scale` resolver-free (works on any trunk, any install state). Cost: no "keyframe travel does
  not scale" warning. No name-suffix substitute (ruled out) — the warning simply goes.
- `event graph` — the mover check only adds an isolated node for a mover carrying **no** `Event` and
  **no** `Tag` (`eventgraph.py:111-113`). A mover with eventing props still appears via the
  `Event`/`Tag` rule, and the unreachable-mover lint fires only on an explicit unused `Tag`
  (`eventgraph.py:99-104`), so it is unaffected. Dropping the mover-node rule makes `event graph`
  resolver-free. Cost: a tagless mover no longer shows as a lone node.

**B. Narrow the question (no observable behaviour change — keep correctness, drop the requirement in
the common case).** Recommended regardless of A, and (being behaviour-preserving) implementable as
the agent's own rationale rather than an owner fork — but surfaced because it changes the
"requires config" contract:

- `stash capture` — resolve the index only when some candidate actor carries a `KeyNum` prop (any
  value); otherwise skip `canonicalize_mover` entirely. Trunk captures (canonical movers, no explicit
  `KeyNum`) become resolver-free; an external `--from-t3d` mover at `KeyNum≠0` still folds correctly.
- `brush intersect`/`deintersect` — build the index only when the piped set contains an actor whose
  class is a **qualified name other than `Brush`** (a plausible mover). An all-classless / all-`Brush`
  generator pipe stays resolver-free; a piped real actor still gets the loud refusal. This is a
  call-site gate, **not** a change to `is_mover` — reordering `is_mover` to answer `False` for a
  classless brush before validating the index is **rejected**, because it reintroduces the
  silently-degrading resolver the design forbids (a broken index would then read every actor as
  not-a-mover).

**C. Keep the question (correctness).** `mover key`, `level doctor`, `brush apply-transform` each
refuse or branch on mover-ness for correctness; they keep the requirement. `mover key` is the
definitional mover verb, so requiring the resolver to confirm the target IS a mover is inherent, not
incidental.

**D. `preview.classify_brush` — the one required single answer.** For **filled** modes,
`cli/rendering.preview_movers` (`rendering.py:550`) already resolves the real index and `*preview`
already requires a project — no change. For **wire** (the resolver-free, `--from-t3d`-capable
default), `classify_brush(is_mover=None)` uses the `bare.endswith("Mover")` name guess
(`preview.py:361`) purely to pick the magenta mover colour. Recommendation: rule the wire name-guess
a **documented cosmetic approximation** — it only mis-colours a wireframe of a mover whose class name
doesn't end in `Mover` (e.g. `CEDoor`, `BreakableGlass`), never affects geometry or a filled render —
and keep it, rather than thread the index into `wire` (which would pull `*preview` wire into the
resolver-requiring set, the opposite of this item's aim). Record the approximation in
`architecture.md` "Mover support" and the `classify_brush` docstring (both already flag it pending
this item).

**Direction reconcile (needs owner yes, folds after the scoping answer).** `direction/conventions.md`
lines 88-93 ("The cost is accepted deliberately… every mover-aware verb …") name the full seven-verb
set as accepted; it must be reworded to the kept set. A superseding `decisions.md`/`rationale` entry
records the scoping. Exact wording proposed once the set is fixed (per the item's stated outcome).

## Edge cases & errors

- A kept-requirement verb with no games config still exits 2 naming the verb + requirement
  (`resources.mover_index`, `MOVER_RESOLVER_WHY`); a missing project stays the house `ProjectError`.
- A narrowed verb (stash capture, intersect/deintersect) in its rare index-needing case fails
  identically to today — the narrowing removes the requirement only where mover-ness cannot matter.
- A dropped-question verb (scale, event graph) never resolves an index, so it no longer emits the
  off-search-path or bare-collision `ClassRefError` for any actor. Empty stdin stays a clean no-op.
- `is_mover` behaviour is unchanged in all cases (no reorder, no fallback) — every change is at the
  call site.

## Tests

- Offline (patched-seam) tests that `brush scale` and `event graph` run to completion with **no**
  games config / **no** resolvable index, and that a trunk with a retail-`.dx`-ingested off-path
  class no longer fails them.
- `event graph`: a tagless mover no longer appears as a node; a mover WITH `Event`/`Tag`, and the
  unreachable-`Tag` lint, are unchanged.
- `stash capture`: a trunk capture of a canonical mover needs no index (regression-guard the
  no-index path); an external `--from-t3d` mover at `KeyNum≠0` still canonicalizes.
- `brush intersect`/`deintersect`: an all-`brush build` pipe needs no index; a piped real Mover is
  still refused loudly.
- Kept verbs (`mover key`, `level doctor`, `brush apply-transform`): unchanged — regression-guard
  that they still exit 2 without a resolver.
- `preview` wire: name-guess colour documented; a filled render still uses the index.

## Open questions

See `questions/`. Two genuine forks: (1) the scoping set — which call sites drop or narrow the mover
question; (2) `preview.classify_brush` wire — documented cosmetic approximation vs thread the index.
The `direction/conventions.md` rewrite and the superseding `decisions.md` entry follow from (1) and
need the owner's yes on exact text.
