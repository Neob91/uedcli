# Implementation Plan — group inspector properties into UnrealEd-style categories

> **For agentic workers:** use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement task-by-task. Follow `dev/docs/rules/building-features.md`
> (worktree, verify, review, squash-merge).

**Spec:** `dev/docs/board/inbox/gui-group-inspector-properties-into-unrealed/spec.md` (read it first —
this plan argues from it). Finding: **(A)** — `Prop.category` already exists in the `.u` decode
(`uprops/base.py`, `uprops/ufield.py`) and `uprops.resolve_class_properties` already resolves it
own+inherited across the Super chain; this plan is plumbing (backend field) + UI (frontend grouping),
not a new decoder.

## Global constraints

- Additive only: `SceneActor.props` keeps its current shape; a new parallel `categories` field is
  added alongside it. No existing consumer of `props` breaks.
- No endpoint failure over a categorization miss: an unresolvable class degrades that actor's props to
  the `"Uncategorized"` fallback bucket, never a `/api/level/{level}/scene` error (spec "Error
  handling").
- Tests: `bin/test -k serve` for the backend change; `npx tsc -b` / `npx vitest run` in `web/` for the
  frontend change. Frontend is isolated under `web/` — no `bin/test` involvement.

---

## Task 1: backend — resolve and ship per-property categories

**Files:** Modify `uedcli/serve/scene.py`; Modify `uedcli/tests/test_serve_scene.py`.

**Interfaces:**
- Add to `SceneActor` (frozen dataclass): `categories: list[str]` — same length and order as `props`;
  `categories[i]` is the UnrealEd category for `props[i]`.
- Add a module-level constant `_FALLBACK_CATEGORY = "Uncategorized"` (see spec "Fallback bucket").
- Add a helper:
  ```python
  def _class_category_map(fqcn: str, index) -> dict[str, str] | None:
      """casefold(prop name) -> category for fqcn's full (own+inherited) schema, or None if the
      class's schema can't be resolved at all (offline index / missing package) — caller falls back
      to _FALLBACK_CATEGORY for every one of that actor's props rather than failing the payload."""
  ```
  Implementation: `resolver = getattr(index, "resolver", None)`; if `resolver is None`, return
  `None`. Else call `uprops.resolve_class_properties(fqcn, resolver=resolver())`, catching
  `uprops.SchemaError` → return `None`. On success, return
  `{p.name.casefold(): (p.category or _FALLBACK_CATEGORY) for p in props}` (own+inherited union;
  `resolve_class_properties` already keeps the most-derived prop on a name collision — matches
  `class show`'s own convention).
- Add a helper:
  ```python
  def _actor_categories(props: list[tuple[str, str]], category_map: dict[str, str] | None) -> list[str]:
      """`categories[i]` for `props[i]`: `_FALLBACK_CATEGORY` if `category_map` is None (unresolvable
      class) or the prop's name (index-stripped) isn't in it."""
  ```
  Uses `typedprops.split_index(key)[0].casefold()` to strip a static-array index before lookup
  (`KeyPos(1)` and `KeyPos` share one category).
- In `build_scene_payload`'s actor loop: memoize `_class_category_map` per `actor.cls` in a local
  `dict` for the duration of the call (a level can have many actors of one class — avoid re-walking
  the Super chain per actor). Pass the per-class map into `_actor_categories` to build each actor's
  `categories` list; pass `categories=...` into the `SceneActor(...)` construction.
- `index` needs no new plumbing — `build_scene_payload` already receives it as a parameter (the
  `ClassIndex` `level photo --native`'s call site assembles).

- [ ] **Step 1: Failing test** — two NEW tests (do not extend
  `test_build_scene_payload_has_polys_and_actors`: that test already uses the file's `_ued22_index()`
  helper, not `StubClassIndex` — confirmed by reading the file; every existing test there uses a real
  index, because `_is_hidden_ed` (`uedcli/serve/scene.py:154-166`) calls `index.resolver()`
  **unconditionally** for any actor with no explicit `bHiddenEd` prop, and `StubClassIndex`
  (`uedcli/tests/conftest.py:205-256`) has no `.resolver()` method — calling `build_scene_payload`
  with a bare `StubClassIndex()` on an actor with no `bHiddenEd` prop raises `AttributeError` inside
  `_is_hidden_ed`, before the new categorization code ever runs):
  1. `test_build_scene_payload_categories_stub_index_fallback` — build a `Room` fixture via
     `cube_room()`, then set an explicit `bHiddenEd=False` prop on it (via `conftest.set_prop`) so
     `_is_hidden_ed` takes its instance-override branch and never calls `index.resolver()`. Call
     `build_scene_payload(project, level_name, StubClassIndex(), ...)` and assert
     `len(room_actor.categories) == len(room_actor.props)` and every entry is `_FALLBACK_CATEGORY`
     (`"Uncategorized"`) — the offline-index fallback path.
  2. `test_build_scene_payload_categories_from_real_schema` — using `_ued22_index()` (real `ClassIndex`
     over the committed `uned/UED22` corpus): build the same `Room` fixture. `cube_room()` calls
     `make_brush_actor(name, cube(...), csg="subtract")` with no `poly_flags` argument, and
     `make_brush_actor` only appends `("PolyFlags", ...)` `if poly_flags:` (default `0`) — so the
     fixture's actual stored props are `[("CsgOper", "CSG_Subtract"), ("Brush",
     "Model'MyLevel.Model_Room'")]`, **not** `CsgOper`/`PolyFlags` (verified against
     `uedcli/builders.py:744-751`). `CsgOper` resolves to real category `"Brush"`; `Brush` resolves to
     a schema `Prop` on `Engine.Actor` whose `category` is `None` (a plain, non-editable `var`, not
     `var(...)`) — per the spec's fallback rule this becomes `_FALLBACK_CATEGORY`. Assert
     `categories == ["Brush", "Uncategorized"]`, in the same order as `props`.
- [ ] **Step 2:** run `bin/test -k serve`, verify FAIL (`SceneActor` has no `categories` attribute
  yet).
- [ ] **Step 3:** implement `_FALLBACK_CATEGORY`, `_class_category_map`, `_actor_categories`, the
  `categories` field, and the per-class memoization in `build_scene_payload`, per the interfaces
  above.
- [ ] **Step 4:** run `bin/test -k serve`, verify PASS. Run the FULL suite once
  (`dev/docs/rules/tests.md`) before merge — this touches a shared dataclass (`SceneActor`)
  constructed only in `scene.py`, but confirm no other test module asserts on `SceneActor`'s field set
  (e.g. via `asdict`/`dataclasses.fields`).
- [ ] **Step 5:** commit `feat: resolve UnrealEd property categories in the scene payload`.

## Task 2: frontend — typed API field + grouping

**Files:** Modify `web/src/api.ts`; Modify `web/src/scene/markers.test.ts`; Modify
`web/src/scene/selection.test.ts`.

**Interfaces:**
- `SceneActor` interface in `web/src/api.ts` gains `categories: string[]` (parallel to the existing
  `props: [string, string][]`).

- [ ] Update the `SceneActor` type.
- [ ] `markers.test.ts`'s `actor()` helper and `selection.test.ts`'s `actor()` helper each build a
  full `SceneActor` object literal with a `props: []` default and no `categories` field — a required
  `categories: string[]` on the interface breaks `npx tsc -b` for both unless fixed. Add
  `categories: []` next to each existing `props: []` default. (`Inspector.test.tsx`'s own fixture is
  handled separately, in Task 3 — it needs real category values, not an empty default.)
- [ ] Commit alongside Task 3 (small enough to not need its own commit).

## Task 3: frontend — group and render collapsible category sections

**Files:** Modify `web/src/panels/Inspector.tsx`; Modify `web/src/panels/Inspector.test.tsx`.

**Interfaces:**
- Add a small pure function (co-located in `Inspector.tsx`, exported for its own unit test):
  ```ts
  function groupByCategory(
    props: [string, string][],
    categories: string[],
  ): Map<string, [string, string][]>
  ```
  Groups `props[i]` under `categories[i]`, preserving first-occurrence category order and
  within-category prop order (both already stored/T3D order — spec "Section order"). Throws/asserts
  on a length mismatch (`props.length !== categories.length`) — a boundary invariant violation, not a
  recoverable UI state (the backend guarantees the invariant; a mismatch means a real bug upstream).
- Replace the inspector's single `<details><summary>Raw properties (N)</summary>` block with one
  `<details>` per entry of `groupByCategory(actor.props, actor.categories)`:
  ```tsx
  {Array.from(groupByCategory(actor.props, actor.categories)).map(([category, rows]) => (
    <details key={category}>
      <summary>{category} ({rows.length})</summary>
      <table>
        <tbody>
          {rows.map(([key, value], i) => (
            <tr key={`${key}-${i}`}><td>{key}</td><td>{value}</td></tr>
          ))}
        </tbody>
      </table>
    </details>
  ))}
  ```

- [ ] **Step 1: Failing tests** — in `Inspector.test.tsx`:
  1. Update `fixtureActor` to include `categories: ['Brush', 'Brush']` (matching its existing
     `CsgOper`/`PolyFlags` props — real values per Task 1's live-verified mapping) as the default, so
     every existing test keeps passing unmodified in spirit.
  2. New test: a fixture actor with props spanning two categories (e.g. `props: [['CsgOper',
     'CSG_Subtract'], ['Mass', '100']]`, `categories: ['Brush', 'Movement']`) renders TWO `<details>`
     elements with summaries `"Brush (1)"` and `"Movement (1)"`, each containing its own row.
  3. New test: a fixture actor whose every prop is `"Uncategorized"` (the fallback) still renders (one
     `"Uncategorized (N)"` section) — the no-crash/no-hidden-props case.
  4. Unit-test `groupByCategory` directly (no render): multiple categories, single category, empty
     `props`.
- [ ] **Step 2:** `npx vitest run` in `web/`, verify FAIL.
- [ ] **Step 3:** implement `groupByCategory` + the `Inspector.tsx` render change.
- [ ] **Step 4:** `npx tsc -b` and `npx vitest run` in `web/`, verify both clean/PASS.
- [ ] **Step 5:** commit `feat: group inspector properties into UnrealEd-style categories`.

---

## Verification (pre-merge, per `building-features.md` + `tests.md`)

- [ ] Backend: `bin/test -k serve` clean (Task 1's new/extended tests); full suite once before merge.
- [ ] Frontend (`web/`): `npx tsc -b` clean, `npx vitest run` clean.
- [ ] **Exercise the real feature** (per `building-features.md` — do not fake this step): check for an
  already-running `uedcli serve` process first (`pgrep -fa serve`) — if one is up against a project
  with real `.u` packages on its search path, hit its `/api/level/<level>/scene` and confirm a
  non-brush actor's `categories` includes a real UnrealEd category (e.g. `"Movement"`/`"Lighting"`/
  `"Collision"`), then open the GUI and confirm the inspector renders collapsible per-category
  sections for a real selected actor. If nothing is running, start one
  (`uedcli serve <level>` against a project with a real games/packages config — not the offline
  fixture project, which has no resolvable schema and would only ever show the `"Uncategorized"`
  fallback)
  and do the same check. Do not skip this step or report it as done without actually running it.

## Self-review

- Spec coverage: backend field (Task 1) → frontend type (Task 2) → frontend grouping/render (Task 3)
  → verification. Every "Design" section of the spec maps to a task. ✔
- Blast radius: `SceneActor` is constructed only in `scene.py` and consumed by `serve`'s tests AND by
  `web/src/scene/markers.test.ts` and `web/src/scene/selection.test.ts` (both add a literal
  `SceneActor`-typed fixture) as well as `web/`'s own panels — Task 2 now updates all three frontend
  fixture builders, not just `Inspector.test.tsx`'s. ✔
- No fabricated UnrealEd facts: the fallback bucket name and section order are explicitly marked as
  uedcli's own choice in the spec, not asserted as real-editor behavior. ✔

## Revision history

- Review (2026-09-14) found four issues, all fixed in this revision:
  1. **Task 1 Step 1's offline-fallback test was unimplementable as written.** It claimed to extend
     `test_build_scene_payload_has_polys_and_actors` using `IDX = StubClassIndex()` — that test
     doesn't exist in that shape; every test in `test_serve_scene.py` already uses `_ued22_index()`
     (a real index), because `_is_hidden_ed` calls `index.resolver()` unconditionally for any actor
     with no explicit `bHiddenEd` prop, and `StubClassIndex` has no `.resolver()` at all — using it
     directly would crash with `AttributeError` before reaching the new categorization code. Fixed:
     split into two independent new tests; the offline one gives its fixture actor an explicit
     `bHiddenEd=False` prop so `_is_hidden_ed` never needs a resolver, isolating the fallback path the
     test actually means to exercise.
  2. **Task 1 Step 1's real-schema test asserted the wrong expected categories.** It claimed
     `cube_room()`'s stored props are `CsgOper`/`PolyFlags` resolving to `["Brush", "Brush"]`. Verified
     against `uedcli/builders.py`: `cube_room()` calls `make_brush_actor(..., csg="subtract")` with no
     `poly_flags` argument, and `PolyFlags` is only appended `if poly_flags:` (default `0`) — so
     `PolyFlags` is never in the actor's stored props at all. The actual props are `CsgOper`/`Brush`;
     `Brush`'s schema `Prop.category` is `None` (a plain `var` on `Engine.Actor`), which falls back per
     the spec's own rule. Fixed: the test now asserts `categories == ["Brush", "Uncategorized"]`
     against the actor's real stored props.
  3. **Task 2's frontend blast-radius was incomplete.** `web/src/scene/markers.test.ts` and
     `web/src/scene/selection.test.ts` each construct a full `SceneActor` object literal with no
     `categories` field; adding a required `categories: string[]` to the `SceneActor` interface
     without touching these breaks `npx tsc -b`. Fixed: both files added to Task 2's file list, each
     fixture builder gets `categories: []` alongside its existing `props: []` default.
  4. **The fallback bucket name `"Advanced"` collides with a real UnrealEd category** (confirmed
     against the `uned/UED22` corpus — see `spec.md`'s "Revision history"). Fixed: renamed to
     `"Uncategorized"` everywhere in this plan (`_FALLBACK_CATEGORY`, test assertions, verification
     text).
