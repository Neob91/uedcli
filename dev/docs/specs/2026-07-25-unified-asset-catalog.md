# Spec: the unified asset catalog — one engine, four kinds (texture / class / sound / music)

**Status:** specced, **two review rounds folded** (2026-07-25, 4 cold reviewers). Next step is a plan.
**Requested by:** Andrzej (2026-07-25, session `uedcli:catalog`).
**Ephemeral:** scratch, per the uedcli `CLAUDE.md`. **The durable homes are
[`direction/asset-catalog.md`](../direction/asset-catalog.md)** (the owner's decisions — agents may not
write it without an explicit yes) **and [`rationale/`](../rationale/)** (the agent's implementation
choices). On build, fold the outcome into `architecture.md` (replacing its "Texture catalog" section) +
`usage.md`, and delete this file.

> **Do not cite `dev/docs/decisions.md`.** Earlier drafts of this spec called it "the durable
> append-only ledger" and pointed at entries *2026-07-25 03:40* and *2026-07-25 05:10*. That file is
> **FROZEN — DO NOT APPEND**, and `CLAUDE.md` states there is no decisions ledger;
> [`rationale/MIGRATION.md`](../rationale/MIGRATION.md) maps every old dated citation to its new home.
> A decision recorded there on build would land in a file nobody is allowed to touch.

**Supersedes / folds in:** [`specs/2026-07-19-texture-catalog-redesign.md`](2026-07-19-texture-catalog-redesign.md)
(specced + review-gated, never built — its mechanics are generalized here; §9 restates what carries
over, because that spec is DELETED on build); the `to-spec` **★ Asset catalog** item; the `inbox`
**annotated class catalog** item; and it supplies the dependency the `to-spec` **ObjectProperty-ref
validation** item was waiting on (§8).

---

## 0. THE GOVERNING PRINCIPLE: the tool does not infer

**uedcli is a faithful data layer, not a clever one.** It does exactly four things:

1. **Lists** what exists on the composed search path.
2. **Reports facts that are literally stored in the package** — image dimensions, mesh bounding box,
   collision radius/height, pivot, parent class, `DrawType`.
3. **Produces the picture** — decodes a texture, renders a mesh.
4. **Stores and queries the classification it is handed.**

**It never infers meaning.** It does not decide what an asset is for, where it is used, whether it
is "commonly placed", or how relevant one asset is to another. **The LLM does that work** — it looks
at the picture, investigates how the game uses the thing, decides what it is, and hands the answer
back to be stored. *(Andrzej, 2026-07-25: "Why does the tool work anything out by itself? It should
be passed classification data, that's it! The LLM will figure out where assets are used and what
they are!")*

**The single exception is texture colours** (§4b), because they come from the texture's own pixels —
that is reading the file, not scanning the corpus — and because they make colour search work
*before* any classification exists.

This principle is what makes the catalog small. An earlier draft had the tool sweep 120 stock maps
to compute a usage index and a placement histogram, and infer "placeable" from it. **All of that is
deleted**, along with its prerequisite (a native map-actor reader). If an agent wants to know where
Deus Ex uses a sound, it investigates and records the answer — which is durable, reviewable, and
correctable, unlike a number the tool computed.

**Corollary — the empty catalog is a starting state, not a verdict.** Two cold reviewers measured
`texture-catalog/`: 4,791 entries, **0 classified**, and untracked by git. They read that as
evidence nobody will ever classify, and recommended building less classification machinery. That is
backwards: nothing has been classified because nothing has ever made it possible — there is no way
to *see* a texture today. Classification is not a side feature that might stay empty; **it is the
product.** The verbs that write and read it are the core, not the periphery.

## 1. The unified model in one paragraph

**One engine, four kinds, four nouns.** A single engine owns everything not kind-specific: package
enumeration over the composed search path, a lazily-built per-`(kind, package)` derived index gated
on a `(realpath, size, st_mtime_ns)` stat tuple, a content-addressed per-user preview cache,
git-tracked sharded classifications, the query layer, and the outdated-entry machinery. Each **kind**
plugs in an adapter answering four questions: *what counts as an asset of this kind*, *what is its
identity key*, *what preview artifact can be produced*, *what file facts does it carry*. The CLI
keeps **per-kind nouns** — `texture …`, `class …`, `sound …`, `music …` — each with the same verb
family, so no verb grows a `--kind` selector.

## 2. Decisions (the owner) — durable home: `direction/asset-catalog.md`

*(This section is a working restatement for the reader's convenience. The authoritative text is
`direction/asset-catalog.md`; where the two differ, that doc wins and this one is stale. Two divergences
were found by the 2026-07-26 gate and are fixed below — music's verb family and the curation override.)*

1. **The tool does not infer** (§0). *Rejected: a tool-computed stock-map usage index and class
   placement histogram* — the tool would be guessing at meaning, the numbers would be unreviewable
   and uncorrectable, and it dragged in a native map-actor reader as a prerequisite. The LLM
   investigates and records instead.
2. **Per-kind nouns over ONE shared engine.** *Rejected: a single `catalog` noun with `--kind`*
   (deletes the `texture` verbs and rewrites every doc naming them); *rejected: both surfaces*.
3. **This spec subsumes the unbuilt texture-catalog redesign.** *Rejected: build it as specced, then
   generalize.*
4. **Identity: content-hash where content exists and is decodable, name otherwise.** Texture →
   pixel-hash (enables cross-package dedup and `classify clone`). **Class, sound and music →
   name** (`Package.Name`). *Rejected: content-hashing sound* — `.uax` decoding is unresolved, so
   phase (a) would have no key at all, and adopting one later would re-key and orphan every tracked
   sound shard. *Rejected: content-hashing music* — `TLazyArray` headers embed absolute file offsets,
   so a repacked-but-identical package would hash differently. *Rejected: name-keying textures* —
   loses the dedup and clone that the texture corpus actually benefits from.
5. **Class thumbnails render NATIVELY**, per spike
   [`2026-07-25-native-mesh-decode`](../spikes/2026-07-25-native-mesh-decode/README.md). *Rejected:
   the container render harness* as the thumbnail path (it stays for real-lighting hero shots). The
   open unlit/fullbright spike is **moot for thumbnails**.
6. **`show` (metadata) and `preview` (image artifact) are SEPARATE VERBS.** Matches the existing
   `actor preview`/`level preview` naming and dissolves the `class show` collision. *Rejected: one
   `show` with a `--preview` flag.*
7. **Only `preview` produces artifacts.** `list`/`search --json` report `preview: <path>|null` for
   already-cached artifacts only. *Rejected: rendering inline for "cheap" kinds* — measurement showed
   a cold `class list --json` would render 657 meshes (~11 min) on an agent's first command.
8. **`classify set -` reads JSONL from stdin.** *Rejected: single-ref writes only* (~0.3 s cold
   start per ref makes classification process- and turn-bound). **This is an owner-approved THIRD stdin
   convention** *(ruling 2026-07-26: "it's fine")*. `direction/conventions.md` otherwise says "Exactly
   TWO stdin conventions … never add a third", so the exception is deliberate and must be recorded
   there as a calibrated carve-out rather than left as a silent contradiction — parked as an
   `[OWNER — confirm]` item on `board/inbox.md`. Within the catalog nouns `-` therefore means a **name
   list** for `show`/`preview`/`classify unset` and a **JSONL row set** for `classify set`, and the
   split is per verb, as the two-convention rule itself already requires.
9. **Cache eviction goes on the existing `cache` noun** (`cache gc`). *Rejected: a `catalog gc` verb*
   — a second maintenance surface over one cache root.
10. **No curated role/category taxonomy for classes.** Andrzej: the **superclass already says what a
    class is for**, and `--subclass-of` already exists. Curation is a **description plus tags**.
    *Rejected: curating a role taxonomy over ~1,900 classes.* This also avoids a second meaning for
    `class show --category` (which means the UnrealEd property category).
    **Open — `direction/asset-catalog.md` is ambiguous here and the spec must not resolve it silently.**
    That doc says curation is "a description, plus **an override where the file fact is wrong**", while its
    own *Rejected* list kills "a curated-vs-derived override model for `placeable`". The shard payload
    (§3b) carries `tags`/`description`/`colors` and no general override field, so as specced a wrong
    file-fact cannot be corrected at all. Parked as an `[OWNER — confirm]` question on `board/inbox.md`;
    the colours override (§4b) stays the one existing instance either way.
11. **`class preview` angles:** `iso` (front-¾) is the default SINGLE shot; `--angles` opts into
    `front, back, left, right, top, bottom, iso`. **"side" is spelled `left`/`right`** — a mesh is
    not symmetric in general. One angle by default because a render measures **~300 ms**, not the
    ~20 ms first assumed; 657 mesh classes × 3 would be ~11 minutes.
12. **Texture colours are pre-filled from the pixels** (§4b) — the one inference-shaped thing the
    tool does, because it reads only the texture itself and makes `--color` search useful on day one,
    before any classification exists. A small fixed palette, **ordered by importance**, LLM-overridable.
13. **No migration; the legacy catalog is deleted.** `texture-catalog/` holds no authored data (0 of
    4,791 classified) and is untracked, so there is nothing to migrate. The dir and the whole
    migration apparatus are deleted, per the no-back-compat-cruft rule. *Rejected: a defensive
    `texture migrate`* — a verb, an ordering contract, a hash-equivalence regression and 4 test
    bullets to protect regenerable cache data.
14. **The contact sheet stays banned.** *Rejected: an opt-in indexed sheet* — misattribution is the
    failure mode that silently corrupts a catalog, and a numbered grid still depends on the model
    reading cell numbers correctly. One asset, one image file.

## 3. Storage layout

### 3a. Per-user derived cache — regenerable, never committed

Root: `~/.uedcli/cache/catalog/v<N>/`. The **version is a path segment as well as part of the key**,
mirroring `schema_cache`: a version bump then leaves whole reclaimable orphan directories instead of
files scattered through live ones that `cache gc` cannot distinguish.

- **`packages/<kind>/<stat-key>.json`** — the per-package index, **one file per (kind, distinct
  file)**. The `<kind>` segment is load-bearing: one package feeds several kinds (`DeusEx.u` carries
  both classes and textures), so a kind-less key would have `texture list` and `class list` clobber
  each other's index forever, each serving a "complete" answer missing the other's rows. `<stat-key>`
  encodes `(realpath, size, st_mtime_ns)` — **realpath** because project overlays shadow base
  packages *by stem*, so a stem key would collide and briefly serve another project's data.
  Row shape:
  ```json
  {"ref": "DeusExDeco.BarStool", "identity": "deusexdeco.barstool",
   "previews": {"iso": "<hash>"},
   "preview_state": "ok|none-for-kind|no-mesh|editor-icon|decode-failed",
   "undecodable": false,
   "deps": [["<realpath>", 12345, 1679...]],
   "facts": {"drawtype": "DT_Mesh", "bbox": [96, 40, 72], "collision": [22, 40]}}
  ```
  `facts` is **per-kind and open for extension**: a texture row carries
  `{"w":…, "h":…, "format":…, "group": "Ladder"|null, "masked": true|false, "colors": […],
  "phash": "<hex>"}` — §4b (colours), §4c (group), §4d (masked) — and a class row the shape above.
  Adding a fact is always safe: see the frozen-identity rule in §3b.
  **`phash` lives here deliberately.** §9 requires a *second*, perceptual hash for `--similar`, which is
  inherently whole-catalog; without a persisted field every `--similar` invocation would re-decode the
  corpus (§9's own measured ~50 s cold, per call). It is a derived digest rather than a package fact, but
  it is stored in the derived index like any other, and it is **not** part of identity — §3b's "adding a
  fact never re-keys anything" covers it for exactly that reason.
  `undecodable` (**genuinely unreadable** — the export cannot be parsed at all; a *procedural* texture is
  NOT undecodable, it is parameter-hashed per §3c. Note the "cannot be classified" consequence is
  **texture-only**: for the name-keyed kinds identity IS the name, so an unreadable class/sound/music
  export still has a key and stays fully classifiable — it merely has no facts and no preview) and
  `preview_state`
  (no artifact available, but fully classifiable) are **separate flags** — one boolean cannot do both
  jobs, and conflating them mislabels a `DT_Brush` class as corrupt.
- **`previews/<hh>/<hash>.png`** — every preview artifact, content-addressed by the bare hex sha256
  of its pixels. Textures, class thumbnails and (later) spectrograms share it and dedupe. For
  **textures the preview hash IS the identity** — no second digest.
- **`shard-index/<hash-of-catalog-realpath>.json`** — the roll-up over the tracked classification
  shards, **keyed per project** (the shards live in the *project's* catalog dir; one unqualified file
  would serve project A's tag vocabulary to project B). Gated on **`(file count, max mtime_ns, total
  size)`** — max-mtime alone cannot see a **deletion**, so `classify prune` or a `git checkout`
  dropping shards would keep serving classifications that no longer exist.

All derived: deletable at any time, rebuilt lazily. An undecodable asset **stays enumerable** —
never silently dropped, which would read as "this package has fewer assets than it does".

**The preview cache is its OWN pool with its OWN budget, and the existing sweep must be made recursive.**
Decision 9 reuses the `cache` noun, which is right, but not the existing *pool*: `schema_cache` LRU-evicts
by atime against a **single shared 256 MiB cap** (`SCHEMA_CACHE_MAX_BYTES`) and sweeps **automatically once
per process after any blob write**. Three concrete failures if previews simply join it:

- `schema_cache.evict_lru` scans **one flat directory**, so it would find nothing under the catalog's
  nested `packages/<kind>/…` and `previews/<hh>/…` — the cache would grow unbounded while appearing managed.
  The sweep has to walk recursively.
- A full `prewarm` (4,791 texture PNGs + 657 mesh renders) is the same order as the whole existing cap, so
  it can **evict its own output mid-run** — and `prewarm` exists precisely to prepare an *offline* session,
  where recovery costs ~11 minutes of re-rendering.
- The existing sweep's safety argument ("a wrongly-evicted blob is merely a future re-decode, never a wrong
  answer") was written for tens-of-KB schema blobs and **does not transfer** to an 11-minute re-render.

So: previews get a separate byte budget, evicted independently of the schema blobs, and the auto-sweep must
never be able to evict a preview written by the *current* process. `cache gc --previews` targets that pool
by name (**not `--catalog`**, which reads as though it touches the tracked catalog one line after the rule
that it never does).

**`cache clear` must learn about the catalog pool in the same change.** Today it is schema-cache-specific in
both name and help; leaving it alone ships a verb whose help says "delete the persistent cache" while a
multi-hundred-MB catalog cache survives — the stale-help failure `conventions.md` names.

**Stat-keyed index files are reclaimed by `gc`, not left to accumulate.** `packages/<kind>/<stat-key>.json`
embeds `(realpath, size, st_mtime_ns)` in the filename, so **every** package rebuild, re-download or `touch`
strands the previous file *inside the live `v<N>/` dir* — precisely the "files scattered through live ones
that `cache gc` cannot distinguish" that §3a's version-as-path-segment rationale claims to avoid. On a tree
whose packages are actively rebuilt this grows without bound. `gc` therefore also drops index rows whose
`realpath` no longer exists **or** whose stat tuple no longer matches the file, which is decidable from the
filename alone.

**Preview paths are verified at emit time, never trusted from the row.** Artifacts are shared by many
rows and `cache gc` LRU-evicts them with no back-reference; the schema cache may evict freely only
because its entries are self-contained, and that licence does not transfer. So `list`/`search` `stat`
the content path and report `preview: null` if it is gone. (Preview PNGs are written once and read
often, so under `relatime` their atimes are near-frozen — they are the *first* LRU victims.)

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

## 4. The kind adapters

| | **texture** | **class** | **sound** | **music** |
|---|---|---|---|---|
| source | every export descending from `Engine.Texture` | `.u` class exports (via `classindex`) | `.uax` + `.u`, minus VO (§4a) | `.umx` music exports |
| identity | sha256(w, h, RGB) | `Package.Class` | `Package.Name` | `Package.Name` |
| preview | decoded PNG | native mesh render (`DT_Mesh`) or the `Texture` default's image (`DT_Sprite`, §6) | spectrogram (phase b) | none |
| file facts | w, h, format, **group (§4c)**, **colours (§4b)** | parent, DrawType, abstract, **bbox, collision, pivot** (§6) | duration/rate/channels (phase b) | format, embedded module title |
| similarity | phash ⊕ colour distance | — | — | — |

### 4a. Corpus scope rules (measured, not assumed)

- **Textures: enumerate every export descending from `Engine.Texture`**, not `class == "Texture"`.
  The stock `.utx` set carries 40 `FireTexture`, 8 `WetTexture`, 1 `WaveTexture` — real, referenceable
  surfaces that today's exact-match enumeration never sees. Procedural ones are **fully classifiable**
  via the parameter-hash identity of §3c; they are never `undecodable`. (Counts here are the stock
  `.utx` subset only; `IceTexture` and `ScriptedTexture` exist too — see §3c.)
- **The VO exclusion is CONFIG, not a hardcoded Deus Ex pattern.** The rule below drops ~10,200 of 10,826
  sound exports, so it must be visible and overridable rather than a substrate fact buried in a
  generic-UE1 tool: the excluded packages come from a per-substrate key in the games config (along
  `paths`), Deus Ex sets it to the `DeusExConAudio*` pattern, and **`--include-vo`** opts back in. A
  listing that omits 94% of the corpus with no way to see it, and no statement of what was dropped, is
  the half-answer `conventions.md` targets — so `sound list` reports the excluded count on stderr. The
  exclusion applies to **enumeration only**: `sound show` and `sound classify` accept a VO ref by name, so
  a deliberately-referenced line is never unreachable. *(This rule is absent from
  `direction/asset-catalog.md`; it is the agent's implementation choice and belongs in `rationale/` on
  build, not in the owner's tree.)*
- **Sound scope is an explicit rule, because `.uax` is the wrong set.** Measured: **10,826** Sound
  exports on the composed path — only **151** in `.uax`, **399** in `DeusExSounds.u` (the real SFX
  library), ~**10,200** conversation VO in `DeusExConAudio*.u`. `.uax`-only omits the most useful
  package; every-package makes `sound list` a 10k-line dump. **Rule: `.uax` plus any `.u`, EXCLUDING
  conversation-audio packages**, with `--include-vo` as the escape hatch for a mod that places VO
  deliberately. Expected corpus ≈ 550.

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
- The sibling `specs/2026-07-25-native-texture-formats.md` §8-D also reports **`bAlphaTexture`**; decide
  during the build whether it joins `facts` beside `masked` (same read rule, same cost).
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

## 5. Verb surface

`<kind>` ∈ `texture` | `class` | `sound` | `music`:

| Verb | Role | Output |
|---|---|---|
| `<kind> list [--package P] [--classified\|--unclassified] [--json]` | **enumerate** — the deterministic corpus listing, sorted by ref | refs one-per-line; `--json` = JSONL rows carrying `preview: <path>\|null` (cached only) |
| `<kind> search <terms…> [--tag T] [--package P] [--classified\|--unclassified] [--json]` + per-kind filters | **ranked discovery** (§5b) — `<terms…>` is REQUIRED | bare refs one-per-line, best first; `--json` as above |
| `<kind> show <ref>… \| -` | **facts + classification** | one block per ref; `--json` |
| `<kind> preview <ref>… \| - [--out DIR] [--skeleton]` | **the sole producer of image artifacts** | `<ref>\t<path>` lines (ref-qualified, so multi-artifact kinds stay unambiguous); `--skeleton` switches the stream to JSONL (§5a) |
| `<kind> classify set <ref> --tags … --description …` **or `-`** | record classification; `-` reads JSONL `{ref, tags, description[, colors]}` | summary → stderr |
| `<kind> classify unset <ref>… \| - [--tags[=T,…]\|--description\|--colors\|--all]` | undo a mis-tag; `--tags a,b` removes THOSE tags, bare `--tags` clears the field | summary → stderr |
| `<kind> classify status [--full] [--json]` | classification progress | counts → **stdout** one metric per line; `--json` for a script |
| `<kind> tags [--package P] [--json]` | the tag vocabulary in use | tags one-per-line → **stdout** (a producer: pipe it into `search --tag`); counts → stderr |
| `<kind> classify list-outdated` / `prune [--outdated]` | classifications whose identity no longer resolves | rows → stdout / count → stderr |
| `<kind> classify clone --from <catalog-dir\|project-root>` | copy classification by identity (keep-local, skip-report) | counts → stderr |
| `<kind> prewarm [--package P] [--force]` | eagerly index/decode/render ahead of an offline session | progress → stderr |
| `cache gc [--previews]` | evict from the DERIVED cache only — never tracked files | freed summary → stderr |

Per-kind filters: `texture --color C --group G --masked --similar REF [--max N]`;
`class --subclass-of FQCN --drawtype DT --include-abstract`. `music` ships a **reduced family**
(`list`, `search`, `show`, `classify …`, `tags`): 35 assets and **no preview artifact**, so it drops
exactly `preview`/`prewarm`/`--similar` and nothing else — matching `direction/asset-catalog.md`, which
authorises dropping only the artifact-dependent verbs. *(An earlier draft also dropped `search`; that
diverged from the owner's doc and from the plan, and is corrected here.)* `--catalog-dir` is **retained**
on every kind (load-bearing for project-less use).

**`search` REQUIRES terms; `list` is the verb for filters alone.** Otherwise the two produce byte-identical
output from identical inputs, and `direction/conventions.md` is explicit: "Two verbs with the same output
shape are one verb too many." A term-less "ranked" query also has no defined order. So: `search` without
terms **exits 2** pointing at `list`; every filter (`--package`, `--tag`, `--classified`/`--unclassified`,
and the per-kind ones) is available on **both**, so nothing is only reachable through ranking. §5a's loop
is written accordingly.

**`--similar` is mutually exclusive with lexical TERMS, and composes with FILTERS.** `--similar REF` plus
terms exits 2 (two different rankings). `--similar REF --package P --group G --masked` is legal and means
"rank by similarity within this subset" — filters narrow the candidate set, they do not rank. Stated because
§4c and §4d added two filters after the original exclusivity rule was written, leaving
`search --similar X --group Ladder` undefined.

**A truncated result set says so.** `--max N` (and any default cap) prints the cap and the number withheld
**to stderr** whenever it elides rows, per "no silent half-answers" — a capped list on stdout is otherwise
taken for the complete answer.

**`class` keeps ONE spelling of the placeable axis: the existing `--include-abstract`.** `class list` has it
today and it means "drop the placeable filter"; there is no `--placeable`, and adding one would ship two
spellings of one axis on sibling verbs — the back-compat cruft `conventions.md` forbids on arrival. The new
`class search` takes `--include-abstract` too.

**`--classified`/`--unclassified` require `--flat` on `class list`.** They select a *set*, and `class list`'s
default output is an indented inheritance TREE where a filtered set has no well-defined shape (prune to
surviving leaves? keep branch-points as context?). Rather than guess, the tree form **exits 2** naming the
flag and pointing at `--flat`. This is the same asymmetry §6 already accepts for `class`, made explicit for
the two new flags.

Inherited rules: producers print to stdout one item per line, summaries to stderr; `-` reads a ref set
from stdin, empty stdin is a clean exit-0 no-op; a command that cannot fully satisfy a request exits 2
naming the offending value; no Python exception reaches the user. Naming follows the **`find` vs
`search` rule** (decision 2026-07-25 00:43): these are `search` — ranked discovery over a corpus, not a
deterministic query over trunk state.

### 5a. The intended agent loop

```bash
texture list --unclassified --package CoreTexMetal \
  | texture preview - --skeleton > work.jsonl     # produces the PNGs, emits one JSONL row per ref
#   each row is {"ref": …, "preview": "<path>", "tags": [], "description": ""}
#   harness Reads row["preview"] as its own image (one asset, one file — no montage, no misattribution),
#   fills tags/description in place, then:
texture classify set - < work.jsonl               # one shard per row
```

**`--skeleton` REPLACES the `<ref>\t<path>` stream with JSONL; the two never interleave.** The row
**carries the artifact path** in a `preview` field, which is what makes the loop closed: without it the
harness would have the JSONL but not the images, and with two formats on one stdout `classify set -`
could not parse the pipe. The extra keys (`tags: []`, `description: ""`) are the ready-to-fill shape, and
`classify set` ignores `preview` on the way back in. Bare `preview` (no `--skeleton`) keeps the plain
`<ref>\t<path>` lines for the common one-off case.

*(Note the producer is `list`, not `search`: this query has filters and no terms, and `search` now
requires terms — see §5. An earlier draft wrote `search --unclassified --package …`, which is exactly the
term-less case that made `search` and `list` the same verb.)*

Classification is therefore a **byproduct of looking** rather than a separate bulk campaign: an agent that
previewed 20 assets while building a room can classify exactly those 20.

### 5b. `search` ranking must be specified, because early on it IS the product

With an empty classification store, `search` runs on names and file facts alone — so "ranked
discovery" cannot be left to the implementer. The build must specify and test:

- **Tokenization** of identifiers: split on case transitions, underscores and digit boundaries, so
  `ClenGrayMetal_A` → `clen gray metal a` and `texture search metal` matches it.
- **Scored fields and weights:** asset name > tags > description > package/group name.
- **Match mode** (substring vs prefix vs fuzzy) and the **default result cap**.
- A regression that `texture search wall` over a **zero-classification** corpus ranks wall textures
  above non-walls — every other texture test assumes classification exists.

## 6. The class arm

**Derived facts only; meaning comes from classification.** `class list`/`class show` already derive
schema, hierarchy, defaults and abstractness; the **superclass already says what a class is for**.
The catalog adds the file facts an agent needs to actually *place* the thing, plus the picture, plus
its stored classification.

**Size is the missing fact and it is cheap.** Today an agent can see a crate and still has to guess
its footprint, and whether its origin sits at the base or the centre — so decorations sink into floors
and interpenetrate. The only way to read a default today is the three-command detour
`actor build | actor add - | actor prop get -`, which needs a trunk. `class show` therefore reports
**mesh bbox × `DrawScale`, `CollisionRadius`/`CollisionHeight`, and `PrePivot`/origin offset**. The
mesh decoder already produces the bbox; the rest are class defaults.

**`class show` prints every property's resolved DEFAULT — not just the placement three.** Today it
prints names and types only (`AmbientBrightness: ByteProperty`), and `actor prop get` prints only
properties that were explicitly *set*, so a freshly placed actor appears to have no properties at all.
Between them there is **no way to answer "what value does this property start at"** without the
`actor build | actor add - | actor prop get -` detour named above — which needs a trunk, writes a
throwaway actor into the user's level, and answers one property at a time. Measured cost: an agent
diagnosing a room that had gone fullbright immediately after 8 `Engine.ZoneInfo` actors were placed
spent **over an hour** on `AmbientBrightness`, per-light radii and polyflags before the real cause
turned out to be elsewhere entirely — and the answer it needed (`AmbientBrightness` defaults to **0**,
so a fresh `ZoneInfo` adds no ambient at all) would have eliminated its prime suspect in seconds.

So `class show` reports the **resolved default beside each property**: `AmbientBrightness: ByteProperty
= 0`. A property with no default anywhere reports its type's zero value, marked as such — never blank,
which reads as "unknown".

**Scope of "each property", stated precisely:** `class show` prints the *category-bearing editable*
properties (it groups by UnrealEd category), so this adds a default to each of those — it is not a dump
of every field on the class. Say so in `--help`; "every property" would over-promise.

**Two honest cost notes, because an earlier draft called this "not new machinery" and that was wrong:**

- The **values** are indeed already paid for — prerequisite 1 persists resolved defaults because the
  class arm needs them corpus-wide, and `Engine.ZoneInfo.AmbientBrightness` really does resolve to `0`
  off the tracked packages (verified 2026-07-26, 282 defaults resolved).
- But **provenance is not**. `uprops.resolve_class_defaults` returns
  `dict[(casefold(name), array_index)] -> rendered str` and its root→leaf overlay loop **overwrites
  without recording which ancestor supplied the value**. Reporting "inherited from `Engine.Actor`"
  therefore changes a shared function's return contract, and prerequisite 1's cached blob holds raw
  per-class tags rather than resolved values. The information is available *at* that loop so the change
  is small — but it is a change to a shared seam, not a pure output tweak. **Either implement provenance
  as part of this, or drop the "names the class it came from" promise; do not assume it is free.**

It also removes the documentation workaround this detour currently lives in — one parenthetical inside
the DX class catalog, which is where an agent looking for lighting behavior does not look.

**A class that declares no own properties says so.** `class show DeusEx.DataCube` prints a header, a
superclass chain and `(+142 inherited, in 16 more categories: …)` — and **no property names**, because
`DataCube` declares none of its own. The output is indistinguishable from "this property does not
exist", and the bare category list gives no clue which of the 16 holds the one you want. When a class
has zero own properties, `show` prints an explicit one-line hint naming the two ways through
(`--depth all`, or `--category NAME`), rather than leaving an empty space to be misread.

**`placeable` keeps ONE definition — the existing file-fact proxy** (`classindex.is_placeable`), and its
`--help` is corrected to state what the predicate actually does. **It is FAIL-OPEN**, which the earlier
wording ("non-abstract, descends from `Actor`") hid: the real test is
`descends_from(fqcn, Engine.Actor) and is_abstract(fqcn) is not True`, so a class whose abstractness is
**undeterminable counts as placeable** — deliberately, so it is listed rather than hidden. Two consequences
to settle in the same slice: the help text must name that third case, and the branch is a "don't know"
answered as a confident yes, which sits against `conventions.md` "A predicate answers or it RAISES".
**Pick one and do it: state the fail-open behaviour in the help, or make the undeterminable case raise.**
Do not ship the promised-but-inaccurate string, which is exactly the stale-help failure `conventions.md`
cites by name. *No histogram, no derived "commonly placed"* (decision 1). Whether something is
worth placing is a classification an LLM writes. This keeps `class list` **offline, maps-free and
~0.4 s**, instead of requiring 120 stock map files on disk.

**No verb collision remains.** `class show` keeps the property-browser view and `--category` keeps
meaning the UnrealEd property category; it gains the catalog fields. `class list` keeps its
inheritance tree and existing flags. Previews live on the new `class preview`. **The build must state,
flag by flag, what `class list --json` and `class show --json` emit** — `class list` today prints a
tree with no `--json`, and its `--package` already means "the *placeable* classes defined in P"
(filtered), not a plain corpus scope. This is the one place the four kinds are **not** literally
uniform, and the spec accepts that explicitly rather than pretending otherwise.

**Thumbnails.** `DT_Mesh` → native render from `Mesh` + `MultiSkins[i]` in the class defaults (the
mesh's own `Textures` array is only a fallback — Deus Ex characters carry none). `DT_Sprite` → the
`Texture` default's image — **read the class's resolved `DrawType`; if it is `DT_Sprite`, the picture is
the resolved `Texture` default's image, reported as-is.** *(Owner ruling, 2026-07-26.)* Probed live on
the tracked packages: `Engine.ZoneInfo` → `Texture'Engine.S_ZoneInfo'`, `Engine.Light` →
`Texture'Engine.S_Light'`, `Engine.PlayerStart` → `Texture'Engine.S_Player'`, all with
`DrawType = DT_Sprite`. Note the property is **`Texture`**, not `Sprite`: `Sprite` exists on
`Engine.Actor` but resolved to `None` on every class sampled.

**There is deliberately NO editor-icon detection, and no `preview_state: editor-icon`.** An earlier
draft marked sprite classes whose `Texture` resolves to an "icon group" and had `prewarm` skip them.
That is deleted for two reasons. First it does not work: measured against tracked `uned/UED22/Engine.u`,
**28 of its 32 texture exports are GROUPLESS** — `S_Weapon`, `S_Camera`, `S_ZoneInfo`, `S_Ambient`, … —
and the only groups present are fonts, so a group pattern matches nothing and every sprite class would
have been silently reported `ok`. Second, and decisive: deciding that a lightbulb glyph "tells an agent
nothing" is the tool **inferring meaning**, which §0 forbids. That glyph genuinely *is* what the class
looks like in the editor. The tool produces the picture; the LLM looks at it and decides it is an icon
and worth little. The only name-based alternative (the `S_` prefix) is exactly the name guess
`direction/conventions.md` rejects for class questions.

`DT_Brush`/`DT_None` → `preview_state: no-mesh` (an honest "no artifact exists", not a judgement).

**`--out DIR` file naming.** `<ref>` with dots replaced by `-`, casefolded, plus the angle for multi-angle
kinds: `coretexmetal-ladder-ladrbrwnmetal.png`, `deusexdeco-barstool-iso.png`. Dots are the ref separator so
they cannot survive into a filename unambiguously; casefolding matches the shard paths (§3b) and refs
resolving case-insensitively everywhere else. A collision after that transformation **exits 2 naming both
refs** rather than overwriting — `--out` writes where the user asked, so `direction/safety.md`'s
never-clobber rule applies to it exactly as to any other destination.

**`sound preview` does not exist in phase (a).** Its artifact is the spectrogram, which is phase (b) work
behind the `.uax` decode spike, and music's precedent is that a verb with nothing behind it should not
ship. So phase (a)'s `sound` family is `list`/`search`/`show`/`classify …`/`tags`, and `preview`/`prewarm`
arrive with phase (b).

**Cost shapes the design:** ~254 ms flat / ~332 ms textured at 256 px per render (~75/109 ms at
128 px); mesh *decode* is only ~2–13 ms — the rasterizer dominates. Hence decisions 7 and 11.

**Invalidation stores tuples, not refs.** A thumbnail depends on the class's `.u` *and* every skin
package it references, but the index filename carries only one file's stat identity. The row stores
the contributing packages' `(realpath, size, st_mtime_ns)` in `deps`, re-stat'd on read (~5 µs each).
Without this, a changed texture package leaves the `.u`'s index valid while its thumbnail is stale.

**Two small engine questions to settle during the build:** whether any placeable actor overrides
`DrawType` per-instance (the adapter assumes the class default is authoritative), and which animation
frame is characteristic (thumbnails use frame 0; an `Idle` sequence's `StartFrame` may read better).

## 7. The audio arms

**Phase (a) — everything that needs no sample decoding.** Enumeration, ref names, package/group
structure, name-keyed identity (decision 4), the full `classify` family, and for `.umx` the
**embedded module title** — verified live: for an **Impulse Tracker** module the header carries it at a
fixed offset (`IMPM` magic + 26-byte name), giving `Area51_Music` → "Area 51", `Credits_Music` → "The
Illuminati", `Area51Bunker_Music` → "Begin the End". A ~20-line sniffer delivers most of the music arm's
value.

**The sniffer must dispatch on magic, and report absence as absence.** `.umx` is a container: UE1 also
wraps **S3M** (`SCRM` at +0x2C), **XM** (`Extended Module:` at 0), and **MOD** (a 4-byte tag at +0x438,
with no reliable magic in the oldest variants). Deus Ex ships IT, but `direction/scope.md` puts other UE1
games in scope, so an IT-only reader silently returns an empty title on a valid S3M. Rule: recognise
IT/S3M/XM by magic and read each one's title field; on an unrecognised container report
`title: null` **and** a `format` fact naming what was found (or `unknown`), never a blank that reads as
"this module has no title". A wrong or silently-absent title is a half-answer.
Because identity is name-based, **phase (a) ships the classify verbs for both audio kinds** — there
is no key to invent later and nothing to re-key.

**Phase (b) — after the `.uax` decode spike.** Duration, rate, channels, loopability, spectrogram
previews, and an opt-in `sound export <ref> --out X.wav` for human audition. Purely additive.

Note what is *not* here: the tool does not tell you where a sound is used. An agent investigates that
and writes it into the description (§0).

**`.unr` is NOT added to the package extension set. Dropped, with the reason recorded.** An earlier draft
made it a one-line aside ("`.unr` must be added … in all three places" — `config.PKG_EXTS`,
`packages._PKG_EXTS`, `dxpkg._PKG_EXTS`). The 2026-07-26 gate established that this is not a catalog
detail but a **global change to the tool's search path**, with no stated reason and no test:

- `config.PKG_EXTS` drives `config.composed_search_files`, i.e. the load set for *every* consumer — the
  class index, all texture resolution, materialize's `editor_search_dirs`, and `_validate_ingest_actors`
  on the **hot author path** (`actor add`), which plan S4 holds to sub-100 ms.
- `_dedup_by_stem` is **extension-blind** ("identity is the bare stem regardless of extension"), so a
  `Foo.unr` would silently **shadow** a same-stemmed `Foo.utx`/`Foo.uax` for all consumers.
- Every measured number in this spec (the ~550 sound corpus, `class list` ~0.4 s, the 26.4 s/~50 s
  texture cold costs, the 10,826-export sweep) was taken **without** it, so adding it invalidates the
  measurements the design rests on.

If map-embedded objects are wanted in the catalog later, that is its own spec with its own measurements
and a `dxpkg._PKG_EXTS` sync test (which does not exist today — only the `config`↔`packages` pair is
enforced). Nothing in the four kinds needs it.

## 8. What the catalog unlocks downstream

Author-time validation of **ObjectProperty refs** (`AmbientSound`, `Song`, `OpeningSound`, mesh, …):
a typo'd ref currently exits 0 and **silently ships a broken level**.

**Honest scoping — this may not need the catalog at all.** The check is "does this object exist on the
composed path", and `utexture.TextureResolver.exists()` already answers it for textures (and is already
wired into `_validate_ingest_actors`, stubbed in tests by `conftest._stub_author_validation`). Validation
must moreover query the **raw export tables**, not the catalog's kind-scoped enumeration — otherwise a
perfectly valid `DeusExConAudio…` ref would exit 2 merely because the VO exclusion (§4a) hides it from
`sound list`. So the honest statement is: **this fix is generalising an existing existence check across
the remaining property types, and the catalog's package-loading layer is a convenience, not a
prerequisite.** It stays early in §13 because it is cheap and fixes a live bug — not because the catalog
unlocks it. *(An earlier draft claimed the catalog "supplies the dependency this was waiting on"; the
2026-07-26 gate showed that overstates it.)*

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

## 10. Non-goals

- **Montage / contact sheets** (decision 14 — misattribution silently corrupts a catalog).
- **Semantic/embedding similarity** (heavier deps, against the Pillow-only offline ethos).
- **Any tool-side inference of meaning or usage** (decision 1) — that is the LLM's job.
- **Similarity for class/sound/music** in v1.
- **Mesh export** (`.3d`/glTF) — the decoder exists, but exporting is not a catalog need.
- **Replacing `preview --game`** — the in-game path stays the answer for real-lighting hero shots.
- **Migration of the legacy catalog** (decision 13).

## 11. Prerequisites

1. **`schema_cache` v2 — persist the class defaults the catalog needs.** `schema_cache` today caches
   discovery + own-property schema and **explicitly no defaults**; `DrawType`, `Mesh`, `MultiSkins`,
   `CollisionRadius`, `PrePivot` all come from `uprops.resolve_class_defaults`, which is memoized
   **per invocation only**. Without persistence every cold `class list --json`/`search --drawtype`/
   `preview` re-resolves defaults corpus-wide (~14.6 s measured) — on exactly the exploratory verbs
   decision 7 exists to keep fast. Add a defaults blob beside the existing ones, bump
   `SCHEMA_CACHE_VERSION`, refresh goldens. *(Gates the class arm. The alternative — letting the
   catalog index own defaults — recreates a second independently-versioned cache over the same `.u`
   and is rejected.)*
2. **Full native texture decode** — gates the **texture arm only**. Now specced in its own right:
   [`specs/2026-07-25-native-texture-formats.md`](2026-07-25-native-texture-formats.md) (review-gated
   2026-07-25). Note it is **not** the generic-UE1-hygiene-only job this spec first assumed: the
   `bHasComp`/`CompMips` finding means **30 textures in the project's own `LUM_CoreTex.utx` are
   invisible to uedcli today**, so it fixes a live bug on this substrate.

*(The earlier "native map-actor reader" prerequisite is GONE with the usage index — decision 1.)*

## 12. Test coverage

**Split offline vs integration deliberately.** `bin/test` is the offline suite; real Deus Ex packages
live in the gitignored install reachable only via `conftest.install_root()` and `-m integration`,
which `pytest.ini` deselects. So every assertion about the real corpus is integration-only unless it
runs against a committed fixture.

**Fixtures come from two sources, and the split is not the one earlier drafts assumed.** This spec once
said "commits tiny synthetic fixture packages (a hand-built `.u`/`.utx` …)"; the plan then rejected that
outright as infeasible ("there is no UE1 package writer in the tree") and switched to real packages only.
**Both were wrong.** Measured 2026-07-26:

- **Synthetic `.utx` is available and is not this spec's to build.** `uedcli/native/pkg_write.py` has
  `build_package`/`NameTable`/`ExportRec`, and `dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py`
  is a **committed, self-verifying** v69 `.utx` builder with back-patched `TLazyArray` offsets. The
  already-gated `specs/2026-07-25-native-texture-formats.md` §5a promotes it to `uedcli/tests/pkgfixture.py`
  and makes it "the fixture API every offline test is written against". **This spec depends on that,
  rather than growing a fixture slice of its own** — say so, because two artifacts inventing one writer is
  how they diverge.
- **Synthetic `.u` is NOT available** — a hand-built class package with a mesh would be a slice in itself
  and the mesh layout is not established until the class arm. So class/sound/music assertions use the
  **34 git-tracked real `.u` packages** under `uned/UED22/` (`DeusEx.u`, `DeusExDeco.u`, `DeusExSounds.u`,
  `Engine.u`, `Fire.u`, `core.u`), which are enough: `Engine.ZoneInfo`'s defaults, the 84 `bMasked`
  exports in `DeusExDeco.u`, and the groupless `S_*` sprite icons in `Engine.u` all resolve offline.
  *(There are **no** tracked `.utx`/`.uax`/`.umx` under `uned/` — the two committed `.utx` live in
  `uedcli/tests/fixtures/` — which is exactly why the synthetic `.utx` writer matters.)* Note `conftest.py`'s autouse `_schema_cache_off`
forces `UEDCLI_SCHEMA_CACHE=off`, so class-adapter tests exercising the cache path must opt back in.

- **Engine (offline, fixtures):** ref → identity → preview resolution per kind; cross-package dedup
  (two refs, one identity, one file, one classification); stat invalidation on
  realpath+size+st_mtime_ns; the **overlay-shadow collision** (same stem, different realpath → two
  entries, no cross-serve); the **kind-keyed index** (indexing one package as textures then as classes
  leaves both intact); `undecodable` vs `preview_state` distinguish unparseable from
  no-artifact; a version bump leaves a reclaimable orphan dir.
- **Preview lifecycle:** `cache gc` evicts an artifact → `list --json` reports `preview: null`, not a
  dangling path.
- **shard-index:** matches a full scan; the gate catches a **deletion** (prune → gone from
  `tags`/`status`); two projects on one machine get separate roll-ups.
- **Merge semantics (§3b):** re-`set` unions tags rather than replacing them; `colors` replace and mark
  `set`; a *different* non-empty `description` exits 2 naming the ref and printing the stored text, and
  `--replace` overwrites it; re-setting identical text is a no-op; filling an empty description merges;
  `unset --tags a,b` removes exactly those and leaves the rest; bare `unset --tags` clears the field;
  **two differently-named refs with identical pixels resolve to ONE shard and the second `set` reports on
  stderr that the identity was already classified under another `ref`**.
- **Classification:** round-trip per kind; write-once `ref` on pixel-hashed shards; two agents writing
  different identities never touch one file; `classify set -` JSONL writes N shards; casefolded
  name-keyed paths (two spellings → one shard); `unset` whole and per-field; `clone` keep-local +
  skip-report; the outdated flow (pixels change → unclassified, old shard surfaces by its stored ref,
  `prune` removes, `cache gc` never touches tracked files).
- **Texture group (§4c):** a grouped texture's `group` is reported as a fact even when its ref is
  2-part (the `LadrBrwnMetal` shape — grouped, no intra-package collision, so the group appears
  nowhere in the ref); a groupless texture reports `null`, not a missing key; `--group Ladder` selects
  it and `--group ""` selects the groupless ones; group is NOT part of identity (two identical images
  in different groups → one shard, and classifying via either ref classifies both).
- **Texture `masked` (§4d):** a texture with the `bMasked` tag reports `true`, one without it reports the
  **resolved class default** (never a missing key). Three distinct regressions, because the obvious one
  is not sufficient: (i) a texture whose palette HAS an index-0 colour but which carries no `bMasked` tag
  reports `false` — stops anyone re-deriving the fact from the palette; (ii) **a texture with no tag whose
  CLASS defaults `bMasked = True` reports `true`** — this is the one that distinguishes the correct
  default-relative rule from "absent means false", and without it the wrong rule ships green, since no
  committed fixture carries the tag at all; (iii) `--masked` filters, and `masked` is not part of
  identity. Offline sources: tracked `uned/UED22/DeusExDeco.u` has 84 tagged exports; case (ii) needs a
  synthetic fixture (§12 fixture note).
- **Frozen identity (§3b):** the committed golden (ref → hex digest over `CoreTexWater.utx`) holds;
  adding a fact to a row does not change any identity.
- **Texture:** `Engine.Texture` **subclasses** enumerated (FireTexture/WetTexture/WaveTexture);
  **colours pre-filled and ordered by share**, and `--color` works with an EMPTY classification store;
  an LLM `colors` override wins and is marked `set`; similarity ranks a known near-pair above an
  unrelated texture AND discriminates two flat same-luminance different-colour textures; `--similar` +
  lexical terms → exit 2; the error taxonomy (unknown / ambiguous / undecodable / EACCES) each named.
- **Class:** thumbnail invalidation on a **skin package** change (not just the `.u`);
  `DT_Brush`/`DT_None` → no preview, editor-icon sprites flagged and skipped by `prewarm`;
  `list`/`search` **never render** (a cold `class list --json` completes producing no artifact);
  `class show` reports bbox/collision/pivot; `class list` stays offline and maps-free.
- **Class defaults in `show` (§6):** `Engine.ZoneInfo.AmbientBrightness` reports `= 0` — the exact
  regression that cost an hour, asserted against a committed fixture so it holds offline; an
  *inherited* default names the class it came from; a property with no default reports its type's zero
  value marked as such, never blank; a class declaring **zero own properties** emits the
  `--depth all`/`--category` hint rather than an empty property list.
- **Search ranking (§5b):** tokenization of `ClenGrayMetal_A`; field weights; `texture search wall`
  ranks walls first over a zero-classification corpus.
- **Audio (§7):** the `.umx` title read is pinned by a committed regression (`rules/spikes.md`: pin every
  checkable finding or it rots) — an IT module's title is read at `IMPM`+26, an S3M's and an XM's from
  their own header fields, and an unrecognised container reports `title: null` with a `format` fact rather
  than a blank; the **VO exclusion** drops the configured packages from `sound list`, reports the excluded
  count on stderr, `--include-vo` restores them, and `sound show`/`classify` still accept an excluded ref
  by name; `sound preview`/`prewarm` are **absent from the parser** in phase (a), as `music`'s are
  permanently.
- **ObjectProperty-ref validation (§8):** a typo'd `AmbientSound`/`Song`/mesh ref exits 2 naming it at
  author time instead of exiting 0; a **valid but VO-excluded** ref still validates (the check reads raw
  export tables, not the kind-scoped enumeration); the existing texture path keeps working.
- **CLI:** `show` vs `preview` output shapes; `preview` emits `<ref>\t<path>`; `--json` carries
  `preview: null` when uncached; `preview --skeleton` emits one JSONL row per ref; empty stdin → exit 0.

## 13. Build sequencing

Value-first (Andrzej, 2026-07-25), with the texture arm no longer first because there is no migration
to serialize behind:

1. **Engine + enumeration + `list`/`show` + ObjectProperty-ref validation (§8).** Fixes a live bug that
   silently ships broken levels today. **Blocks on prerequisite 1 (`schema_cache` v2), NOT on nothing** —
   an earlier draft said "blocks on nothing" and that is wrong: `DrawType` is a class file-fact (§4) and
   is default-sourced, and `masked` is default-sourced too (§4d), so without persisted defaults every
   cold `class list --json` / `class show` / `--drawtype` re-resolves corpus-wide (~14.6 s measured) —
   the exact outcome decision 7 exists to prevent, on the very first exploratory command. **Prerequisite
   1 therefore lands FIRST, ahead of the adapters**, and gates the texture arm as well as the class arm.
2. **Class arm** — then productise the spike's mesh decoder into
   `uedcli/`, `class preview`, and the size/collision/pivot facts. This is the capability an agent
   most lacks: it cannot see what it is placing.
3. **Texture arm** — prerequisite 2 (non-P8), native decode, pre-filled colours, `--similar`; deletes
   `texture sync` and the UCC/Wine path; deletes the legacy `texture-catalog/` (decision 13).
4. **Audio phase (a)** — enumeration, names, module titles, classify for both audio kinds.
5. **Audio phase (b)** — after the `.uax` decode spike: spectrograms, duration, `sound export`.

**Two changes need a slice that the plan does not currently have** — the plan predates them and its
done-when for the class slice still says "no existing `class` OUTPUT changes", which they violate:
**§4d** (`masked` as a texture fact, in the texture arm, and it moves `masked`'s default-resolution
dependency onto prerequisite 1) and **§6**'s `class show` default-value reporting (in the class arm,
including the `uprops` provenance question). Re-cut the plan before building; neither is optional
polish, and both change user-visible output.

## 14. Review history

**Round 1 + 2 (2026-07-25, 4 cold reviewers)** — see the two entries below.

**Revision (2026-07-26, owner-directed) — four changes.** (1) **§4c** makes the texture **group** a
stored, queryable fact with `--group`, where it had been consumed only while assigning refs and discarded
whenever a ref came out 2-part, hiding `Ladder`-group membership; (2) **§3b** pins the pixel-hash identity
as load-bearing and **frozen**; (3) **§4d** adds `masked` as a fact read from the export's stored flag;
(4) **§6** makes `class show` print each property's **resolved default** and makes a class with no own
properties say so. *(An earlier version of this section said "two owner-directed changes" while listing
four.)*

**Round 3 (2026-07-26, 3 cold Opus reviewers) — ~58 findings, all three verdicts "not ready to build on".**
Convergence was high: 17+ findings were hit independently by two or three reviewers, including **all four
defects in the revision above**. The round is recorded here rather than summarised away because it changed
the design, not just the prose.

**Owner rulings that resolved the structural findings** (2026-07-26; durable home
`direction/asset-catalog.md`, parked as `[OWNER — confirm]` items where that tree needs editing):

- **Procedural textures are hashed on what makes them distinct** → new **§3c** (per-class declared
  parameter set, frozen, class-namespaced). Replaces the earlier consequence that ~326 water/fire/ice
  textures were enumerable but permanently unclassifiable.
- **Only pixels are hashed** → §3b. The mask is *not* in identity, so the preview PNG is opaque RGB at
  native size and cut-out-ness reaches the agent as the `masked` fact instead.
- **`ScriptedTexture`**: no preview (`preview_state: scripted`, reason on stderr), name-keyed identity.
- **`classify set` MERGES** (tags union, colours replace, conflicting description refused) → §3b.
- **JSONL on `classify set -` is an approved third stdin convention** → decision 8.
- **The catalog dir default is `asset-catalog/`** → `direction/projects-and-config.md` updated.
- **Sprite previews**: `DrawType == DT_Sprite` → the resolved `Texture` default's image, reported as-is;
  **editor-icon detection deleted** (the "icon group" signal does not exist — 28 of 32 `Engine.u` texture
  exports are groupless `S_*` — and judging a glyph useless was the tool inferring meaning).

**What the non-structural findings changed** (all folded, this revision): the group fact's real source is
the export **Outer**, not the deleted PCX-stem parser; `bMasked` is **default-relative**, so the read rule
is tag-else-class-default and the texture arm now needs prerequisite 1; `class show`'s provenance is **not**
free (`resolve_class_defaults` discards it); the row shape carries `masked` and `phash`; **`search` now
requires terms** (term-less it was byte-identical to `list`); `--placeable` dropped for the existing
`--include-abstract`; `is_placeable` is **fail-open** so the promised help text was wrong; `--skeleton`
replaces the stdout stream and carries the artifact path, making §5a's loop actually typecheck; the preview
cache is its **own pool** with its own budget and a recursive sweep; stat-keyed index files are reclaimed by
`gc`; the VO exclusion is **config with `--include-vo`**, not a hardcoded DX pattern; the `.umx` sniffer
dispatches on magic instead of assuming Impulse Tracker; **`.unr` is dropped** from the package extension
set (global blast radius, no rationale, and it would have invalidated every measurement here); `§8`'s
premise is scoped down to "generalising an existing existence check"; the fixture story is split into the
sibling spec's synthetic `.utx` writer plus the 34 tracked `.u` packages; and every citation of the frozen
`decisions.md` is repointed.

**Still open, and NOT resolvable by an implementer** — `board/inbox.md` carries each as `[OWNER — confirm]`:
the `conventions.md` carve-out for the third stdin convention, and whether curation gets a general
file-fact **override** field (decision 10 — `direction/asset-catalog.md` contradicts itself).

**Round 1 (2026-07-25, 2 cold reviewers)** — 21 findings, all folded: the false "reads `.dx` natively"
claim, class-default-sourced refs, sound identity in phase (a), the kind-less index key, migration
ordering, cross-project shard-index, the `class` verb collision, sound corpus scope, thumbnail cost,
batch classify, `show`'s contract, skin invalidation, dropped carry-overs, music identity, `catalog gc`,
the bogus pipe example, texture subclasses, and the non-P8 serialization.

**Round 2 (2026-07-25, 2 cold reviewers)** — the round that reshaped the spec. `schema_cache` cannot
serve class defaults (→ prerequisite 1); the legacy catalog holds no authored data and is untracked
(→ decision 13, migration deleted); `class list`/`show` shapes still collided in detail (→ §6 states
the asymmetry); `placeable` had two definitions with circular sequencing (→ one file-fact definition);
dangling previews after `gc` (→ verify at emit); the flock domain mismatch (→ two lock domains);
§13's tests were integration-only (→ committed fixtures); `.unr` in three places; the cache-version
path segment; missing class size facts (→ §6); unspecified `search` ranking (→ §5b); editor-icon
sprites (→ §6).

**The reframe both rounds missed.** Round 2 recommended building *less* classification machinery
because the existing catalog is 0% classified, and both rounds encouraged the tool to compute more
(usage sweeps, placement histograms). Andrzej rejected the premise outright: the tool should be
**passed** classification data, not work things out (§0, decision 1). That deleted the usage index,
the placement histogram, derived `placeable`, and the map-actor reader prerequisite — and restored
classification to the centre of the design, with texture colours (§4b) as the single deliberate
exception.
