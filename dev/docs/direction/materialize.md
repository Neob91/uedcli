# Materializing the map file — `level materialize`

## What we want

Editing produces the git-tracked T3D trunk; **`level materialize`** is the pure build step that
turns the current trunk into the `.dx`/`.unr` **map file**. It is **map-file output only** — the
T3D tree is the *source*, reached through git, never a build target.

- **Strategy is FULL RE-IMPORT**, never an incremental patch of a live editor: `MAP NEW` on a
  blank level, then re-import the entire trunk in order. Cheap to reason about, crash-recoverable,
  and it cannot leave a stale actor behind.
- **The destination is named explicitly (`--out`), and an existing file is never silently
  clobbered** — materialize refuses and exits 2 naming the file. The opt-in **`--overwrite`**
  allows it, because rebuilding to the same path is the inner loop and forcing a manual `rm` every
  time is friction on the most-run command ([`safety.md`](safety.md)).
- **The build preloads only the packages the level's own actors reference**, not the whole
  installed set. The composed search path still populates the editor's `[Core.System] Paths`, so an
  indirect reference still resolves by demand-load; only the explicit preload is O(level) rather
  than O(install). Hundreds of explicit loads are hundreds of chances for a crash-prone editor to
  wedge.
- **The duplicate-`order_value` warning is emitted here too**, not only by `level doctor`: two
  actors sharing a rank have their CSG precedence decided by a tiebreak nobody chose, and the build
  that ships the map is where that must be unmissable. Warn only — no block, no auto-fix.
- **Committing is the user's own `git`.** A level's durable identity is its **level name**.

### The post-build verify

Every build is checked by a **post-build verify**: the freshly built map file is re-exported
offline and compared against the trunk it was supposed to be built from. It catches a silent
`MAP SAVE` failure or a wedged editor producing a plausible-looking but wrong map — a
build-correctness check, wholly independent of clobber safety.

**The comparison is over TYPED EFFECTIVE VALUES, not text.** Every property of both sides resolves
to its effective value — the value the actor states, or else the class default — decoded according
to the property's declared type from the offline-decoded class schema. **Two actors are equal iff
they would import to the same object.** The editor's own spellings therefore stop being mismatches
to tolerate and become simply the same value: `4.0` and `4` are one float, `(Yaw=8192)` and
`(Pitch=0,Yaw=8192,Roll=0)` are one rotator, an omitted `LightRadius` is the class default. Three
failures fall out fixed rather than papered over: a numeric float compare, "absent means the CLASS
DEFAULT, not zero" (so an `Engine.Camera` that omits an axis is not silently moved 300 uu), and a
genuinely zero-valued scalar, whose zero now comes from the type in the schema rather than from how
the text happens to read.

Two consequences we hold deliberately:

- **No "assume zero" fallback.** Reading the schema needs the game's `.u` packages. They are
  resolved **before the editor container starts**, so an unqualified or unresolvable actor class
  costs ~0.1 s and `exit 2` naming the actor and the class — never a fallback default of zero,
  which is the exact bug the typed compare exists to remove, reintroduced on the one path whose job
  is to detect wrongness.
- **The identity hash and the compare view are separate things.** The compare view may fold every
  editor-owned representation difference it likes. The content hash stays **pure and schema-free**,
  because it is also the preview build-cache key: every equivalence folded into a cache key is a
  chance to serve a map built from something else, whereas a stricter hash can only ever cost a
  rebuild.

### The write side never omits a property to mean zero

Symmetrically, and this is the rule that makes the typed expansion compare-only: **no write path
may leave a property out to mean zero.** An omitted property re-imports as the *class default*, so
the trunk and the `MAP IMPORT` payload state every authored value explicitly. Where this rule was
broken, the map was built **wrong and the verify PASSED**, because both sides shared the mistake.

The write paths get **no class-defaults resolver** to let them omit correctly: that would make the
trunk's bytes depend on which packages happen to be installed, and reproducible trunk bytes are
worth more than one saved line per actor.

### The editor container

The editor build runs in a **warm per-user editor container**, reused across invocations so a build
stops paying a full editor boot. Reuse is gated on a fingerprint covering the image, the mounts and
the mutable package inputs, so any stale input reboots rather than silently building against
yesterday's assets. Acquisition is **non-blocking**: if the container is busy or pinned to a
different configuration, that invocation falls back to its own **per-command ephemeral container**.
The ephemeral container remains the concurrency story — parallel builds compose, with no session
and no queue — and the warm container is a fast path in front of it, never a replacement
([`containers.md`](containers.md)).

A warm-mode failure **fails with a hint, never with a silent automatic retry** on the ephemeral
path: masking whether warm reuse is flaky is worse than one honest failure, and an editor that
misbehaved is torn down rather than left warm.

### The native build's bar is byte-identity

The **native** (editor-free) build's fidelity bar is **byte-identity with UnrealEd's build of the
same trunk** — the `UModel` body plus the name/import/export tables, with the per-save random
package GUID and timestamps excluded. It is reached by porting the editor's **incremental
`bspBrushCSG`** pipeline in place of a point-in-solid classifier, and judged by materializing the
same trunk both ways and byte-diffing.

Byte-identity is a **fidelity** bar, not the functional one: a native build that is merely playable
does not clear it. The point-in-solid classifier stays valid for a "playable and close" build and is
demoted to a differential validation oracle.

If a classification-affecting site were ever found that cannot be reproduced bit-exactly, the honest
fallback is **"abandon literal byte-identity, keep structural and functional parity"** — not
"byte-identical after a snap pass". A snap only rescues sub-ULP noise on an already
topology-identical tree; it cannot cross a topology cliff.

## Lighting, BSP and engine runtime state are build output, not authored state

Lightmaps and rebuilt BSP/geometry are **regenerable build output**. Losing them on a rebuild or a
re-materialize is explicitly a non-concern: they are never part of the level hash, never authored,
and never block an operation.

The same rule governs **engine- and editor-injected per-actor runtime fields** — the ones the
editor's export adds that the authored trunk never wrote: `Region`, `BasePos`/`BaseRot`,
`bSelected`, the mover `SavedPos`/`SavedRot` sentinels. They are never authored, never emitted, and
never compared. The canonical list is `normalize.COMPUTED_PROPS`; the taxonomy behind it is
`../unrealed/t3d.md` "Authored-vs-computed field taxonomy".

**A field earns a place on that list only with evidence that the engine really does overwrite it,
and only when stripping it is right for EVERY class that declares the name** — the set is keyed by
bare name, across all classes. That is why `SavedTrigger` stays off it and must never be added:
`Engine.TriggerLight` declares its own placeable `SavedTrigger`, so adding the name would silently
strip a real authored property from every TriggerLight in the trunk.

Editor-owned *representation* differences are treated the same way at the compare seam and excluded
from the content hash: the engine-assigned `LevelInfo` actor name, geometry quantized to the float32
the engine actually stores, and the polygon `Normal` the importer recomputes from vertex winding. No
authoring discipline can avoid these — a level and its own faithful rebuild legitimately differ in
them.

## Rejected

**Build strategy**

- **Suffix-rebuild** — keep the running editor's level, diff the changed actors, delete and
  re-import only those. A spike proved it cannot work: brushes added via `MAP IMPORTADD` carry no
  `Bound`, so they are never `ACTOR SELECT INSIDE`-selectable and cannot be deleted or replaced.
- **Keeping `--reapply` / `--continue`** on the old `level apply`. Both duplicated what other
  primitives already did; a dedicated deterministic re-materialize verb earns its complexity only
  if the artifact were unrecoverable, and it is not.
- **Keeping apply's 3-way reconcile and a `--to-t3d-tree` output mode** — git is the merge engine,
  and "applying to the tree" is just a commit. Build is map-file-only.
- **Loading the whole composed search path explicitly** — correct but O(install): it explicitly
  loaded 214 packages for a level referencing one, and each load is another chance for the editor
  to wedge. Also rejected: making that whole-set load merely resilient-skip (same size, same wedge
  count), and trimming the games config to fewer categories (that blames the configuration for a
  tool bug).
- **Deriving a per-level package set by walking the import-table transitive closure** — needs a
  closure walker *and* needs every stored reference fully qualified, which T3D class references are
  not.

**The verify**

- **Dropping the post-build verify** along with the clobber guards — it is a build-correctness
  check and is independent of them.
- **Canonicalizing TEXT, and the class-default *contraction* built on it.** A numeric-equality
  predicate had to be *told* that `4.0` and `4` mean the same thing; parsed type-aware they simply
  *are* the same value, and a whole class of problems dissolves rather than being tolerated. One
  mechanism, never two — the contraction was deleted, not kept alongside.
- **Folding the rotator spelling in the durable emit path** — that path feeds the git-tracked
  trunk, the `MAP IMPORT` payload and `actor show`, so folding there rewrites authored data.
- **Fixing the producers and migrating existing trunks** to the editor's spelling — rewrites
  authored files, leaves hand-edited and imported trunks unfixed, and makes every future producer a
  place to forget the rule.
- **Reducing rotator components modulo 65536** while comparing. The editor preserves over-range and
  full-turn values (`Yaw=-65536`, `-131072`, `-81920` all occur in the retail corpus), so a
  normalizing round-trip would rewrite a real rotator to zero and *cause* the mismatch it was meant
  to fix.
- **One hash serving both the compare and the cache key** — it forces the cache key to inherit
  every compare-time equivalence and puts a package-dependent resolver inside a key that must be
  reproducible.
- **Falling back to "assume the default is zero"** for a class that cannot be resolved — the silent
  half-answer, on the one path whose whole job is detecting wrongness.
- **Giving the write paths a defaults resolver so they can omit correctly** — makes the trunk's
  bytes depend on which packages are installed, to save one line per actor.
- **Making an actor's location axes individually optional in the model**, or **maintaining a "was
  it stated?" flag at every mutation site** — the first ripples through bbox, preview, transforms
  and CSG; the second turns one forgotten site into a silently wrong compare.

**Engine-stamped fields**

- **Authoring the mover `SavedPos`/`SavedRot` sentinels into the trunk** to make the compare agree.
  It writes engine *runtime* state into the durable source of truth, has to be repeated for every
  mover forever, and encodes a magic constant belonging to the engine build rather than to the
  level.
- **Adding `SavedTrigger` to the computed set** — and it must never be added.
- **Stripping `bDynamicLightMover` or the `KeyPos[]` array** as injected too. A live materialize
  re-exports all of them verbatim: they are authored content.

**The editor container**

- **Blocking on the warm-container lock.** It serialises multi-minute builds machine-wide.
- **Per-project warm containers** — more idle editors and more lifecycle bookkeeping, while
  same-project builds still contend.
- **A configuration-only reuse fingerprint** — a regenerated stub or a re-synced overlay package
  would silently build stale.
- **Always rebooting the editor process** — forfeits the boot saving, which is the entire point.
- **One automatic ephemeral retry after a warm-mode failure.** It masks whether warm reuse is flaky
  and doubles the cost of a genuinely bad build.

**Native byte-identity**

- **Post-processing the classifier's tree to inflate fragments to match.** Impossible: the fragment
  set is an emergent property of incremental filtering, not recoverable from a collapsed surface
  list.
- **Canonicalizing both sides and comparing topology only** — that is the fallback, not the target.
- **Keeping the synthetic leaf-bounding scaffold behind a flag "just in case"** — it grafts nodes
  the editor never emits, diverging the tree from the thing we are trying to match.
- **Assuming x87 floating point and building an extended-precision emulator up front** — the
  shipped binaries are an SSE2 build, so scalar float is true 32-bit with no 80-bit intermediates.
- **Treating a snap pass as the floating-point fallback** for a classification-affecting divergence
  — dishonest, because a snap cannot cross a topology cliff.

## Refs

`../architecture.md` "The core write pattern" · "The compare view vs the identity hash" ·
"Native (editor-free) materialize" · `../unrealed/t3d.md` "Authored-vs-computed field taxonomy" ·
`../unrealed/quirks.md` "How brushes enter the level" ·
`../spikes/2026-07-25-mover-savedpos-savedrot-engine-stamped/findings.md`
