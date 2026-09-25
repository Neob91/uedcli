+++
priority = "p2"
kind = "implement"
summary = "Shared Rust core for class-schema resolution: native + WASM"
+++

# Shared Rust core for class-schema resolution: native + WASM

Split out of `gui-inspector-props-payload-redesign` (2026-09-24): that spec's frontend needs to
parse raw `.u` package bytes and resolve a class's full effective property shape/defaults
(Super-chain merge, default-tag decode, enum/struct canonicalization) **entirely client-side,
synchronously, with no API round trip** — the owner's explicit requirement is that the Inspector
must never show a spinner for connectivity reasons. The same resolution logic already exists,
today, only in Python (`uedcli/uprops/uclass.py`, `uedcli/uprops/values.py`,
`uedcli/effective_props.py`, `uedcli/propedit/*`), currently consumed by `/scene`
(`effective_props.py`'s walk — superseded by this item, not kept running alongside it). Writing a
second, separate TypeScript implementation of the same walk would be real duplication the owner
explicitly ruled out — so this needs ONE implementation, in a language that can run natively
(consumed by `/scene`'s own route handler, the same way `uedcli-native` is already consumed via
PyO3) and compiled to WebAssembly (consumed by the browser). **Scope, confirmed with the owner
2026-09-24**: this pass covers only the Inspector-props path `effective_props.py` already owned —
the CLI's own class-display (`class show`) and the write path's validation
(`propedit.effective_value` and friends) keep their existing, separate resolution code for now,
even though they resolve conceptually the same kind of data. The core is built to be natively
callable regardless (nothing here is WASM-only), so migrating those later reuses this work rather
than needing a new one — tracked, not committed to, at `dev/docs/board/inbox/
migrate-radii-bhiddened-bdirectional-and-cli/`.

**Foundation that already exists**: `uedcli-native/src/package_read.rs` already parses raw `.u`
package bytes in Rust — `parse_package` (name/import/export tables) and `read_property_tags`
(`PropertyTag` decode). This is the low-level layer the GUI feature's raw-file-serving design
depends on already being portable.

**Two entry points, one implementation** (settled 2026-09-24, after the first spec review of the
payload-redesign spec found the two-implementations gap this split originally left open):
- `resolve_class(fqcn, parsed_packages) -> {class shape+defaults, types}` — called BOTH natively
  (by `/scene`'s own route, for §1's contract) AND via WASM (the browser, lazily, per class). This
  is what "GUI feature" above meant originally. NOT wired into the CLI/write path in this pass —
  see the Scope note above.
- `resolve_actor_props(actor, parsed_packages) -> (sparse value map, notes)` — called ONLY
  natively, by `/scene`'s own route handler. The browser never calls this directly (an actor's
  stated values arrive already resolved in `/scene`'s JSON). **Built ON `resolve_class`, not
  independent of it**: internally calls `resolve_class(actor.cls, parsed_packages)` for that
  class's shape+defaults (the expensive Super-chain-walk half — cached per FQCN, so resolving many
  actors of the same class costs that walk ONCE), then does its own cheap, per-actor
  work on top (read `actor.props`' raw stored text, keep only present paths, canonicalize). This is
  what makes "one implementation" literally true — not a separate Python walk kept in sync by hand.
  `uedcli/effective_props.py`'s existing Python walk is SUPERSEDED by this, not kept running
  alongside it. `notes` is a whole-class failure note (mirrors today's `resolve_actor_props`'s
  existing third return value; `ctx_by_type`, its SECOND return value today, has no successor here
  — `types` data is a `resolve_class`-only concern under this design, per `gui-inspector-props-
  payload-redesign/spec.md` §2).

**Cache ownership shape, corrected 2026-09-24 (v17 fourth fix round)**: the per-FQCN cache is
NOT process-global and NOT scoped to `scene.py`'s existing per-request `ctx_cache` (a real
cross-request regression risk — see `gui-inspector-props-payload-redesign/spec.md` §2's own
correction of this exact point, including why `ctx.generation`/`TrunkWatcher` is the WRONG
invalidation signal). It must be a caller-HELD handle/context object — something the route stores
alongside its own `(search_files, index, defaults)` tuple (`app.py`'s `scene_inputs_ref`) and can
drop when that tuple is replaced (`/load`), not a static inside the Rust extension. This is real
API-surface work for this item's own plan: `resolve_class`/`resolve_actor_props` need a
context-object parameter (or equivalent), not just `parsed_packages`.

**What needs porting** (currently Python-only, no Rust equivalent):
- The Super-chain merge (`uprops.uclass.resolve_class_properties`): walk a class's ancestors
  across packages, override on case-folded name collision, most-derived kept.
- Class-defaults decode + overlay (`uprops.values.resolve_class_defaults`): each ancestor's
  default-tag block is a sparse diff against its super; render root→leaf.
- Canonicalization: enum ordinal→name, dequoting, the various per-type value-rendering rules
  `propedit.effective_value`/`uprops.values.render_default_tag` already implement.
- Struct/enum type identity + shape resolution: the `(package, outer, name)` keying scheme
  `gui-inspector-props-payload-redesign/spec.md` §1 documents and corpus-verifies in detail —
  that evidence is reusable as-is; only the "where this runs" changes.
- The `TYPED_FIELDS` special case (`Location`/`MainScale`/`PostScale`, `effective_props.py`'s
  `_resolve_typed_fields`) — reads model fields directly rather than `ctx.schema()`. Two concrete
  sub-fixes the port must include, not just the existing behavior: (1) a class-schema-only variant
  that emits `MainScale`/`PostScale`'s `SheerAxis` default already canonicalized (today's Python
  `_resolve_typed_fields` never calls `_canonicalize_enum_text` for it — an existing, narrower bug
  this port must not carry forward); (2) that variant must emit the real resolved key
  `Core.Scale.ESheerAxis` (via the SAME `outer`-based struct/enum identity rule every other type
  in this design uses), not the hardcoded Python string `"typedprops.ESheerAxis"` the existing code
  reads today — see `gui-inspector-props-payload-redesign/spec.md`'s `MainScale`/`ESheerAxis`
  discussion for the full worked-through reasoning.
- **The `ClassCtx` loader-contract gap** (`uedcli/propedit/base.py`): its loader signatures
  currently return SHAPE only (`load_members`/`load_enums`), with no channel for the resolved TYPE
  IDENTITY this design's normalization needs. `uedcli/serve/scene.py`'s `_struct_members_via`
  already computes `(tp, ti) = resolve_type_export(...)` internally and discards it — the port
  needs this identity surfaced, not thrown away.
- **The shared struct/enum resolver bug**, one root cause, two call sites, both must be fixed as
  part of this port (not carried forward): `_struct_members_via`/`_enum_names_via`
  (`uedcli/serve/scene.py`) both assume `prop.owner`'s first dot-segment is a real package name,
  which is false whenever `prop` is reached through a STRUCT MEMBER (a struct member's `owner` is
  the bare, unqualified struct name). Real, reachable scope (script-verified against the corpus,
  see the payload-redesign spec's Open Questions for the full count): at least 7 real
  struct-nested-in-struct cases, and 31 real `(class, property)` pairs across 30 classes for the
  enum-member variant. Fix direction: resolve the containing struct's own true package first, via
  the struct's own export record (the same `outer`-based mechanism this whole design already uses
  for identity), rather than guessing from `prop.owner`.
- **An actor-optional variant of `propedit.effective_value`'s resolution** for
  `resolve_class`'s own default resolution — its first statement is `_stored_map(actor)`, and
  `actor` threads through the rest of its body, not isolable the way `_resolve_one`'s two leaf
  calls are. A synthetic empty-props actor, or a genuinely actor-less entry point, are both
  plausible — pick one with real code in front of you.
- **`resolve_actor_props`'s own statedness rules for `Location`/`MainScale`/`PostScale`** —
  `normalize._stated_axes(actor)` and `effective_props._stated_scale_members(text, current)` — a
  DIFFERENT mechanism from the generic `ctx.schema()` walk (`gui-inspector-props-payload-redesign/
  spec.md` §2 has the full rule). Not yet named in this list before this pass's scope widened to
  cover `/scene`'s resolution too; needed now.
- **How `model.Actor` crosses the PyO3 boundary for the native `resolve_actor_props` call** — an
  open question this item's own plan needs to answer, not assumed free: `actor.props`'s raw stored
  text needs to reach Rust somehow (the actor's own already-parsed fields, or a lighter serialized
  form), and `actor.cls` needs to reach `resolve_class` the same way. Sized at plan time.

**Build targets**: native (PyO3, extending the existing `uedcli_native` Python extension — no new
Python-side integration mechanism needed) and `wasm32` for the browser (`wasm-bindgen`/
`wasm-pack` — `web/` has no existing WASM tooling; this is a first-time addition to the frontend
build pipeline).

**Cross-implementation correctness, load-bearing, not a nice-to-have**: because `/scene`'s sparse
map (native call) and the Inspector's default resolution (WASM call) must agree byte-for-byte on
both canonicalized VALUE text and dotted-path SPELLING — the frontend's explicitness test is a
literal string match, `path in actor.props`, against keys this core produced on the OTHER call —
a golden/round-trip test comparing the two entry points' output against the same real corpus data
belongs in this item's own plan, not left to be caught by a UI bug later.

**Out of scope for this item** (belongs to `gui-inspector-props-payload-redesign` instead): the
`/scene` payload's own wire SHAPE (the sparse value-map design itself, not its resolution), the
raw-`.u`-file-serving endpoint and its ETag/caching design, and the frontend's transitive-package
fetch strategy and render walk once this core exists.

See `gui-inspector-props-payload-redesign/spec.md` for the full corpus evidence (struct/enum
identity collisions, per-class-not-per-type defaults proof, canonicalization rules) this port
must reproduce exactly — not re-derive from scratch.
