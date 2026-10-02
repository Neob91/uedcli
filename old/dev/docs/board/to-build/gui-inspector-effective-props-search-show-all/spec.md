# Spec — GUI Inspector: effective props, search, show-all, struct/array expansion

## Goal

The Inspector (`web/src/panels/Inspector.tsx`) currently shows only the actor's *explicitly stored*
raw T3D props, grouped by category, as flat text rows — no search, no way to see class-default
values, no typed rendering, no struct/array structure. This spec makes it: searchable, able to show
defaulted properties distinctly from explicit ones (per-struct-member, not just per-property), and
typed enough to be a real editing surface later (though editing itself is out of scope here — see
"Explicitly out of scope").

Also in scope: surface detail gains the real `Package.Group.Name` texture identity (not a bare
`#index`) plus poly `area`/`normal`; the actor header's Folder/Labels rows get a display refresh.

## Current state

- `SceneActor.props: [string, string][]` + `.categories: string[]` (parallel arrays) —
  `uedcli/serve/scene.py`, built by `_actor_categories`/`_with_synthetic_location`. Only
  EXPLICITLY-stored props (`actor.props` verbatim, Location synthesized in from the typed model
  field). No defaults, no typing, no struct/array structure.
- `Inspector.tsx` renders these as `<dl>` rows plus `<details>` per category — flat KEY/VALUE text,
  no search, no filtering.
- `ScenePoly` (`web/src/api.ts`) has `tex_index: number` (an atlas-manifest index, no name) and no
  `area`/`normal`. `SurfaceDetail` (`Inspector.tsx`) shows `#{poly.tex_index}` or `(untextured)`.
- `propedit/edit.py` (the CLI's `actor prop` engine) has the resolution machinery this spec reuses:
  `effective_value` (stored → class default → zero, text in/out — `NameProperty`/`ObjectProperty`
  zero renders `"None"`, capitalized T3D spelling), `effective_all_lines` (whole-actor effective
  dump, `TYPED_FIELDS`-first then schema-resolved, filtered by `HARD_REJECT` +
  `is_computed_key` — a NAME-based blocklist, `Region`/`Level`/`PawnList`/`TimeSeconds`/…, not
  `CPF_Edit`), `dump_all_lines` (stored-only, hard errors on an unknown stored prop — ruling R4).
  `propedit.TYPED_FIELDS` (`propedit/fields.py`) intercepts `Location`/`MainScale`/`PostScale`
  before generic schema resolution; `Rotation` is NOT in `TYPED_FIELDS` and already resolves
  through the ordinary `ctx.schema()` path. `propedit` has ZERO handling for `ArrayProperty` (UE1's
  dynamic array kind) anywhere — every array code path branches on `prop.array_dim > 1` (a fixed,
  STATIC array), a different and already-fully-handled thing. `ArrayProperty` is excluded from this
  spec's scope entirely — see "Explicitly out of scope".
- `uedcli/typedprops.py`/`t3d.md` "Partial struct/array property values" (✅, live-verified
  2026-07-18): a partial struct literal is member-wise onto the CLASS DEFAULT, not zero-filled — a
  `DeusEx.Rat`'s `RotationRate=(Yaw=1234)` means `(Pitch=4096, Yaw=1234, Roll=3072)`, its real
  non-zero default Pitch/Roll, not `(0, 1234, 0)`. This is the real UnrealEd import semantic this
  spec's per-member explicit marking reproduces (see Design).
- `model.Actor.location_text` + `normalize._stated_axes` already compute, for `Location` only,
  exactly which axes the actor's own T3D text stated vs. omitted — existing, working, just not
  consulted by `propedit`/this spec's resolution yet. No equivalent exists for `MainScale`/
  `PostScale` (`model.py` carries no `main_scale_text`/`post_scale_text`).
- `uedcli/utexture.py::group_of_export` reads a texture export's real Outer group name (independent
  of whatever the trunk's stored `Texture=` ref happens to spell) — see the separately-filed
  `dev/docs/board/inbox/trunk-texture-refs-strip-group-which-is/` for why the stored ref itself is
  wrong to trust as identity.

## Design

### Data model — `SceneActor.props`

Replaced outright (no back-compat — uedcli is unreleased): `props: [string,string][]` +
`categories: string[]` → `props: EffectiveProp[]`, a discriminated union keyed on `kind` (not a
flat interface with optional kind-specific fields — a `float` prop has no business carrying an
`enum_type` slot it never uses):

```ts
interface EffectivePropBase {
  name: string                    // real declared casing
  category: string
}

type EffectiveProp = EffectivePropBase & (
  | { kind: 'float' | 'int' | 'bool' | 'byte' | 'name' | 'string'
      stored_value: string | null       // the actor's own stated value; null = not stated
      default_value: string }           // class default, always resolved (propedit's engine — see below)
  | { kind: 'enum'
      enum_type: string                 // key into ScenePayload.enums
      stored_value: string | null
      default_value: string }
  | { kind: 'struct'
      members: EffectiveProp[] }        // recursive, same shape — see "Server-side resolution"
  | { kind: 'array'
      element_kind: EffectiveProp['kind']  // the declared element type (always a STATIC array's
                                            // own Prop kind — see "Explicitly out of scope")
      elements: EffectiveProp[] }       // one entry per array_dim slot; never empty (array_dim is
                                         // always ≥ 2 for a genuine static array)
)
```

`object`/`class`/`ArrayProperty` (dynamic array)/`PointerProperty` kinds are excluded from scope
(see "Explicitly out of scope") — a property of any of these is simply not included in `props` at
all, same treatment either way.

Frontend derives: shown value = `stored_value ?? default_value` (only meaningful for the
scalar/enum variants — a `struct`/`array` entry has no top-level text value at all, it renders
exclusively through `members`/`elements`); "explicit" (not-defaulted) mark = `stored_value !==
null`; "overrides only" filter = `stored_value !== null` (recurses into `members`/`elements` the
same way — see Frontend below).

`ScenePayload` gains `enums: Record<string, string[]>` — enum type name (`enum_type`, format
`<Package>.<Class>.<EnumName>`, e.g. `DeusEx.FirePlug.ESkinColor`) → ordered value names. Built once
per `/scene` response by unioning every distinct `enum_type` hit while resolving props across all
actors. `prop.owner` (from `uprops.Prop`) correctly names the true declaring class even for an
inherited enum property — that's structural, not empirical: the qualified key is collision-safe by
construction (a bare enum NAME can collide across classes — e.g. two different `ESkinColor`s — but
`Package.Class.EnumName` can't, since `Class` is exactly what distinguishes them). An ad-hoc script
run against the real substrate this session (94 packages, not committed as a spike) found zero
collisions even on the bare name, consistent with but not required to prove the above.

### Server-side resolution (`uedcli/serve/scene.py`)

For each actor, walk `ctx.schema()` — every property the class declares (own + inherited), filtered
by `HARD_REJECT` + `is_computed_key` (`propedit.edit.effective_all_lines`'s own existing filter,
reused exactly, not reimplemented) — in the SAME `TYPED_FIELDS`-first-then-schema order
`effective_all_lines` already uses:

1. **`Location`/`MainScale`/`PostScale`** resolve through `propedit.TYPED_FIELDS` (`TypedField`/
   `ScaleField`), NOT generic schema resolution — the existing CLI mechanism, reused, not
   reinvented. `scene.py`'s own current bespoke `_with_synthetic_location` is deleted; both the CLI
   and the GUI now consult the one shared `TYPED_FIELDS` table. Since `ScaleField` has no
   `typedprops.Field`/kind classification of its own, a small adapter (new, scoped to this feature)
   gives these three the right `EffectiveProp` shape:
   - `Location` → `kind: 'struct'`, `members`: X/Y/Z (`kind: 'float'`).
   - `MainScale`/`PostScale` → `kind: 'struct'`, `members`: `Scale` (itself `kind: 'struct'`,
     members X/Y/Z float) + `SheerRate` (float) + `SheerAxis` (`kind: 'enum'`, `enum_type` a fixed
     constant naming `typedprops.ESHEER_AXIS` — no schema resolution needed, the value list is
     already a static Python tuple).
   - **Per-member `explicit`, matching the real engine's partial-struct-literal semantics** (see
     "Current state"): for `Location`, reuse `model.Actor.location_text` + `normalize._stated_axes`
     to determine which axes the actor's own text actually stated — a member's `stored_value` is
     non-null iff that specific axis was stated, `null` (falling back to `default_value`, the real
     class-default member, not zero) otherwise. For `MainScale`/`PostScale`, add the equivalent
     side-channel (`main_scale_text`/`post_scale_text` on `model.Actor`, populated at parse time the
     same way `location_text` already is) — new, but small and directly precedented, not a design
     question.
2. **Every other property** (including `Rotation`, which was never in `TYPED_FIELDS`) resolves
   through the ordinary `ctx.schema()` walk, one `EffectiveProp` per declared property:
   - Scalar/enum kinds: `stored_value` = the actor's own text if present (casefold key match
     against `actor.props`), else `null`; `default_value` = `propedit.edit.effective_value`'s
     resolution for that key (stored → class default → zero — the CLI's own engine, so the GUI and
     `actor prop get --effective` show identical defaults).
   - `struct` kind: `members` populated recursively from the `Prop`'s struct member tree
     (`uprops.struct_members`/`typedprops.Field.members`), each member's `stored_value`/
     `default_value` resolved the SAME member-precise way `typedprops`/`t3d.md` already document —
     a struct member stated by the actor's own struct text vs. falling back to the corresponding
     DEFAULT member.
   - Static array (`array_dim > 1`): `kind: 'array'`, one `elements` entry PER SLOT (`array_dim`
     total) — matches the CLI's own `dump_all_lines`/`effective_all_lines` indexed-line convention
     (`Field.0`, `Field.1`, …) exactly, so nothing new is invented for this case. Each element is a
     full `EffectiveProp` of `element_kind` (itself `struct`/`enum`/scalar, recursing as needed —
     e.g. a static array of structs).
   - `ArrayProperty` (dynamic array) and `PointerProperty`: excluded entirely, same treatment as
     `object`/`class` — see "Explicitly out of scope".
3. **A stored prop the schema doesn't know at all** (foreign/stale trunk content) is **silently
   omitted** from `EffectiveProp[]` — no entry, no error, no note. This is a DELIBERATE divergence
   from `propedit.edit.dump_all_lines`'s hard-error behavior (ruling R4: `actor prop get --stored`
   raises on this same situation) — the CLI keeps surfacing a stale/corrupt trunk loudly; the GUI
   does not. (Owner-confirmed 2026-09-23; not to be silently "fixed" back to matching the CLI later
   without asking again.)

### Frontend (`web/src/panels/Inspector.tsx`, `SurfaceDetail`)

- **Search box.** Filters `EffectiveProp[]` by `name` substring, case-insensitive, across every
  category. A struct/array row matches ONLY on its OWN name — a member/element name matching does
  NOT surface the parent row (owner-confirmed 2026-09-23); its children are visible only once the
  row itself is expanded, same as browsing without a search term. A category with zero matching
  rows collapses out of the `<details>` list entirely.
- **Overrides-only / show-all toggle.** Default = overrides-only (`stored_value !== null`, today's
  behavior, recursing into `members`/`elements`). Show-all reveals every property surviving the
  `HARD_REJECT`/`is_computed_key` filter above; a row whose `stored_value === null` renders visually
  distinct (dimmed/italic + a small "default" tag) — an EXPLICIT row that happens to equal its
  default renders as a normal, untagged row. Applies per-member/per-element, not just per top-level
  property.
- **Struct rows.** Render as a nested `<details>`/sub-table (mirrors the existing per-category
  `<details>` pattern) with one row per member, not one opaque value line.
- **Array rows.** One summary row (`Field (N)`, showing a compact joined preview of `elements`),
  expandable via `<details>` to per-element rows (`Field.0`, `Field.1`, …) — same expand affordance
  as struct rows.
- **Typed display** (display-only this round — see "Explicitly out of scope"): `bool` → checkbox
  (disabled); `enum` → the resolved name via `ScenePayload.enums[enum_type][ordinal]`, not the raw
  stored/default ordinal text; everything else → text, unchanged from today.
- **Folder/Labels** (`ActorSection`'s header `<dl>` rows): labels render as individual chip elements
  (not a comma-joined string); folder keeps its raw dotted-path text (`castle.tower.roof` — no
  breadcrumb-arrow rendering); both get a plain dash (`—`) empty state instead of a full sentence
  (`(no folder)`/`(no label)`).

### `ScenePoly` / surface detail

- `ScenePoly` gains `normal: [number, number, number]` (`normalize(tu × tv)`, computed server-side)
  and `area: number` (shoelace sum over `verts`, computed server-side).
- The `/atlas` manifest (`uedcli/serve/textures.py::build_atlas`) packs ONE rect per `texture_table`
  entry, brush-poly AND mesh-skin textures alike (its own docstring: "mesh-skin entries included —
  polys index into the same table"). Only brush-poly entries (`preview_native.py`'s
  `_TextureTable.index_for`, real export-backed) can resolve a real Group — mesh-skin entries
  (`index_for_decoded`, no export index) genuinely cannot (see "Explicitly out of scope"). So
  `AtlasRect.name: string | null` — the real `Package.Group.Name` via `utexture.group_of_export`
  (`Package.Name` alone when the export has no group) for a brush-poly entry, `null` for a mesh-skin
  entry. `SurfaceDetail` shows this name when non-null; falls back to `#index` for BOTH a `null` name
  and an untextured poly (`tex_index === -1`, unchanged from today) — one fallback rule, two causes.

## Explicitly out of scope (this item)

- **Editing** — no `<select>`/typed `<input>` write-back for any property, no surface texture
  reassignment. No write path is built here. Held for the in-flight "Persistent GUI Editing
  Sessions" staging rewrite — see `overview.md`. Correction (found during plan review, 2026-09-23):
  `default_value` is resolved via `propedit.edit.effective_value`'s stored→default→zero cascade,
  which returns the STORED value when the actor states one — so for an explicit property,
  `default_value` is NOT a true actor-independent class default, it collapses to `stored_value`. A
  future "reset to default" action on an already-explicit property is therefore NOT free from this
  field alone; it would need a genuinely separate, class-only default resolution. See
  `dev/docs/board/someday/gui-inspector-editing-write-back-for-props/` for the corrected note.
- **`object`/`class`-kind properties** — no read-only display beyond what already exists at the
  top-level `Class`/`Location`/etc. header fields (unaffected by this spec); no jump-to-actor link.
  Declined for this round.
- **`ArrayProperty` (dynamic array)** — a real, closed-set `uprops` kind, structurally distinct from
  the STATIC arrays this spec supports. Fully excluded, same as `object`/`class` (no row, not a
  placeholder). Owner-confirmed 2026-09-23 after RE: the T3D/binary serialization format is fully
  known (`uprops.decode_array_tag`/`mapimport.render_prop`, already tested) but `propedit` never
  calls it, AND — the decisive reason to skip, not the format gap — no real Deus Ex level actor
  anywhere in the substrate has an editable one (13 total declarations exist across every package on
  the real search path; exactly one has `CPF_Edit`, and it's editor/UCC config, not level content).
  Tracked: `dev/docs/board/someday/gui-inspector-dynamic-arrayproperty-support/`.
- **`PointerProperty`** — a raw native memory pointer field, never authored in T3D text at all (only
  ever appears on `native` classes). No textual value could ever be shown for one. Excluded, same as
  `object`/`class`.
- **Multi-select (2+ actors) comparison table** — `ActorSection`'s 2+ view stays a plain name list,
  unchanged. Declined for this round.
- **Copy-to-clipboard.** Declined for this round.
- **Mesh-actor skin textures** (`_TextureTable.index_for_decoded`, no export index/group available)
  — out of scope; only brush-poly textures (`index_for`, real export-backed) get a real group name.

## Open questions

None remaining — every question this spec raised (resolution engine, the show-all filter, `ABSENT`
reachability, per-member explicit for the three typed fields, `ArrayProperty`/`PointerProperty`
handling, the struct/array search-match rule) was resolved in the design conversation of
2026-09-22/23 and is stated as settled Design above. Reviewed twice
(`superpowers:requesting-code-review`); the second pass found nothing major.

## Where the detail lives

- Backend: `uedcli/serve/scene.py` (`SceneActor.props` builder, `ScenePoly`), `uedcli/preview_native.py`
  (`_TextureTable`/`index_for`, where the group-name read threads in), `uedcli/serve/textures.py`
  (`build_atlas`, the `/atlas` manifest itself), `uedcli/serve/app.py` (the `/atlas` route),
  `uedcli/propedit/` (reused, not modified, except the small `ScaleField`/`TypedField` → `EffectiveProp`
  adapter and the new `main_scale_text`/`post_scale_text` side-channel), `uedcli/model.py`
  (the new side-channel fields, mirroring `location_text`), `uedcli/utexture.py` (`group_of_export`,
  already exists).
- Frontend: `web/src/api.ts` (`EffectiveProp`, `ScenePayload.enums`, `AtlasRect.name`,
  `ScenePoly.normal`/`.area`), `web/src/panels/Inspector.tsx`, `web/src/panels/groupByCategory.ts`.
- Related, separately filed: `dev/docs/board/inbox/trunk-texture-refs-strip-group-which-is/` (p0,
  the texture-Group-stripping bug this design surfaced — not a blocker for this item, since
  `group_of_export` reads the real export's group independent of whatever the stored ref spells);
  `dev/docs/board/someday/gui-inspector-dynamic-arrayproperty-support/` (the excluded `ArrayProperty`
  case, tracked for later); `dev/docs/board/inbox/committed-uned-ued22-engine-u-vs-substrate/`
  (tangential `Engine.u` version-mismatch finding from the same RE pass, unrelated to this item).
