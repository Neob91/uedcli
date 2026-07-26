# Spec: asset catalog — the TEXTURE arm

**Status:** split out of the unified spec 2026-07-26. **NOT READY TO BUILD — four owner decisions are
open** (listed below). This arm holds every irreversible decision in the catalog design, which is why it
was split: its identity function is frozen and is every tracked shard's path, so a wrong call here
destroys authored work and cannot be corrected without an explicit migration.
**Ephemeral:** fold into `architecture.md` + `usage.md` on build, then delete.

> **Part of the split asset-catalog spec set** (split 2026-07-26 after two spec-gate rounds returned
> ~103 findings and the churn proved to be concentrated in the texture and audio arms — see
> `board/inbox.md`). The shared engine, storage layout, verb surface, decisions and prerequisites live in
> **[`2026-07-26-asset-catalog-engine.md`](2026-07-26-asset-catalog-engine.md)**, which every arm depends
> on and which is built first. Sibling arms:
> [class](2026-07-26-asset-catalog-class-arm.md) ·
> [texture](2026-07-26-asset-catalog-texture-arm.md) ·
> [audio](2026-07-26-asset-catalog-audio-arm.md).

---

## OPEN OWNER DECISIONS — this arm does not enter the gate until these are settled

1. **The procedural parameter hash conflicts with an owner *Rejected* bullet.**
   `direction/asset-catalog.md` rejects "**Content-hashing everything** — a class fingerprint over default
   properties is brittle", reason: "any game patch would orphan the curated description." §3c below hashes
   procedural parameters **resolved against the class defaults**, so a patch to `Fire.u` re-keys every
   procedural shard *with no uedcli change*, which §3b's owner-approved-migration guard cannot catch.
2. **RULED 2026-07-26 — `bAlphaTexture` is a fact.** Graded 8-bit alpha (BC2/BC3) is not covered by
   `masked`, so a glass pane and its opaque twin are one identity with one opaque preview. Identity stays
   **pixels only** — the ruling is not reopened — and `bAlphaTexture` joins `facts` beside `masked`, same
   read rule (stored tag else resolved class default), same cost, and filterable. The twins remain one
   identity; they become *distinguishable*. See "Facts this arm reports".
3. **RULED 2026-07-26 — classification CARRIES FORWARD by `Package.Name`, automatically.** *(Owner: "should
   accept `Package.Name` — nobody's gonna know the refs, they're internal. The classification should be
   pulled from the last version for that `package.name` texture.")*

   When indexing produces a **new identity** for a ref that an **outdated shard** already names, the new
   identity **adopts** that shard's classification rather than reading as unclassified. So retouching
   `LUM_CoreTex.SomeWall` keeps its tags and description; nothing is retyped and `prune --outdated` no
   longer destroys accurate work.

   - **The user-facing key is the REF, never the digest.** Any verb that addresses a classification takes
     `Package.Name`; a sha256 is internal and must never be something a person types. That includes the
     manual form, `classify reassign <ref>`, for the case where automatic adoption did not fire.
   - **This makes the write-once `ref` load-bearing for carry-forward, not just for labelling outdated
     entries** — state that where the field is defined, because it changes why it exists.
   - **Adoption is RECORDED, not silent.** An adopted classification is marked (e.g.
     `adopted_from: <old-identity>`) and `classify status` counts it, because the pixels genuinely changed
     and the description may now be wrong — repaint a wall green and "brown rusted panel" carries forward
     with it. **OPEN, small:** decide whether adopted entries also surface in a `--needs-review` listing.
     Do not make adoption invisible.
   - Ambiguity rule needed: if two outdated shards name the same ref (edited twice), adopt the **most
     recent** and say so. If a ref resolves to an identity that is *already* classified, adoption does not
     fire — the existing classification wins.
4. **Procedural class routing and the out-of-table case.** The declared property table must match **by
   descent, not exact class name** — `TNMScriptedTexture` (a mod-defined `ScriptedTexture` subclass, 4
   exports) already exists on this install. An out-of-table pixel-less class currently falls through to a
   pixel hash over **zero pixels**, collapsing every such texture to one identity.

**Measurement correction, recorded before anything is built on it.** §3c's "208 + 42 + 14 + 8 + 50 + 4 =
326 procedural exports" reproduces only by walking `System.bak/`, `TNM2/`, `2027/`, `IWR/` and `Maps/`. On
the **composed search path** (119 package stems) the real figures are **40 `FireTexture`, 8 `WetTexture`,
1 `WaveTexture`, 0 `IceTexture`, 0 `ScriptedTexture` = 49**. So the entire `ScriptedTexture` apparatus is
sized by "50 of 326" of which **zero are reachable**. Re-measure on the composed path before sizing any of
this work.

---

### 3b. Per-project tracked classification — git-committed, sharded

Root: the project's catalog dir (`uedcli.toml` `catalog` key), default **`asset-catalog/`**.

```
<catalog>/classified/texture/<hh>/<pixel-hash>.json
<catalog>/classified/class/<package>/<classname>.json
<catalog>/classified/sound/<package>/<name>.json
<catalog>/classified/music/<package>/<name>.json
```

One file per classified thing, so disjoint edits never touch the same file → conflict-free
`git merge` under concurrent agents, mirroring the per-actor `.t3d` ethos. **Name-keyed paths are
casefolded** (authored spelling preserved in the payload): refs resolve case-insensitively
everywhere else in uedcli, so a case-sensitive path would let two agents write two shards for one
class.

```json
{"kind": "texture", "identity": "<hex-sha256>",
 "ref": "CoreTexMetal.Area51Wall_A",
 "tags": ["metal", "wall", "industrial"],
 "description": "riveted metal wall panel; DX uses it across Area 51 interiors",
 "colors": ["grey", "brown"], "colors_source": "set"}
```

**`classify set` MERGES into an existing shard — it does not replace it.** *(Owner ruling,
2026-07-26.)* Two agents (or one agent twice) will classify the same identity, and the earlier work must
survive. "Merge" needs a rule per field, because only one of them is a set:

| field | on re-`set` |
|---------------|---
| `tags` | **union** with what is stored, deduped and normalized through `_norm_tags`. Additive, so a second agent's tags never displace the first's. |
| `colors` | **replaced**, and `colors_source` becomes `"set"` — an explicit colour override is a single answer, and the override already beats the derived list by design (§4b). |
| `description` | **prose, and the only scalar** — see the rule below. |

**A conflicting `description` is REFUSED, not overwritten.** If the shard already holds a *different*,
non-empty description, `classify set --description …` **exits 2**, naming the ref and printing the stored
text, and `--replace` is the explicit opt-in that overwrites it. Re-setting the *same* text is a no-op,
and filling in an empty description is an ordinary merge. Rationale: `direction/safety.md` makes
"never irretrievably clobber" the tool's uniform rule and requires that same-target concurrent edits be
"DETECTED and REFUSED, not lost", and a curated description is the most expensive thing in the catalog to
recreate — `direction/asset-catalog.md` calls classification "the product". Merging prose is not
possible, so refusing is the only option that does not silently destroy it.
*(This last rule is the agent applying `safety.md` to the one field the merge ruling cannot cover —
flagged for veto, not presented as a separate owner decision.)*

**Sharding does NOT make this unnecessary, and that is the subtle part.** §3b's conflict-free-merge
argument is about *git*: disjoint identities are disjoint files, so `git merge` never conflicts. But
identity ignores names, so two agents classifying two **differently named** refs whose pixels are
identical (`CoreTexMetal.X` and `LUM_CoreTex.X`) write the **same shard** — disjointness by asset *name*,
which is what an agent can see, is not disjointness by *identity*, which is what the path is. Without
merge the second write silently wins while the write-once `ref` still names the first, so
`classify list-outdated` would later report a ref that does not describe the stored text. So
**`classify set` must also report on stderr when it is writing an identity that is already classified
under a different `ref`** — the agent has no other way to know it just edited what it thought was a
different texture.

**There is deliberately NO `classify clear`.** `unset --all` already is it; a second spelling of one
operation is the back-compat cruft `direction/conventions.md` forbids on arrival. What merge *does*
require is the ability to remove a NAMED tag — with `set` additive and bare `unset --tags` clearing the
whole field, dropping one wrong tag would otherwise mean clearing and retyping the rest. Hence
`unset --tags a,b`.

Everything in `tags`/`description` comes from the LLM. Note the description carries *usage* — that is
where "where is this used" lives now, written by whoever investigated it, rather than computed.

For **pixel-hashed textures** the `ref` is **write-once** — set at classify time, never appended —
existing only to identify outdated entries. A *mutable* ref list would reintroduce a per-hash write
conflict (two agents classifying two refs of the same image would read-modify-write one shard).

**Textures are stored by PIXEL HASH, never by name, and the identity function is FROZEN.**
*(Owner, 2026-07-26 — reaffirming the design, so no later revision quietly reverts it.)* A texture's
key is `sha256(w, h, RGB)` over its decoded pixels; the name plays no part in it. That is what makes a
classification survive a rename, a repack, or the same image appearing in two packages, and it is why
the same digest doubles as the preview artifact's content address (§3a) with no second hash.

**ONLY PIXELS ARE HASHED.** *(Owner ruling, 2026-07-26, resolving a structural gate finding.)* The
digest covers `(w, h, RGB)` and **nothing else** — in particular the **transparency mask is NOT part of
identity**, even though the decode path returns one (`utexture.TextureResolver.resolve_masked()` yields
`(w, h, rgb, mask)`, and the gated `specs/2026-07-25-native-texture-formats.md` §8-D derives the mask
from pixel data: P8 index-0, BC1 punch-through, BC2/BC3 block alpha).

Two consequences follow, and **both are binding**, because §3a addresses the preview artifact by this
same digest ("for textures the preview hash IS the identity — no second digest"):

1. **A texture preview PNG is plain, opaque RGB at the texture's own size** — no alpha channel, no
   resampling. If it ever carried the mask, its pixel digest would stop equalling the identity and the
   "no second digest" invariant would break; and since the digest is every shard's path, "improving"
   the preview to RGBA later would silently **re-key every shard**. Do not do it. This is the specific
   trap all three 2026-07-26 gate reviewers independently flagged.
2. **Cut-out-ness reaches the agent as a FACT, not as a picture.** Because the preview is opaque, a
   masked texture's holes are not visible in it — which is fine, and is why §4d exists: `masked` is
   reported as a queryable fact and `--masked` filters on it. The agent is *told*, rather than having
   to *see* it. (`level preview --native` renders masked faces opaque for the same reason, which the
   level-building friction log found makes it a free index-0 detector.)

Accepted cost, stated so nobody rediscovers it as a bug: two textures with identical RGB but different
masks are **one identity and share one preview file**. They are the same image; they differ only in a
flag that `masked` reports separately.

The function is **frozen**: `(w, h, RGB)` in that order, over the decoded RGB triples, and a committed
golden (ref → hex digest over `CoreTexWater.utx`) pins it. **Pin the byte encoding too, because a golden
only fixes whatever the first builder happened to write.** The existing `texture_catalog.image_hash`
digests `b"%d:%d:" % (w, h)` followed by `rgb.tobytes()` and returns a **`sha256:`-prefixed** string,
while §9 mandates a bare hex digest: adopt that exact byte encoding and strip the prefix, so the frozen
function is a known, already-exercised one rather than a fresh invention.

**Consequence to state plainly: `texture list` is NOT a cheap verb on a cold cache.** A texture's identity
*is* its decoded pixels, so answering `list` — or `--classified`/`--unclassified`, which need the identity to
look up a shard — requires decoding the corpus (§9's measured ~26.4 s / ~50 s cold). That is in tension with
`direction/asset-catalog.md`'s promise that "no exploratory command can ever trigger a long render", so the
spec must be explicit rather than let a user discover it: the first `texture list` on a cold cache announces
that it is indexing, with progress on stderr, and every later run is served from the index. It is a *decode*,
not a *render* — no PNG is produced — which is what keeps decision 7 intact. **And because the decode has
already been paid for, index-building writes the preview PNG it has in hand**; otherwise the corpus is
decoded twice, once to key it and once to look at it. This is the one narrow exception to "only `preview`
produces artifacts", and it is invisible: the artifact is a cache entry, `list` still prints no path unless
one is cached. Every tracked shard's *path* is that digest,
so any change to what the decode path emits silently re-keys every shard at once — every
classification reads back "unclassified" and becomes a prunable outdated entry. **This is the one
irreversibility in the design that can destroy authored work**, so the identity function is changed
only by an explicit, owner-approved migration that rewrites the shards, never as a side effect of
touching the decoder.

Two corollaries worth stating, because they are easy to get backwards:

- **Adding a FACT never re-keys anything.** Facts (§4) are read from the package and stored in the
  derived cache, outside the identity. Recording a new one — `group`, or a palette-derived flag — is
  purely additive and safe at any time. The hazard is *changing the RGB the decoder emits*, not
  *reading more about the texture*.
- **Identity deliberately ignores everything but pixels.** Two textures with the same pixels in
  different packages, groups, or under different names are ONE classifiable thing, and classifying
  either classifies both. The write-once `ref` (below) exists only so an outdated entry can be named
  in a report.

### 3c. Procedural textures — hashed on what makes them DISTINCT

*(Owner ruling, 2026-07-26, resolving a structural gate finding.)*

A **procedural** texture stores **no pixels**: measured, every `FireTexture`, `WetTexture`,
`WaveTexture`, `IceTexture` and `ScriptedTexture` carries mips whose `DataCount == 0`
(208 + 42 + 14 + 8 + 50 + 4 across the Deus Ex tree — `specs/2026-07-25-native-texture-formats.md`).
Its pixels are **generated at runtime from its stored parameters**. So the pixel hash of §3b has
nothing to bite on, and an earlier draft's consequence — that water and fire are enumerable but
*permanently unclassifiable* — is rejected.

**A procedural texture is identified by a hash over the properties that make it distinct.** This is
the same principle as §3b, not an exception to it: a procedural texture's *content* IS its parameter
set, because that set is what determines every pixel the engine will draw. Two `FireTexture`s with
identical parameters render identically and are deliberately one classifiable thing, exactly as two
byte-identical images are.

Rules this must satisfy:

- **The distinguishing property set is declared PER CLASS, and is FROZEN like §3b's function.** It is
  the stored tagged properties that determine the generated output (a `FireTexture`'s fire parameters,
  a `WaveTexture`'s wave parameters), resolved against the class defaults so an unstored parameter
  still contributes its effective value. `USize`/`VSize` are stored even with no mip data and are part
  of the key. Changing the set re-keys every procedural shard, with the same irreversibility and the
  same owner-approved-migration requirement as §3b — and the same kind of committed golden pins it.
- **Selecting the set is a declared table, NOT inference.** The tool does not work out which properties
  matter; the set is written down per class and read from there, which keeps §0 intact. Reading the
  values is "reports facts literally stored in the package."
- **The hash is namespaced by class**, so a `FireTexture` and a `WaveTexture` with coincidentally equal
  parameter values cannot collide.
- **A procedural texture is NOT `undecodable`** (§3a): it is fully enumerable, classifiable and
  outdated-detectable. Only a genuinely unparseable export is `undecodable`.
- **`preview_state`** still reports honestly that there is no pixel preview to produce, which is a
  separate axis from identity — that distinction is exactly why §3a keeps the two flags apart.

**`ScriptedTexture` is the one procedural class the parameter hash does NOT cover, and it is handled
separately.** *(Owner ruling, 2026-07-26.)* It is drawn by UnrealScript at runtime, so its appearance is
not a function of its stored properties — there is no distinguishing set to hash. 50 of the 326
procedural exports are this class.

- **No preview artifact, and the reason is named.** `texture preview` produces nothing for a
  `ScriptedTexture` and **says on stderr that it is scripted**; the row carries
  `preview_state: scripted` so `--json` reports it honestly and `prewarm` skips it. This is an honest
  "no artifact exists for this kind of thing", the same shape as `no-mesh` — not a judgement about
  whether the picture would be useful.
- **Batch vs single ref follows the existing calibrated exception** (`direction/asset-catalog.md`): in a
  batch (`-`, `--package`) it is **skipped with the stderr note and a count**, because enumeration must
  keep listing what exists; asked for **by name as the only ref**, `preview` **exits 2 naming it**,
  because silently producing nothing for an explicit single request is the half-answer
  `direction/conventions.md` forbids.
- **Identity falls back to the NAME** (`Package.Name`), like class/sound/music. This follows the owner's
  own rule in `direction/asset-catalog.md` — "content hash where content exists, **name where it does
  not**" — and it is the only option left once the pixels are absent *and* the parameters do not
  determine them: an empty declared set would otherwise collapse every `ScriptedTexture` in a package to
  one identity. It keeps them individually classifiable, which is the point. **Flagged for veto rather
  than assumed settled:** this is the agent applying the owner's stated rule, not a separate ruling.
  It also means a renamed `ScriptedTexture` drifts to an outdated entry, exactly as the name-keyed kinds
  already do.

**Change-awareness without a `stale` flag.** When a texture's pixels change, its identity changes, so
it **shows unclassified** — correct, the new pixels genuinely are. The prior classification survives
under the old identity as an **outdated entry**, surfaced by `classify list-outdated` (showing its
stored `ref`) and removed by `classify prune --outdated`. Name-keyed kinds drift the same way when an
asset is renamed or removed.

---

## Facts this arm reports

### 4b. Texture colours — the one pre-filled field

A small **fixed palette** of base colour names. For each texture the tool quantizes its own decoded
pixels and stores the palette entries present, **ordered by importance** (descending share of the
image), with a share threshold to drop noise. So `texture search --color brown` works on a fresh
clone with an empty classification store — which is the point. An LLM classification may override the
list (`colors_source: "set"`), and the override wins. This is deliberately the *only* pre-filled
field: it reads nothing but the texture itself.

### 4c. Texture group — a stored fact, not just a ref component

A UE1 texture object carries a **Group** — an optional name that subdivides a package, so a texture is
addressed `Package.Name` or, fully, `Package.Group.Name`. In the package it is the texture export's
**Outer** name.

**Read it from the export table: `pkg.name_of_ref(export["outer"])`, `None` when there is no outer.**
`utexture` already carries `outer` on every export row and already resolves it this way when it builds
3-part refs (`utexture._texture_named`, `_decode_ref`), so no new parsing is needed. Verified live
2026-07-26 against tracked `uned/UED22/Engine.u`: the font textures report `SmallFont`/`MedFont`/…, plain
textures report `None`; `CoreTexWater.utx`'s two textures report `water`.

*(Do NOT reach for `texture_catalog.parse_pcx_stem` / `TextureEntry.group`. They exist today and do carry
the group, but they parse a **UCC `batchexport` PCX filename** — `Skins.Wood.pcx` → group `Skins` — and
§9 deletes that whole export/sync path, with both symbols named in the plan's deletion inventory. An
earlier draft of this section cited them, which would have routed a new first-class fact through code
being removed in the same change.)*

**The group is a first-class fact and MUST be stored and queryable**, not merely consumed while
assigning refs. Two independent reasons:

1. **In Deus Ex the group is load-bearing gameplay data.** 📖 A surface is climbable if and only if its
   texture's group is the reserved `Ladder` — the group, not the name, is what the engine tests. So
   "which textures are ladders" is a question the catalog must be able to answer directly.
   *(Evidence: `docs/leveldesign/deusex/classes.md` and `recipes/ladder.md` state the rule; the
   level-building friction log records an agent spending ~10 min recovering a group by hand because no
   verb prints it. **NOT live-probed** — there is no spike and no ✅/🔬 entry under `unrealed/`, so this
   is 📖 by `CLAUDE.md`'s marker scale. It is load-bearing for this fact and two filters: probe it, and
   land the result in `unrealed/`, during the texture-arm slice.)*
2. **Ref assignment DISCARDS it in the common case.** §9's rule emits a 2-part `Package.Name` ref
   unless there is an intra-package name collision. `CoreTexMetal.LadrBrwnMetal` is in group `Ladder`
   and has no colliding sibling, so its ref is 2-part and **the group appears nowhere in the output**.
   Recovering it meant reading the raw per-package JSON by hand — measured at ~10 minutes of an
   agent's time, for a fact the tool had already parsed and thrown away.

Concretely:

- `group` joins the texture `facts` dict in the §3a per-package index row (`"group": "Ladder"`, or
  `null` for a groupless texture — never omitted, so absence is distinguishable from "not yet
  indexed").
- `texture show` prints it, and `--json` carries it.
- **`texture list --group G` and `texture search --group G`** filter on it (added to §5's per-kind
  filter list). `--group ""` selects the groupless textures, which is otherwise unaskable.
- It is a **fact, never a classification**: it is read from the package, so it is not LLM-overridable
  and does not live in a tracked shard. This is not an exception to §0 — reporting a value literally
  stored in the package is exactly what "reports file facts" means.

Group is **not** part of texture identity (§3b): identity is the pixel hash, and two textures with
identical pixels in different groups are deliberately one classifiable thing.

### 4d. Texture `masked` — read the stored flag, never infer it

**`Masked` is a property of the TEXTURE OBJECT, set when the texture is imported into UnrealEd** (the
import dialog's `Masked` checkbox), and it is stored in the package on that texture's export. It is
**the same flag** as the surface polyflag of that name — UE1 ORs a texture's own flags into the
surface's at render time — which is why a texture imported as masked draws its palette-index-0 pixels
as holes **on any surface, with no surface flag set at all**.

- `masked` joins the texture `facts` dict (`true`/`false`, never omitted).
- **The property is spelled `bMasked`** (a bool tag), and it is **stored only when it differs from the
  class default** — a UE1 tagged-property block is a sparse diff against the class defaults, not a full
  record. Probed 2026-07-26 across four `.utx`: present on 84 of 320 texture exports in tracked
  `DeusExDeco.u` and 9 in `UNATCO.utx`; entirely **absent** from both committed fixtures
  (`CoreTexWater.utx`, `LUM_InfoPortraits.utx`).
- **So the read rule is: the export's `bMasked` tag if present, ELSE the resolved class default.** Not
  "absent means false". On this substrate `Engine.Texture`, `Fire.FireTexture`, `Fire.WetTexture`,
  `Fire.WaveTexture` and `Engine.ScriptedTexture` all default it `False`, so absent-means-false is
  *accidentally* right here and silently wrong on a mod — or another UE1 game, which is this tool's
  stated scope — whose texture class defaults it `True`. **This makes `masked` a default-sourced fact,
  so §11 prerequisite 1 gates the texture arm too, not just the class arm.** `utexture.decode_texture`
  already returns the export's tagged properties (`TextureObj.props`), so the *tag* read is free; the
  default resolution is the part that needs the prerequisite.
- **`bAlphaTexture` joins `facts` beside `masked`** *(owner ruling 2026-07-26)*, same read rule and same
  cost. It is the only thing that distinguishes a graded-alpha texture (BC2/BC3, 10 measured here) from its
  opaque twin, since identity is pixels-only and they share one identity and one opaque preview. Without it
  they are indistinguishable — and identity is frozen, so it cannot be added to the key later. The sibling
  `specs/2026-07-25-native-texture-formats.md` §8-D already reports it, so the read is available.
- `texture show` prints it; `--json` carries it; **`texture list --masked` / `search --masked`** filter
  on it (added to §5's per-kind filters).
- It is a **fact, not a classification**: not LLM-overridable, no tracked shard.

**It must be READ, not derived.** An earlier draft of this section proposed inferring hole-punching
from palette index 0, or from the auto-derived colour list containing `pink`. Both are inference,
which §0 forbids, and both are wrong in ways that matter: a texture can have an index-0 colour without
being imported masked (the flag is what the engine tests), and `pink` is a coincidence of the stock
art, not a rule. Reading the stored flag is exact.

**Why it earns a field of its own.** A masked texture is only correct where real geometry sits behind
it — a grille, a fence, a mover leaf, a detail brush against a wall. On a *solid* wall it is a
see-through hole into unbuilt space, and it is undetectable by auditing surface flags because the
offending polys carry none. This is the one texture fact whose misuse produces a defect that reads as
a lighting or BSP bug; making it a filterable fact turns "which of this level's textures punch holes"
from a `--game` render into a lookup. *(Evidence: `spikes/levelbuild-friction/agent-reports.md` — hit
independently on two of three levels; `unrealed/quirks.md` "Surfaces / polys".)*

Not part of identity (§3b): identity is pixels, and the flag lives beside them.

---

## 9. Carried over from the texture-catalog redesign (that spec is DELETED on build)

- On-demand **native** decode; no mandatory `sync`. The `sync` verb and its coupled surface are
  deleted in the same change: the `dispatch.py` sync branch + ephemeral-container start path, the
  `tsync` parser, `texture.py`'s `batchexport_textures`, the "run texture sync" error strings,
  `container_assets.py`'s comment, and the sync tests.
- Lazy stat-tuple invalidation; `prewarm` + `cache gc` replace the bulk step; `prewarm --force` is the
  re-decode escape hatch.
- Content-addressed cache with **bare-hex** keys (no `sha256:` prefix), dedup across packages.
- **Two hashes for textures:** exact pixel-hash for identity/dedup/clone; a separate perceptual hash
  for similarity, scored as **phash ⊕ colour distance** (dHash alone is colour-blind and collapses the
  flat tiling wall/floor textures that dominate this corpus). Framed honestly as near-duplicate +
  rough look-alike, not semantic search. `--similar` is mutually exclusive with lexical terms/filters
  (exit 2 otherwise), defaults `--max 20`, may be scoped by `--package`, and surfaces its `distance`.
- **A new enumerate-and-decode error layer.** `utexture.TextureResolver.resolve()` collapses *every*
  failure to `None`, so it cannot produce a taxonomy: layer over `textures()`/`decode_texture` to
  distinguish **unknown ref** / **ambiguous 2-part ref** (list the 3-part candidates) / **undecodable**
  / **cache-unreadable** (`EACCES` ≠ ENOENT). "Errors name the offending value" is unachievable with
  the current API.
- **Ref assignment:** 2-part `Package.Name` by default, 3-part `Package.Group.Name` on intra-package
  collision (`texture_catalog.assign_refs`).
- **Atomic writes, and TWO distinct lock domains.** Tracked-shard writes keep the catalog-dir flock
  (`<catalog>/.locks/`, per-catalog and correct). The derived cache — which is **per-user and
  cross-project** — needs its own flock under `~/.uedcli/cache/catalog/.locks/`, because two projects
  with different catalog dirs decoding the same base package would otherwise be unserialized. Atomic
  writes already prevent torn reads, so the cache flock is duplicate-work suppression only.
- Broad/cold queries pay a real cost and must **say so** on stderr. Measured: **26.4 s** to decode the
  57 stock `.utx` (2,669 textures, 61.5 Mpx), plus ~2,400 more textures inside `.u` → **~50 s** cold.
  `--similar` is inherently whole-catalog.
- **Non-P8 texture decoders remain a BUILD PREREQUISITE for the TEXTURE ARM only** — all 2,669 stock
  textures decode P8 today, so it buys generic-UE1 honesty; the class and audio arms need no new
  decoders on Deus Ex.

---

## Test coverage — texture arm

Read `../rules/tests.md` first. Offline fixtures: the sibling
[`2026-07-25-native-texture-formats.md`](2026-07-25-native-texture-formats.md) §5a promotes its committed,
self-verifying `.utx` builder (`spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py`) to
`uedcli/tests/pkgfixture.py` and makes it "the fixture API every offline test is written against". **This
arm depends on that rather than building a writer.** Note there are **no** tracked `.utx`/`.uax`/`.umx`
under `uned/`; the two committed `.utx` live in `uedcli/tests/fixtures/`.

- **Frozen identity:** the committed golden (ref → hex digest over `CoreTexWater.utx`) holds; adding a fact
  to a row changes no identity; the byte encoding is the pinned one (`b"%d:%d:" % (w,h) + rgb.tobytes()`,
  bare hex, no `sha256:` prefix).
- **Group:** a grouped texture reports its group even when its ref is 2-part (the `LadrBrwnMetal` shape);
  a groupless texture reports `null`, not a missing key; `--group Ladder` selects, `--group ""` selects the
  groupless; group is not part of identity.
- **`masked`:** three cases, because the obvious one is insufficient — (i) a palette with an index-0 colour
  and no `bMasked` tag reports `false`; (ii) **no tag, class defaults `bMasked = True` → reports `true`**,
  the case that distinguishes the correct default-relative rule from "absent means false"; (iii) `--masked`
  filters and `masked` is not part of identity. **Case (ii) needs the synthetic `.utx`/`.u` pair** — every
  offline candidate class defaults `False`, so without it the wrong rule ships green.
- **Procedural (§3c):** the parameter-hash golden per declared class; the routing rule; the out-of-table
  fallback (whatever decision 4 settles); `ScriptedTexture` name-key and `preview_state: scripted`;
  batch-skip vs single-ref exit 2.
- **Colours:** pre-filled and ordered by share, `--color` works with an EMPTY classification store, an LLM
  override wins and is marked `set`. Preserve today's documented derivation (12-name palette, 64×64
  nearest resample, ≥12% share, cap 3) or state the change.
- **Similarity:** ranks a known near-pair above an unrelated texture AND discriminates two flat
  same-luminance different-colour textures; the `--similar` + terms exclusivity; the persisted `phash`.
