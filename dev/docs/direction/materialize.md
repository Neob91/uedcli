# Materializing the map file — `level materialize`

## What we want

Editing produces the git-tracked T3D trunk; **`level materialize`** is the pure build step that turns
the current trunk into the `.dx`/`.unr` **map file**. It is **map-file output only** — the T3D tree
is the source, reached through git, never a build target.

- **The build runs entirely inside uedcli, with no UnrealEd editor involved at all — geometry and
  lighting both authored natively.** That is the goal; it is not yet built. Today `level materialize`
  still needs a live editor: `native.unbuilt.assemble_unbuilt` writes every actor (movers included) in
  trunk order, with real brush polys and every typed prop (structs, arrays, mover keyframes,
  `PrePivot`), as an **unbuilt** `.dx`/`.unr`; the editor `MAP LOAD`s it, `MAP REBUILD`s the world CSG
  and each mover's private model, `LIGHT APPLY`s the lighting, then `MAP SAVE`s the result. Writing
  the package ourselves and loading it avoids the editor's add path (`MAP NEW` + `EDIT
  PASTE`/`IMPORTADD`), which GPFs on complex retail geometry and cannot express every authored value;
  the built `Actors` array is faithful, with no append reorder. A native path (behind the temporary
  `UEDCLI_NATIVE_MATERIALIZE=1` test gate) already reaches exact BSP parity with the editor's own
  build on `01_NYC_UNATCOHQ` and bakes the lighting to 99% of its shadow bit-planes byte-identical;
  it still cannot build a mover's private model, and its BSP does not yet match on every level, so it
  is not yet the default. On failure nothing is written — the build exits 2 and the existing `--out`
  file is left untouched.
- **The destination is named explicitly (`--out`), and an existing file is never silently clobbered**
  — materialize refuses and exits 2 naming the file. The opt-in **`--overwrite`** allows it, because
  rebuilding to the same path is the inner loop ([`safety.md`](safety.md)).
- **The build preloads only the packages the level's own actors reference**, not the whole installed
  set. The composed search path still populates the editor's `[Core.System] Paths`, so an indirect
  reference still resolves by demand-load; only the explicit preload is O(level) rather than
  O(install).
- **The duplicate-`order_value` warning is emitted here too**, not only by `level doctor`: two actors
  sharing a rank have their CSG precedence decided by a tiebreak nobody chose. Warn only — no block,
  no auto-fix.
- **Committing is the user's own `git`.** A level's durable identity is its **level name**.

### The post-build verify

Every build is checked by a **post-build verify**: the freshly built map file is re-exported offline
and compared against the trunk it was built from. It catches a silent `MAP SAVE` failure or a wedged
editor producing a plausible-looking but wrong map — a build-correctness check, independent of clobber
safety.

**The comparison is over TYPED EFFECTIVE VALUES, not text.** Every property of both sides resolves to
its effective value — the value the actor states, or else the class default — decoded per the
property's declared type from the offline-decoded class schema. **Two actors are equal iff they would
import to the same object.** The editor's own spellings stop being mismatches and become the same
value: `4.0` and `4` are one float, `(Yaw=8192)` and `(Pitch=0,Yaw=8192,Roll=0)` are one rotator, an
omitted `LightRadius` is the class default. Three failures are fixed by construction: a numeric float
compare, "absent means the class default, not zero" (so an `Engine.Camera` that omits an axis is not
silently moved 300 uu), and a genuinely zero-valued scalar whose zero comes from the type in the
schema.

Two consequences:

- **No "assume zero" fallback.** Reading the schema needs the game's `.u` packages. They are resolved
  before the editor container starts, so an unqualified or unresolvable actor class costs ~0.1 s and
  `exit 2` naming the actor and class — never a fallback default of zero, which is the exact bug the
  typed compare exists to remove.
- **The identity hash and the compare view are separate.** The compare view may fold every
  editor-owned representation difference. The content hash stays **pure and schema-free**, because it
  is also the preview build-cache key: every equivalence folded into a cache key is a chance to serve
  a map built from something else, whereas a stricter hash can only cost a rebuild.

### The write side never omits a property to mean zero

Symmetrically — and this is what makes the typed expansion compare-only: **no write path may leave a
property out to mean zero.** An omitted property re-imports as the class default, so the trunk and the
`MAP IMPORT` payload state every authored value explicitly. Where this rule was broken, the map was
built wrong and the verify PASSED, because both sides shared the mistake.

The write paths get **no class-defaults resolver** to let them omit correctly: that would make the
trunk's bytes depend on which packages are installed, and reproducible trunk bytes are worth more than
one saved line per actor.

### The editor container

The editor build runs in a **warm per-user editor container**, reused across invocations so a build
stops paying a full editor boot. Reuse is gated on a fingerprint covering the image, the mounts and
the mutable package inputs, so any stale input reboots rather than silently building against
yesterday's assets. Acquisition is **non-blocking**: if the container is busy or pinned to a different
configuration, that invocation falls back to its own **per-command ephemeral container**. The
ephemeral container is the concurrency story — parallel builds compose, with no session and no queue —
and the warm container is a fast path in front of it ([`containers.md`](containers.md)).

A warm-mode failure **fails with a hint, never with a silent automatic retry** on the ephemeral path,
and an editor that misbehaved is torn down rather than left warm.

### The native build's bar is byte-identity

The **native** (editor-free) build's fidelity bar is **byte-identity with UnrealEd's build of the same
trunk** — the `UModel` body plus the name/import/export tables, with the per-save random package GUID
and timestamps excluded. It is reached by porting the editor's incremental `bspBrushCSG` pipeline in
place of a point-in-solid classifier, and judged by materializing the same trunk both ways and
byte-diffing.

Byte-identity is a fidelity bar, not the functional one: a native build that is merely playable does
not clear it. The point-in-solid classifier stays valid for a "playable and close" build and is
demoted to a differential validation oracle.

If a classification-affecting site were ever found that cannot be reproduced bit-exactly, the fallback
is **"abandon literal byte-identity, keep structural and functional parity"** — not "byte-identical
after a snap pass". A snap only rescues sub-ULP noise on an already topology-identical tree; it cannot
cross a topology cliff.

## Lighting, BSP and engine runtime state are build output, not authored state

Lightmaps and rebuilt BSP/geometry are **regenerable build output**. Losing them on a rebuild is a
non-concern: they are never part of the level hash, never authored, never block an operation.

The same rule governs **engine- and editor-injected per-actor runtime fields** the editor's export
adds that the authored trunk never wrote: `Region`, `BasePos`/`BaseRot`, `bSelected`, the mover
`SavedPos`/`SavedRot` sentinels. They are never authored, never emitted, never compared. The canonical
list is `normalize.COMPUTED_PROPS`; the taxonomy is `../unrealed/t3d.md` "Authored-vs-computed field
taxonomy".

**A field earns a place on that list only with evidence that the engine really does overwrite it, and
only when stripping it is right for EVERY class that declares the name** — the set is keyed by bare
name across all classes. That is why `SavedTrigger` stays off it and must never be added:
`Engine.TriggerLight` declares its own placeable `SavedTrigger`, so adding the name would strip a real
authored property from every TriggerLight.

Editor-owned representation differences are treated the same way at the compare seam and excluded from
the content hash: the engine-assigned `LevelInfo` actor name, geometry quantized to the float32 the
engine stores, and the polygon `Normal` the importer recomputes from vertex winding. No authoring
discipline can avoid these.

## Rejected

**Build strategy**
- **Suffix-rebuild** — keep the running editor's level, diff the changed actors, delete and re-import
  only those. A spike proved it cannot work: brushes added via `MAP IMPORTADD` carry no `Bound`, so
  they are never `ACTOR SELECT INSIDE`-selectable and cannot be deleted or replaced.
- **`MAP NEW` + re-import the whole trunk via `EDIT PASTE`/`IMPORTADD`** — the editor's paste GPFs
  building the brush model of complex retail geometry, and console verbs cannot express every authored
  value (structs, arrays, keyframes, `PrePivot`). Superseded by assembling the unbuilt package
  natively and `MAP LOAD`ing it.
- **Keeping `--reapply` / `--continue`** on the old `level apply` — both duplicated existing
  primitives.
- **Keeping apply's 3-way reconcile and a `--to-t3d-tree` output mode** — git is the merge engine, and
  "applying to the tree" is just a commit. Build is map-file-only.
- **Loading the whole composed search path explicitly** — O(install): it loaded 214 packages for a
  level referencing one. Also rejected: making that whole-set load merely resilient-skip, and trimming
  the games config to fewer categories.
- **Deriving a per-level package set by walking the import-table transitive closure** — needs a
  closure walker and fully-qualified stored refs, which T3D class references are not.

**The verify**
- **Dropping the post-build verify** along with the clobber guards — it is a build-correctness check,
  independent of them.
- **Canonicalizing TEXT, and the class-default contraction built on it** — parsed type-aware, `4.0`
  and `4` simply are the same value; the text contraction was deleted, not kept alongside.
- **Folding the rotator spelling in the durable emit path** — that path feeds the trunk, the `MAP
  IMPORT` payload and `actor show`, so folding there rewrites authored data.
- **Fixing the producers and migrating existing trunks** to the editor's spelling — rewrites authored
  files and makes every future producer a place to forget the rule.
- **Reducing rotator components modulo 65536** while comparing — the editor preserves over-range
  values (`Yaw=-65536`, `-131072`, `-81920` occur in the retail corpus).
- **One hash serving both the compare and the cache key** — forces the cache key to inherit every
  compare-time equivalence and puts a package-dependent resolver inside a key that must be
  reproducible.
- **Falling back to "assume the default is zero"** for an unresolvable class.
- **Giving the write paths a defaults resolver so they can omit correctly** — makes the trunk's bytes
  depend on which packages are installed.
- **Making an actor's location axes individually optional**, or **maintaining a "was it stated?" flag
  at every mutation site** — the first ripples through bbox, preview, transforms and CSG; the second
  turns one forgotten site into a silently wrong compare.

**Engine-stamped fields**
- **Authoring the mover `SavedPos`/`SavedRot` sentinels into the trunk** — writes engine runtime state
  into the durable source, and encodes a magic constant belonging to the engine build.
- **Adding `SavedTrigger` to the computed set** — and it must never be added.
- **Stripping `bDynamicLightMover` or the `KeyPos[]` array** as injected — a live materialize
  re-exports them verbatim: they are authored content.

**The editor container**
- **Blocking on the warm-container lock** — serialises multi-minute builds machine-wide.
- **Per-project warm containers** — more idle editors and lifecycle bookkeeping.
- **A configuration-only reuse fingerprint** — a regenerated stub or re-synced overlay would silently
  build stale.
- **Always rebooting the editor process** — forfeits the boot saving.
- **One automatic ephemeral retry after a warm-mode failure** — masks whether warm reuse is flaky.

**Native byte-identity**
- **Post-processing the classifier's tree to inflate fragments to match** — the fragment set is
  emergent from incremental filtering, not recoverable from a collapsed surface list.
- **Canonicalizing both sides and comparing topology only** — that is the fallback, not the target.
- **Keeping the synthetic leaf-bounding scaffold behind a flag** — grafts nodes the editor never
  emits.
- **Assuming x87 floating point and building an extended-precision emulator** — the shipped binaries
  are an SSE2 build, so scalar float is true 32-bit.
- **Treating a snap pass as the floating-point fallback** — a snap cannot cross a topology cliff.

## Refs

`../architecture.md` "The core write pattern" · "The compare view vs the identity hash" · "Native
(editor-free) materialize" · `../unrealed/t3d.md` "Authored-vs-computed field taxonomy" ·
`../unrealed/quirks.md` "How brushes enter the level" ·
`../spikes/2026-07-25-mover-savedpos-savedrot-engine-stamped/findings.md`
