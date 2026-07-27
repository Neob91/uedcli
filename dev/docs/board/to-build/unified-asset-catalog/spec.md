# Spec: asset catalog — the shared ENGINE (and the split index)

**Status:** the unified spec was **SPLIT on 2026-07-26** after two spec-gate rounds (3 cold Opus reviewers
each) returned ~103 findings and the churn proved to be concentrated in two arms. This document keeps what
every arm shares — the governing principle, the owner's decisions, the storage layout, the verb surface, the
prerequisites — and the arms live beside it.

| document | status |
|---------------------------------------------------------------------|---
| **this file** — engine, storage, verbs, decisions, prerequisites | needs a spec round on the split |
| `class arm` (board item `the-asset-catalog-class-arm-needs-four-changes`) | **findings folded; build FIRST** |
| [`texture arm`](spec-texture-arm.md) | **4 open owner decisions** — holds every irreversible call |
| `audio arms` (board item `sound-corpus-remeasure`) | **BLOCKED** — corpus must be re-measured on the composed path |

**Why split.** Two rounds of fixing did not converge, and the second round's defects were partly created by
the first round's fixes — the pattern `CLAUDE.md` "Review gates" says another round will not land. The
findings clustered: the **texture** arm carries every frozen/irreversible decision (identity, procedural
hashing, alpha, the preview↔identity coupling), the **audio** arm's scope rule was sized by measurements
taken over directories the tool does not load, and the **class** arm — the capability an agent most lacks —
was nearly clean and blocked on neither. Splitting lets the class arm ship while the texture decisions get a
dedicated gate. *(Owner's call, 2026-07-26; `board/inbox.md` carries the round outcome and the escalations.)*

**Build order is the dependency order:** this engine → class arm → texture arm → audio arms.

**Requested by:** the owner (2026-07-25, session `uedcli:catalog`).
**Ephemeral:** scratch, per `CLAUDE.md`. **The durable homes are
[`direction/asset-catalog.md`](../../../direction/asset-catalog.md)** (the owner's decisions — agents may not
write it without an explicit yes) **and [`rationale/`](../../../rationale/)** (the agent's choices). Fold the
outcome into `architecture.md` + `usage.md` on build, then delete.

> **Do not cite `dev/docs/decisions.md`** — it is FROZEN, and `CLAUDE.md` states there is no decisions
> ledger. [`rationale/MIGRATION.md`](../../../rationale/MIGRATION.md) maps every old dated citation to its home.


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
   [`2026-07-25-native-mesh-decode`](../../../spikes/2026-07-25-native-mesh-decode/README.md). *Rejected:
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

## 3. Storage layout — the shared engine

**The per-project tracked classification (§3b) and the procedural identity rule (§3c) moved to the**
**[texture arm](spec-texture-arm.md)**, because that is where identity is frozen and
where the open owner decisions sit. What stays here is the derived cache every arm writes.

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

## 4. The kind adapters — the protocol

## 4. The kind adapters

| | **texture** | **class** | **sound** | **music** |
|---|---|---|---|---|
| source | every export descending from `Engine.Texture` | `.u` class exports (via `classindex`) | `.uax` + `.u`, minus VO (§4a) | `.umx` music exports |
| identity | sha256(w, h, RGB) | `Package.Class` | `Package.Name` | `Package.Name` |
| preview | decoded PNG | native mesh render (`DT_Mesh`) or the `Texture` default's image (`DT_Sprite`, §6) | spectrogram (phase b) | none |
| file facts | w, h, format, **group (§4c)**, **colours (§4b)** | parent, DrawType, abstract, **bbox, collision, pivot** (§6) | duration/rate/channels (phase b) | format, embedded module title |
| similarity | phash ⊕ colour distance | — | — | — |

**Each arm owns its own adapter row and its own facts.** The per-arm detail — corpus scope, the facts
read, and the per-kind filters — lives in that arm's spec. **Note the table above is STALE for texture**
**and must be re-derived from the texture arm** (its identity is no longer a single pixel hash; its facts
now include `masked` and a persisted `phash`).

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

## 6. What the catalog unlocks downstream

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
   board item `three-design-calls-the-native-texture-formats` (review-gated
   2026-07-25). Note it is **not** the generic-UE1-hygiene-only job this spec first assumed: the
   `bHasComp`/`CompMips` finding means **30 textures in the project's own `LUM_CoreTex.utx` are
   invisible to uedcli today**, so it fixes a live bug on this substrate.

*(The earlier "native map-actor reader" prerequisite is GONE with the usage index — decision 1.)*

## 12. Test coverage — the engine

Read `dev/docs/rules/tests.md` first. **Per-arm coverage lives in each arm's spec.** This section covers only
the shared engine.

**Split offline vs integration deliberately.** `bin/test` is the offline suite; real Deus Ex packages
live in the gitignored install reachable only via `conftest.install_root()` and `-m integration`,
which `pytest.ini` deselects. So every assertion about the real corpus is integration-only unless it
runs against a committed fixture.

**Fixtures come from two sources, and the split is not the one earlier drafts assumed.** This spec once
- **Engine (offline, fixtures):** ref → identity → preview resolution per kind; cross-package dedup
  (two refs, one identity, one file, one classification); stat invalidation on realpath+size+st_mtime_ns;
  the **overlay-shadow collision** (same stem, different realpath → two entries, no cross-serve); the
  **kind-keyed index** (indexing one package as textures then as classes leaves both intact);
  `undecodable` vs `preview_state` distinguish unparseable from no-artifact; a version bump leaves a
  reclaimable orphan dir; `gc` reclaims stat-keyed index files whose stat tuple no longer matches.
- **Preview lifecycle:** `cache gc` evicts an artifact → `list --json` reports `preview: null`, not a
  dangling path; the preview pool is evicted independently of the schema pool; a `prewarm`'s output is
  not evicted by the next process's sweep.
- **shard-index:** matches a full scan; the gate catches a **deletion** (prune → gone from
  `tags`/`status`); two projects on one machine get separate roll-ups.
- **Classification + merge:** round-trip per kind; re-`set` unions tags; `colors` replace and mark `set`;
  a *different* non-empty `description` exits 2 printing the stored text, `--replace` overwrites;
  re-setting identical text is a no-op; `unset --tags a,b` removes exactly those; two agents writing
  different identities never touch one file; **two differently-named refs with identical pixels resolve
  to ONE shard and the second `set` reports it on stderr**; `classify set -` JSONL writes N shards;
  casefolded name-keyed paths; `clone` keep-local + skip-report; the outdated flow.
- **CLI:** `show` vs `preview` output shapes; `preview` emits `<ref>\t<path>`; `--skeleton` REPLACES that
  stream with JSONL carrying the artifact path; `--json` carries `preview: null` when uncached; empty
  stdin → exit 0; a truncated result set reports the cap and the withheld count on stderr.
- **ObjectProperty-ref validation:** a typo'd `AmbientSound`/`Song`/mesh ref exits 2 at author time
  instead of exiting 0; the check reads **raw export tables**, not the kind-scoped enumeration.

## 13. Build sequencing

**This engine first, then the arms in dependency order.** Within the engine:

1. **Prerequisite 1 (`schema_cache` v2)** — persists resolved class defaults. It gates more than the
   class arm: `DrawType` is default-sourced, and so is the texture arm's `masked`.
   *(Cost note: a gate reviewer measured resolving all six texture classes' defaults at **0.28 s** cold,
   not the ~14.6 s corpus-wide figure — so this gates the texture arm cheaply, and the sequencing
   argument for it rests on the CLASS corpus, not on `masked`.)*
2. **Engine core** — the per-`(kind, package)` index, the derived cache, the classification store and
   its locks, the shared fixture dependency.
3. **`list`/`show` + ObjectProperty-ref validation** — the validation fixes a live bug that silently
   ships broken levels today. Scoped honestly: it generalises an existing existence check
   (`utexture.TextureResolver.exists()`), and the catalog's package-loading layer is a convenience, not
   a prerequisite.
4. Then: **class arm (board item `the-asset-catalog-class-arm-needs-four-changes`)** →
   **[texture arm](spec-texture-arm.md)** (blocked on 4 owner decisions) →
   **audio arms (board item `sound-corpus-remeasure`)** (blocked on a re-measurement spike).

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
