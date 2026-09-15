# Spec — group inspector properties into UnrealEd-style categories

Written for a reader who has not seen the design discussion. Terms are defined before use.

## Goal

The GUI's read-only inspector (`web/src/panels/Inspector.tsx`) shows a selected actor's stored T3D
properties as one flat `<table>`. Group them into UnrealEd-style categories (`Display`, `Movement`,
`Collision`, `Lighting`, …) as collapsible sections, matching how the real editor's property window
organizes them — per the `uedcli-human-gui` spec's "Selection & inspector" line: "the full raw T3D
property set (grouped, collapsible)". Nothing is hidden — grouping only, same property set as today.

## Investigation finding: **(A) — the category metadata already exists, unused, in the `.u` decode**

This is the load-bearing fact the whole design rests on, so it is stated plainly with its evidence:

Real UnrealEd's property window groups by the `Category` a property's original `.uc` source declares
(`var(Movement) float Speed;`). `uedcli/uprops/`'s `.u` package decoder **already parses and exposes
this per-property**, RE'd byte-exact 2026-07-18 (`dev/docs/unrealed/class-schema.md` "UProperty body
layout — and the editor Category"):

- `uprops.base.Prop.category: str | None` — decoded by `uprops/ufield.py:_decode_property` from the
  UProperty body's `Category` FName field (`uedcli/uprops/ufield.py:41-42`).
- Semantics (RE'd, not assumed): `var(Group)` → `Group` (crosses classes, e.g. `Actor.Mass` →
  `Movement`, `Actor.Mesh` → `Display`, `Actor.LightType` → `Lighting`, `Actor.CollisionRadius` →
  `Collision`); bare `var()` → the declaring class's own name (e.g. `Engine.Brush.CsgOper` →
  `"Brush"`, `Engine.Mover.KeyNum` → `"Mover"` — confirmed live against the committed `uned/UED22`
  corpus below); a non-editable plain `var` (no parens) → `None`, meaning "not in the real editor's
  property window at all."
- `uprops.resolve_class_properties(fqcn, resolver=...)` already returns the full own+inherited `Prop`
  list (`category` included) for any class, unioned across the Super chain, package boundaries
  crossed via a resolver. This is not new/theoretical machinery: `uedcli/cli/commands/classes.py`'s
  `class show --category` (lines ~658–790) already groups a class's **schema** by `p.category` today
  — own props, inherited props collapsed to a count, `--category NAME` filters. This spec's frontend
  design mirrors that grouping, applied to an **actor's stored property values** instead of a bare
  class schema listing.

Live-verified against the git-tracked `uned/UED22/*.u` corpus (read-only check, this investigation):

```
Engine.Brush PolyFlags       -> Brush     (owner Engine.Brush)
Engine.Brush CsgOper         -> Brush     (owner Engine.Brush)
Engine.Brush CollisionRadius -> Collision (owner Engine.Actor)
Engine.Brush Mass            -> Movement  (owner Engine.Actor)
Engine.Brush Mesh            -> Display   (owner Engine.Actor)
Engine.Brush LightType       -> Lighting  (owner Engine.Actor)
Engine.Mover KeyNum          -> Mover     (owner Engine.Mover)
Engine.Mover MoveTime        -> Mover     (owner Engine.Mover)
```

So this is **not** a "decode the category from the compiled `.u` format" feature (path B) — that work
is already done and sitting unused. It is a **plumbing + UI** feature: pull `Prop.category` through to
the client for each of an actor's *stored* properties, and group the inspector's list by it.

**What is NOT already proven (flagged honestly, not assumed):** whether real UnrealEd's property
window uses a specific catch-all bucket NAME (e.g. literally "Advanced") for anything, and what order
it renders categories/sections in. Nothing in `dev/docs/unrealed/` documents either fact (grepped
`categor` case-insensitively across the whole tree — the class-schema.md decode note above is the only
hit that bears on this, and it documents the on-disk encoding, not the property-window's bucket naming
or section order). This design therefore picks its own answers for those two things (below), clearly
marked as uedcli's own UI choice, not a verified UnrealEd fact.

## Design

### Backend (`uedcli/serve/scene.py`)

`SceneActor.props` (`list[tuple[str, str]]`, actor's *stored* T3D properties — a strict subset of the
class's full schema, since a T3D only states properties that differ from class defaults) gains a
sibling field:

```python
categories: list[str]   # same length/order as props; categories[i] is props[i]'s UnrealEd category
```

(Kept as a parallel array, not `props: list[tuple[str, str, str]]`, so the existing raw-props shape —
and every current reader of it — is untouched; this is additive.)

Per actor, resolve once per **class** (not per prop) via the existing
`uprops.resolve_class_properties(actor.cls, resolver=index.resolver())` — `index` is the `ClassIndex`
`build_scene_payload` already receives as a parameter (same object `level photo --native` assembles;
no new plumbing to reach a resolver). Build `casefold(prop name) -> category` from the returned `Prop`
list, memoized per class for the duration of one `build_scene_payload` call (a level can have many
actors of the same class; `resolve_class_properties` itself is already schema-cache-backed across
calls, but re-walking the Super chain per actor is needless repeated work within one request).

For each stored prop, strip a static-array index (`KeyPos(1)` → `KeyPos`, via the existing
`typedprops.split_index`) before the casefold lookup — the category applies to the property, not to
one element.

**Fallback bucket — `"Uncategorized"`.** A stored prop's category is `"Uncategorized"` (not hidden,
not an error) whenever:
- the class's schema can't be resolved at all (`index.resolver()` doesn't exist — the offline
  `StubClassIndex` test double used by some `serve` tests has no `resolver()` — or
  `resolve_class_properties` raises `SchemaError`, e.g. a missing package on the search path), or
- the prop name isn't found in the resolved schema at all (stale/renamed/deprecated key, or a
  uedcli-authored prop with no `.uc` declaration), or
- the resolved `Prop.category` is `None` (a non-editable plain `var` — real UnrealEd would not show
  it at all, but this inspector's contract is "the full raw T3D property set," so it still renders,
  just uncategorized).

This is a deliberate, visible label (never a silent drop) — consistent with the "no silent
half-answers" rule: a schema-resolution failure degrades that actor's grouping, not the property list
itself, and never the whole `/api/level/{level}/scene` response. **`"Uncategorized"` is uedcli's own
catch-all name**, not a documented real-UnrealEd bucket — flagged per the above. (Originally
`"Advanced"`, to match the owner's own example list in this board item's `overview.md`; renamed per
review, see "Revision history" — `Advanced` is itself a real, actively-used UnrealEd category, so it
could not double as the "uncategorized" bucket without the two becoming visually indistinguishable.)

**Section order — first-appearance in the stored T3D order.** `categories[i]` lines up with
`props[i]`, which is already in the actor's stored (T3D-authored) order; the frontend groups by
first-occurrence order of `categories`, so the section order follows however the actor's T3D happens
to state its properties. This is **not** a claim about real UnrealEd's own category ordering (also
undocumented here) — it is the simplest rule that needs no extra backend data.

### Frontend (`web/src/panels/Inspector.tsx`)

Replace the single `<details><summary>Raw properties (N)</summary><table>…flat rows…</table></details>`
block with one `<details>` per category (open by default only for the first, matching a typical
collapsible-sections default — exact default-open policy is a build-time call, not pinned here):

```tsx
<details key={category}>
  <summary>{category} ({rows.length})</summary>
  <table>…</table>
</details>
```

Grouping (`props[i]` + `categories[i]` → `Map<category, [key, value][]>`, insertion-ordered) is a
small pure function, unit-testable on its own without a DOM render.

## Data flow

1. `/api/level/{level}/scene` (existing route, `uedcli/serve/app.py`) — no new endpoint.
2. `build_scene_payload` resolves each actor's class category map once (memoized per class per
   request) and ships `categories` alongside `props` per actor.
3. `web/src/api.ts`'s `SceneActor` type gains `categories: string[]`.
4. `Inspector` groups client-side and renders one collapsible section per category.

## Error handling

- A resolvable class with a resolvable schema: every stored prop gets its real category (or
  `"Uncategorized"` if the prop is schema-`None`/unmatched).
- An unresolvable class/schema (missing package, offline index): **the whole actor still renders**,
  all its stored props under `"Uncategorized"` — never a scene-endpoint failure over a categorization
  miss. (Contrast with `class show`'s CLI behavior, which hard-errors on an unresolvable schema — that
  command's whole job is schema introspection; the scene endpoint's job is rendering a level, and
  category grouping is a display nicety on top, not its output.)

## Testing (see `plan.md` for concrete tasks)

- Backend: `bin/test -k serve` — a real test against the committed `uned/UED22` corpus asserting a
  known category for a real fixture's stored props (see `plan.md` Task 1 for the exact fixture and
  expected values — `cube_room()`'s actual stored props are `CsgOper`/`Brush`, not `CsgOper`/
  `PolyFlags`) and the offline-index fallback (`StubClassIndex`, no `resolver()` → every prop
  `"Uncategorized"`, no crash).
- Frontend: `npx tsc -b` / `npx vitest run` in `web/` — the grouping function's unit tests (multiple
  categories, empty props, all-fallback) plus an `Inspector` render test asserting collapsible
  sections per category.
- Manual: run the feature against a real actor's real properties in a live `uedcli serve` session (see
  plan's Verification section — no server was assumed running for this doc; check with `pgrep -fa
  serve` at build time).

## Non-goals

- No change to *which* properties are shown (still the full stored set) — grouping only.
- No attempt to reproduce real UnrealEd's exact category-section ORDER or catch-all bucket NAME (both
  undocumented here, per above) — that would need a live UnrealEd probe, out of scope for this item.
- No change to `uprops`/`upackage` decoding — the category decode already exists and is untouched.

## Revision history

- Review (2026-09-14) found the fallback bucket name `"Advanced"` collides with a real, actively-used
  UnrealEd category — confirmed by scanning the committed `uned/UED22` corpus (`uprops.iter_classes` +
  `own_class_properties`, 246 real categories found), `Advanced` genuinely declared (`var(Advanced)
  ...`) on `DeusEx.DeusExCarcass`, `DeusEx.DeusExDecoration`, `DeusEx.DeusExPlayer`,
  `DeusEx.DeusExFragment`, `DeusEx.ScriptedPawn`. A genuinely-`Advanced` prop and an
  unresolvable/uncategorized one would render in the same section, indistinguishable to the user.
  This revision renames the fallback bucket to `"Uncategorized"` throughout (a name no real category
  in the corpus uses) — everywhere `"Advanced"` appeared as the fallback value. `plan.md` updated to
  match; see its own "Revision history" for the three further fixture/test corrections from the same
  review.
