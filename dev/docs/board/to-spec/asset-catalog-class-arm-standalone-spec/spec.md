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
the cylinder carries **zero** facing information. The **mesh-local bounding box** is the only place facing
can come from: reported as signed lo..hi per axis, the **thin axis is the mount normal** and the
**asymmetry locates the origin** relative to the mounting face. Same decoder output as a size triple, a
different rendering of it. This is what closes owner finding 7's horizontal half (a subway button floating
off a wall) that a size triple cannot. *(Evidence: `spikes/levelbuild-friction/owner-reports.md` finding 7.)*

**Source:** the decoder returns the mesh `FBox` (`Min`/`Max` FVec) — spike `2026-07-25-native-mesh-decode`,
`Mesh.box`. Reported extents are defined as the box with the mesh's own `Scale` and `Origin` applied
(intrinsic to the asset), rounded to integer Unreal units; the actor's `DrawScale` is **not** applied (it
varies per placement).

> 🔬 **Build-time probe (not an owner question):** whether the stored `FBox` is already post-`Scale`/`Origin`
> or is in raw vertex space is unverified — the decoder returns the box, `Scale` and `Origin` all three, so
> the probe is cheap. The reported value is defined as **post-`Scale`+`Origin`** regardless; the probe only
> settles whether the transform is applied or already baked. Land the finding in `dev/docs/unrealed/`.

**`class show` Facts block** (text):

```
Facts:
  drawtype: DT_Mesh
  mesh:     DeusExDeco.BarStool
  extents:  x -18..18  y -18..18  z 0..34      (mesh-local uu; Scale+Origin applied, DrawScale not)
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
  preview a *candidate placement rotation* before committing it. Measured **~254 ms** per render
  (`the-asset-catalog-class-arm-needs-four-changes`), which replaces a ~2.5-min `preview --game` batch as
  the way to check facing. One shot per invocation; the row's `azimuth`/pose reflects `--rotate`.

Defaults inherited from the engine: `iso` (front-¾) is the single default shot; `--angles` opts into
`front, back, left, right, top, bottom, iso` ("side" spelled `left`/`right` — a mesh is not symmetric). A
render is **~254 ms**, so multi-angle is opt-in (657 mesh classes × several angles is minutes).

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
**union** through `_norm_tags`; `description` is prose and the only scalar — a *different* non-empty
description **exits 2** printing the stored text, `--replace` overwrites, identical text is a no-op.
`unset --tags a,b` removes named tags; bare `unset --tags` clears the field; `unset --all` is the only
clear. Concurrent agents editing disjoint classes never touch one file.

**The `mount:`/`faces:` namespace.** Mount facts — "wall-mounted, face on local +X" — cannot be derived
(§0 forbids it), but an LLM reading the thumbnail plus the signed extents can write them, in the same loop
that fills tags/description. `texture_catalog._norm_tags` only strips and lowercases, so a `mount:wall` /
`faces:+x` tag **survives intact but nothing reserves or validates it** — the convention needs writing down
and a shape check:

- A tag matching `^(mount|faces):` is **namespaced**. `faces:` requires an **axis token** —
  `+x -x +y -y +z -z` (lowercased by `_norm_tags`, so `faces:+X` normalizes in); any other `faces:` value
  **exits 2** naming it. `mount:` requires a non-empty value; the value itself is free text.
- Only the **shape** is validated, never the meaning — refusing a malformed handed-in classification is
  storage hygiene, not inference (§0 intact). What `mount:wall` *means* is authored, not computed.
- These are ordinary tags for `search --tag`, `tags`, and `unset --tags`; nothing new plumbs them.

## 6. Change 4 — value framing

The class arm's value is **placement**, and the spec should say so plainly: with signed extents and a
posed preview, *props stop sinking into floors, floating off walls, and facing the wrong way* — the three
concrete defects in owner findings 7. The arm needs no new decoder beyond the proven spike and is the
cheapest high-value slice available. **Honest limit:** this fixes the *facts* half. It cannot tell you a
button belongs on *that* wall — that is intent, and stays with the independent-reviewer question
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
   `"extents": {"x":[lo,hi], …}` (`--json`), always signed, integer Unreal units, with **`Scale`+`Origin`
   applied and `DrawScale` not**. *Recommended default: adopt as written.* Why: signed lo..hi is the only
   representation that carries facing and origin-relative-to-face; integers are directly comparable to
   `CollisionRadius`/`CollisionHeight` and to human-scale/world coordinates, which are integers.

2. **The `mount:`/`faces:` tag namespace + its validation shape (§5).** *Proposed:* reserve `mount:` and
   `faces:` in class shards; validate `faces:` against the six axis tokens and `mount:` against non-empty;
   validate **shape only**, never meaning. *Recommended default: adopt.* Why: the namespace already
   survives `_norm_tags` but is unguarded, so a typo (`faces:foward`) ships silently; a shape check is
   storage hygiene, not inference, so §0 holds. The **meaning vocabulary** (what mount values exist, how
   `faces:` relates to the thin extent axis) is a craft claim — see 3.

3. **Value framing + the craft line (§6).** *Proposed:* state the arm's headline value as "props stop
   sinking/floating/mis-facing," and add one short line to `docs/leveldesign/general/` tying the thin
   extent axis + `faces:` to mounting. *Recommended default:* keep the value framing in the spec now; land
   the `docs/leveldesign` craft line **only on owner yes**, and do **not** assert "measured on three
   shipped levels" until a before/after exists — new level-design knowledge needs owner approval
   (`CLAUDE.md` "Documentation"), and an inaccurate craft claim is costly and hard to catch.

## 9. Build sequencing — value-first

Each slice is one commit; `docs/usage.md` updated in the same commit; no new test skips versus baseline.

| slice | delivers |
|------|---
| **C0** | prereq — `schema_cache` v2 persists resolved class defaults (gates the rest) |
| **C1** | engine core (class-only cache/index) + mesh decoder promoted to `uedcli/`; **`class show` Facts + `--json`** — signed extents, collision, prepivot, drawtype, parent. **Highest value, cheapest: closes finding 7's footprint/origin half with no rendering.** |
| **C2** | `class preview` — rasterizer promoted; `iso` default, `--angles`, **`--rotate P,Y,R` + `azimuth`**; preview cache pool + `cache gc --previews` |
| **C3** | classification store — `classify set/unset/status`, `tags`, merge rules, **`mount:`/`faces:` namespace validation**, locks, shard-index; `class list --classified/--unclassified --json` |
| **C4** | `class search` (ranked discovery, terms required) + `class prewarm` |
| **C5** | doc sweep — `docs/usage.md`; the proposed `docs/leveldesign` craft line (owner-gated, §8.3) |

## 10. Done when

- `class show <mesh-class>` prints the signed mesh-local `extents`, `collision`, `prepivot`, `drawtype`,
  `parent`, and any stored classification; `--json` carries the §3 shape; a non-mesh class reports
  `extents`/`mesh` as `null`, not a missing key or a traceback.
- `class preview` renders natively (iso default, `--angles`, `--rotate P,Y,R`), reports `azimuth` on the
  row, and produces one file per asset (no montage). `list`/`search --json` never render — they report a
  cached `preview` path or `null`.
- `class classify set/unset/status/tags` round-trip class shards with the merge rules; a bad `faces:` token
  exits 2 naming it; `mount:`/`faces:` tags survive `_norm_tags` and filter through `search --tag`.
- Every checkable claim is pinned by a committed regression test (§11); `bin/test` and `bin/test -k board`
  pass; the three §8 owner decisions are ruled on before build.

## 11. Test coverage (offline, committed fixtures)

Read `dev/docs/rules/tests.md` first. Real DX packages are integration-only (`-m integration`); the
committed `.u` fixtures and `uedcli/tests/pkgfixture.py` back the offline suite.

- **Extents:** a known mesh class reports the exact signed `x/y/z` lo..hi; the values are **signed**, not
  magnitudes; an asymmetric mesh keeps its asymmetry (the origin-locating property); a `DT_Sprite`/`DT_Brush`
  class reports `extents: null`, not a missing key or an exception; `--json` matches §3.
- **Facts provenance:** `collision`/`prepivot`/`drawtype`/`parent` come from resolved class defaults via C0
  (a class with no own value inherits it correctly).
- **Preview:** `iso` default single shot; `--angles` produces the named set; `--rotate P,Y,R` renders and
  the row's `azimuth`/pose reflects it; `list --json` reports `preview: null` when uncached and a path once
  cached; `cache gc --previews` evicts, after which `list --json` reports `null`, not a dangling path; a
  `prewarm`'s output is not evicted by the next process's sweep.
- **Classification:** round-trip; re-`set` unions tags; a conflicting description exits 2 printing the
  stored text, `--replace` overwrites; `unset --tags a,b` removes exactly those; casefolded path; two agents
  on disjoint classes never touch one file; `classify set -` JSONL writes N shards; the outdated/prune flow.
- **Namespace:** `faces:+x` survives `_norm_tags` and filters via `search --tag faces:+x`; `faces:foward`
  exits 2 naming it; `mount:` with an empty value exits 2; `mount:wall` is accepted and free-form.
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
