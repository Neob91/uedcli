# Native map import — why the decode is the way it is

Engineering decisions about `uedcli/mapimport.py` and the `level import` verb: reading a compiled
`.dx`/`.unr` back into the per-actor T3D a trunk holds, with no editor, container or game in the path.

What the module does and the on-disk shapes it walks:
[`../architecture.md`](../architecture.md) "Native (editor-free) map IMPORT". The format traps it
exists around: [`../unrealed/package-format.md`](../unrealed/package-format.md). This file is the why.

## The decode goes through T3D text, not straight into the model

`import_map` returns a `Begin Map … End Map` string for `model.parse_t3d`, rather than constructing
`model.Actor`/`model.Brush` directly.

**Why it is this way:** text→model is already the tested ingest path for every other actor source
(`actor add`, stash apply, the generators), and it carries routing that is easy to get subtly wrong a
second time — which properties become `Actor.location`/`MainScale`/`PostScale` fields instead of
staying in the generic property list, how a brush's model ref is bound, how a folder comment attaches.
Text also cannot build a level shape the rest of the tool would reject, and the intermediate is
inspectable: a string you can diff against an editor export of the same map.

**Rejected:** decoding into `model.Actor` directly — drops the location/scale routing (the values
would sit in `props` as raw text, invisible to every geometry verb) and gives the decode a second,
parallel definition of a parsed actor.

**Refs:** `uedcli/mapimport.py` (`import_map`), `uedcli/model.py` (`parse_t3d`, `parse_t3d_actors`).

## Value rendering is a style on the existing decoder, not a wrapper around it

`uprops.ValueStyle` gives the existing value decoder two spellings: `CLI_STYLE` (what every
pre-existing caller gets, unchanged) and `T3D_STYLE` (what the editor writes — six-decimal floats, and
a byte struct MEMBER as its enum value name).

**Why it is this way:** both differences live inside the struct decoder, where one member becomes
text. A caller wrapping `render_default_tag` receives `(A=1,B=SHEER_ZX)` already joined and cannot
re-render a member whose type it does not know — so the plan's "thin `mapimport` wrapper" could not
have worked. A style parameter keeps the blast radius nil: `CLI_STYLE` is the default everywhere and
byte-identical to the previous behaviour.

**Rejected:** post-processing the rendered string in `mapimport` — cannot reach inside a joined struct
value, and would re-parse text just produced. Also rejected: changing the shared renderer's float
format globally — that would alter `actor show` and every query verb for one caller's benefit.

**Refs:** `uedcli/uprops.py` (`ValueStyle`, `T3D_STYLE`, `_byte_member_text`, `format_float_t3d`).

## The struct member-drop compares a nested tree, not flat pairs

`struct_tag_member_tree` decodes a struct value into nested `{key: text | subtree}`;
`strip_member_tree` removes members equal to the default's, recursing; `render_member_tree` writes the
result.

**Why it is this way:** the editor's member-drop is recursive. A mirrored brush exports
`MainScale=(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)` — the nested vector states the one changed axis
and drops the two matching the default of 1 (real editor output, committed at
`uedcli/tests/fixtures/level_small.t3d`). Flat `(member, text)` pairs pre-join the nested struct, so a
comparison can only keep or drop the whole of it, yielding
`Scale=(X=-1.000000,Y=1.000000,Z=1.000000)`. That is still semantically correct — an unstated member
is filled from the class default — but it is not what the editor writes, so every scaled brush would
diverge textually from an export of the same map and the fidelity gate would fail.

The zero side is built by `zero_struct_tree`, not by decoding an all-zero byte buffer: a zero name or
object reference spells `None`, whereas decoding zero bytes would yield name-table index 0 — an
ordinary name, not a sentinel (see the `Item` entry below).

**Rejected:** splitting the joined `(A=…,B=(X=…))` text back apart to recurse — a struct member that
is a string can contain `,` or `)`, so the split is not sound. Also rejected: walking value and
default raw bytes in parallel — needs two value packages threaded through the shared decoder, for no
gain over comparing trees.

**Refs:** `uedcli/uprops.py` (`struct_tag_member_tree`, `zero_struct_tree`, `strip_member_tree`,
`render_member_tree`), `uedcli/tests/test_mapimport_import.py`.

## `Prop.array_inner` is persisted in the schema cache, and the cache version was bumped

An `ArrayProperty`'s element property is resolved one level deep and stored on `Prop`, and
`schema_cache` encodes it recursively rather than dropping it. `SCHEMA_CACHE_VERSION` went 1 → 2.

**Why it is this way:** an array property's own type reference points at the element property
*object*, so its type name is that object's name and the element kind is recorded nowhere else —
without it, array values are undecodable. If the cache handed back `array_inner=None`, dynamic-array
decode would fail (or silently skip the array) only on machines whose cache happened to be warm:
unreproducible, and invisible on a cold CI run. The version bump is mandatory: the persisted row is
decoded with `zip(_PROP_FIELDS, row)`, and `zip` truncates, so a stale v1 row would load cleanly with
`array_inner` silently `None`. Resolution stops at one level because UnrealScript has no
`array<array<T>>` and a self-referential element reference in a corrupt package would recurse forever.

**Rejected:** recomputing `array_inner` on cache read — the cache exists precisely to avoid re-walking
the package. Also rejected: leaving the version at 1 — see the `zip`-truncation trap.

**Refs:** `uedcli/uprops.py` (`Prop.array_inner`, `_decode_property(_inner=True)`),
`uedcli/schema_cache.py` (`_PROP_FIELDS`, `_prop_row`/`_prop_from_row`),
`uedcli/tests/test_mapimport_array.py`.

## Brush geometry is re-rendered through `emit.emit_brush`

The decoded `FPoly` records become `model.Polygon`s and are written out by the same emitter the trunk
and the materialize payload use, rather than by geometry-printing code local to the decode.

**Why it is this way:** it makes "the decode produced text that parses back" true by construction for
the geometry half — the emitter and the parser are already a tested pair. A second geometry printer
would be a second place for the coordinate formatting, the winding order and the optional `Pan`/
`Item`/`Texture` lines to drift.

**Refs:** `uedcli/emit.py` (`emit_brush`), [`emit.md`](emit.md).

## Every body is entered through the StateFrame skip, decided on the export's flags

Every body reader enters through `_skip_state_frame` — actors, `Model`, `Polys`, and the `Level`
itself — never at the raw serial offset.

**Why it is this way:** `RF_HasStack` is a per-export flag, and retail maps set it on a minority of
plain data objects that run no UnrealScript at all. Branching on the object's CLASS instead — the
natural assumption, since an actor is the thing with an execution state — desyncs those bodies by the
frame's length. The consume-to-EOF checks catch it, but it made `00_Training.dx` fail to import
outright. No sampled map flags its `Level` export, but the rule is applied there too: the flag turns
up where nobody expects it, and honouring it costs one call.

**Refs:** [`../unrealed/package-format.md`](../unrealed/package-format.md) "`RF_HasStack` is a
per-EXPORT flag", `uedcli/tests/test_mapimport_geometry.py`.

## A face's `Item` label is resolved by name, never by index 0

The test for an unset polygon label is `pkg.names[idx] == "None"`, not `idx == 0`.

**Why it is this way:** index 0 of a package's name table is an ordinary name, and in every Deus Ex
map sampled it is `OUTSIDE` — the editor's own default face label, carried by 7399 of
`02_NYC_Street.dx`'s 10690 authored polygons. Treating 0 as a sentinel deletes every one of them,
with no error and no short count; it is visible only by reading the emitted text and counting labels,
which is how it was found. The name `None` sits wherever the package's table happens to put it (index
2 in `00_Training.dx`), so nothing pins it to a fixed slot.

**Refs:** [`../unrealed/package-format.md`](../unrealed/package-format.md) "`FPoly.ItemName` — name
index 0 is a REAL name", `uedcli/tests/test_mapimport_geometry.py`.

## Import drops the editor's scratch objects — and must do so before qualification

`drop_editor_scratch` removes the builder brush and the `Camera` viewport actors, and the verb calls
it before `_validate_ingest_actors` qualifies class names.

**Why it is this way:** an owner ruling (2026-07-27), narrowing the spec's earlier "all actors
imported verbatim" to all content actors. A saved map carries the apparatus the designer was holding:
exactly one builder brush (the red scratch shape) and one `Camera` per open viewport — six in the
committed `paste.dx`, four to eight in the others, tagged with the editor's own
`U2Viewport1`/`MeshBrowser`. Keeping them would put editing tools in the durable tree as though placed
deliberately, and a later `level materialize` of that tree would paste the imported builder brush in
beside the fresh one the editor creates for itself, colliding over `Brush0`.

The ordering is load-bearing: both tests key on the SHORT class name — the builder-brush predicate
requires `Class=Brush` — and qualification rewrites those to `Engine.Brush`/`Engine.Camera`, after
which neither can match. Same constraint `_validate_ingest_actors` already documents for `actor add`.

`Camera` is matched as an exact class. It has no subclasses at all in the composed Deus Ex class set,
so an exact match cannot take real content with it; and although `Engine.Camera` derives from
`Engine.PlayerPawn`, nothing derives from it, so this is not a route to dropping a player start
(checked against the composed `.u` set, 2026-07-27).

**Rejected:** keeping them verbatim as the spec originally locked — leaves apparatus in every imported
tree and keeps the rebuild collision live. Also rejected: keeping them and excluding them at
materialize instead — pushes the work into a different subsystem and leaves the tree wrong meanwhile.
Also rejected: matching `Camera` by descent — the wrong direction on this hierarchy, and it buys
nothing since the class has no children.

**Refs:** `uedcli/mapimport.py` (`drop_editor_scratch`, `EDITOR_SCRATCH_CLASSES`),
`uedcli/normalize.py` (`is_builder_brush`), `uedcli/tests/test_import_verb.py`.

## An `--overwrite` level import names the previous actors as deletions

The verb reads the destination trunk first and passes the actors it will no longer contain as
`deleted=` to `trunk.write_level`.

**Why it is this way:** `write_level` is a delta write — it leaves actor directories it was not told
about alone, so concurrent edits to different actors compose instead of stomping each other. Without
naming the old actors, the previous level's content would survive and silently merge into the imported
level, producing a tree that is neither map.

**Refs:** `uedcli/dispatch.py` (`_level_import`), `uedcli/t3dtree.py` (`write_actor_tree`),
`uedcli/tests/test_import_verb.py`.

## An empty destination directory does not count as "already exists"

The overwrite guard treats a level as existing only when its `actors/` directory holds something.

**Why it is this way:** it matches `level create`'s rule. A previous failed or interrupted import
leaves a bare directory behind, and treating that as existing would permanently demand `--overwrite`
to retry past it — for no benefit, since there is nothing there to lose.

**Refs:** `uedcli/dispatch.py` (`_resolve_import_dest`), `uedcli/tests/test_import_verb.py`.

## Import is strict, and refuses rather than importing partially

Every class and every polygon texture must resolve on the project's package path; one that does not
fails the whole import, exit 2, naming it. Likewise a duplicate actor name, a corrupt body, or an
actor missing from the level's own order array.

**Why it is this way:** the "no silent half-answers" convention at its most consequential. A trunk
that looks complete but quietly dropped an actor — or carries an unresolvable class reference — is
worse than a failed import, because the failure surfaces much later, as a rebuild that does not match
or a map that will not load, with nothing pointing back at the import. The duplicate-name guard is a
real case: the level dict is keyed by actor name, so two exports sharing a name would collapse into
one and the import would report success.

**Rejected:** a lenient mode that imports anyway and keeps unresolved references — deferred, not
dismissed; it is on `dev/docs/board/inbox/`. It needs its own thinking about how such a tree is marked
so it cannot be mistaken for a complete one.

**Refs:** `uedcli/mapimport.py` (`import_map`'s two integrity gates), `uedcli/dispatch.py`
(`_level_import`), `uedcli/tests/test_import_verb.py`.

## What is not yet verified — the engine-faithfulness gap

The decode is pinned by: round-trip tests against uedcli's own writers, an end-to-end decode of three
real editor-built maps that must parse back and re-emit stably, and text-form assertions checked
against committed editor exports.

None of that proves byte-agreement with what the official exporter would write for the same map. That
check — comparing an import against a UCC export of the same retail map through the shared comparison
lens — has not been run. It needs the retail maps (copyrighted, so deliberately not in the repo;
`dev/scripts/install-deusex-assets.sh` populates them from a game copy you supply, and never
downloads) and the `dx-lum-uned` editor container that produces the reference output. The session that
built this had neither.

The corpus is not unavailable in general. Facts elsewhere in the docs were measured on the retail
corpus, on the same date, from a session that did have it:
[`../unrealed/package-format.md`](../unrealed/package-format.md) carries a per-map `RF_HasStack` census
over twelve maps and the `02_NYC_Street.dx` polygon-label count. The blocker is environmental: on a
machine with a game copy and the container, the gate is runnable as specified. It is logged as an
outstanding item on [`dev/docs/board/inbox/`](../board/inbox/).

The decode demonstrably reads real compiled maps and produces parseable, stable, correctly-shaped T3D.
Whether every value form matches the editor's spelling exactly is checked only where a committed
editor export happened to cover it.

**Refs:** `uedcli/tests/test_mapimport_import.py`, `uedcli/tests/test_mapimport_geometry.py`,
`uedcli/tests/test_mapimport_array.py`, `dev/docs/board/inbox/`.
