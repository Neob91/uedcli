# GUI Inspector: Effective Props Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Inspector's flat, explicit-only prop display with a searchable,
typed, default-aware `EffectiveProp` tree (struct/array expansion, texture group identity,
Folder/Labels display refresh) — read-only, no write path.

**Architecture:** Backend (`uedcli/serve/scene.py` + two small new modules) resolves each actor's
full class schema into a recursive `EffectiveProp` tree per-request, reusing `propedit`'s existing
`TYPED_FIELDS`/`effective_value` engine (never reinventing validation/defaults resolution) plus a
new per-member "which axis did the actor state" side-channel for `Location`/`MainScale`/`PostScale`.
Frontend (`web/src/panels/Inspector.tsx`) renders the tree with search/show-all filtering and
struct/array expansion, replacing the old flat `<dl>`+per-category-`<details>` view.

**Tech Stack:** Python (FastAPI backend, `uedcli/`), TypeScript/React (`web/src/`, Vitest + React
Testing Library).

**Spec:** `dev/docs/board/to-plan/gui-inspector-effective-props-search-show-all/spec.md` — this plan
implements it task-by-task; read both together. All copy/naming/behavior calls not repeated here
defer to the spec.

## Global Constraints

- No back-compat shims — uedcli is unreleased (`direction/conventions.md`). `SceneActor.props`'s old
  `[string,string][]` + `categories: string[]` shape is replaced outright, not migrated or kept
  alongside the new one.
- Every command/verb/flag this touches keeps its existing `help=`/docstring conventions; this plan
  touches no CLI surface, only the GUI-serve backend and the web frontend.
- Tests via `bin/test` (never bare `pytest`) per `dev/docs/rules/tests.md`; scope to touched modules
  while iterating (`bin/test -k scene` / `bin/test -k utexture`), run the non-integration default
  suite once before the final commit of each task.
- Frontend tests via the existing `web/` Vitest setup (`npm test` under `web/`, or this repo's usual
  frontend test command) — scope to touched files while iterating, full suite once before the final
  task's commit.
- Every new Python dataclass is `@dataclass(frozen=True, kw_only=True)` per this project's code
  style; every new function has real type hints, `list[X]`/`X | None` style, never `List`/`Optional`.
- **No Python exception reaches the API boundary uncaught.** This is load-bearing for this plan
  specifically: `ctx.schema()` can and does contain `ArrayProperty`/`PointerProperty` entries (13
  real ones exist across the substrate per the spec) and struct/enum members that fail to resolve
  cross-package — both MUST degrade safely (omit the property / empty enum list), never raise past
  `resolve_actor_props`. Task 4 and Task 2 are where this is actually enforced; every other task
  that calls into them inherits the guarantee, it is not re-checked per call site.

---

## File map (what's created/modified, one responsibility each)

- `uedcli/model.py` — MODIFY: `Actor.main_scale_text`/`Actor.post_scale_text` fields + parse-time
  population, mirroring `location_text` exactly.
- `uedcli/effective_props.py` — CREATE: the `EffectiveProp` Python dataclass hierarchy + the pure
  resolution logic (schema walk → `EffectiveProp` tree). No FastAPI/scene-payload knowledge — takes
  an `Actor`, a `ClassCtx`-shaped bundle, and `TYPED_FIELDS`; returns `list[EffectiveProp]`. Kept
  separate from `scene.py` because it's substantial, independently unit-testable pure logic, matching
  this project's "smaller, focused files" convention.
- `uedcli/serve/scene.py` — MODIFY: delete `_actor_categories`/`_with_synthetic_location`/
  `_class_category_map`'s prop-list use (category resolution now lives inside
  `effective_props.py`, reusing the same `ctx.schema()` walk instead of a separate pass); add the
  `ClassCtx`-from-`index` adapter (`_class_ctx_for`); wire `effective_props.resolve_actor_props`
  into `_build_actors`; `SceneActor.props: list[EffectiveProp]`; `ScenePoly.normal`/`.area`;
  `ScenePayload.enums`.
- `uedcli/serve/textures.py` — MODIFY: `AtlasRect` gains `name: str | None`.
- `uedcli/preview_native.py` — MODIFY: `_TextureTable.index_for` records the resolved export's real
  group name alongside its pixel decode, via `TextureResolver.package_for_ref` (existing method,
  purpose-built for exactly this — see Task 7).
- `web/src/api.ts` — MODIFY: `EffectiveProp` discriminated union, `SceneActor.props` retyped,
  `ScenePayload.enums`, `AtlasRect.name`, `ScenePoly.normal`/`.area`.
- `web/src/panels/effectiveProps.ts` — CREATE: pure frontend helpers (search filter, overrides-only
  filter, shown-value derivation) operating on `EffectiveProp[]` — kept out of `Inspector.tsx` so
  they're unit-testable without React, matching this project's existing `groupByCategory.ts`/
  `selectionSet.ts` convention of pure-logic sibling modules next to their consuming component.
- `web/src/panels/Inspector.tsx` — MODIFY: search box, overrides/show-all toggle, struct/array
  `<details>` rendering, typed display (checkbox — enum needs no lookup, see Task 4's enum
  canonicalization), Folder/Labels chip+dash refresh, `SurfaceDetail` texture-name/area/normal
  display. Split across Tasks 10a/10b/10c (see "Task right-sizing" note below the file map).
- `web/src/panels/groupByCategory.ts` — MODIFY: input type changes from `(props: [string,string][],
  categories: string[])` to `(props: EffectiveProp[])` (category is now on each `EffectiveProp`
  directly, no parallel array).

**Task right-sizing note**: the original draft of this plan bundled search, the overrides/show-all
toggle, struct/array rendering, typed display, and the Folder/Labels refresh into one Task 10 with a
single commit — reviewed and correctly flagged as too coarse (a reviewer could accept "search +
toggle" while rejecting "struct/array rendering," the riskiest piece, with no way to separate them).
Split into 10a/10b/10c below, each its own commit.

---

### Task 1: `main_scale_text`/`post_scale_text` side-channel on `model.Actor`

**Files:**
- Modify: `uedcli/model.py` (near `Actor.location_text`; the `MainScale`/`PostScale` parse branch,
  currently at `model.py:225`)
- Test: `uedcli/tests/test_model.py` (or whichever file already covers `location_text` parsing —
  run `grep -rln "location_text" uedcli/tests/` first and mirror that test's exact fixture style)

**Interfaces:**
- Consumes: nothing new (reads the existing T3D parse loop's `key`/`val` locals).
- Produces: `Actor.main_scale_text: str | None`, `Actor.post_scale_text: str | None` — the verbatim
  `MainScale=`/`PostScale=` T3D text as parsed, `None` if the actor never states that field.
  Task 3 consumes both.

- [ ] **Step 1: Write the failing test**

```bash
grep -rln "location_text" uedcli/tests/
```

Add a parallel case to that same file (same fixture style) asserting `main_scale_text`:

```python
def test_mainscale_text_captures_stated_axes():
    t3d = """Begin Actor Class=Engine.Brush Name=Brush0
        MainScale=(Scale=(X=2.000000))
        Location=(X=0.000000,Y=0.000000,Z=0.000000)
    End Actor
    """
    level = parse_t3d(t3d)  # match the exact parse entry point the location_text test uses
    actor = level.actors["Brush0"]
    assert actor.main_scale_text == "(Scale=(X=2.000000))"
    assert actor.post_scale_text is None
```

- [ ] **Step 2: Run test to verify it fails**

`bin/test -k mainscale_text -v` — Expected: FAIL, `AttributeError: 'Actor' object has no attribute
'main_scale_text'`.

- [ ] **Step 3: Implement**

In `model.py`, add both fields next to `location_text` (same default, same doc-comment style —
copy `location_text`'s own comment, swapping "Location" for "MainScale"/"PostScale" and citing
`architecture.md`'s "Scale" section instead of the compare-seam citation):

```python
    main_scale_text: str | None = None
    post_scale_text: str | None = None
```

In the parse loop's `elif key in ("MainScale", "PostScale"):` branch (`model.py:225`), record the
raw text alongside the existing typed-field assignment:

```python
            elif key in ("MainScale", "PostScale"):
                fs = parse_fscale(val)          # existing call, unchanged
                if key == "MainScale":
                    actor.main_scale = fs
                    actor.main_scale_text = val
                else:
                    actor.post_scale = fs
                    actor.post_scale_text = val
```

- [ ] **Step 4: Run test to verify it passes**

`bin/test -k mainscale_text -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/model.py uedcli/tests/test_model.py
git commit -m "Add main_scale_text/post_scale_text side-channel, mirroring location_text"
```

---

### Task 2: `EffectiveProp` dataclass hierarchy + `ClassCtx`-from-`index` adapter

**Files:**
- Create: `uedcli/effective_props.py`
- Modify: `uedcli/serve/scene.py` (add `_class_ctx_for`, near `_class_category_map`)
- Test: `uedcli/tests/test_effective_props.py`

**Interfaces:**
- Consumes: `propedit.ClassCtx` (existing — `cls`, `load_schema`/`load_defaults`/`load_members`/
  `load_enums` callables; `.schema()`/`.defaults()`/`.members(prop)`/`.enums(prop)` memoized public
  accessors — `.enums()` catches `SchemaError` internally and degrades to `()`; `.members()` does
  NOT catch anything, callers must guard it themselves), `uedcli.uprops.Prop` (existing).
- Produces (this task): the `EffectiveProp` variant dataclasses below, and
  `_class_ctx_for(cls: str, index) -> propedit.ClassCtx` in `scene.py` — Tasks 3/4 consume both.

**The type shape** (mirrors the spec's TS discriminated union — a Python union of frozen
dataclasses, not one dataclass with optional fields, matching this project's "small frozen
dataclasses over ad-hoc tuples/dicts" convention):

```python
"""Effective-property resolution for the GUI Inspector — schema + stored/default value, structured
as a tree (struct/array expansion), not a flat KEY=VALUE list. Pure: takes a `model.Actor` and a
`propedit.ClassCtx`, returns `list[EffectiveProp]`. No FastAPI/scene-payload knowledge here — that
wiring lives in `serve/scene.py`.

See `dev/docs/board/to-plan/gui-inspector-effective-props-search-show-all/spec.md` for the design
this implements — the resolution engine (`propedit.effective_value`), the show-all filter
(`HARD_REJECT`+`is_computed_key`, not `CPF_Edit`), and the ArrayProperty/PointerProperty exclusion
are all owner-ruled decisions from that spec, not judgment calls made here."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class ScalarProp:
    name: str
    category: str
    kind: str                          # 'float'|'int'|'bool'|'byte'|'name'|'string'
    stored_value: str | None
    default_value: str


@dataclass(frozen=True, kw_only=True)
class EnumProp:
    name: str
    category: str
    enum_type: str                     # key into ScenePayload.enums, "<Package>.<Class>.<EnumName>"
    stored_value: str | None           # ALWAYS a canonical enum NAME, never a bare ordinal (Task 4
    default_value: str                 # canonicalizes both — see Task 4's enum branch)
    kind: str = "enum"


@dataclass(frozen=True, kw_only=True)
class StructProp:
    name: str
    category: str
    members: list["EffectiveProp"]
    kind: str = "struct"


@dataclass(frozen=True, kw_only=True)
class ArrayProp:
    name: str
    category: str
    element_kind: str
    elements: list["EffectiveProp"]
    kind: str = "array"


EffectiveProp = ScalarProp | EnumProp | StructProp | ArrayProp
```

`_class_ctx_for` in `scene.py` — mirrors `cli/resources.py::struct_members`/`enum_names`'s REAL
bodies (read directly during plan review, not guessed), reparameterized on `resolver` (which
`scene.py`'s `index.resolver()` already provides — see `_class_category_map`, the existing sibling
function) instead of `project`/`resolve_project(args)` (which don't exist outside the CLI):

```python
def _struct_members_via(resolver, prop) -> list[Prop]:
    """Port of cli/resources.py::struct_members, parameterized on `resolver` instead of `project` --
    scene.py has no CLI args/project to resolve one from, only index.resolver()."""
    owner_pkg_name = prop.owner.split(".", 1)[0]
    path = resolver(owner_pkg_name)
    if path is None:
        raise uprops.SchemaError(f"package {owner_pkg_name!r} not found on the schema search path "
                                 f"(needed to resolve {prop.owner}.{prop.name})")
    dp = uprops.load_package(path, name=owner_pkg_name)
    tp, ti = uprops.resolve_type_export(dp, prop.type_ref, "Struct", resolver=resolver, _pkgs={})
    return uprops.struct_members(tp, ti, owner=prop.type_name or prop.name)


def _enum_names_via(resolver, prop) -> tuple[str, ...]:
    """Port of cli/resources.py::enum_names, same reparameterization."""
    owner_pkg_name = prop.owner.split(".", 1)[0]
    path = resolver(owner_pkg_name)
    if path is None:
        raise uprops.SchemaError(f"package {owner_pkg_name!r} not found on the schema search path "
                                 f"(needed to resolve {prop.owner}.{prop.name})")
    dp = uprops.load_package(path, name=owner_pkg_name)
    return uprops.resolve_enum_names(prop, dp, resolver=resolver)


def _class_ctx_for(cls: str, index) -> propedit.ClassCtx:
    """The same lazy per-class schema bundle `cli/resources.py::class_ctx` builds for the CLI,
    sourced from the GUI-serve `index`'s own resolver instead of CLI `args`."""
    resolver = index.resolver()
    return propedit.ClassCtx(
        cls=cls,
        load_schema=lambda: {p.name.casefold(): p for p in
                            uprops.resolve_class_properties(cls, resolver=resolver)},
        # dict, NOT the raw list resolve_class_properties returns -- ClassCtx.schema()'s contract
        # (propedit/base.py) is dict[str, Prop], and Task 4's `for prop in ctx.schema().values()`
        # depends on it. Confirmed via the existing sibling `_class_category_map` (scene.py:532),
        # which wraps the SAME resolve_class_properties call the identical way.
        load_defaults=lambda: uprops.resolve_class_defaults(cls, resolver=resolver),
        load_members=lambda p: _struct_members_via(resolver, p),
        load_enums=lambda p: _enum_names_via(resolver, p),
    )
```

Note the two ported helpers `raise SchemaError` on an unresolvable package — that's correct and
matches the CLI's own behavior exactly; Task 4 is responsible for catching it (via `ctx.enums()`'s
built-in guard for enums, and an explicit `try/except` for struct members, since `ClassCtx.members()`
has no built-in guard — see Task 4's Global-Constraints note).

- [ ] **Step 1: Write the failing test**

```python
# uedcli/tests/test_effective_props.py
from uedcli.effective_props import ScalarProp, EnumProp, StructProp, ArrayProp

def test_scalar_prop_shape():
    p = ScalarProp(name="LightRadius", category="Lighting", kind="byte",
                   stored_value="8", default_value="0")
    assert p.kind == "byte"
    assert p.stored_value == "8"

def test_struct_prop_has_no_stored_value_field():
    p = StructProp(name="Rotation", category="Movement", members=[])
    assert not hasattr(p, "stored_value")   # struct variant genuinely has no such field
```

- [ ] **Step 2: Run test to verify it fails**

`bin/test -k effective_props -v` — Expected: FAIL, `ModuleNotFoundError: No module named
'uedcli.effective_props'`.

- [ ] **Step 3: Implement**

Create `uedcli/effective_props.py` with exactly the dataclasses shown above. Add `_struct_members_via`/
`_enum_names_via`/`_class_ctx_for` to `scene.py`, exactly as shown (do not re-derive — these are
verified ports of the real `cli/resources.py` bodies, not sketches).

- [ ] **Step 4: Run test to verify it passes**

`bin/test -k effective_props -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/effective_props.py uedcli/serve/scene.py uedcli/tests/test_effective_props.py
git commit -m "Add EffectiveProp dataclass hierarchy + ClassCtx-from-index adapter"
```

---

### Task 3: `Location`/`MainScale`/`PostScale` resolution via `TYPED_FIELDS`, per-member explicit

**COMPLETE — signature revised during the fix loop, real code is authoritative over this section's
snippets below.** The implementer's own report surfaced a genuine plan defect this section's shown
code didn't handle: `default_value` for an unstated member must be the TRUE class default (per
`t3d.md`'s live-verified `DeusEx.Rat` example), not `actor.location`'s own parse-time zero-fill.
Controller ruling (ledgered in `.superpowers/sdd/plan/progress.md`): thread a `ctx:
propedit.ClassCtx` parameter through, resolving each member's default via `ctx.defaults().get((...,
0))` + `propedit.structtext.split_struct_text` instead of the actor's own value. Real, final
signature: `_resolve_typed_fields(actor, ctx, ctx_by_type)` (this section's snippets below still
show the pre-fix 2-arg form — kept as historical record of the original design, not re-edited
line-by-line; the committed code and its tests are the source of truth). Task 4's call site below
is updated to the real signature.

**Files:**
- Modify: `uedcli/effective_props.py` (add `_resolve_typed_fields`)
- Test: `uedcli/tests/test_effective_props.py`

**Interfaces:**
- Consumes: `propedit.TYPED_FIELDS` (existing, `propedit/fields.py`), `model.Actor.location`/
  `.location_text`/`.main_scale`/`.main_scale_text`/`.post_scale`/`.post_scale_text` (Task 1 added
  the two new ones), `normalize._stated_axes` (existing — `uedcli/normalize.py:366`),
  `typedprops.ESHEER_AXIS` (existing, `uedcli/typedprops.py`).
- Produces: `_resolve_typed_fields(actor, ctx_by_type: dict[str, list[str]]) -> list[EffectiveProp]`
  — exactly 3 entries (`Location`, `MainScale`, `PostScale`), each a `StructProp`. **Takes and
  mutates `ctx_by_type`** — it always builds a `SheerAxis` `EnumProp` (`enum_type =
  "typedprops.ESheerAxis"`), and since this is a fixed Python constant, not a schema-resolved value,
  it must seed `ctx_by_type["typedprops.ESheerAxis"] = list(typedprops.ESHEER_AXIS)` itself rather
  than relying on Task 5's enum collector to have populated it — nothing else ever will, since this
  enum never goes through `ctx.enums()`. Task 4 threads the SAME dict through the generic schema
  walk, so both halves of `resolve_actor_props` share one accumulator (see Task 4).

**Design point from the spec, restated precisely for the implementer:** `normalize._stated_axes`
only exists for `Location` (takes an `Actor`, reads `.location`/`.location_text`). There is no
`_stated_axes`-equivalent for `MainScale`/`PostScale` today — write one, following `_stated_axes`'s
OWN exact algorithm (self-invalidating: trust `*_text` only while it still parses back to the
current typed value; on mismatch, treat as if every member were stated) rather than a new algorithm.

- [ ] **Step 1: Write the failing test**

```python
def test_location_partial_axis_marks_only_stated_explicit():
    actor = make_actor(location=(100, 0, 0), location_text="(X=100.000000)")
    fields = _resolve_typed_fields(actor, {})
    loc = next(f for f in fields if f.name == "Location")
    x, y, z = loc.members
    assert x.stored_value == "100.000000" and x.default_value is not None
    assert y.stored_value is None   # NOT explicit -- omitted from the stated text
    assert z.stored_value is None

def test_location_text_self_invalidated_by_mutation_marks_all_explicit():
    # location_text says (X=100) but .location no longer round-trips to it (a move happened) --
    # normalize._stated_axes's own self-invalidation rule: all three axes read as stated.
    actor = make_actor(location=(200, 0, 0), location_text="(X=100.000000)")
    fields = _resolve_typed_fields(actor, {})
    loc = next(f for f in fields if f.name == "Location")
    assert all(m.stored_value is not None for m in loc.members)

def test_sheeraxis_enum_type_self_seeded_into_ctx_by_type():
    ctx_by_type: dict = {}
    _resolve_typed_fields(make_actor(location=(0, 0, 0)), ctx_by_type)
    assert ctx_by_type["typedprops.ESheerAxis"] == list(ESHEER_AXIS)
```

(`make_actor` — check `uedcli/tests/test_normalize.py`'s existing helper for constructing a minimal
`Actor` with `location`/`location_text` set; reuse it, don't write a new one.)

- [ ] **Step 2: Run test to verify it fails**

`bin/test -k typed_fields -v` — Expected: FAIL, `ImportError` (`_resolve_typed_fields` doesn't
exist yet).

- [ ] **Step 3: Implement**

```python
def _stated_scale_members(text: str | None, current) -> str:
    """MainScale/PostScale's own `_stated_axes` -- same self-invalidation rule as Location's, ported
    to FScale's three real members (Scale, SheerRate, SheerAxis) instead of X/Y/Z. Returns a string
    of stated member tags, e.g. 'ScaleSheerRate' -- or the empty string when nothing was stated."""
    from .transform import IDENTITY, parse_fscale
    if text is not None and parse_fscale(text) == (current or IDENTITY):
        stated = []
        if "Scale" in text:
            stated.append("Scale")
        if "SheerRate" in text:
            stated.append("SheerRate")
        if "SheerAxis" in text:
            stated.append("SheerAxis")
        return "".join(stated)
    return "ScaleSheerRateSheerAxis"   # self-invalidated: every member reads as stated


def _resolve_typed_fields(actor, ctx_by_type: dict[str, list[str]]) -> list[EffectiveProp]:
    from . import propedit
    from .normalize import _stated_axes
    from .typedprops import ESHEER_AXIS

    ctx_by_type.setdefault("typedprops.ESheerAxis", list(ESHEER_AXIS))

    tf_location = propedit.TYPED_FIELDS["location"]
    stated = _stated_axes(actor)
    loc_members = []
    for ax in "XYZ":
        _, text = tf_location.get(_axis_token(ax), actor.location)
        loc_members.append(ScalarProp(
            name=ax, category="Movement", kind="float",
            stored_value=text if ax in stated else None,
            default_value=text))
    location_prop = StructProp(name="Location", category="Movement", members=loc_members)

    scale_props = []
    for key, attr, text_attr, category in (
        ("mainscale", "main_scale", "main_scale_text", "Brush"),
        ("postscale", "post_scale", "post_scale_text", "Brush"),
    ):
        tf = propedit.TYPED_FIELDS[key]
        current = getattr(actor, attr)
        stated_members = _stated_scale_members(getattr(actor, text_attr), current)
        scale_members = []
        for ax in "XYZ":
            _, text = tf.get(_scale_component_token(ax), current)
            scale_members.append(ScalarProp(
                name=ax, category=category, kind="float",
                stored_value=text if "Scale" in stated_members else None,
                default_value=text))
        _, rate_text = tf.get(_sheerrate_token(), current)
        _, axis_text = tf.get(_sheeraxis_token(), current)
        scale_props.append(StructProp(
            name=tf.name, category=category,
            members=[
                StructProp(name="Scale", category=category, members=scale_members),
                ScalarProp(name="SheerRate", category=category, kind="float",
                          stored_value=rate_text if "SheerRate" in stated_members else None,
                          default_value=rate_text),
                EnumProp(name="SheerAxis", category=category, enum_type="typedprops.ESheerAxis",
                        stored_value=axis_text if "SheerAxis" in stated_members else None,
                        default_value=axis_text),
            ]))
    return [location_prop, *scale_props]
```

`_axis_token`/`_scale_component_token`/`_sheerrate_token`/`_sheeraxis_token` — tiny `PropToken`
constructors matching what `TypedField.get`/`ScaleField.get` expect as their first argument.
`propedit/tokens.py::PropToken`/`fields.py`'s `_axis_of`/`_member` methods only inspect `tok.segs`
(a tuple of path segments) — build the smallest `PropToken` that satisfies that, e.g.
`PropToken(raw=ax, base="Location", segs=(ax,), value=None)` for `_axis_token`; confirm the exact
`PropToken` field names against `propedit/tokens.py` before writing these (a dataclass with 4-5
fields, not guessed).

- [ ] **Step 4: Run test to verify it passes**

`bin/test -k typed_fields -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/effective_props.py uedcli/tests/test_effective_props.py
git commit -m "Resolve Location/MainScale/PostScale via TYPED_FIELDS with per-member explicit"
```

---

### Task 4: generic schema walk (scalar/enum/struct/array), wired into `_build_actors`

**Files:**
- Modify: `uedcli/effective_props.py` (add `resolve_actor_props`)
- Modify: `uedcli/serve/scene.py` (`SceneActor.props` type, `_build_actors`, delete
  `_actor_categories`/`_with_synthetic_location`)
- Test: `uedcli/tests/test_effective_props.py`, `uedcli/tests/test_serve_scene.py`

**Interfaces:**
- Consumes: Task 2's dataclasses + `_class_ctx_for`, Task 3's `_resolve_typed_fields`,
  `propedit.edit.effective_value` (existing), `propedit.base.HARD_REJECT`/`normalize.is_computed_key`
  (existing), `ClassCtx.members(prop)`/`.enums(prop)` (existing PUBLIC accessors — use these, NOT
  `.load_members`/`.load_enums` directly; `.enums()` alone catches `SchemaError`, `.members()` does
  not, this function must guard it).
- Produces: `resolve_actor_props(actor, ctx: propedit.ClassCtx) -> tuple[list[EffectiveProp],
  dict[str, list[str]], str | None]` — the complete per-actor tree, the `ctx_by_type` enum
  accumulator (Task 5 consumes the second element across all actors; returning it here, rather than
  a second full schema walk later, avoids re-resolving every enum a second time), and a `note`
  (third element, `None` when nothing went wrong) for the SAME class-unresolvable degrade convention
  `_is_hidden_ed`/`_actor_radii` already use elsewhere in `scene.py` — see the "class-unresolvable"
  fix note in Step 3 below (added after `_resolve_typed_fields` started needing `ctx.defaults()`,
  which — like `ctx.schema()` on the very next line — can raise `SchemaError` for an actor whose
  class can't be resolved at all; the ORIGINAL per-property `try/except` inside the loop only ever
  covered a single unresolvable MEMBER, never the whole-class case). `TYPED_FIELDS`-first then
  schema-resolved (mirrors `effective_all_lines`'s own order), filtered, foreign-prop-omitting (spec
  point 3), `ArrayProperty`/`PointerProperty`-excluding (spec's explicit exclusion — enforced HERE,
  in the filter, not as a downstream assertion). `scene.py`'s `_build_actors` calls this once per
  actor instead of `_actor_categories`+`_with_synthetic_location`.

- [ ] **Step 1: Write the failing test**

```python
def test_resolve_actor_props_omits_unknown_stored_prop():
    actor = make_actor(props=[("TotallyFakeProp", "1")])
    ctx = fake_ctx(schema={})   # empty schema -- TotallyFakeProp isn't declared anywhere
    result, _, note = resolve_actor_props(actor, ctx)
    assert not any(p.name == "TotallyFakeProp" for p in result)
    assert note is None

def test_resolve_actor_props_excludes_array_and_pointer_kinds():
    actor = make_actor(props=[])
    ctx = fake_ctx(schema={"editpackages": array_property_prop(),
                           "variablemap": pointer_property_prop()})
    result, _, note = resolve_actor_props(actor, ctx)   # must NOT raise -- this is the crash this test pins
    assert result == []
    assert note is None

def test_resolve_actor_props_struct_member_precise():
    actor = make_actor(props=[("Rotation", "(Yaw=1234)")])
    ctx = fake_ctx(schema={"rotation": rotation_prop()},
                   defaults={("pitch", 0): "4096", ("yaw", 0): "0", ("roll", 0): "3072"})
    result, _, note = resolve_actor_props(actor, ctx)
    rot = next(p for p in result if p.name == "Rotation")
    yaw = next(m for m in rot.members if m.name == "Yaw")
    pitch = next(m for m in rot.members if m.name == "Pitch")
    assert yaw.stored_value == "1234"
    assert pitch.stored_value is None and pitch.default_value == "4096"   # NOT zero
    assert note is None

def test_resolve_actor_props_degrades_on_unresolvable_struct_member():
    # a StructProperty whose MEMBERS can't be resolved (cross-package miss) must NOT crash the
    # whole request -- degrades to an empty members list + a stderr note, same convention as
    # _is_hidden_ed/_actor_radii elsewhere in this file. This is a per-PROPERTY failure (the class
    # itself resolves fine) -- distinct from the next test, a per-CLASS failure.
    actor = make_actor(props=[])
    ctx = fake_ctx(schema={"badstruct": unresolvable_struct_prop()})
    result, _, note = resolve_actor_props(actor, ctx)
    bad = next(p for p in result if p.name == "BadStruct")
    assert bad.members == []
    assert note is None   # a per-property degrade, not per-class -- no note at this level

def test_resolve_actor_props_degrades_on_unresolvable_class():
    # the CLASS itself can't be resolved at all (ctx.schema() or ctx.defaults() raises
    # SchemaError -- _resolve_typed_fields calls ctx.defaults() unconditionally since the round-1
    # fix, and the schema walk's own `for prop in ctx.schema().values()` can raise identically).
    # Must degrade to (empty props, empty enum dict, a real note) -- never crash the whole payload,
    # matching _is_hidden_ed's exact convention (a caught SchemaError becomes a safe default +
    # a stderr note, never propagates).
    actor = make_actor(props=[], cls="DeusEx.SomeUnresolvableClass")
    ctx = fake_ctx(schema_raises=True)   # .schema() (and/or .defaults()) raises SchemaError
    result, enums, note = resolve_actor_props(actor, ctx)
    assert result == []
    assert enums == {}
    assert note is not None and "DeusEx.SomeUnresolvableClass" in note
```

(`fake_ctx` — a small test double implementing `propedit.ClassCtx`'s interface with canned
schema/defaults dicts, and `.members()`/`.enums()` that raise `SchemaError` for the "unresolvable"
fixtures. No existing test in this codebase constructs a `ClassCtx` today — `test_propedit.py`
exercises token parsing / struct-text splitting / `TypedField` in isolation, never the full
`ClassCtx`/`effective_value` path — so there is no prior pattern to copy; build this fake directly
from `propedit/base.py`'s `ClassCtx` dataclass shape, already read in full this session.
`array_property_prop()`/`pointer_property_prop()`/`rotation_prop()`/`unresolvable_struct_prop()` —
minimal `uprops.Prop` fixtures, one field each set to the relevant `kind`. `fake_ctx(schema_raises=
True)` — a variant whose `.schema()` AND `.defaults()` both raise `SchemaError` immediately, for the
whole-class-unresolvable test below.)

- [ ] **Step 2: Run test to verify it fails**

`bin/test -k resolve_actor_props -v` — Expected: FAIL, `ImportError`.

- [ ] **Step 3: Implement**

**Class-unresolvable degrade, added here (not in Task 3) because it wasn't visible until Task 3's
fix round made `_resolve_typed_fields` call `ctx.defaults()` unconditionally** — `ctx.schema()` (the
very next line after) has the identical exposure and always did; both needed the same guard, so both
are covered by one outer `try/except`, matching `_is_hidden_ed`'s real degrade-with-note shape
(`uedcli/serve/scene.py`'s existing function, already read this session — `except uprops.SchemaError
as e: return False, (f"actor {actor.name!r}: schema unavailable ({actor.cls}) — ... ({e})")`):

```python
def resolve_actor_props(actor, ctx) -> tuple[list[EffectiveProp], dict[str, list[str]], str | None]:
    from . import propedit
    from .normalize import is_computed_key
    from .uprops import SchemaError

    try:
        out, ctx_by_type = _resolve_actor_props_unsafe(actor, ctx)
        return out, ctx_by_type, None
    except SchemaError as e:
        return [], {}, (f"actor {actor.name!r}: schema unavailable ({actor.cls}) — cannot resolve "
                        f"effective props ({e})")


def _resolve_actor_props_unsafe(actor, ctx) -> tuple[list[EffectiveProp], dict[str, list[str]]]:
    """The real work, unguarded -- resolve_actor_props wraps the WHOLE thing in one try/except so
    a class-level failure (ctx.schema() or ctx.defaults(), both reachable per-actor, not just
    per-property) degrades exactly once, the same way _is_hidden_ed/_actor_radii already do
    elsewhere in this file. A per-PROPERTY failure (one struct member unresolvable, the class
    itself fine) still degrades independently inside the loop below -- that inner try/except is
    unchanged from the pre-fix design and stays; this outer one is new."""
    ctx_by_type: dict[str, list[str]] = {}
    out: list[EffectiveProp] = _resolve_typed_fields(actor, ctx, ctx_by_type)
    stored = {k.casefold(): v for k, v in actor.props}
    for prop in ctx.schema().values():
        base = prop.name.casefold()
        if (base in propedit.HARD_REJECT or base in propedit.TYPED_FIELDS
                or is_computed_key(base) or prop.kind in ("ArrayProperty", "PointerProperty")):
            continue
        try:
            out.append(_resolve_one(prop, stored, ctx, category=_category_for(prop),
                                    ctx_by_type=ctx_by_type))
        except SchemaError:
            # unresolvable struct member / cross-package miss: degrade, never 500 the whole payload
            out.append(StructProp(name=prop.name, category=_category_for(prop), members=[]))
    return out, ctx_by_type


def _resolve_one(prop, stored, ctx, *, category: str, ctx_by_type: dict) -> EffectiveProp:
    if prop.kind == "StructProperty":
        members = [_resolve_one(m, _member_stored(stored, prop.name), ctx,
                                category=category, ctx_by_type=ctx_by_type)
                  for m in ctx.members(prop)]
        return StructProp(name=prop.name, category=category, members=members)
    if prop.array_dim > 1:
        elements = [_resolve_array_element(prop, i, stored, ctx, category, ctx_by_type)
                   for i in range(prop.array_dim)]
        return ArrayProp(name=prop.name, category=category,
                         element_kind=_scalar_kind(prop), elements=elements)
    if prop.kind == "ByteProperty" and ctx.enums(prop):
        enum_type = f"{prop.owner}.{prop.type_name}"
        names = list(ctx.enums(prop))
        ctx_by_type.setdefault(enum_type, names)
        raw_stored = stored.get(prop.name.casefold())
        return EnumProp(name=prop.name, category=category, enum_type=enum_type,
                        stored_value=_canonicalize_enum_text(raw_stored, names),
                        default_value=_canonicalize_enum_text(_effective_default(prop, ctx), names))
    return ScalarProp(name=prop.name, category=category, kind=_scalar_kind(prop),
                      stored_value=stored.get(prop.name.casefold()),
                      default_value=_effective_default(prop, ctx))


def _canonicalize_enum_text(text: str | None, names: list[str]) -> str | None:
    """An ordinal string -> its NAME; an already-a-name string (or None) passes through unchanged.
    `propedit.edit.effective_value`'s own default/zero branches do NOT canonicalize (only its stored
    branch does, via `_canonicalize_enum`) -- this GUI-only helper applies the SAME conversion to
    both stored_value and default_value, so an EnumProp's two fields are always consistently
    NAME-form, never a mix. Mirrors propedit.edit._canonicalize_enum's own ordinal-detection rule
    exactly (isdigit check) rather than inventing a new one."""
    if text is None:
        return None
    if text.strip().isdigit():
        i = int(text.strip())
        if i < len(names):
            return names[i]
    return text
```

(`_member_stored`/`_resolve_array_element`/`_scalar_kind`/`_effective_default`/`_category_for` —
each a small, single-purpose helper; `_effective_default` calls `propedit.edit.effective_value` for
the "whole property, no member path" case — needs a `ResolvedPath`, not a bare `Prop`; construct one
the same way `effective_all_lines` does at `propedit/edit.py:372`
(`ResolvedPath(prop=prop, index=None, members=(), canonical=prop.name)`), exactly matching the
spec's "default_value = propedit.edit.effective_value's resolution for that key" line.
`_resolve_array_element` recurses through `_resolve_one` on the element's own `Prop` at each index,
same shape as the struct case.)

Wire into `scene.py`:

```python
# SceneActor.props: list[tuple[str, str]] -> list[EffectiveProp]
#
# `_build_actors` has NO existing notes-gathering mechanism today (confirm via
# `grep -n "notes" uedcli/serve/scene.py` before assuming otherwise) -- the ONLY precedent is
# `_resolve_hidden_ed`'s OWN separate `notes: list[str]`, in a DIFFERENT, earlier-called function.
# THIS task adds a genuinely new local `notes: list[str] = []` to `_build_actors` itself --
# declare it near `category_maps`'s own declaration (Task 5 will ALSO append `payload_enums`
# tracking next to it, reusing this same `notes` list, not re-declaring it).
#
# Replace:
#   props, categories = _with_synthetic_location(
#       list(actor.props), _actor_categories(actor.props, category_maps[cls]), loc)
# with:
props, actor_enum_types, note = effective_props.resolve_actor_props(actor, _class_ctx_for(cls, index))
if note:
    notes.append(note)
# actor_enum_types is unused by THIS task (Task 5 adds the accumulator that consumes it) -- don't
# let it trigger an unused-variable lint; either `_ = actor_enum_types` or leave it for Task 5 to
# wire immediately after (the two tasks touch adjacent lines; sequencing them back-to-back in one
# review pass is reasonable if that's how they land).
#
# After the for-loop, before `return actors` (today's plain `return actors` -- Task 5 changes this
# return's SHAPE to a tuple, this task only adds the print loop before whatever the return becomes):
for line in notes:
    print(line, file=sys.stderr)
```

Delete `_actor_categories`/`_with_synthetic_location`/`_class_category_map`'s use in `_build_actors`
(category resolution now happens per-prop inside `_resolve_one`'s `_category_for`, sourced the same
way `_class_category_map` did — `prop.category or _FALLBACK_CATEGORY` — just inline per property
instead of a separate pre-pass). **Also delete `SceneActor.categories: list[str]` itself** (the
dataclass field, `scene.py:240` — confirmed present today alongside `props`) — it's now redundant
with each `EffectiveProp.category`, and since `SceneActor` is `@dataclass(frozen=True, kw_only=True)`
with no default on that field, leaving it declared without a source to populate it from is a
`TypeError` on every `SceneActor(...)` construction, not a silent gap.

- [ ] **Step 4: Run test to verify it passes**

`bin/test -k "resolve_actor_props or serve_scene" -v` — Expected: PASS, including the
`excludes_array_and_pointer_kinds` and `degrades_on_unresolvable_struct_member` cases, which are the
two crash-prevention tests this task exists to pin. Also run the FULL non-integration
`uedcli/tests/test_serve_scene.py` once here (this task changes a widely-used function) per
`NATIVE-MATERIALIZE.md`'s own testing-discipline convention of never trusting only the new test.

- [ ] **Step 5: Commit**

```bash
git add uedcli/effective_props.py uedcli/serve/scene.py uedcli/tests/
git commit -m "Wire generic schema-walk EffectiveProp resolution into _build_actors"
```

---

### Task 5: `ScenePayload.enums`

**Files:**
- Modify: `uedcli/serve/scene.py` (`ScenePayload` dataclass, `_build_actors`, **both** of
  `_build_actors`'s two callers — `build_scene_payload` AND `build_wireframe_payload`, confirmed via
  `grep -n "_build_actors(" uedcli/serve/scene.py`: two call sites, `build_scene_payload` at line
  774 and `build_wireframe_payload` at line 807. `ScenePayload` is `@dataclass(frozen=True,
  kw_only=True)` with no default on any existing field, so `enums` becomes a REQUIRED kwarg at
  BOTH construction sites — missing it at either one is a `TypeError`, not a silent gap. An earlier
  draft of this task only updated `build_scene_payload`, which would have broken the cold-open /
  no-Rebuild-yet payload (`build_wireframe_payload`'s own docstring: "the cold-open... payload") —
  a real, reachable path, not an edge case.)
- Test: `uedcli/tests/test_serve_scene.py`

**Interfaces:**
- Consumes: Task 4's `resolve_actor_props` return shape — `tuple[list[EffectiveProp], dict[str,
  list[str]]]` — the SECOND element is already the fully-populated per-actor enum accumulator
  (including the `typedprops.ESheerAxis` self-seed from Task 3). No new schema walk needed here —
  this task is pure accumulation across actors.
- Produces: `ScenePayload.enums: dict[str, list[str]]`.

- [ ] **Step 1: Write the failing test**

```python
def test_build_scene_payload_collects_enum_types():
    payload = build_scene_payload(trunk_with_light_actor(), geometry, index, defaults)
    assert "Engine.Light.ELightType" in payload.enums
    assert payload.enums["Engine.Light.ELightType"][0] == "LT_None"   # ordinal 0 first

def test_build_scene_payload_collects_sheeraxis_even_with_no_brush():
    # Task 3 seeds this unconditionally -- confirm it survives all the way to the payload even for
    # a level with no brush actors at all (every actor still gets 3 typed-field entries resolved).
    payload = build_scene_payload(trunk_with_one_light_only(), geometry, index, defaults)
    assert "typedprops.ESheerAxis" in payload.enums
```

- [ ] **Step 2: Run test to verify it fails**

`bin/test -k collects_enum_types -v` — Expected: FAIL, `AttributeError`.

- [ ] **Step 3: Implement**

In `_build_actors`, accumulate each actor's `ctx_by_type` (Task 4's second return value) into one
payload-wide dict as actors are built, and return it as a second value:

```python
def _build_actors(trunk, hidden_ed, *, tex_offset, index, radii_map, arrow_map
                  ) -> tuple[list[SceneActor], dict[str, list[str]]]:
    ...
    payload_enums: dict[str, list[str]] = {}
    # `notes: list[str] = []` and the `if note: notes.append(note)` line already exist from Task 4
    # -- this task only adds `payload_enums` tracking alongside the existing `actor_enum_types`
    # Task 4 already unpacks per actor, and changes the function's RETURN shape to a tuple.
    for csg_rank, name in enumerate(level.order, start=1):
        ...
        payload_enums.update(actor_enum_types)   # same enum_type key -> same value list, safe to overwrite
        ...
    # the `for line in notes: print(...)` loop already exists from Task 4, unchanged
    return actors, payload_enums
```

Add `enums: dict[str, list[str]]` to `ScenePayload`. Update **BOTH** call sites (this task's whole
point — see the Files note above):

```python
# build_scene_payload:
actors, payload_enums = _build_actors(trunk, hidden_ed, tex_offset=..., index=index,
                                      radii_map=radii_map, arrow_map=arrow_map)
...
return ScenePayload(polys=polys, actors=actors, enums=payload_enums, ...)  # existing other fields unchanged

# build_wireframe_payload (uedcli/serve/scene.py:807, was: `actors = _build_actors(...)`):
actors, payload_enums = _build_actors(trunk, hidden_ed, tex_offset=0, index=index,
                                      radii_map=radii_map, arrow_map=arrow_map)
...
return ScenePayload(polys=polys, actors=actors, enums=payload_enums)
```

- [ ] **Step 4: Run test to verify it passes**

`bin/test -k collects_enum_types -v` — Expected: PASS. Also add and run a test that calls
`build_wireframe_payload` directly (the cold-open path) and asserts `.enums` is populated there too
— the two-caller gap above was found in review precisely because no such test existed.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/scene.py uedcli/tests/test_serve_scene.py
git commit -m "Add ScenePayload.enums, accumulated while resolving actor props"
```

---

### Task 6: `ScenePoly.normal`/`.area`

**Files:**
- Modify: `uedcli/serve/scene.py` (`ScenePoly` dataclass; the 3 `ScenePoly(...)` construction sites
  — currently `scene.py:658`, `:679`, `:763`; confirm with `grep -n "ScenePoly(" uedcli/serve/
  scene.py` before editing, since earlier tasks in this plan may shift these line numbers)
- Test: `uedcli/tests/test_serve_scene.py`

**Interfaces:**
- Consumes: `ScenePoly.tu`/`.tv` (existing fields, already on every construction site), `ScenePoly.verts`.
- Produces: `ScenePoly.normal: list[float]`, `ScenePoly.area: float`.

- [ ] **Step 1: Write the failing test**

```python
def test_scenepoly_normal_and_area_for_unit_square():
    poly = build_test_poly(verts=[0,0,0, 1,0,0, 1,1,0, 0,1,0], tu=[1,0,0], tv=[0,1,0])
    assert poly.normal == pytest.approx([0, 0, 1])
    assert poly.area == pytest.approx(1.0)
```

- [ ] **Step 2: Run test to verify it fails**

`bin/test -k scenepoly_normal -v` — Expected: FAIL, `TypeError: unexpected keyword argument 'normal'`.

- [ ] **Step 3: Implement**

```python
def _poly_normal(tu: list[float], tv: list[float]) -> list[float]:
    ax, ay, az = tu
    bx, by, bz = tv
    cx, cy, cz = ay*bz - az*by, az*bx - ax*bz, ax*by - ay*bx
    length = (cx*cx + cy*cy + cz*cz) ** 0.5
    return [cx/length, cy/length, cz/length] if length else [0.0, 0.0, 0.0]


def _poly_area(verts: list[float]) -> float:
    """Shoelace sum, 3D via the cross-product-of-consecutive-edges form (planar polygon assumed --
    a CSG-solved ScenePoly always is)."""
    n = len(verts) // 3
    if n < 3:
        return 0.0
    ox, oy, oz = verts[0], verts[1], verts[2]
    total = [0.0, 0.0, 0.0]
    for i in range(1, n - 1):
        ax, ay, az = verts[i*3] - ox, verts[i*3+1] - oy, verts[i*3+2] - oz
        bx, by, bz = verts[(i+1)*3] - ox, verts[(i+1)*3+1] - oy, verts[(i+1)*3+2] - oz
        total[0] += ay*bz - az*by
        total[1] += az*bx - ax*bz
        total[2] += ax*by - ay*bx
    return 0.5 * (total[0]**2 + total[1]**2 + total[2]**2) ** 0.5
```

Add `normal=_poly_normal(tu, tv), area=_poly_area(verts)` at every `ScenePoly(...)` construction
site (3 sites, re-confirmed via `grep` immediately above — not 4; an earlier draft of this plan
miscounted).

- [ ] **Step 4: Run test to verify it passes**

`bin/test -k scenepoly_normal -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/scene.py uedcli/tests/test_serve_scene.py
git commit -m "Add ScenePoly.normal/.area, computed server-side"
```

---

### Task 7: `AtlasRect.name` — real texture group identity

**Files:**
- Modify: `uedcli/preview_native.py` (`_TextureTable.index_for`, `_TextureTable.__init__`)
- Modify: `uedcli/serve/textures.py` (`AtlasRect`/`build_atlas` — check whether `AtlasRect` is
  currently a dataclass here or a plain dict per the manifest's `{tex_index: {x,y,w,h}}` shape; if
  it's still a dict, this task also promotes it to a named shape matching `web/src/api.ts`'s
  existing `AtlasRect` TS interface)
- Test: `uedcli/tests/test_preview_native.py` (or wherever `_TextureTable` is already tested),
  `uedcli/tests/test_serve_textures.py`

**Interfaces:**
- Consumes: `TextureResolver.package_for_ref(ref: str) -> tuple[Package, int] | None` (existing,
  `uedcli/utexture.py:803` — purpose-built for exactly this: its own docstring says "the seam
  `show`/`list --json` use to read Layer-2 facts (group needs the export, which `DecodedTexture`
  does not carry)"), `utexture.group_of_export` (existing, `uedcli/utexture.py:676`).
- Produces: `_TextureTable.group_for(idx: int) -> str | None`, threaded into `build_atlas`'s manifest
  as each rect's `name`.

- [ ] **Step 1: Write the failing test**

```python
def test_texture_table_records_real_group_name():
    table = _TextureTable(real_resolver_for_coretexmetal())
    idx = table.index_for("CoreTexMetal.Area51Wall_A")
    assert table.group_for(idx) == "CoreTexMetal.Metal.Area51Wall_A"

def test_texture_table_group_none_when_export_has_none():
    table = _TextureTable(real_resolver_for_ungrouped_texture())
    idx = table.index_for(...)
    assert table.group_for(idx) is None or table.group_for(idx) == "Package.Name"  # per spec, ungrouped case
```

(Use the same `Area51Wall_A`/`CoreTexMetal` example `dev/docs/unrealed/quirks.md`'s "T3D format"
section already cites as a live-confirmed grouped texture — don't invent a new fixture texture.)

- [ ] **Step 2: Run test to verify it fails**

`bin/test -k texture_table_records_real_group -v` — Expected: FAIL, `AttributeError: 'TextureTable'
object has no attribute 'group_for'`.

- [ ] **Step 3: Implement**

In `_TextureTable.__init__`, add `self._group: list[str | None] = []` alongside the existing
`self.bmasked`. `index_for`'s real current body (`uedcli/preview_native.py:546`, re-read in full
during plan review — no `name` local exists in it, only `ref`/`key`/`got`/`idx`). Note carefully:
`utexture.py` defines its OWN `Package` class (`utexture.py:90`), distinct from `upackage.Package` —
on THIS local type, **`.name` is a METHOD** (`name(self, idx: int) -> str | None`, a name-table
lookup by index — confirmed via its own doc comment: "Named `stem`, not `name`, to not collide with
the `name()` accessor below"), and **the package's own name string is `.stem: str | None`**, not
`.name`. An earlier draft of this task got this backwards (`f"{pkg.name}..."` treating `.name` as a
string) — that would have called an unbound method into an f-string and produced garbage, not a
crash necessarily, but silently wrong text. The export's own bare name is read the same way
`utexture.py`'s own `TextureResolver.texture_refs` already does it —
`pkg.name(pkg.exports[i]["nm"])` — never parsed out of `ref`'s text, which could differ in case from
the canonical export name. After `got = resolve_or_procedural_red(self._resolver, ref)` finds a real
(non-error) result, call `self._resolver.package_for_ref(ref)` — the SAME resolver, a SECOND, cheap,
purpose-built lookup (not a re-resolve of the whole texture, just the `(package, export_index)` pair
— `package_for_ref` reuses `_locate_texture`'s own cache, so this is not an expensive duplicate
decode):

```python
        located = self._resolver.package_for_ref(ref)
        if located is not None:
            pkg, export_index = located
            export_name = pkg.name(pkg.exports[export_index]["nm"]) or ""
            group = group_of_export(pkg, export_index)
            pkg_name = pkg.stem or ""   # display convenience -- may not always match the resolver's
                                        # own canonical case-preserved spelling (_stem_spelling,
                                        # a private TextureResolver attribute); acceptable here since
                                        # this is Inspector display text, not a round-trip identity
            self._group.append(f"{pkg_name}.{group}.{export_name}" if group
                               else f"{pkg_name}.{export_name}")
        else:
            self._group.append(None)
```

Add `group_for(self, idx: int) -> str | None` returning `self._group[idx]` (bounds-checked, `None`
for an out-of-range index — `index_for_decoded` never appends to `self._group` at all, so a
mesh-skin index's slot is simply absent, matching the spec's mesh-skin-excluded case exactly).

Thread into `serve/textures.py::build_atlas`: it currently takes `texture_table:
list[tuple[int,int,bytes,bytes]]` with no group info — add a parallel `groups: list[str | None]`
parameter. Update the `/atlas` route (`serve/app.py`) to pass
`[texture_table_obj.group_for(i) for i in range(len(texture_table_obj.table))]` alongside the
existing raw-tuple `texture_table` it already constructs — confirm the `_TextureTable` OBJECT
(not just its already-flattened `.table`) is still in scope at the route's call site; if it's been
discarded by the time `build_atlas` is called, capture `groups` earlier, right where `texture_table`
itself is currently built.

- [ ] **Step 4: Run test to verify it passes**

`bin/test -k "texture_table_records_real_group or serve_textures" -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/preview_native.py uedcli/serve/textures.py uedcli/serve/app.py uedcli/tests/
git commit -m "Thread real texture group identity into the /atlas manifest"
```

---

### Task 8: Frontend types (`web/src/api.ts`)

**Files:**
- Modify: `web/src/api.ts`
- Test: none needed (pure type declarations — TypeScript compilation itself is the check: `tsc -b`)

**Interfaces:**
- Produces: `EffectiveProp` (TS discriminated union, exactly the spec's shape — copy it verbatim
  from `spec.md`'s Design section, it's already the final agreed type), `ScenePayload.enums:
  Record<string, string[]>`, `AtlasRect.name: string | null`, `ScenePoly.normal: [number,number,number]`,
  `ScenePoly.area: number`, `SceneActor.props: EffectiveProp[]` (was `[string,string][]` +
  `.categories: string[]` — both fields removed, replaced by this one). NOTE (corrected from an
  earlier draft of this plan): a backend-side fix in Task 4 means `EnumProp.stored_value`/
  `.default_value` are ALWAYS canonical enum NAME text, never a bare ordinal — the frontend never
  needs to index into `ScenePayload.enums[enum_type]` for DISPLAY (only a future editing dropdown
  would). Don't design Task 10's enum rendering around an ordinal lookup.

- [ ] **Step 1: N/A (no failing-test step for pure type changes)** — go straight to implementation;
  Step 2 below is the verification.

- [ ] **Step 2: Implement**

Add the `EffectiveProp` union and `EffectivePropBase` interface exactly as in `spec.md`'s Design
section (copy verbatim — it's the reviewed, final type). Update `SceneActor`: remove `props:
[string, string][]` and `categories: string[]`, add `props: EffectiveProp[]`. Update `ScenePoly`:
add `normal: [number, number, number]` and `area: number`. Update `AtlasRect`: add `name: string |
null`. Update `ScenePayload`: add `enums: Record<string, string[]>`.

- [ ] **Step 3: Run the TypeScript compiler to verify**

`cd web && npx tsc -b` — Expected: FAILS at every call site that constructed the old `props`/
`categories` shape or read `SceneActor.categories` (`Inspector.tsx`, `groupByCategory.ts`, and any
test file) — this is the correct, expected failure; Tasks 9-10c fix them. Confirm the failures are
ONLY in those files, not elsewhere (a stray failure elsewhere means a type was defined wrong).

- [ ] **Step 4: Commit**

```bash
git add web/src/api.ts
git commit -m "Add EffectiveProp discriminated union + related type changes to api.ts"
```
(This commit will not build standalone — the frontend is broken until Tasks 9-10c land. Acceptable
here since Tasks 8-10c are one contiguous frontend change; do not push/merge this commit in isolation.)

---

### Task 9: `web/src/panels/effectiveProps.ts` — pure frontend helpers

**Files:**
- Create: `web/src/panels/effectiveProps.ts`
- Test: `web/src/panels/effectiveProps.test.ts`

**Interfaces:**
- Consumes: `EffectiveProp` (Task 8).
- Produces: `shownValue(p: EffectiveProp): string | null` (returns `null` for struct/array — no
  top-level text), `isExplicit(p: EffectiveProp): boolean` (recurses into `members`/`elements` for
  struct/array — a container is "explicit" if ANY descendant is), `filterOverridesOnly(props:
  EffectiveProp[]): EffectiveProp[]`, `searchMatch(p: EffectiveProp, query: string): boolean`
  (own-name-only per the spec's resolved search rule — NOT recursive into descendants).

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect } from 'vitest'
import { shownValue, isExplicit, searchMatch } from './effectiveProps'

describe('shownValue', () => {
  it('returns stored_value when present', () => {
    expect(shownValue({ kind: 'float', name: 'X', category: 'Movement',
                        stored_value: '5', default_value: '0' })).toBe('5')
  })
  it('falls back to default_value when stored_value is null', () => {
    expect(shownValue({ kind: 'float', name: 'X', category: 'Movement',
                        stored_value: null, default_value: '0' })).toBe('0')
  })
  it('returns null for a struct (no top-level text)', () => {
    expect(shownValue({ kind: 'struct', name: 'Rotation', category: 'Movement', members: [] }))
      .toBeNull()
  })
  it('an enum shown value is already a canonical name, no ordinal lookup needed', () => {
    expect(shownValue({ kind: 'enum', name: 'LightType', category: 'Lighting',
                        enum_type: 'Engine.Light.ELightType',
                        stored_value: 'LT_Steady', default_value: 'LT_None' })).toBe('LT_Steady')
  })
})

describe('searchMatch', () => {
  it('matches only the own name, never a descendant', () => {
    const rot = { kind: 'struct' as const, name: 'Rotation', category: 'Movement',
                  members: [{ kind: 'float' as const, name: 'Yaw', category: 'Movement',
                             stored_value: '100', default_value: '0' }] }
    expect(searchMatch(rot, 'yaw')).toBe(false)   // Yaw is a MEMBER's name, not Rotation's own
    expect(searchMatch(rot, 'rot')).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

`cd web && npx vitest run effectiveProps` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

```typescript
import type { EffectiveProp } from '../api'

export function shownValue(p: EffectiveProp): string | null {
  if (p.kind === 'struct' || p.kind === 'array') return null
  return p.stored_value ?? p.default_value
}

export function isExplicit(p: EffectiveProp): boolean {
  if (p.kind === 'struct') return p.members.some(isExplicit)
  if (p.kind === 'array') return p.elements.some(isExplicit)
  return p.stored_value !== null
}

export function searchMatch(p: EffectiveProp, query: string): boolean {
  return p.name.toLowerCase().includes(query.toLowerCase())
}

export function filterOverridesOnly(props: EffectiveProp[]): EffectiveProp[] {
  return props.filter(isExplicit)
}
```

- [ ] **Step 4: Run test to verify it passes**

`cd web && npx vitest run effectiveProps` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/panels/effectiveProps.ts web/src/panels/effectiveProps.test.ts
git commit -m "Add pure EffectiveProp frontend helpers"
```

---

### Task 10a: `Inspector.tsx` — search box + overrides/show-all toggle

**Files:**
- Modify: `web/src/panels/Inspector.tsx`
- Modify: `web/src/panels/groupByCategory.ts` (input type: `(props: EffectiveProp[]) => Map<string,
  EffectiveProp[]>`, replacing the old `(props: [string,string][], categories: string[])` — group by
  each `EffectiveProp.category` directly)
- Test: `web/src/panels/Inspector.test.tsx`, `web/src/panels/groupByCategory.test.ts`

**Interfaces:**
- Consumes: Task 8's types, Task 9's `searchMatch`/`filterOverridesOnly`.
- Produces: search + toggle wired into `ActorSection`; struct/array/typed rendering (Task 10b) and
  Folder/Labels (Task 10c) build on top of this in later, separate commits.

- [ ] **Step 1: Write the failing tests**

```typescript
it('filters props by name substring', () => {
  const actor = makeActorWith(effectiveProps([
    { kind: 'float', name: 'LightRadius', category: 'Lighting', stored_value: '8', default_value: '0' },
    { kind: 'string', name: 'Tag', category: 'Object', stored_value: null, default_value: '' },
  ]))
  render(<Inspector selected={[actor]} enums={{}} />)
  fireEvent.change(screen.getByPlaceholderText('Search properties'), { target: { value: 'light' } })
  expect(screen.getByText('LightRadius')).toBeInTheDocument()
  expect(screen.queryByText('Tag')).not.toBeInTheDocument()
})

it('overrides-only is the default; show-all reveals a defaulted row, tagged', () => {
  const actor = makeActorWith(effectiveProps([
    { kind: 'float', name: 'LightRadius', category: 'Lighting', stored_value: null, default_value: '0' },
  ]))
  render(<Inspector selected={[actor]} enums={{}} />)
  expect(screen.queryByText('LightRadius')).not.toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('Show all'))
  expect(screen.getByText('LightRadius')).toBeInTheDocument()
  expect(screen.getByText('LightRadius').closest('[data-default]')).not.toBeNull()
})
```

- [ ] **Step 2: Run, verify fail** — `cd web && npx vitest run Inspector` (other Inspector tests may
  already be failing from Task 8's type break — that's expected; only these two new cases matter
  for this task's own gate, but don't let unrelated pre-existing failures mask a real regression).

- [ ] **Step 3: Implement** the search box + toggle, using Task 9's `searchMatch`/
  `filterOverridesOnly`, and update `groupByCategory.ts`'s signature.

- [ ] **Step 4: Run, verify both new tests pass.**

- [ ] **Step 5: Commit**

```bash
git add web/src/panels/Inspector.tsx web/src/panels/groupByCategory.ts web/src/panels/*.test.ts*
git commit -m "Inspector: search box + overrides/show-all toggle"
```

---

### Task 10b: `Inspector.tsx` — struct/array expansion + typed display

**Files:**
- Modify: `web/src/panels/Inspector.tsx`
- Test: `web/src/panels/Inspector.test.tsx`

**Interfaces:**
- Consumes: Task 10a's filtered/grouped prop list.
- Produces: struct/array `<details>` rendering, bool checkbox, enum plain-text display (no lookup —
  see Task 8's corrected note; the backend already canonicalizes enum text to names).

- [ ] **Step 1: Write the failing tests**

```typescript
it('renders a struct as nested rows, one per member', () => {
  const actor = makeActorWith(effectiveProps([
    { kind: 'struct', name: 'Rotation', category: 'Movement', members: [
      { kind: 'int', name: 'Yaw', category: 'Movement', stored_value: '8192', default_value: '0' },
    ]},
  ]))
  render(<Inspector selected={[actor]} enums={{}} />)
  fireEvent.click(screen.getByText('Rotation'))   // expand
  expect(screen.getByText('Yaw')).toBeInTheDocument()
})

it('renders a static array as a summary row, expandable to elements', () => {
  const actor = makeActorWith(effectiveProps([
    { kind: 'array', name: 'MultiSkins', category: 'Display', element_kind: 'string',
      elements: [
        { kind: 'string', name: '0', category: 'Display', stored_value: 'A', default_value: '' },
        { kind: 'string', name: '1', category: 'Display', stored_value: null, default_value: '' },
      ]},
  ]))
  render(<Inspector selected={[actor]} enums={{}} />)
  expect(screen.getByText('MultiSkins (2)')).toBeInTheDocument()
  fireEvent.click(screen.getByText('MultiSkins (2)'))
  expect(screen.getByText('MultiSkins.0')).toBeInTheDocument()
})

it('an enum shows the canonical name directly, no ordinal', () => {
  const actor = makeActorWith(effectiveProps([
    { kind: 'enum', name: 'LightType', category: 'Lighting', enum_type: 'Engine.Light.ELightType',
      stored_value: 'LT_Steady', default_value: 'LT_None' },
  ]))
  render(<Inspector selected={[actor]} enums={{ 'Engine.Light.ELightType': ['LT_None', 'LT_Steady'] }} />)
  expect(screen.getByText('LT_Steady')).toBeInTheDocument()
})

it('a bool shows a disabled checkbox', () => {
  const actor = makeActorWith(effectiveProps([
    { kind: 'bool', name: 'bHidden', category: 'Display', stored_value: 'True', default_value: 'False' },
  ]))
  render(<Inspector selected={[actor]} enums={{}} />)
  expect(screen.getByRole('checkbox')).toBeDisabled()
  expect(screen.getByRole('checkbox')).toBeChecked()
})
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** struct/array rendering as nested `<details>`, checkbox for `bool`, plain
  text for `enum` (Task 8's corrected note: no `ScenePayload.enums` lookup needed for display).

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Commit**

```bash
git add web/src/panels/Inspector.tsx web/src/panels/Inspector.test.tsx
git commit -m "Inspector: struct/array expansion + typed display (checkbox/enum text)"
```

---

### Task 10c: `Inspector.tsx` — Folder/Labels display refresh

**Files:**
- Modify: `web/src/panels/Inspector.tsx` (`ActorSection`'s header `<dl>` rows)
- Test: `web/src/panels/Inspector.test.tsx`

**Interfaces:** none new — purely internal to `ActorSection`'s existing markup.

- [ ] **Step 1: Write the failing tests**

```typescript
it('labels render as individual chip elements, not a joined string', () => {
  const actor = makeActor({ labels: ['lit', 'indoor'] })
  render(<Inspector selected={[actor]} enums={{}} />)
  expect(screen.getByText('lit')).toBeInTheDocument()
  expect(screen.getByText('indoor')).toBeInTheDocument()
  expect(screen.queryByText('lit, indoor')).not.toBeInTheDocument()
})

it('empty folder/labels show a dash, not a sentence', () => {
  const actor = makeActor({ folder: null, labels: [] })
  render(<Inspector selected={[actor]} enums={{}} />)
  expect(screen.queryByText('(no folder)')).not.toBeInTheDocument()
  expect(screen.queryByText('(no label)')).not.toBeInTheDocument()
  expect(screen.getAllByText('—')).toHaveLength(2)
})

it('folder keeps its raw dotted path, no breadcrumb rendering', () => {
  const actor = makeActor({ folder: 'castle.tower.roof' })
  render(<Inspector selected={[actor]} enums={{}} />)
  expect(screen.getByText('castle.tower.roof')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** the Folder/Labels refresh.

- [ ] **Step 4: Run the FULL `Inspector.test.tsx` + `groupByCategory.test.ts` suites once, verify
  all pass** — Tasks 10a-10c together touched the most call sites of any tasks in this plan; a full
  local pass here (not just this task's own new cases) is the real gate before moving on.

- [ ] **Step 5: Commit**

```bash
git add web/src/panels/Inspector.tsx web/src/panels/Inspector.test.tsx
git commit -m "Inspector: Folder/Labels chip + dash-empty-state refresh"
```

---

### Task 11: `SurfaceDetail` — texture name, area, normal

**Files:**
- Modify: `web/src/panels/Inspector.tsx` (`SurfaceDetail` component)
- Test: `web/src/panels/Inspector.test.tsx`

**Interfaces:**
- Consumes: Task 8's `ScenePoly.normal`/`.area`/`AtlasRect.name`, needs the atlas manifest threaded
  into `SurfaceDetail` as a new prop (check how `Inspector`/`App.tsx` currently pass atlas data
  anywhere else in the app — likely already available via a context or a prop from the viewport
  code; do NOT re-fetch `/atlas` from inside `Inspector` if it's already loaded elsewhere).

- [ ] **Step 1: Write the failing test**

```typescript
it('shows the real texture name instead of a bare index', () => {
  const surface = makeSurfaceWith({ tex_index: 3 }, atlasManifest({ 3: { name: 'CoreTexMetal.Metal.Area51Wall_A', x:0,y:0,w:8,h:8 } }))
  render(<Inspector selected={[]} selectedSurfaces={[surface]} enums={{}} />)
  expect(screen.getByText('CoreTexMetal.Metal.Area51Wall_A')).toBeInTheDocument()
})

it('falls back to #index when the atlas name is null (mesh-skin entry)', () => {
  const surface = makeSurfaceWith({ tex_index: 5 }, atlasManifest({ 5: { name: null, x:0,y:0,w:8,h:8 } }))
  render(<Inspector selected={[]} selectedSurfaces={[surface]} enums={{}} />)
  expect(screen.getByText('#5')).toBeInTheDocument()
})

it('shows area and normal', () => {
  const surface = makeSurfaceWith({ area: 42.5, normal: [0, 0, 1] })
  render(<Inspector selected={[]} selectedSurfaces={[surface]} enums={{}} />)
  expect(screen.getByText('42.5')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** — replace `SurfaceDetail`'s `poly.tex_index >= 0 ? '#'+poly.tex_index :
  '(untextured)'` line with the atlas-name lookup + the dual fallback (`null` name OR `tex_index ===
  -1`); add `Area`/`Normal` rows to the existing `<dl>`.

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Commit**

```bash
git add web/src/panels/Inspector.tsx web/src/panels/Inspector.test.tsx
git commit -m "SurfaceDetail: real texture group name, area, normal"
```

---

## Known spec-level gap, not fixed by this plan (flagged, not silently patched)

`default_value` is computed via `propedit.edit.effective_value` (Task 4), which — per the spec's own
Design section — returns the STORED value when the actor states one, not an actor-independent class
default. So for an explicit property, `default_value` collapses to the same text as `stored_value`,
not the true class default. This is harmless for THIS plan's own read-only deliverable (a row's
shown value is `stored_value ?? default_value`, and `default_value` is only ever DISPLAYED when
`stored_value` is null, where it correctly IS the true class default) — but it means the spec's own
claim, in its "Explicitly out of scope" section, that a future "reset to default" editing action
gets `default_value` "already available at no extra cost," is not accurate for an already-explicit
property: reset-to-default there would need a genuinely separate, actor-independent default
resolution this plan does not build. Not fixing the spec's wording here (that's a document the owner
approved as-is) — flagging so whoever picks up `dev/docs/board/someday/gui-inspector-editing-write-
back-for-props/` knows this going in, and correcting that item's own "already available" claim
directly (see that item's own overview.md) is worth doing in the same pass, not blocking this plan.

## Self-review (per superpowers:writing-plans)

**Execution-time ruling (added during Task 3's fix loop, not part of the original 3 review
rounds):** Task 3's real fix (threading `ctx` into `_resolve_typed_fields` so an unstated member's
`default_value` resolves the TRUE class default, not a zero-fill — see the ledger,
`.superpowers/sdd/plan/progress.md`) made `ctx.defaults()` a new, unconditional call inside a
function that previously needed no schema access at all. `ctx.schema()` (Task 4's own schema walk)
has the identical `SchemaError`-on-unresolvable-class exposure and always did. Neither was guarded
at the whole-class level — only Task 4's inner per-PROPERTY `try/except` existed, which does not
cover a class that fails to resolve AT ALL. Fixed by wrapping `resolve_actor_props`'s entire body in
one outer `try/except SchemaError`, degrading to `([], {}, note)` — the same convention
`_is_hidden_ed`/`_actor_radii` already use elsewhere in `scene.py`. This changed
`resolve_actor_props`'s return shape to a 3-tuple (added a `note: str | None`) and required
threading that note through `_build_actors`/`build_wireframe_payload`/`build_scene_payload`'s own
notes-list-then-print-once pattern (Task 4/5's sections above are updated to match; `_build_actors`
had no pre-existing notes mechanism of its own to reuse — a new local list, same pattern).

**Spec coverage** — every spec.md Design/Frontend/`ScenePoly` bullet maps to a task: `EffectiveProp`
type (Tasks 2, 8), `TYPED_FIELDS` resolution + per-member explicit (Task 3), generic schema walk +
foreign-prop omission + `ArrayProperty`/`PointerProperty` exclusion (Task 4 — the exclusion is now
enforced in the filter itself, not as a downstream assertion, per plan review finding #2),
`ScenePayload.enums` (Task 5), `ScenePoly.normal`/`.area` (Task 6), `AtlasRect.name` (Task 7),
search/toggle (10a), struct/array/typed-display (10b), Folder/Labels (10c), `SurfaceDetail` (Task
11). `main_scale_text`/`post_scale_text` is Task 1. No spec bullet found without a task.

**Placeholder scan / hedge audit** — this plan went through TWO review rounds. Round 1 found 4
severe bugs (a `KeyError` in the enum accumulator, a reachable crash on `ArrayProperty`/
`PointerProperty`, a wrong function signature in the `ClassCtx` adapter, unguarded `SchemaError`
propagation), 2 real bugs (mixed ordinal/name enum text, a wrong-guess hedge in Task 7), and 4
moderate issues (stale line citations ×2, an undercount of the plan's own hedge spots, the
`default_value` self-contradiction noted above) — all fixed, then round 2 (a confirming pass on
those fixes) found the round-1 fix had introduced or left 2 MORE severe bugs (`_class_ctx_for`'s
`load_schema` returning the wrong shape — a list where `ClassCtx.schema()`'s contract requires a
dict, confirmed against the real `cli/resources.py::class_schema` and the sibling
`_class_category_map`; `ScenePayload.enums` only being wired into `build_scene_payload`, not the
OTHER real caller of `_build_actors`, `build_wireframe_payload` — a reachable crash on the cold-open
path) plus a moderate issue (Task 7's shown code referenced a Python variable, `name`, that does not
exist anywhere in `index_for`'s real scope) and a minor gap (`SceneActor.categories`'s removal never
made explicit). All of these are fixed in THIS version — including one caught independently while
fixing Task 7's `name` bug: `utexture.py` defines its own `Package` class where `.name` is a METHOD
(name-table lookup), not the package's own name string (`.stem`) — an earlier fix attempt would have
silently produced garbage text rather than crashing. Two full review rounds is more scrutiny than
this plan's earlier single-pass claim implied; both are recorded here rather than only the latest.

**Type consistency** — `EffectiveProp`'s Python (Task 2) and TS (Task 8) shapes match `spec.md`'s
single source of truth; `resolve_actor_props`'s return shape (`tuple[list[EffectiveProp],
dict[str, list[str]]]`) is used identically and consistently in Tasks 4 and 5; `ClassCtx` is never
redefined, only `_class_ctx_for`/`_struct_members_via`/`_enum_names_via` construct/feed one, using
its real public accessors (`.members()`/`.enums()`) rather than the raw `load_*` callables anywhere
resolution happens (Task 4) — the raw callables are only ever passed INTO the `ClassCtx` constructor
(Task 2), never called directly elsewhere.

## Task right-sizing

Original Task 10 (search + toggle + struct/array + typed display + Folder/Labels, one commit) was
reviewed and split into 10a/10b/10c along its own natural TDD seams — each independently
reviewable/rejectable, matching this project's "split only where a reviewer could meaningfully
reject one task while approving its neighbor" rule. 10b (struct/array rendering) is the riskiest and
most novel piece; isolating it means a reviewer can approve 10a/10c on their own merits without that
risk contaminating the review.

## Execution

This plan is large (13 tasks spanning Python backend + TypeScript frontend). Recommended:
**Subagent-Driven** (`superpowers:subagent-driven-development`) — fresh subagent per task, review
between tasks, catches drift early rather than compounding it across many tasks before the first
review.
