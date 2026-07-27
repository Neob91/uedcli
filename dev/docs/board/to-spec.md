# To spec / backlog

The entry queue: ideas/capability gaps that need a **spec** written (`dev/docs/specs/`), plus the
general **backlog** of known `[implement]`/`[chore]`/`[debug]` work not yet scheduled onto
`to-build.md`. As an item is picked up it moves through `to-spike.md` / `to-plan.md` and,
once it has a reviewed plan, onto **`to-build.md`** (the on-deck build queue — the source of
truth for what to build next). See [`README.md`](README.md). Tags: `[spec]`/`[implement]`/
`[chore]`/`[debug]`; `pN` priority rides each line.

> Items with a reviewed plan already live in [`to-build/`](to-build/) — a few are
> cross-noted "(also in to-build.md #N)" so you can see what's on-deck vs backlog.

---

## Needs a spec

- [ ] `p2` `[spec]` **Why do SEVEN verbs now require the games config? Investigate what each one
  actually needs mover-ness FOR, then scope the requirement back.** Making `movers.is_mover`
  schema-aware (`decisions.md` 2026-07-25 10:18 UTC — "one predicate, no split") propagated the
  class-resolver requirement to every call site: **`mover key`, `level doctor`, `event graph`,
  `stash capture`, `brush scale`, `brush apply-transform`, `brush intersect`/`deintersect`** now
  exit 2 without a project + `~/.uedcli/config.toml`. (`level materialize` and both `level preview`
  tiers already required one.) Andrzej's ruling only sanctioned it for `level doctor`; the other six
  came along as a consequence, and that is a wider user-facing narrowing than the question asked
  about.
  **Investigate first, decide second.** Per call site, answer with evidence from the code: (a) *why*
  does it ask the mover question at all; (b) what would the verb do differently if it simply did not
  ask; (c) is the answer load-bearing for correctness, or only for an optimization/warning. A verb
  in class (c) can stop asking, which drops its resolver requirement with no fallback and no second
  predicate. Suspect cases worth checking first: `brush intersect`/`deintersect` were **pure
  stdin→stdout filters** needing no project at all before this, and `event graph` resolves mover-ness
  before its skip so it fails on a class with no `Event`/`Tag` that it would have ignored anyway.
  **Same decision owns the second flag:** the predicate also hard-fails on any actor whose class is
  off the composed search path — stricter than "no games config", so a trunk ingested from a retail
  `.dx`, or a mod actor whose `.u` sits elsewhere, now fails verbs that used to produce a report.
  Both resolve as one scoping call: *which verbs may skip the mover question entirely.*
  **Also in scope — the ONE surviving name-suffix mover test, `preview.classify_brush`.** It still
  decides mover-ness with `bare.endswith("Mover")`, on the shared `actor preview` / `stash preview` /
  `prefab preview` path, where it picks the CSG palette's magenta *mover* colour. (It also feeds
  `is_solid` for hidden-line removal, but `"mover"` and `"add"` are both solid there, so usually only
  the colour differs — unless the misclassified mover carries `CsgOper=CSG_Subtract` or
  `PF_NotSolid`, which also costs it its solidity.)
  It was deliberately NOT threaded with the index, because doing so would add a further
  verb family to the resolver requirement this very item is trying to scope back — the same
  decision, so it is answered here rather than pre-empted. Today it diverges from `mover key` /
  `level doctor` on exactly the classes the schema-aware predicate was written for
  (`CaroneElevatorSet.CEDoor`, `DeusEx.BreakableGlass`/`BreakableWall`, `TNM.Barricade`, and —
  `endswith` being case-sensitive while UE1 `FName`s are not — `TNM.fanmover`/`platformmover`/
  `weakmover`): they render as ordinary additive brushes. Whatever the scoping call is, this
  function must come out of it with ONE answer: either it takes the index (and `*preview` joins the
  resolver-requiring set), or preview is ruled a class-(c) "cosmetic only" caller and the name test
  stays with that written down as a deliberate, documented approximation. `architecture.md`
  "Mover support" and the `classify_brush` docstring both record it as pending this item.
  **Ruled out in advance** (`decisions.md` 2026-07-25 10:18): a name-suffix fallback, an optional
  resolver that silently degrades, and a second divergent predicate. The only sanctioned fix is
  scoping. Outcome is a superseding `decisions.md` entry + `direction.md` reconcile — the current
  "Explicit, discoverable, model-side" bullet names all seven verbs and would need rewriting.
  (Andrzej, 2026-07-25; consequence of `to-build.md` #9.4.)

- [ ] `p2` `[spec]` **`brush snap` — round a brush's vertices to a nearby grid (T3D filter).** A stateless
  filter that reads a brush T3D on **stdin** and emits the snapped brush T3D on **stdout** (pipes like
  `brush clip`/`intersect` → `actor add -` / `brush replace`). Two params: **`--grid N`** = the grid size
  to snap to (e.g. 16 / 8 / 1), and **`--tolerance T`** = how close a vertex must be to a grid line to
  snap — a vertex farther than T from the grid is **left in place**, so *intentional* off-grid geometry
  (angled/rotated/curved brushes) is preserved and only near-grid **float-noise / slop** is corrected.
  **DECIDED (Andrzej): snap the brush's LOCAL vertices, NOT world coords** — clean the authored geometry
  independent of the actor's Location/Rotation/Scale transform, per-axis. **Motivation:** real/imported DX
  brushes carry sub-unit off-grid noise (e.g. WanChai `Brush615` at x≈-62.5455 ±1e-4), and off-grid coords
  are the main cause of BSP holes (`docs/leveldesign/general/geometry-and-bsp.md`); snapping the noise (not
  the angles) cleans geometry for reliable CSG. Spec the exact snap/round rule (round-half behavior),
  single-brush vs a brush SET on stdin, and whether a `level doctor`/lint tie-in should FLAG near-grid
  slop. (Andrzej, 2026-07-25.)

- [ ] `p2` `[spec]` **`brush clip` should be a T3D-stdin FILTER (`-`), not only a by-name trunk edit.**
  Today `brush clip <name> --plane …` mutates a placed trunk actor in place — but every other geometric
  brush *transform* is a stateless T3D-in/T3D-out generator (`brush build`, `brush intersect`/
  `deintersect`, and the proposed `brush snap`). Clip is the odd one out. Make it read a brush T3D on
  **stdin** and emit the clipped brush on **stdout**, so it composes BEFORE the trunk:
  `brush build cube | brush clip - --plane 96,0,0 1,0,1 --keep below | actor add -` (a chamfered box in
  ONE pipeline, vs today's add-then-clip-by-name). Spec: keep the by-name in-place form too, or replace
  it with the filter + `brush replace` (`actor show X | brush clip - … | brush replace X -`)?; single
  brush vs a SET on stdin. Aligns clip with the generator family; would simplify the shape recipes
  (`docs/leveldesign/general/recipes/shapes/`), which currently show the two-step by-name form.
  (Andrzej, 2026-07-25.)

- [ ] `p3` `[spec]` **`actor find --overlapping-bbox X0,Y0,Z0,X1,Y1,Z1` — region-grab (AABB INTERSECTS a
  box).** The looser companion to the built `--within-bbox` (full containment, `decisions.md` 2026-07-24
  21:44 UTC): match actors whose world AABB **intersects** the box, so a room shell / floor / wall that
  straddles the box edge IS grabbed — better for "show me everything in this area" (feeding
  `actor preview -`) than strict containment, which drops straddling brushes. Same machinery as
  `--within-bbox`: a Decimal AABB predicate (`writes.aabb_intersects`, edge-inclusive) over
  `writes.actor_bounds` in the dispatch find handler; reuse `parse_bbox`. Spec: the flag name/semantics,
  whether it and `--within-bbox` can co-exist (they're distinct predicates, both single-valued), and the
  L-brush AABB false-positive caveat (documented, not fixed — that's the `--precise`/`--within-brush`
  follow-up in the parked `specs/2026-07-24-find-spatial.md`). Deferred from the `--within-bbox` build per
  Andrzej. (2026-07-24.)

- [ ] `p2` `[spec]` **`brush build cylinder/cone --axis x|y|z` — build a prism oriented along a chosen
  axis, no `--rotate`.** `cylinder`/`cone` always build along **+Z**; to lay a horizontal pipe, beam,
  or duct run the author must `--rotate` the brush — which (a) forces reasoning about which of
  pitch/yaw/roll maps to which world axis (undocumented; see the orientation doc gap). An
  `--axis x|y|z` builds the cross-section normal along that axis directly, emitting **no `Rotation`
  field** — so the common horizontal-pipe case needs no `--rotate` and the obvious first attempt just
  works.
  **NAMING IS ALREADY SETTLED — adopt it, don't re-litigate:** `specs/2026-07-25-brush-profile-generators.md`
  §2.2 (`decisions.md` 2026-07-25 00:14 UTC D3) defines `--axis x|y|z` on the new `extrude`/`revolve`
  generators as "the axis the profile plane is normal to", with the `(u,v)` → world mapping fixed by
  right-handed cyclic order (`z`→X,Y; `x`→Y,Z; `y`→Z,X). Use that same flag name, semantics and table
  here so the family is consistent. Note also that the same spec (D9) replaces `--angle-offset DEG`
  with the boolean `--align-to-side`, so this item's composition question is now "how does `--axis`
  compose with `--align-to-side`" (answer should be: trivially — the bool is defined relative to the
  shape's own axis). Spec: which shapes take it
  (`cylinder`/`cone`; `cube` is symmetric so N/A; `sheet`?), how it composes with `--align-to-side` and
  `--at` (still center-anchored?), and whether to generalize to a free direction vector later. **Why it
  matters:** in a cold-agent build session (2026-07-24) the agent built a horizontal pipe via
  `--rotate 0,0,16384` and had to guess which rotation axis lays a +Z prism onto Y — `--axis` removes
  that guesswork (build it oriented, no `--rotate`). Related: the "semisolid = freedom / build detail
  from primitives" doc gap. (The post-verify abort that originally co-motivated this is now FIXED by
  the `Rotation` zero-omit canonicalization, `decisions.md` 2026-07-24 21:40 UTC — so `--axis` now
  stands on the axis-mapping ergonomics alone.) (Surfaced by the cold-agent build session, 2026-07-24.)

- [ ] `p3` `[spec]` **Make `actor preview` faster.** The offline wireframe renderer is a pure-Python
  stdlib rasterizer (`preview.py` — `render_brushes_pgm`/`render_quad_pgm`, per-pixel/per-poly loops);
  it's the model-side build-loop viewer, so its latency is felt on every iterate-and-look cycle. Spec
  should **profile first** (which stage dominates — poly rasterization, text/label drawing, PPM/PNG
  encode, `--size` scaling — the default `--size` was just bumped 512→1024, which quadruples fill), then
  pick the lever(s): vectorize hot loops (NumPy is not a current dep — decide), cache/skip offscreen
  polys, cheaper text, faster encode, or a resolution/quality knob. Set a target (e.g. a quad of a
  ~20-brush selection under Xms). Keep output byte-comparable where tests pin it. (Andrzej, 2026-07-24.)

> **one-actor `brush build` (staircase) + doctor T-junction-aware watertight** — BUILT 2026-07-21
> (`done.md`). **`actor preview` (was `brush preview`) ergonomics** — BUILT 2026-07-21 (`done.md`). The **spiral**
> single-brush redo was split into its own `[spec]` — see the "Spiral staircase builder" entry below.

- [ ] `p3` `[spec]` **Add the missing surface poly-flags to the settable `--add-flag`/`--remove-flag` set
  (`PF_NAMES`).** `query.py PF_NAMES` exposes 16 poly-flags by name, but `kb/textures.md`'s catalog documents
  five more real `PF_*` bits that `decode_flags` can READ yet no verb can SET: `brightcorners` (0x80000),
  `smallwavy` (0x2000), `bigwavy` (0x1000), `highshadowdetail` (0x800000), `lowshadowdetail` (0x8000). Spec
  adding them to `PF_NAMES` (which also feeds the CLI `choices=`), deciding whether ALL are safe / round-trip
  clean to author (shadow-detail changes lightmap resolution; small/big-wavy are render distortions) or only
  a subset, plus a regression that the settable set matches the catalog, and updating `kb/textures.md`'s
  "these are the `--add-flag` names" claim to match. (Surfaced 2026-07-20 level-design docs review.)

- [ ] `p2` `[spec]` **Extract uedcli into its own standalone git repo (out of the `dx_lum` mod tree).**
  `direction.md` already frames uedcli as a **globally-installed, generic-UE1 CLI that operates on many
  independent projects, not a tool living inside one content repo** (project = any repo with a
  `uedcli.toml`; tool-install assets resolve package-relative, never from a project). Its home should match
  that identity — independent of the mod. Spec scope: which dirs travel (the `uedcli/` package, `bin/`,
  `dev/docs/**` incl. this board + `spikes/`, the compose dir / UED22 substrate / umodel tool assets);
  git-history handling (a fresh repo vs a `filter-repo`/subtree extraction of `Tools/uedcli/**` — note the
  global "never rewrite published history" rule applies to the EXISTING repo, so this builds a NEW repo from
  a copy, never a rewrite of `dx_lum`); how the mod repo consumes the CLI afterward (pipx install / pinned
  dependency / submodule — decide); the pipx/Nuitka release story; and cutover mechanics (CI/tests, the
  `dev/docs/board` pipeline, cross-repo references in `LUM/CLAUDE.md`). Prerequisite for the skills-plugin
  distribution entry below. (Andrzej, 2026-07-19; decisions.md addendum.)

- [ ] `p3` `[spec]` **Skills-plugin distribution via repo-as-its-own-marketplace (depends on the repo
  move).** Ship uedcli's `claude/plugins/uedcli/` skills through the plugin marketplace (decisions
  2026-07-19). **Blocked on the standalone-repo extraction above:** `/plugin marketplace add` on the current
  `dx_lum` tree would clone the whole ~3.3 GB private mod repo to deliver a few KB of skills; a dedicated
  small CLI repo makes distribution clean. Spec the marketplace manifest, the skills layout, and the
  install/update flow once the CLI has its own repo. Interim dev install = symlink `skills/` into
  `.claude/skills/`. (Andrzej, 2026-07-19; decisions.md addendum.)

- [ ] `p2` `[spec]` **`level delete` / `rename` / `clone` — git-agnostic trunk-dir lifecycle verbs.** The probe found no way to delete, rename, or copy a level. Spec thin verbs operating on the TRUNK DIRECTORY directly (filesystem — git-agnostic, per `direction.md`'s "uedcli never wraps version control"), NOT git wrappers: `rename` = move `<maps>/<old>` → `<new>` (+ name/rank fixups + retarget the selected pointer if it pointed there); `clone` = copy the trunk under a new name; `delete` = rm the trunk dir behind a guard (refuse if selected, or `--force`). Works whether or not the project is under git. (Surfaced 2026-07-19 usability probe; git-agnostic per Andrzej.)

- [ ] `p2` `[spec]` **Author-time validation of ObjectProperty refs (AmbientSound/Song/OpeningSound/mesh/…).** A typo'd object-property ref currently exits 0 and ships a silently-broken level — the same class of gap `class`/`texture` validation already closed for class + texture refs. Spec author-time existence-validation of object-valued props against the composed package set. Rides the unified asset catalog's ENUMERATION layer for the reference set (specced 2026-07-25, `specs/2026-07-25-unified-asset-catalog.md` §8) — it needs enumeration only, NOT classification, so it is not gated on the catalog being populated. (Surfaced 2026-07-19 usability probe.)

- [ ] `p2` `[spec]` **`event link` / `unlink` — AUTHOR the Tag↔Event wiring `event graph` only reads.** `event graph` (built 2026-07-18) lints trigger wiring (edge A→B when `A.Event == B.Tag`) but no verb SETS it. Spec `event link <source> <target>` (set `source.Event := target.Tag`, minting a Tag if the target lacks one) + `event unlink`, model-side over the trunk — the natural completion of event-graph. Consider multi-event array props (Dispatcher `OutEvents`, Counter). (Surfaced 2026-07-19 usability probe.)

- [ ] `p3` `[spec]` **`stash capture -` (stdin).** Read a T3D snippet from stdin directly into a
  stash entry, without going through `actor add`. Useful for
  `stash deintersect X | stash capture - --id baked`. Deferred from the generator-pattern spec
  (2026-06-24); needs its own spec.

- [ ] `p2` `[spec]` **Texture-alignment solver (`poly align`) — planar wall/floor + curved
  (cylinder/sphere) alignment.** ⚠ *"Reproduce UnrealEd's TEXTURE ALIGN semantics" (as this item
  used to read) is no longer a usable goal: there IS no `TEXTURE ALIGN` verb — the editor's is
  `POLY TEXALIGN`, its nine modes were measured 2026-07-26 (`../unrealed/texalign.md`), none of them
  changes texel density, `ONETILE` is a no-op, and uedcli's `--wall`/`--floor` match none of them.
  What to do about that is the `[OWNER — decide]` item on `inbox.md`.* The rest of this item stands:
  make
  pan/rotation/texture-vectors continuous across adjacent coplanar/wrapped faces (`--wall`/`--floor`)
  so brickwork doesn't seam at every brush boundary — pure offline math on the PolyList texture
  vectors, currently impossible via uedcli (per-face `poly set --pan` only). ALSO wanted (Andrzej
  2026-07-16): alignment onto **curved surfaces** — wrap a texture continuously around e.g. a
  cylinder's facet ring or a sphere (per-face U advance matching arc length), so curved builder
  output doesn't seam at every facet. (AI brainstorm 2026-07-16; endorsed + extended by Andrzej
  2026-07-16.) ALSO fold in `texture scale` / `texture rotate` (2 of the 4 canonical surface ops, flagged missing by the 2026-07-19 usability probe) — same per-face texture-vector math.


- `[spec]` **Namespace `COMPUTED_PROPS` by declaring class — `Engine.Mover.BasePos`, inherited by
  subclasses.** p2. `normalize.COMPUTED_PROPS` is a flat set of BARE property names matched
  case-insensitively against every actor (`is_computed_key`), so a name that is engine-computed on one
  class is stripped from EVERY class that happens to declare it. That is a silent-data-loss shape: the
  strip runs in `normalize_actor`, which feeds `canonical_actor_t3d` — the durable git-tracked trunk
  emit AND the `MAP IMPORT` payload — so a wrong entry erases authored content from the source of
  truth, not just from a comparison.
  **This nearly happened.** Adding `SavedTrigger` alongside `SavedPos`/`SavedRot` (2026-07-25) looked
  obviously right — same `Engine.Mover` runtime family — but `Engine.TriggerLight` declares its OWN
  `SavedTrigger` and IS placeable, so the bare name would have silently stripped a real property from
  every TriggerLight ever materialized. Caught by a cold reviewer, not by the code. `Tag` was moved out
  of this set earlier for the same reason (5 TNM classes default it to `'Player'`). The current 12
  entries are correct only because each was hand-audited; nothing enforces that.
  **Proposal:** key entries as `<Package>.<Class>.<Prop>` (`Engine.Mover.BasePos`), scoped to the
  DECLARING class and inherited by descendants (so `DeusEx.DeusExMover` picks up `Engine.Mover`'s
  entries automatically).
  **The load-bearing design question the spec must resolve:** class-scoped matching needs the actor's
  ANCESTRY, i.e. a class resolver — but `normalize_actor` must stay schema-free, because
  `canonical_actor_t3d`'s bytes may not depend on which packages happen to be installed (same trunk,
  same bytes, every machine — `decisions.md` 2026-07-25). The likely answer is the one the rest of the
  2026-07-25 work converged on: move the computed-strip OFF the durable emit and onto the THROWAWAY
  COMPARE COPY, where the schema is already available and `typedprops`/`ClassDefaults` already run —
  which also stops the strip from mutating authored data at all. Spec should confirm that, or justify a
  schema-free approximation.
  **Also in scope:** re-audit all 12 existing entries against the same collision test (which other
  classes declare each name, and are any placeable?); decide the fallback when a class is unresolvable
  (hard-fail vs strip nothing); `actor prop`'s "won't persist" warning shares `is_computed_key` and
  moves with it; and the parked `[debug]` `DistanceFromPlayer`/`LastRenderTime` item becomes decidable
  once entries can be scoped. (Andrzej, 2026-07-25.)

- `[spec]` **A `brush shear` / diagonal-wall helper — and a grid-alignment caveat on `actor rotate`.**
  p2. Building a 45° wall the RIGHT way (grid-aligned, no rotation) was: `brush build cube` → then
  `brush vertex move` the 4 corners at one end by a grid delta to shear the box onto the diagonal.
  Correct + watertight + all-integer vertices, but I had to hand-compute the far-end corner coords and
  the shear delta. A `brush shear --edge <face> --by dX,dY,dZ` (or a diagonal-wall builder taking two
  grid endpoints + thickness) would make this one call. **Related bug/UX:** `actor rotate` cheerfully
  applies an arbitrary rotation that puts vertices OFF the grid (a 45° yaw → ×0.707 fractional coords →
  CSG cracks/leaks) with no warning — Andrzej flagged this live. `actor rotate` should warn when a
  rotation yields off-grid vertices (or snap to grid / suggest the vertex-shear path), and the
  grid-align-don't-rotate rule is a real UnrealEd best-practice to document in `unrealed/` (diagonal
  geometry is built by vertex-editing to grid points, not by rotating).

- `[spec]` **`actor folder list` + `actor label list` — enumerate the folders/labels in use.** p2.
  Today you can find actors BY a folder/label (`actor find --folder/--label`) but cannot ask *what
  folders/labels exist*. Add two read verbs UNDER `actor` (the top-level-promotion question is CLOSED —
  keep everything under `actor`, `decisions.md` 2026-07-25 00:43 UTC): `folder list` prints the distinct
  folder paths in use (one per line, sorted — the pipe-friendly producer form); `label list` prints the
  distinct labels (flat, so no tree). Spec the exact output: per-path/per-label actor COUNTS (to stderr,
  or a `--count` column?); a `folder tree` view rendering the hierarchy indented (labels have none); do
  they take `-`/stdin to scope the enumeration to a piped actor set; `--json`. Both are uedcli-side
  sidecars, never emitted to the built map; query stays on `actor find`, this is pure enumeration.
  (Andrzej, 2026-07-25 — reframed from the closed "promote folder/label to top-level" item.)

- `[spec]` **`folder rename <old-path> <new-path>` — whole-subtree re-parent/rename.** p3. Deferred
  from the actor-folders v1 (assign-only). Re-parent/rename an entire folder subtree in one call
  (rewrite the `folder` sidecar of every actor under `<old-path>` to the `<new-path>` prefix).
  Andrzej, 2026-07-18.

- `[spec]` **Exact-single-node folder match (no subtree).** p3. Deferred from actor-folders v1:
  a wildcard-free `--folder X` now selects X's whole subtree, and `--prop Group=` no longer reaches
  the folder (it's a sidecar, not a prop), so there is no form for "exactly this folder, excluding
  descendants." A niche need — add later, e.g. `--folder-exact` or an `=path` sigil. Andrzej,
  2026-07-18.

- `[spec]` **`--from-group` bulk folder-migration sugar.** p3. Deferred from actor-folders v1.
  Existing `Group=`-organized levels start with EMPTY folders (independence — Group is never
  auto-absorbed). Today's opt-in recipe is `actor find --group cellblock | actor folder set --to
  act2.cellblock -`; a one-shot `--from-group` sugar could fold a whole level's flat groups into
  folders in one call. Andrzej, 2026-07-18.

- `[spec]` **uplayctl readiness should surface a game-side `Critical Error` instead of a generic
  "level never became X" timeout.** p2. The whole earlier symptom — `session start` logging `link up;
  traveling to Test_Castle (level-name-gated)` then `level never became Test_Castle (last=None)`,
  followed by `ConnectionRefused` on every `shot`/`GetCurrentLevelName` — was NOT a "link doesn't
  survive map travel" bug. The game had popped a modal `Critical Error: Failed to spawn player actor`
  dialog and the process was wedged on it (link socket never re-listens on 7777). The readiness poll
  should detect the `Critical Error` window (or grep the crash in the log) and fail fast with the
  actual engine error + backtrace, instead of a content-free timeout that sends the operator down the
  wrong path (I spent a long time suspecting the link/travel mechanism). Cheap detection: `xdotool
  search --name "Critical Error"` on :99, or tail the crash line the engine writes. Andrzej,
  2026-07-12.

- `p2` `[spec] follow-up from the schema-cache v1 build (2026-07-18)` — **v2 defaults-value schema
  cache.** v1 (`schema_cache.py`, `PackageSchema`) caches only the discovery primitives; v2 adds the
  defaults-render primitives so `actor prop get`/`actor find --prop` render default VALUES buf-lessly
  (the review's HIGH-1 full fix): raw DEFAULTS blocks (`class_default_tags`), local enum tables
  (`enum_values`), per-Struct member schemas (`struct_members`), compact name/import/export tables;
  plus a NEW whole-package enum/struct enumerator (no `iter_structs`/`iter_enums` today) and
  imported-type resolution by CHAINING `load_package_schema` on the foreign package. Re-plumb the
  render consumers (`resolve_class_defaults`/`render_default_tag`/`struct_members`/`_resolve_type_
  export`/object-ref renderer) off the live `Package`/`buf`. Bumps `SCHEMA_CACHE_VERSION` + refreshes
  the frozen golden. Spec §4.1b/§4.6. Open Q (spec §9): pre-render object-refs to text at decode time
  to DROP the cached tables entirely.

---

## Backlog — active (implement / chore / debug)

- [ ] `p2` `[debug]` **Live-verify the `/stubs` container mount under the env-fed source** (git-native
  slice 7; premise updated 2026-07-18). The stub-mount source is now
  `${UEDCLI_STUB_CACHE:-${HOME}/.uedcli/cache/stubs}` — BOTH `editor.ensure_editor` and
  `stub.ephemeral_build_container` pass `UEDCLI_STUB_CACHE` (the resolved `config.stub_cache_root()`,
  an absolute path) in the compose env, so `${HOME}` interpolation and the stripped-env cron/systemd
  concern no longer apply to uedcli-driven spin-ups (only to a hand-run `docker compose`). Remaining
  leg: confirm on a live editor container that a real `level materialize`/`level preview` still
  `OBJ LOAD`s the v69 stubs from `/stubs`. Substrate-gated — cannot be checked offline. From the
  slice-7 flag (2026-07-08).

- [ ] `p1` `[implement]` **BSP-issue ground-truth detector = D0 + D1 (the complete detector on the
  real editor build); D2 = optional fully-offline upgrade.** Full design (3-round-reviewed):
  `specs/2026-06-24-uedcli-offline-bsp-engine-design.md`; decision: `decisions.md` 2026-06-24 12:40
  UTC (revises 09:07). Five grounding spikes (`spikes/2026-06-24-*bsp*` / `*offline-bsp-engine*`)
  hold the decoded substrate. **(Also in `to-build.md` #1.)**
  - **D0 DONE + validated** (`spikes/2026-06-24-offline-bsp-engine-d0-editorlog.md`): `bsp_editorlog.py`
    parses the editor's `MAP REBUILD` drop-warnings — caught an injected open-box hole live.
    **Next:** **D0-b** — run it over the repo's real DeusEx maps (needs gitignored install content)
    to measure build-emergent vs single-brush hole frequency; then promote `bsp_editorlog.py` →
    `uedcli/bsp/editorlog.py` with offline golden + integration tests and a `level doctor` verb.
  - **D1 (next):** **P0-a** — feasibility of a binary `UModel` parser for the saved `.dx` built model;
    then `report.analyze_built` LOCATES HoM/T-junction cracks, invisible-wall phantom nodes,
    fall-through. D0+D1 = complete detector.
  (D0/D1 use the live editor once per check — NOT fully offline. The shipped static `level doctor`
  is the fully-offline per-brush tier; D2 below is the fully-offline build-emergent tier, deferred.)

- [ ] `p2` `[implement]` **D2 — fully-offline BSP/CSG/collision engine (the no-editor-ever upgrade —
  FOR LATER).** The pure-Python reimplementation so build-emergent holes/HoM/invisible-walls/
  fall-through are caught with **no editor at all**. Fully specced:
  `specs/2026-06-24-uedcli-offline-bsp-engine-design.md` (D2 sections) + `decisions.md` 2026-06-24
  09:07/12:40 UTC. Slice-1/1b/2/3 already prototyped (`_scratch/bspspike/`): single-box &
  abutting-subtracts exact, 3/5 corpus diverge 4–8 nodes with both gaps located — port the
  leaf-filter `0x32bf0`/`0x32030` and the real `SplitPolyList 0x34530`, then cleanup passes +
  leaf/zone + a binary `UModel` parser (Tier-S oracle), behind the spec's budgeted Tier-S bar.
  Build when prioritized; D0 doubles as its verification oracle. **Partition-heuristic gate CLOSED
  2026-06-26** (`spikes/2026-06-26-bsp-partition-heuristic-from-binary.md`): `FindBestSplit`'s last
  open items (the structural-splitter candidate skip + `SplitWithPlaneFast`) are decoded and
  byte-verified, and a faithful reference port (incl. the slot-scan candidate selection for
  GOOD/LAME) ships in that spike's `harness/find_best_split.py`. The remaining D2 work is the
  `SplitPolyList` recursion + CSG filter (volume, not unknowns).

- [ ] `p2` `[chore]` **Document the day-to-day git-trunk dev workflow (doc only).** Write a
  short how-to for the CURRENT (post-session-store) loop: work on a git feature branch → edit the
  T3D trunk model-side (`actor …`/`brush …`/`poly …`) → `level preview` to eyeball → `level
  materialize --out <map>` to build the artifact → `git commit`/`git merge` into trunk (git is the
  history + merge engine; per-actor `.t3d` files merge natively). Half of this is already decided
  (`direction.md`: the trunk is a git-committed T3D tree, map files demoted to build artifacts); the
  gap is that the loop isn't written down. Doc only. *(Reframed 2026-07-18 from the old
  `session start`/`apply --check`/`apply --to-t3d-tree` phrasing — sessions + the `apply` verb were
  removed by the git-native migration, decisions.md 2026-07-05 14:58.)* From Andrzej (was
  to-resolve #1) / dump.md Part B2; originally 2026-06-25.

- [ ] `p2` `[chore]` **Host package search-dirs and container `/content` mounts can drift
  silently.** `packages.substrate_search_dirs` lists repo-root `Sounds`, `Music`, `LUM` (plus
  `System`/`Textures`/`Maps`), and `_remap_to_container` maps any of them to `/content/<sub>`. But
  `uned/docker-compose.yml` mounts only `/content/{Textures,Maps,System}` plus stub
  `/content/{Sounds,Music}`; there is **no `/content/LUM` mount**. Latent today, but if a `LUM`
  content package lands, `ensure_load` hands the editor `/content/LUM/...` which the container can't
  see — reviving the silent unresolved-load failure D4 exists to prevent. Decide where compiled
  `LUM` content lives, whether the repo-root `Sounds`/`Music` search dirs are vestigial, then make
  the two lists derive from one source (or add a test parsing `docker-compose.yml` that asserts
  every `/content/*` remap target is mounted). Surfaced by the 2026-06-21 container-fs-isolation
  review.

- [ ] `p2` `[implement]` **`level build` (paths only) + a `--quality` escalation knob.**
  `LIGHT APPLY` folding into `level apply` is DONE 2026-06-21. `BSP REBUILD` quality args CONFIRMED
  2026-06-23 (`LAME`/`GOOD`/`OPTIMAL`); `PATHS DEFINE`/`PATHS BUILD LOWOPT`/`HIGHOPT` CONFIRMED.
  Still open: wire a `--quality` knob into `level apply` (`BSP REBUILD LAME` default, `GOOD`/
  `OPTIMAL` on demand) and implement `level build` as a standalone paths-only verb. No longer
  spike-gated.

- [ ] `p2` `[implement]` **On-demand Deus Ex package stubbing (v68→v69) — IMPLEMENTED, REMNANTS.**
  DONE end-to-end 2026-06-22 (live-validated against `DeusExItems`). **REMAINING (small):** `--deps`
  recursive-stub flag (unused today — closure bottoms out on substrate); broader cross-package asset
  resolution (deferred, flagged). See `spikes/2026-06-21-deusex-package-stubbing-roundtrip.md` +
  `decisions.md` (2026-06-21, 2026-06-22).

- [ ] `p2` `[debug]` **Live-verify a same-name-collision texture binds correctly end-to-end through
  a real `apply`** — not just the synthetic `MAP IMPORTADD` probe (`unrealed/quirks.md` "T3D
  format") that found the auto-demand-load bug `apply._ensure_load` already fixes via an explicit
  `OBJ LOAD` per package.

- [ ] `p2` `[debug]` **Verify `write_paths_and_reload`'s `Paths=` ini-edit is redundant once `OBJ
  LOAD` runs.** Spike 2 (2026-06-23) confirmed `OBJ LOAD FILE=<abs>` works without `Paths=` entries
  and packages survive `MAP NEW`; the full probe was substrate-gated. To close: run a real DeusEx
  content-map apply with the `Paths=` ini-edit disabled but `OBJ LOAD` kept; if it resolves, delete
  `write_paths_and_reload` (and its fragile dedup check) and simplify `packages.py`.

- [ ] `p2` `[implement]` **`level preview` multi-preview port/URL surfacing.** The ephemeral noVNC
  port (`-p 0:6080` + `docker port`) supports 2+ simultaneous previews in principle, but the printed
  URL story for multiple concurrent editors is unfinished — v1 is one previewable editor per host.
  Finish if needed.

- [ ] `[implement]` **Subtractive CSG: remaining CLI surface.** Round-trip + carving verified live;
  the first-class intersect/deintersect verb is superseded by `stash intersect`/`stash deintersect`.
  REMAINING: (2) wire `--solidity` flags through a live verification; (3) expose CSG order /
  select-by-type as CLI verbs. See `unrealed/quirks.md` "CSG model". ALSO unify the fragmented brush namespace (2026-07-19 probe): add `brush find`/`brush list`, and note CSG-reorder lives on `actor order` + intersect on `stash`.

- [ ] `[implement]` **`brush poly move` — translate a whole poly (all its vertices at once).** Builds
  on vertex move: select a poly `(brush, poly index)`, translate every vertex by `--by DX,DY,DZ`
  (and/or `--to` for the centroid). Moves shared corners consistently (deforms neighbours);
  `validate_brush` must still pass (most non-axis moves rejected — document the constraint).
  Pipeline: mutate PolyList → `validate_brush` → `record_mutation` (model-side). Decide selector ergonomics.

- [ ] `[implement]` **Zones** — water / fog / gravity / ambient light / reverb / sound regions. A
  zone portal is a *surface flag* (supported by `poly set`); zones resolve on rebuild; max 64.
  Place/configure `ZoneInfo` actors + flag the portal surfaces.

- [ ] `[implement]` **AI pathing (`PATHS DEFINE`).** NPC/bot levels need NavigationPoints + `PATHS
  DEFINE` (reachspecs are computed, rebuilt after geometry/actor changes; nodes ≥50uu apart).
  `PATHS DEFINE` + `PATHS BUILD LOWOPT/HIGHOPT` confirmed live 2026-06-23. Implement as part of
  `level build`.

- [ ] `[implement]` **Driver liveness recovery.** Fast crash detection is DONE (`wine_ctl`
  `_assert_alive()`). Still TODO: higher-level *recovery* (restart + resume) around brush writes —
  see [[uned-liveness-monitoring]].

- [ ] `p3` `[implement]` **Code-stripped LUM maps still block live `apply`.** Base-content maps run
  (DONE 2026-06-20), but code-stripped maps stay blocked — LUM mission maps need a recompiled
  `LUM_Core.u`; `20_Lenz` + the 5 retail cinematics need un-stripped
  `Engine.CameraPoint`/`DeusEx.DeusExDecoration.BeginPlay`. (Package stubbing covers v68 code deps;
  the cinematics' stripped *engine* symbols and first-party `LUM_Core.u` remain out of scope.)

- [ ] `p3` `[implement]` **Multi-actor sub-object manipulation across `poly`/`vertex`/`clip`.** Make
  the `BRUSH:SELECTOR` target token (from `poly set`, e.g. `poly set Wall1:3,5 Wall2:all`) the
  consistent pattern for the other sub-object tools: `brush vertex move` (currently single-brush
  `--at`), `brush clip` (currently single-brush), future `poly` ops. Generalize the target-token
  parser into a shared helper.

- [ ] `p3` `[implement]` **`actor preview` rendering improvements** — filled faces (back-to-front
  grey alpha compositing for stacked/concentric geometry), depth-sorted, pane captions in a header
  strip (not overlaid). See `specs/2026-06-22-uedcli-brush-preview-improvements-design.md`.

- [ ] `p3` `[implement]` **`texture view` + dockerized web viewer with a search UI** — reads the
  tracked `texture-catalog/` + gitignored `.uedcli/textures/`; `view` is the entry verb. See
  `decisions.md` 2026-06-22. Deferred from the 2026-06-22 texture tool.

- [ ] `p3` `[implement]` **`classify prune` / `sync --prune`** — explicitly remove `removed` entries
  from the catalog manifest; v1 only marks them. Deferred from the 2026-06-22 texture tool.

- [ ] `p3` `[implement]` **`test_apply_round_trips_a_base_content_map` self-skips on `Maps/Entry.dx`**
  (no `Light` actor to move) — needs a base-content map fixture that actually has one for full live
  coverage of that test's move-and-apply path.

- [ ] `p3` `[chore]` **Activate the noVNC abs→rel drag bridge on the standing editors.** Bridge is
  DONE and live-verified (`uned/vnc_input_bridge.py` + `entrypoint.sh` `-pipeinput`; image rebuilt
  2026-06-22), but a container only picks it up on a fresh start — recreate `dx-lum-uned`
  (`docker compose up -d --force-recreate`) when no session is mid-drive. Re-confirm in a real
  browser once one runs here.

- [ ] `p3` `[chore]` **Boot-time floating windows (Log Window / Textures browser / boot-time
  `xmessage`) still cover the panes.** Apply the fix in `unrealed/rendering.md`: drop `-log` from
  `entrypoint.sh` + set `X=2000`/`Y=2000` on every `[* Browser]` ini section.

- [ ] `p3` `[chore]` **Thin the board entries to one-liners where possible.** Keep the queues
  scannable; extract spec-grade items to `dev/docs/specs/` (+ `plans/`), leaving a one-line pointer.
  (The 2026-06-25 stage-queue reorg partially addressed the original "thin `todo.md`" intent.)

- **[implement] p3 Reconcile `level doctor --category` to the `class show --category` shape.** Surfaced
  in the `class show --category` spec review (2026-07-18). `level doctor --category` is comma-split +
  case-sensitive with a bare `print;return 2` on a bad value; `class show --category` (specced) is
  repeatable-append + case-insensitive + `_SelectionExit`-listing. Two same-named flags that parse/fail
  differently is a wart — migrate `level doctor --category` to the append + case-insensitive + listing
  shape (keep accepting comma-lists for back-compat if cheap). Spec:
  `specs/2026-07-18-class-show-category-filter.md`.

- **[debug] p3 `stash apply` double-suffixes names (`Pillar_iisch_77db4m`) and its `--at` anchor
  (bbox-min corner) is undocumented.** Cosmetic naming + a doc gap the agent had to probe empirically
  (is `--at` centroid or bbox-min? → bbox-min). (Agent C.)

- **[debug] `actor rotate`/`actor prop` store `Rotation=(Pitch=0,Yaw=8192,Roll=0)` with explicit
  ZERO fields — the editor re-exports `(Yaw=8192)` (zero fields omitted), so the trunk fails H3
  post-verify on its next materialize.** p2. Hit live 2026-07-16 building the native-preview anchor
  fixture (worked around with `actor prop --set "Rotation=(Yaw=8192)"`). Fix: emit/normalize
  FRotator props with zero fields omitted (`rotation.emit_frotator` already does this — the write
  path that stores the composed Rotation doesn't use it), or canonicalize in `normalize`.

- `[implement] p3` **Materialize should fail/WARN loudly instead of silently dropping textures when the composed search path resolves to 0 packages or a referenced package is missing.** Residual hardening of the two now-fixed texture CRITICALs (H3 re-export can't-find-package; symlink-outside-repo 0-package drop). The underlying resolution is fixed (host-native CLI + uniform mount), but the failure mode was *silent* — a dangling glob / missing package dropped every face's `Texture=` with no error and a misleading "0 packages" report. Add: (i) WARN on a 0-package composed path / dangling glob; (ii) materialize fails loudly on a referenced package absent from the load set (vs. a later opaque H3 mismatch).

- `[chore]` **LOW: materialize log noise — `XGetWindowProperty[_NET_ACTIVE_WINDOW] failed (code=1)`
  repeated on every editor run.** p3. Cosmetic; buries the real message.

- `[chore]` p3 **Migrate `utexture.py` + `dxpkg.py` onto the unified `upackage.py` core** (once the
  `actor prop` subcommands build lands it — spec `specs/2026-07-18-actor-prop-subcommands.md` §5.1/
  §10, decision 2026-07-18 10:02 §7). Both are byte-validated decoders, so the migration is a
  deliberate separate pass with the texture-corpus revalidation, not part of the feature change.
  UNBLOCKED 2026-07-18 — the `upackage.py` core landed with the actor-prop build.

- `p3 [chore]` **Dead-code removal follow-ups** (from the 2026-07-19 store-deletion dead-code removal):
  (a) drop `dispatch._apply_set`'s now-unused `packages=` positional param + its two call sites
  (stash-apply, prefab-apply) — deferred from the removal because it's a 4-touch-point `dispatch.py`
  edit; do when `dispatch.py` is quiet. (b) Docs/comment sweep: `export_and_qualify` mentions survive
  in `apply.py`/`stub.py`/`packages.py`/`driver.py`/`architecture.md` (+ a couple of tests), and
  `dispatch.py`'s "no editor_lock" comment references the now-deleted helper — prose only, no live code.

- `p2 [chore/bug]` **`upackage.read_fstring` hard-errors on a Unicode (negative-length) FString** —
  found while running `event graph` on retail maps (2026-07-19). `load_package` on
  `Maps/20_AireGardens.dx` (v69, UED22-written) dies with `FString overruns buffer (len=-66 at
  2305)`, taking the WHOLE package down. Root cause: UE stores a Unicode string/name with a
  **negative** length prefix (abs value = UTF-16LE char count, 2 bytes/char); `read_fstring`
  (`upackage.py:56`) treats any `length < 0` as a hard `SchemaError` instead of decoding UTF-16. The
  offending name-table entry decodes (UTF-16LE) to `'gardens,gardens_shared,gardens_corridor_1,
  gardens_lights,tmp_mig储'` — a long comma-joined multi-**Group** value whose trailing non-ASCII
  char (`储`) is what forced UED to pick the Unicode encoding (Andrzej's "exceeded Group size / not
  a hard error" hunch — it IS a Group value, ~66 chars; the actual trigger is the non-ASCII →
  Unicode path, not a length cap). **Fix:** in `read_fstring`, when `length < 0` read `abs(length)`
  UTF-16LE code units and `.decode('utf-16-le')` (the standard UE convention) — this is the
  low-level shared reader, so it fixes offline loading of EVERY package with a non-ASCII name/string
  (textures, schema, the actor decode `event graph` needs). Keep the hard error for a genuinely
  malformed length; a valid Unicode string must load. Add a regression (synthetic bytes or a small
  committed package with a Unicode name). NB the `_read_name_v61` path may need the same treatment.

- `p3` `[chore] plain `brush build` (no --prop/--texture/--mover-class) hard-requires the games
  config for zero validation value` — every `brush build`/`actor build` runs the author-time ingest
  gate `_validate_ingest_actors` (`dispatch.py:2711`) before emit, which resolves the game's base
  package paths (exit 2 `_NO_GAMES_CONFIG` if `~/.uedcli/config.toml` is absent) to existence-check
  the class + textures. But for a plain shape the class is the hardcoded `Engine.Brush` (always
  exists) and the default texture is `None` (texture loop skipped) — the gate can only ever pass, yet
  it still blocks the stateless generator on config. Consider skipping the gate (or the config
  requirement) when there is nothing substrate-specific to validate: fixed class, no `--texture`, no
  `--prop`, no `--mover-class`. Surfaced 2026-07-21 while exercising the preview verbs.

> The former **Backlog — deferred (someday)** section (stash/prefab v1 remnants + other
> deferred items) moved to [`someday.md`](someday.md), the dedicated parking lane.
