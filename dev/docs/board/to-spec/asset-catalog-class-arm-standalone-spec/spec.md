# Spec: asset catalog — the CLASS arm (standalone)

**Status:** split out of the unified catalog spec on **2026-08-01** by owner ruling — the class arm gets a
fresh, self-contained spec instead of a third re-gate of the shared 4-kind engine. **Needs an owner gate
before build.** The calls the gate must rule on are in [§8](#8-owner-decisions-to-rule-on); everything else
is agent design, flagged for veto where it is load-bearing.

**Ephemeral**, per `CLAUDE.md`: fold into `dev/docs/architecture.md` + `docs/usage.md` on build, then delete.
The durable homes are [`direction/asset-catalog.md`](../../../direction/asset-catalog.md) (the owner's
decisions — agents may not write it without a yes) and [`rationale/`](../../../rationale/) (the agent's).

**Split siblings:** engine + texture arm — board item `unified-asset-catalog`
([`spec.md`](../../to-build/unified-asset-catalog/spec.md),
[`spec-texture-arm.md`](../../to-build/unified-asset-catalog/spec-texture-arm.md)); audio — board item
`sound-corpus-remeasure`; the four changes folded here — board item
`the-asset-catalog-class-arm-needs-four-changes`.

---

## 0. Governing principle (inherited, not restated)

The tool **lists, reports facts stored in the package, produces the picture, and stores the classification
it is handed — it never infers meaning.** Full text: `direction/asset-catalog.md`. Two consequences bind
this arm: the placement facts below are **read** from the mesh, never derived; and mount/facing meaning is
**written by the LLM into a shard**, never worked out by the tool.

## 1. What the class arm is — a self-contained feature

A user can `class list` today, but cannot **see** a mesh, learn its **footprint or origin**, or record
what a class **is**. This arm adds exactly that, over the classes already on the composed `.u` path. It
depends on **no other catalog arm** — not texture, not audio. It reuses the existing `class` command
family and a small, kind-generic engine core; it ships only the **class** adapter of that core.

### Reuse vs add

| area | reuse (exists today) | add (this arm) |
|--------------------|----------------------------------------------------------------------|---
| enumeration | `classindex` — `list_classes`, `subclasses`, `ancestry`, `is_abstract`, `is_placeable` (fail-open) | `--json`, `--classified`/`--unclassified` on `class list` |
| class defaults | `uprops.resolve_class_defaults` — `DrawType`, `Mesh`, `MultiSkins`, `Skin`, `CollisionRadius`, `CollisionHeight`, `PrePivot` | nothing (prereq C0 persists them) |
| mesh body | native decoder + software rasterizer, proven on 902 meshes (spike `2026-07-25-native-mesh-decode`) | **promote** the spike harness into `uedcli/` (decoder for C1 facts, rasterizer for C2 preview) |
| skins | `utexture` P8 decode (DX class skins are P8) | nothing |
| `class show` | prints the property-schema categories | a **Facts** block (extents/collision/pivot/drawtype/parent) + stored **classification** |
| cache/locks | `cache` noun; `schema_cache` stat-tuple pattern | a class-only derived cache + a git-tracked class-shard store (§5) |

**`class show` is extended, not replaced** *(agent call, flagged for veto)*: the existing property-schema
output stays; a `Facts:` block and a `Classification:` block are appended. `class preview` is a **new**
verb — matching the engine's ruling that `show` (facts) and `preview` (image) are separate verbs.

## 2. The minimal engine core it needs

Kind-generic primitives, written once but registering **only** the class adapter, so the later texture/audio
arms generalize them rather than replace throwaway code:

- **Derived cache** `~/.uedcli/cache/catalog/v<N>/` — `packages/class/<stat-key>.json` (one row per class,
  stat-keyed on `(realpath, size, st_mtime_ns)`, kind segment load-bearing) and `previews/<hh>/<hash>.png`
  (content-addressed). Regenerable, never committed, rebuilt lazily; `class prewarm` is the optional eager
  pass. Reclaimed by `cache gc` (stat-keyed rows whose file changed) and `cache gc --previews`.
- **Preview pool is its own byte budget**, evicted independently of the schema blobs, and the auto-sweep
  must never evict a preview written by the current process (a re-render is minutes, not a re-decode). The
  existing sweep is made recursive. *(Carried verbatim from the engine spec §3a — it applies unchanged.)*
- **Classification store** (§5) — git-tracked, sharded one file per class, casefolded paths, catalog-dir
  flock; plus a per-project `shard-index` roll-up gated on `(file count, max mtime_ns, total size)` so a
  deletion is seen.

**Prerequisite C0 — `schema_cache` v2 persists resolved class defaults.** Today `resolve_class_defaults`
is memoized per-invocation only, so every cold `class show`/`list --json`/`preview` re-resolves defaults
corpus-wide (~14.6 s measured). Add a defaults blob beside the existing schema blobs, bump
`SCHEMA_CACHE_VERSION`, refresh goldens. This gates the class arm. *(From the engine spec, prerequisite 1.)*

## 3. Change 1 — mesh facts as SIGNED MESH-LOCAL EXTENTS (the load-bearing change)

**A size triple (`W×D×H`) answers seating and says nothing about facing.** UE1 collision is a
rotation-invariant **upright cylinder** — `CollisionRadius`/`CollisionHeight`, "always upright regardless
of the actor's rotation", and "a mesh's shape never collides" (✅ `docs/leveldesign/general/actors.md`). So
the cylinder carries **zero** facing information. The **mesh-local bounding box** is where facing
information, if any, lives: reported as signed lo..hi per axis, it *carries* the geometry's asymmetry
relative to the mesh pivot. The design hypothesis — **thin axis = mount normal, asymmetry locates the
origin relative to the mounting face** — is craft, unconfirmed (§8.2); it motivates the signed
representation but is not asserted as fact. Same decoder output as a size triple, a different rendering of
it. What C1 settles cleanly is finding 7's **vertical/seating half** (a prop sunk into the floor); the
**world-facing** half (a subway button floating off a wall) is scoped below.
*(Evidence: `spikes/levelbuild-friction/owner-reports.md` finding 7.)*

**The one mesh-local frame.** The reported `extents`, `class preview`'s `azimuth`, and the preview image
are all expressed in a **single** frame: mesh vertex space with the mesh's own `Scale` applied per-axis
(UE1 axes +X forward, +Y right, +Z up), **pre-`Origin`, pre-`RotOrigin`**. The promoted rasterizer applies
exactly this — `Scale`, then camera yaw/pitch — and auto-centres, so `Origin` (a translation) drops out;
the box, the azimuth, and the picture therefore cannot disagree.

**This is not the world-display frame.** UE1 bakes `Scale`, `Origin`, **and `RotOrigin`** into the
mesh-to-world transform; the rasterizer applies only `Scale`. `Origin` moves the pivot, not the box shape.
`RotOrigin` is a **rotation**: a non-identity `RotOrigin` changes which mesh axis points "forward" in the
world, so the mesh-local thin axis equals the world mount normal **only when `RotOrigin` is identity**. The
tool reports the mesh-local frame and does not claim it equals world facing until the probe below settles
`RotOrigin` prevalence.

**Scope of the SETTLED claim.** The **vertical/seating half** — height, footprint, whether the mesh sits at
`z=0` — is read straight off the box and is settled with no rendering: it closes finding 7's
sinking-into-floors defect. **World-facing** is **UNVERIFIED**, pending the probe (§8.6).

**Source:** the decoder returns the mesh `FBox` (`Min`/`Max` FVec), `Scale`, `Origin`, `RotOrigin` — spike
`2026-07-25-native-mesh-decode`, `Mesh.box`. Reported extents are the box with `Scale` applied, **each axis
re-sorted to lo≤hi** (a negative `Scale` flips an axis, which must not yield `lo>hi`), rounded to integer
Unreal units; `DrawScale` is **not** applied (it varies per placement).

> 🔬 **Build-time probe (a tracked TODO, not an owner question).** When the decoder lands in `uedcli/`,
> measure against real DX deco meshes: (1) whether the stored `FBox` is already post-`Scale`/`Origin` or raw
> vertex space — cheap, since box/`Scale`/`Origin` all decode; the reported value is post-`Scale` regardless,
> so the probe only settles apply-vs-baked; (2) **`RotOrigin`/`Origin` prevalence** — how many deco meshes
> carry a non-identity `RotOrigin`, the field that breaks the mesh-local → world-facing mapping. Real DX
> packages may be content-blocked here; if so this stays a board TODO, **not** an owner question, and
> world-facing stays UNVERIFIED until it runs. Land the finding in `dev/docs/unrealed/`.

**`class show` Facts block** (text):

```
Facts:
  drawtype: DT_Mesh
  mesh:     DeusExDeco.BarStool
  extents:  x -18..18  y -18..18  z 0..34      (mesh-local uu; Scale applied, pre-Origin/RotOrigin, DrawScale not)
  collision: radius 22  height 40
  prepivot:  0,0,0
  parent:    DeusExDeco.Furniture
```

**`--json` shape** (the `facts` object; `extents` is `[lo, hi]` per axis, always signed, never a magnitude):

```json
{"ref": "DeusExDeco.BarStool", "drawtype": "DT_Mesh", "mesh": "DeusExDeco.BarStool",
 "extents": {"x": [-18, 18], "y": [-18, 18], "z": [0, 34]},
 "collision": {"radius": 22, "height": 40}, "prepivot": [0, 0, 0],
 "parent": "DeusExDeco.Furniture", "abstract": false, "placeable": true,
 "preview": "<path>|null",
 "classification": {"tags": ["chair", "mount:floor"], "description": "..."}}
```

**Non-mesh classes:** `DT_Sprite`/`DT_Brush`/`DT_None` carry no `extents`/`mesh`; the fields are **`null`**,
never omitted (absence stays distinguishable from "not indexed"). `collision`/`prepivot`/`parent` are
reported for every class.

## 4. Change 2 — `class preview --rotate P,Y,R` and the azimuth field

The `--out` name already suffixes the angle (`deusexdeco-barstool-iso.png`), but a picture of a wall lamp
does not say **which yaw points it at the player**, so the agent still guesses — how a flat light lands 90°
off. Two additions, both on the existing rasterizer, no new decoder:

- **Azimuth on the row.** Every preview row states the camera's mesh-local yaw in Unreal rotator units
  (65536 = 360°), so the agent can read which yaw in the image faces the viewer. `class preview` emits
  `<ref>\t<path>` by default; `--json` and `--skeleton` rows carry an `azimuth` field. This is a field, not
  a new render.
- **`--rotate P,Y,R`** renders the mesh at that mesh-local rotator pose before shooting — the pose oracle:
  preview a *candidate placement rotation* before committing it, replacing a ~2.5-min `preview --game`
  batch as the way to check facing. One shot per invocation; the row's `azimuth`/pose reflects `--rotate`.

**Per-render cost (one figure, used throughout):** **~254 ms flat / ~332 ms textured, at 256 px**
(`the-asset-catalog-class-arm-needs-four-changes`; the rasterizer dominates — decode is only ~2–13 ms). A
class thumbnail is textured, so budget the ~332 ms figure. Multi-angle is therefore opt-in (657 mesh
classes × several angles is minutes). Defaults inherited from the engine: `iso` (front-¾) is the single
default shot; `--angles` opts into `front, back, left, right, top, bottom, iso` ("side" spelled
`left`/`right` — a mesh is not symmetric).

**Error dispositions** (mirroring `direction/asset-catalog.md` "Produce the picture, or a named error"):

- A **per-ref `class preview`** whose `Mesh` default is unresolvable, or whose skin fails to decode, **exits
  2** naming the offending class/mesh — never a traceback. This is distinct from a **non-mesh** class
  (`DT_Sprite`/`DT_Brush`/`DT_None`), which is **not** an error: `preview` has nothing to render and the
  `preview` field is `null` (§3).
- **Enumeration keeps listing:** `list --json`/`search --json` report `preview: null` for a class whose
  preview cannot be produced and continue — they never render, and a failing class does not abort the list.
- **No project / no package search path:** any new verb invoked with no composed `.u` path **exits 2**
  ("no package search path") — not empty success, not a traceback.

## 5. Change 3 — the class classification store, with a reserved `mount:`/`faces:` namespace

**Store.** One shard per class, git-tracked, at `<catalog>/classified/class/<package>/<classname>.json`
(casefolded path; authored spelling preserved in the payload). Identity is the **name** (`Package.Class`),
so the shard `ref` equals identity and is write-once (it also names an outdated entry when a class is
renamed/removed). Payload:

```json
{"kind": "class", "ref": "DeusExDeco.BarStool",
 "tags": ["chair", "mount:floor", "faces:+z"],
 "description": "bar stool; DX places these along the DiveBar counter"}
```

No `colors` (that is the texture pre-fill). **Merge on re-`set`** *(owner ruling, engine spec)*: `tags`
**union** through the class engine core's **own** tag-normalizer (a `_norm_tags`-equivalent — strip,
lowercase, de-dupe). The legacy `texture_catalog._norm_tags` is cited only as **behaviour to match**, not a
dependency: that module is slated for deletion (`direction/asset-catalog.md`, "the legacy name-keyed
texture catalog is deleted"). `description` is prose and the only scalar — a *different* non-empty
description **exits 2** printing the stored text, `--replace` overwrites, identical text is a no-op.
`unset --tags a,b` removes named tags; bare `unset --tags` clears the field; `unset --all` is the only
clear. Concurrent agents editing disjoint classes never touch one file.

**The `mount:`/`faces:` namespace.** Mount facts — "wall-mounted, face on local +X" — cannot be derived
(§0 forbids it), but an LLM reading the thumbnail plus the signed extents can write them, in the same loop
that fills tags/description. The tag-normalizer only strips and lowercases, so a `mount:wall` /
`faces:+x` tag **survives intact but nothing reserves or validates it** — the convention needs writing down
and a shape check:

- A tag matching `^(mount|faces):` is **namespaced**. `faces:` requires an **axis token** —
  `+x -x +y -y +z -z` (the normalizer lowercases, so `faces:+X` normalizes in); any other `faces:` value
  **exits 2** naming it. `mount:` requires a non-empty value; the value itself is free text.
- Only the **shape** is validated, never the meaning — refusing a malformed handed-in classification is
  storage hygiene, not inference (§0 intact). What `mount:wall` *means* is authored, not computed.
- These are ordinary tags for `search --tag`, `tags`, and `unset --tags`; nothing new plumbs them.

## 6. Change 4 — value framing

The class arm's value is **placement**, and the spec should say so plainly: with signed extents and a
posed preview, *props stop sinking into floors, floating off walls, and facing the wrong way* — the three
concrete defects in owner findings 7. The arm needs no new decoder beyond the proven spike and is the
cheapest high-value slice available. **Two honest limits.** (1) The *seating* defect (sinking) is closed
by the signed extents outright; *floating* and *mis-facing* are addressed by the **posed preview** an agent
looks at — the extents-based `faces:` signal that would settle them without a render stays UNVERIFIED
pending the `RotOrigin` probe (§3, §8.6). (2) This fixes the *facts* half only. It cannot tell you a button
belongs on *that* wall — that is intent, and stays with the independent-reviewer question
(`owner-reports.md` open question 1).

*(The stronger claim — "measured on three shipped levels" — is a craft/measurement assertion, not yet
evidence. It is proposed in §8, owner to confirm, and is not stated as fact until a before/after exists.)*

## 7. Verb surface

`class` keeps the same verb family as the other kinds (reduced only where the artifact does not exist):

| Verb | Role |
|-----------------------------------------------------------------------|---
| `class list [--flat] [--classified\|--unclassified] [--json] …` | enumerate (existing tree/flat; `--classified`/`--unclassified` require `--flat`; `--json` carries `preview: path\|null`, cached only) |
| `class search <terms…> [--tag T] [--subclass-of FQCN] [--drawtype DT] [--include-abstract] [--json]` | ranked discovery; terms REQUIRED (term-less → exit 2 pointing at `list`) |
| `class show <ref>… \| -` | property schema (existing) + **Facts** + **Classification** |
| `class preview <ref>… \| - [--out DIR] [--angles …] [--rotate P,Y,R]` | the sole image producer; `<ref>\t<path>`, `--skeleton` → JSONL carrying the path + `azimuth` |
| `class classify set <ref> --tags … --description … \| -` | record; `-` reads JSONL; merges (§5) |
| `class classify unset <ref>… \| - [--tags[=T,…]\|--description\|--all]` | undo |
| `class classify status [--json]` / `tags [--json]` | progress / vocabulary → stdout |
| `class classify list-outdated` / `prune [--outdated]` | shards whose class no longer resolves |
| `class prewarm [--package P] [--force]` | eager index/decode/render ahead of an offline session |

Inherited conventions: producers print to stdout one item per line, summaries to stderr; `-` reads a ref
set from stdin (JSONL for `classify set`), empty stdin is a clean exit-0 no-op; a request that cannot be
fully satisfied exits 2 naming the value; no Python traceback reaches the user; a truncated result prints
the cap and withheld count on stderr. `--include-abstract` is the single spelling of the placeable axis
(no `--placeable`).

## 8. Owner decisions to rule on

The gate accepts or revises each. These touch product intent / `docs/leveldesign` and are **not**
settled by this spec.

1. **Signed-extents output format (§3).** *Proposed:* `extents: x lo..hi  y lo..hi  z lo..hi` (text) and
   `"extents": {"x":[lo,hi], …}` (`--json`), always signed, integer Unreal units, in the one mesh-local
   frame — **`Scale` applied, pre-`Origin`/`RotOrigin`, each axis re-sorted lo≤hi, `DrawScale` not**.
   *Recommended default: adopt as written.* Why: signed lo..hi is the only representation that carries the
   pivot-relative asymmetry the facing hypothesis (2, 6) rests on; integers are directly comparable to
   `CollisionRadius`/`CollisionHeight` and to human-scale/world coordinates, which are integers.

2. **The `mount:`/`faces:` tag namespace + its validation shape (§5).** *Proposed:* reserve `mount:` and
   `faces:` in class shards; validate `faces:` against the six axis tokens and `mount:` against non-empty;
   validate **shape only**, never meaning. *Recommended default: adopt.* Why: the namespace already
   survives tag normalization but is unguarded, so a typo (`faces:foward`) ships silently; a shape check is
   storage hygiene, not inference, so §0 holds. The **meaning vocabulary** (what mount values exist, how
   `faces:` relates to the thin extent axis) is a craft claim — see 3.

3. **Value framing + the craft line (§6).** *Proposed:* state the arm's headline value as "props stop
   sinking/floating/mis-facing," and add one short line to `docs/leveldesign/general/` tying the thin
   extent axis + `faces:` to mounting. *Recommended default:* keep the value framing in the spec now; land
   the `docs/leveldesign` craft line **only on owner yes**, and do **not** assert "measured on three
   shipped levels" until a before/after exists — new level-design knowledge needs owner approval
   (`CLAUDE.md` "Documentation"), and an inaccurate craft claim is costly and hard to catch.

4. **[CARRIED — do not resolve] A general file-fact OVERRIDE field on the class shard.**
   `direction/asset-catalog.md` says class curation is "a description, plus **an override where the file
   fact is wrong**," but the same doc's *Rejected* list kills "a curated-vs-derived override model for
   `placeable`," and this arm's shard payload `{kind, ref, tags, description}` carries **no** general
   override — so as specced a wrong file fact cannot be corrected at all. Raised independently by two of
   three gate reviewers (2026-07-26); board item `does-class-curation-get-a-general-file-fact`. *This is the
   owner's contradiction to resolve, not the implementer's:* either the topic drops the override clause, or
   the shard gains a field. *Recommended default:* **defer to the owner** — do not add a field on our own
   read. (The §4b texture-colours override is the one existing instance and stays either way.)

5. **[CARRIED — do not resolve] `classify set -` JSONL is a THIRD `-` convention, pending a
   `conventions.md` carve-out.** `direction/conventions.md` still says "exactly TWO stdin conventions …
   never add a third"; the JSONL row set on `classify set -` (§7) is that third, ruled "it's fine"
   (2026-07-26) but not yet written into the protected doc. Board item
   `conventions-md-needs-a-calibrated-carve-out` holds the proposed carve-out text verbatim. **C3 depends on
   it** — the classification store cannot ship its batch path until the carve-out lands. *Recommended
   default:* **land the carve-out, then build C3;** do not ship the third convention while the doc forbids
   it.

6. **Facing-scope call (§3).** *Proposed:* scope C1's SETTLED claim to the **vertical/seating** half
   (height, footprint, `z=0` seating), and mark **world-facing UNVERIFIED** pending the `RotOrigin`/`Origin`
   prevalence probe — the mesh-local thin axis equals the world mount normal only when `RotOrigin` is
   identity, which is unmeasured (and may be content-blocked here → a board TODO, not an owner question).
   *Recommended default: adopt the scoped claim* — build C1's seating/footprint now, do not assert
   world-facing until the probe runs. Alternative the gate may pick: block C1's facing claim entirely until
   the probe is unblocked.

## 9. Build sequencing — value-first

Each slice is one commit; `docs/usage.md` updated in the same commit; no new test skips versus baseline.

| slice | delivers |
|------|---
| **C0** | prereq — `schema_cache` v2 persists resolved class defaults (gates the rest) |
| **C1** | engine core (class-only cache/index) + mesh decoder promoted to `uedcli/`; **`class show` Facts + `--json`** — signed extents, collision, prepivot, drawtype, parent; the `RotOrigin`/`Origin` probe (§3). **Highest value, cheapest: closes finding 7's seating/footprint half with no rendering; world-facing stays UNVERIFIED (§8.6).** |
| **C2** | `class preview` — rasterizer promoted; `iso` default, `--angles`, **`--rotate P,Y,R` + `azimuth`**; preview cache pool + `cache gc --previews`; per-ref/enumeration error dispositions (§4) |
| **C3** | classification store — `classify set/unset/status`, `tags`, merge rules, **`mount:`/`faces:` namespace validation**, locks, shard-index; `class list --classified/--unclassified --json`. **Blocked on the `conventions.md` third-`-` carve-out (§8.5) before its `classify set -` JSONL path ships.** |
| **C4** | `class search` (ranked discovery, terms required) + `class prewarm` |
| **C5** | doc sweep — `docs/usage.md`; the proposed `docs/leveldesign` craft line (owner-gated, §8.3) |

## 10. Done when

- `class show <mesh-class>` prints the signed mesh-local `extents`, `collision`, `prepivot`, `drawtype`,
  `parent`, and any stored classification; `--json` carries the §3 shape; a non-mesh class reports
  `extents`/`mesh` as `null`, not a missing key or a traceback.
- `class preview` renders natively (iso default, `--angles`, `--rotate P,Y,R`), reports `azimuth` on the
  row, and produces one file per asset (no montage). `list`/`search --json` never render — they report a
  cached `preview` path or `null`. A per-ref `preview` whose `Mesh` is unresolvable or whose skin fails to
  decode **exits 2** naming it; a non-mesh class is `null`, not an error (§4).
- Any new verb run with no composed `.u` path **exits 2** ("no package search path"), never empty success
  or a traceback.
- `class classify set/unset/status/tags` round-trip class shards with the merge rules; a bad `faces:` token
  exits 2 naming it; `mount:`/`faces:` tags survive tag normalization and filter through `search --tag`.
- Every checkable claim is pinned by a committed regression test (§11); `bin/test` and `bin/test -k board`
  pass; the §8 owner decisions (the three design calls, the two carried-forward questions, and the
  facing-scope call) are ruled on before build.

## 11. Test coverage (offline, committed fixtures)

Read `dev/docs/rules/tests.md` first. Real DX packages are integration-only (`-m integration`); the
committed `.u` fixtures and `uedcli/tests/pkgfixture.py` back the offline suite.

- **Extents:** a known mesh class reports the exact signed `x/y/z` lo..hi in the one mesh-local frame
  (`Scale` applied, pre-`Origin`/`RotOrigin`); the values are **signed**, not magnitudes; a **negative
  `Scale`** on an axis still reports `lo≤hi` (re-sorted after scaling, never `lo>hi`); an asymmetric mesh
  keeps its asymmetry (the origin-locating property); a `DT_Sprite`/`DT_Brush` class reports `extents:
  null`, not a missing key or an exception; `--json` matches §3.
- **Facts provenance:** `collision`/`prepivot`/`drawtype`/`parent` come from resolved class defaults via C0
  (a class with no own value inherits it correctly).
- **Preview:** `iso` default single shot; `--angles` produces the named set; `--rotate P,Y,R` renders and
  the row's `azimuth`/pose reflects it; `list --json` reports `preview: null` when uncached and a path once
  cached; `cache gc --previews` evicts, after which `list --json` reports `null`, not a dangling path; a
  `prewarm`'s output is not evicted by the next process's sweep.
- **Preview errors:** a per-ref `class preview` on a class whose `Mesh` default is unresolvable **exits 2**
  naming the class/mesh (no traceback); a class whose skin fails to decode likewise; a non-mesh class is
  `null`, **not** an error (distinct from the above); `list --json` over a set containing a preview-failing
  class reports its `preview: null` and still enumerates the rest.
- **No project:** each new verb (`show`/`preview`/`classify …`/`search`/`list`) invoked with no composed
  `.u` path **exits 2** ("no package search path"), not empty success and not a traceback.
- **Classification:** round-trip; re-`set` unions tags; a conflicting description exits 2 printing the
  stored text, `--replace` overwrites; `unset --tags a,b` removes exactly those; casefolded path; two agents
  on disjoint classes never touch one file; `classify set -` JSONL writes N shards; the outdated/prune flow.
- **Namespace:** `faces:+x` survives tag normalization and filters via `search --tag faces:+x`;
  `faces:foward` exits 2 naming it; `mount:` with an empty value exits 2; `mount:wall` is accepted and
  free-form.
- **CLI shape:** `show` vs `preview` output shapes; `search` term-less → exit 2 pointing at `list`;
  `--classified`/`--unclassified` without `--flat` → exit 2; empty stdin → exit 0; a truncated result reports
  the cap and withheld count on stderr; no traceback on a bad class name.

## 12. Non-goals

- **Any tool-side inference of mount/facing meaning** — that is the LLM's, written into a shard (§0).
- **Multi-frame/animation frame selection** for previews — frame 0; a *characteristic* frame is a later
  quality question (spike `2026-07-25-native-mesh-decode`, deferred).
- **Mesh export** (`.3d`/glTF) — the decoder exists, but exporting is not a catalog need.
- **Similarity for classes** — texture-only in v1.
- **Replacing `preview --game`** — the in-game path stays for real-lighting hero shots.
- **A curated role/category taxonomy** — the superclass and `--subclass-of` already say what a class is for
  (`direction/asset-catalog.md`).
