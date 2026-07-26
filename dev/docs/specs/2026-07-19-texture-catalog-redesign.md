# Spec: texture catalog redesign — lazy native decode, content-addressed cache, `show` + similarity

**Status:** specced (awaiting review gate → plan → build).
**Requested by:** Andrzej (2026-07-19, session `uedcli:board`). A re-design of the whole texture
catalog, not just the `texture show` add-on. Supersedes the narrower
[`specs/2026-07-19-texture-show-for-llm.md`](2026-07-19-texture-show-for-llm.md).
**Ephemeral:** per the uedcli `CLAUDE.md`, this spec is scratch. The load-bearing decisions +
rejected alternatives are recorded in the durable append-only
[`dev/docs/decisions.md`](../decisions.md) (entry **2026-07-19 03:58 UTC — texture catalog
redesign**). On build, fold the outcome into `architecture.md` (replace the current "Texture catalog"
section) + `usage.md`, and delete/stale-mark this file and the `texture-show-for-llm` spec.

**Folds in three previously-separate board items** (all subsumed here):
- the `texture show` plan item (`to-plan.md`),
- the "native `texture sync` decode — drop UCC-under-Wine" spec item (`to-spec.md`),
- the deferred "content-addressed texture-image cache + `texture classify clone`" spec item (`to-spec.md`).

---

## 0. Who the consumer is (frames everything)

The **main consumer is an LLM agent**, not a human at a GUI. It cannot open an image viewer, but the
harness (Claude Code) **can read an image file** when handed its path, rendering the pixels into the
model's context. So the catalog's job is: **given a way to find textures (by name / tag / color /
visual similarity), hand back each one's decoded-image path and its metadata**, so the agent sees the
pixels and records a classification that persists.

## 1. What's wrong with the catalog today (the motivation)

Today (`texture` verbs: `sync`, `list`, `search`, `tags`, `classify status|set`):

1. **`sync` is a slow, mandatory prerequisite.** It shells `UCC.exe batchexport` under **Wine inside a
   Docker container** per package (container round-trip + Wine + per-package UCC startup), copies PCX
   out, decodes host-side with Pillow. Nothing works until it has run; it is ~40–65 s/package with no
   progress output.
2. **Classification is blind.** No verb surfaces the pixels — `list`/`search`/`classify status` print
   text rows only.
3. **The decoded-image path is unlocatable by hand.** The cache filename uses the texture's internal
   **Group**, not the ref's package (`CoreTexWater.bluewater` → `.../CoreTexWater/water.bluewater.png`),
   so a human/LLM can't map a ref to its file, and the path is derived-by-convention (not stored) so it
   can't just be printed reliably either.
4. **The manifest is name-keyed and per-package.** A texture re-exported into two packages is two
   independent entries; classification can't be shared across packages or projects; `stale`/`removed`
   bookkeeping exists to paper over rename/change churn.

## 2. The redesigned model (one paragraph)

Decode becomes **on-demand and native** (the pure-Python `utexture.py` decoder — no UCC, no Wine, no
Docker), **lazily** driven by a per-package **stat tuple (path, size, mtime)** exactly like the
`class list`/`class show` schema cache: no bulk `sync` step, the cache re-decodes a package only when
its bytes change. Decoded images live in a **per-user, content-addressed cache** keyed by the
**exact pixel-hash** (`sha256` of the decoded RGB), so identical textures dedupe across packages. A
separate **perceptual hash** drives **visual-similarity search**. Durable **classification**
(tags/description/color-overrides) is **git-tracked per project**, keyed by the **pixel-hash**, stored
**sharded one-file-per-texture** so concurrent agents never merge-conflict, and **cloneable** between
projects by pixel identity. The query verbs (`list`/`search --json`) carry each texture's image path +
metadata so the find→see→classify loop is one pass; a thin `texture show` covers the already-hold-a-ref
case.

## 3. Decisions (Andrzej, this session) — recorded in `decisions.md`

1. **On-demand native decode, no mandatory sync.** `utexture.py` decodes a package's textures directly
   when a verb needs them. *Rejected: keep UCC-under-Wine*, and *rejected: keep an eager sync-first
   model* — decode is cheap enough native that lazy access wins.
2. **Lazy, stat-tuple invalidation like `class list/show`.** A per-package `(path, size, mtime)` tuple
   gates the derived cache; a changed tuple re-decodes that package on next access ("re-check
   in-flight"). *Rejected: a mandatory `texture sync` bulk pass.*
3. **Drop the `sync` verb; add `prewarm` + `gc`.** No bulk step is required. `texture prewarm
   [--package]` eagerly decodes ahead of an offline session; `texture gc` evicts orphaned/stale cache.
   *Rejected: keeping `sync` as an opt-in prewarm* — a clean lazy model reads better than a vestigial
   verb.
4. **Content-addressed cache: `<pixel-hash>.png`, dedup across packages.** The exact pixel-hash
   (`sha256` of decoded RGB, size-qualified) is the cache key and the identity for dedup + clone.
   *Rejected: ref-keyed filenames* (no dedup/clone) and *storing the derived path in the manifest* (can
   dangle vs the gitignored cache).
5. **Two hashes.** Exact pixel-hash = identity/dedup/clone key; a separate lightweight **perceptual
   hash** (Pillow-only, no new deps) = similarity. *Rejected: one perceptual hash for both* — exact
   identity must be crisp (a re-encode must not merge distinct textures).
6. **Durable classification: per-project git-tracked, pixel-hash-keyed, sharded one-file-per-texture.**
   *Rejected: per-user shared auto-applied store* (not committed with the repo) and *a single
   hash-keyed `classifications.json`* (merge-hostile under concurrent agents). *Rejected: the current
   per-package name-keyed manifest.*
7. **`texture classify clone` — keep-local, skip already-classified.** Clone fills only pixel-hashes
   unclassified locally; never overwrites local work; reports skipped conflicts. *Rejected: incoming
   wins* and *error-on-conflict.*
8. **Batched distinct reads; enrich `list`/`search --json`; thin `show`.** `search --unclassified
   --json` is the batch producer (ref + path + metadata); the harness reads each image as its own file
   (no montage → no spatial misattribution); `classify set <ref>` is the sole per-ref write; auto-colors
   are trusted unless overridden. *(Carried from the 2026-07-18 22:25 texture-show decision, unchanged.)*
9. **Visual similarity = graded perceptual-hash ranking.** `texture search --similar <ref> [--max N]`
   ranks the catalog by Hamming distance on the perceptual hash. *Rejected: near-duplicate-only* and
   *semantic/embedding search* (heavier deps, against the Pillow-only offline ethos).

## 4. Storage layout (concrete)

### 4a. Per-user derived cache — regenerable, never committed

Root: `~/.uedcli/cache/textures/` (`config.texture_images_root`).

- **`images/<hh>/<pixel-hash>.png`** — the decoded image, content-addressed. The key is the **bare
  hex sha256 digest** (no `sha256:` prefix — the current code stores `"sha256:"+digest`; strip it);
  `<hh>` = the digest's first 2 hex chars = 256-way shard. One file per *distinct* image; dedupes
  identical textures across packages.
- **`packages/<package-index-key>.json`** — the per-package **decoded index**, keyed like the
  `class list`/`class show` schema cache: the **filename encodes the full stat identity**
  `(CACHE_VERSION, realpath, size, st_mtime_ns)` (architecture.md schema-cache §), NOT the bare package
  stem. This matters because uedcli is a multi-project CLI where **project overlays shadow base packages
  by stem** — stock `CoreTexMetal.utx` and a project's modified overlay both have stem `CoreTexMetal`,
  so a stem-keyed file would collide + thrash + briefly serve the wrong project's data. Realpath-keying
  (the schema cache's exact trick) gives each distinct file its own entry; a changed
  `(size, st_mtime_ns)` mints a new key (old one is `gc`-able). Contents: the package's stat tuple + a
  list of `{ref, pixel_hash | null, undecodable, phash | null, width, height, colors, color_hist}` —
  one row per export in the package's texture table, where `colors` is the ≤3 kept color names (display/
  `--color` filtering) and `color_hist` is the **full 12-bin normalized color histogram** that
  `--similar` scores against (§7) (see "undecodable" below). This is the **ref ↔ pixel-hash**
  bridge and the enumeration source for `list`/`search`. A per-package `flock` in the derived cache
  serializes concurrent decoders of the same package.
- **`shard-index.json`** — a **derived, gitignored** roll-up over the tracked `classified/` shards
  (below), stat-gated on the **max mtime across all `classified/**/*.json` shards** (a root-dir mtime is
  insufficient — editing/adding a shard two levels down, or a `git merge`/`checkout` rewriting shards,
  need not touch the root). An O(N) stat sweep (no reads) or a write-bumped generation counter detects
  any shard change; a mismatch triggers a full rescan. Without it, every cold-process `texture tags` /
  `search --tag` / `classify status` would have to open *every* shard file (O(N) tiny reads per
  invocation — the cost of sharding for merge-freedom). This index restores O(1)-ish reads; it is
  rebuilt lazily when the catalog dir changes. Lives in the per-user cache, never committed.

All three are **derived** — deletable at any time, rebuilt lazily. `image_hash`/`colors` were manifest
fields before; they move here (regenerable).

**Undecodable textures stay visible, never vanish.** `utexture.py` decodes **P8 today** (see §7 scope;
the non-P8 decoders are a build prerequisite, so at ship a supported format is NOT undecodable);
a genuinely corrupt / unparseable export must appear in the index with `undecodable: true` and
`pixel_hash: null` (still enumerable by `list`/`search`, still shown, just not viewable/hashable/
similar-rankable), NOT silently dropped from the catalog. Dropping it would be a coverage regression vs
today's UCC path.

### 4b. Per-project tracked classification — git-committed, pixel-hash-keyed

Root: the project's catalog dir (`uedcli.toml` `catalog` key, default `<root>/texture-catalog/`).

- **`classified/<hh>/<pixel-hash>.json`** — ONE file per classified *image* (`<hh>` = digest's first
  2 hex chars; `<pixel-hash>` = bare hex digest). Contents:
  ```json
  {
    "pixel_hash": "<hex-sha256>",
    "ref": "CoreTexMetal.Area51Wall_A",   // the <package>.<name> it was classified as — write-once, for outdated-entry identification (NOT the lookup key)
    "tags": ["metal", "wall"],
    "description": "riveted metal wall panel",
    "colors": ["grey"],                    // present only when overridden
    "colors_source": "set"                 // present only when overridden (absence ⇒ auto)
  }
  ```
  **The key is the hash and the file is WRITE-ONCE-per-classification** — a rename or a cross-package
  dup keeps ONE classification. The shard stores a SINGLE **write-once** `ref` (set once at classify
  time, never appended) purely for outdated-entry identification — this preserves conflict-freedom (the
  forbidden thing the review caught was a MUTABLE `refs` LIST appended on every re-sighting, so two
  agents classifying two *different refs of the same image* would read-modify-write the same shard → a
  real per-hash conflict; a write-once identifier has no such re-write). The ref↔hash *lookup* still
  runs off the derived per-package index (§4a), recomputed on read, NOT off the shard, so the shard's
  write granularity is per-**image**, and disjoint edits (different hashes) never touch the same file →
  conflict-free `git merge`, mirroring the per-actor `.t3d` ethos in `direction.md`.

- **`classified/` vs the migrating `<package>.json` files** coexist under the same tracked catalog root
  during migration; the loader must glob `classified/**/*.json` for shards and NOT sweep the old
  top-level `<package>.json` manifests as if they were shards (and vice-versa).

**Change-awareness via "outdated entries" — no stored `stale`/`removed` flag (Andrzej-designed 2026-07-19).** The shard stores the **`ref`** it was classified as (`<package>.<name>`), written ONCE at `classify set` time and never appended — so it stays write-once and merge-conflict-free (a cross-package dup of the same image keeps the first classification+ref via the keep-local rule; this is NOT the mutable `refs` list an earlier draft was told to drop). The `ref` is for **identifying outdated entries** (below); it is never the lookup key — the pixel-hash is.

When a texture's pixels change (art edited / package patched), its **current** pixel-hash differs, so it resolves to NO classification and simply **shows UNCLASSIFIED** through the CLI. That is correct — the new pixels are genuinely unclassified — and it needs no computed/stored "changed" status (the derived-status attempt was unworkable: the pre-change hash lives only in a wipeable derived cache, and a durable ref→hash ledger would reintroduce the per-hash write conflict). The prior classification is not lost: it stays keyed by the **old** hash and becomes an **outdated entry** — a shard whose `pixel_hash` matches no texture currently on the composed path.

Two verbs manage outdated entries:
- **`texture classify list-outdated`** — list every classification shard whose `pixel_hash` is present in no current package index, each row showing the stored **`ref`** (`CoreTexMetal.Foo`) + tags/description, so you see *what it was* and can re-classify the changed texture under its new hash.
- **`texture classify prune [--outdated]`** — remove outdated shards (explicit, tracked-file cleanup; `gc` never touches tracked classifications, §10-C).

So there are no `stale`/`removed` flags to maintain: change AND removal are a *derived query* ("does this hash still resolve?"), and the stored write-once `ref` makes each orphan human-identifiable.

### 4c. Migration from the current catalog (offline, lossless, no re-decode)

The existing `texture-catalog/<package>.json` entries are name-keyed and **already store the identity
hash we need**: today's `image_hash` is `"sha256:" + sha256((w,h) + raw RGB bytes)` — the *byte-identical
construction* to §7's pixel-hash. So migration is a **pure metadata rewrite, offline, needing no
package and no re-decode**: for every classified old entry, strip the `sha256:` prefix and write
`classified/<hh>/<hash>.json` preserving `tags`/`description`/`colors`/`colors_source`. **Do NOT
re-decode to recompute the hash** (the review caught that re-decoding is fragile + lossy: a since-changed
/ moved / absent package would yield a different hash → orphaned tags, or no hash → lost classification).
Because it reuses the stored hash, migration also **preserves classifications for old `removed`/`stale`
entries whose texture no longer decodes** — they carry a valid hash and must survive.
**Sequencing (must be explicit):** migrate **ALL** classified entries across **every** old
`<package>.json` FIRST; only then remove the superseded manifests. The old-manifest removal is a
distinct, explicit migration step (or `--prune-legacy` on a `texture migrate` verb) — it is **never**
folded into `gc` (which touches only the derived per-user cache; see §5). **Build-time choice
(flag to Andrzej):** auto-convert-on-read vs a one-shot `texture migrate` verb — parallel to the
prefab-migration flag in decisions.md 2026-07-18 23:01. Auto-convert-on-read is safe here *because it
reuses the stored hash* (no package access needed), but it must convert the whole catalog in one pass,
not lazily per-accessed-package, to keep the "all before any removal" invariant.

Auto-convert is idempotent via a per-package signal: convert an old `<package>.json` only while it
still exists with no corresponding `classified/` shards; a converted manifest is removed only by the
explicit `--prune-legacy` step (never `gc`), so old manifests linger until then. NOTE a read verb
(`texture list`) thereby WRITES tracked `classified/**` shards on first touch — intended; it is exempt
from the trunk "no-uncommitted-changes" pre-flight (catalog writes are not trunk writes). If that
side-effect-on-read is unwanted, make migration a required explicit `texture migrate` verb instead —
flag for Andrzej at build.

## 5. Verb surface

| Verb | Role | Output |
|---|---|---|
| `texture list [--package P] [--unclassified\|--classified] [--json]` | enumerate cataloged textures (lazy-decodes as needed) | refs one-per-line (stdout); `--json` = JSONL `{ref, png_path, width, height, colors, colors_source, tags, description, classified}` |
| `texture search <terms> [--tag] [--color] [--package] [--unclassified] [--similar <ref>] [--max N] [--json]` | rank textures by name/tag/description/color, OR by visual similarity | same shape as `list`; bare-ref-per-line by default so `search … \| brush poly set --texture -` is unbroken |
| `texture show <ref> [<ref> …] \| -` | resolve each ref → its decoded-PNG absolute path (the already-hold-a-ref case) | one path per line; `--json` = the same per-ref metadata object |
| `texture classify set <ref> --tags … --description … [--colors …]` | record classification (writes the pixel-hash-keyed sharded file) | summary → stderr |
| `texture classify unset <ref> [--tags\|--description\|--colors\|--all]` | remove a classification (or specific fields) — the undo path for a mis-tag | summary → stderr |
| `texture classify status [--full]` | classification progress (uses the derived shard-index) | text/summary |
| `texture classify list-outdated` | list classifications whose pixel-hash no longer resolves to any current texture (shows the stored ref) | rows → stdout; `--json` |
| `texture classify prune [--outdated]` | remove outdated classification shards (explicit tracked-file cleanup; not `gc`) | removed count → stderr |
| `texture classify clone --from <catalog-dir\|project-root>` | copy classifications by pixel identity (keep-local, skip already-classified) | copied/skipped counts → stderr |
| `texture prewarm [--package P] [--force]` | eagerly decode (optional; for offline sessions); `--force` re-decodes even when the stat tuple is unchanged (the escape hatch that dropping `sync --force` otherwise removes) | progress → stderr |
| `texture gc` | evict orphaned/stale entries from the DERIVED per-user cache ONLY (never touches tracked files) | freed summary → stderr |
| `texture tags [--package P]` | tag vocabulary + counts (via the derived shard-index) | text |

- **`--similar <ref>`** decodes the ref (lazily), takes its perceptual hash, ranks every cataloged
  texture by ascending distance (see §7 for the metric), prints the top `--max` (default **20**).
  **Mutually exclusive with lexical `<terms>`/`--tag`/`--color`** (a perceptual-hash ranking and a
  lexical score are different operations — combining them is undefined; exit 2 with a clear message if
  both are given). `--package` MAY still scope the candidate set. The distance is surfaced: `--json`
  carries a `distance` field, and the text form appends it, so an agent can see the similarity cliff
  when tuning `--max`. *(A dedicated `texture similar <ref>` verb was considered per the CLI
  "small verbs" philosophy; Andrzej chose `search --similar` — kept, with the mutual-exclusion above
  closing the mode-interaction hole.)*
- **Error taxonomy needs a new enumerate-and-decode layer, not `utexture.resolve()`.** Today
  `utexture.TextureResolver.resolve()` collapses EVERY failure — unknown package, unknown name,
  non-P8 format, bad palette, corrupt — to an indistinguishable `None`. To deliver a real taxonomy the
  build adds a thin layer over `utexture`'s lower primitives (`textures()` enumeration +
  `decode_texture`) that distinguishes: **unknown ref** (no such export) → named non-zero error;
  **ambiguous 2-part ref** → list the 3-part candidates; **undecodable** (found but corrupt/unparseable) →
  distinct named error AND an `undecodable` index row (§4a), never "not found"; **cache-unreadable**
  (`EACCES`, e.g. the root-owned-cache bootstrap wall) → distinct message, separate from ENOENT. No
  traceback ever reaches the user (CLI rule). `classify set` (or `list-outdated`/`prune` targeting) on
  an **undecodable** ref (no `pixel_hash` to key the shard) is a clean named non-zero error — there is
  no hash to classify. *(The old "known-ref-but-PNG-missing → run sync" error
  disappears — decode is on-demand.)*
- **Broad queries pay a cold-decode cost — report it.** `--similar` (inherently whole-catalog), and any
  un-`--package`'d `list`/`search`/`tags`/`status`, must lazily decode every not-yet-cached package on
  first use. Native pure-Python decode is ~2 Mpx/s (Pillow-only, no numpy), so a cold catalog-wide op is
  tens of seconds. This is NOT free — the spec does not claim the full pass was eliminated, only made
  incremental + stat-cached. Mitigations (build): emit a `decoding N packages…` progress line to
  **stderr** for any catalog-wide op (so stdout stays pipe-clean), cache the phash in the per-package
  index so `--similar` never re-decodes a cached package, and have the first catalog-wide op effectively
  run `prewarm` with that progress. `prewarm` stays the way to pay the cost up-front, deliberately.
- **Empty stdin via `-`** (for `show -` / any stdin consumer) is a clean no-op, exit 0 (CLI convention).

## 6. The intended LLM loop (document in `usage.md`)

```bash
texture search --unclassified --package CoreTexMetal --json   # refs + png_paths + auto-colors, JSONL
#   harness Reads each png_path as its own image (batched, distinct files — no montage)
texture classify set CoreTexMetal.Area51Wall_A \
    --tags metal,wall --description "riveted metal wall panel"
#   colors stay auto → no --colors unless the auto derivation is wrong

# "find me more like this one":
texture search --similar CoreTexMetal.Area51Wall_A --max 12 --json
```

## 7. Two hashes — definitions

- **Pixel-hash (identity):** `sha256` over `(width, height, raw RGB bytes)` of the decoded image, so
  different-size textures never collide. Content-address key for `images/`, dedup key, and the
  classification key. Crisp: a 1-pixel difference is a different texture. **MUST match the legacy
  construction** so migration attaches: the digest is `sha256(b"%d:%d:" % (width, height) +
  rgb.tobytes())` — byte-identical to the current `texture_catalog.image_hash` (minus its `sha256:`
  prefix). The native decode path MUST reproduce the exact same RGB bytes (masked/index-0 pixels
  included) or every migrated classification silently orphans.
- **Perceptual hash (similarity):** a lightweight Pillow-only hash (e.g. dHash: grayscale → resize to
  `9×8` → 64-bit "each pixel brighter than its left neighbor"), stored in the per-package index.
  **But dHash ALONE is insufficient for this corpus** (review R1#7): it is a grayscale
  luminance-gradient signature, so it is **blind to color** (grey brick vs red brick read identical) and
  **collapses flat/tiling/low-contrast wall & floor textures** — exactly the DX corpus — into
  near-identical hashes → false-positive floods. **Similarity metric = a WEIGHTED COMBINATION of the
  perceptual-hash Hamming distance ⊕ the 12-name color-palette signature distance**
  (the palette is derived for free at decode). The color operand is the **full 12-bin normalized color
  histogram** (not the ≤3 kept names) stored in the per-package index row; distance = L1 (or cosine)
  over the 12-vector. The ≤3-name `colors` stay for display/`--color` filtering; the 12-bin vector is
  what `--similar` scores. Only the ⊕ weight is a free tuning knob. This restores color discrimination
  and separates
  flat-but-differently-colored textures. The exact weighting is a build-time tuning knob to validate
  against a corpus-representative sample before committing — flagged, not "build picks blindly". Frame
  the capability honestly as **near-duplicate + rough look-alike**, not semantic "find me a rusty
  industrial wall".

**Scope — P8 today; non-P8 decoders are a build prerequisite.** P8 today; the non-P8 decoders
(RGBA8/DXT1/RGB16/imported-palette) are a BUILD PREREQUISITE (§10-F), so at ship the accepted-format
set matches UCC and `undecodable` covers only genuinely corrupt/unparseable textures — not a supported
format. `utexture.py` decodes **P8 palettized textures only** today (`fmt==0`, local palette); it
returns nothing for RGBA8/DXT1/imported-palette/other formats until the prerequisite lands. The DX
corpus is ~100 % P8, so this redesign is complete FOR DEUS EX. But `direction.md` aims uedcli at
**generic UE1** (incl. `.unr` UT/Unreal, which ship non-P8 textures), and UCC `batchexport` (being
dropped) exported *every* format. So on a non-P8 substrate this is a **coverage regression**: such
textures would otherwise become `undecodable` index rows (§4a) on a non-P8 substrate. **RESOLVED
(Andrzej, 2026-07-19, §10-F / decisions.md addendum): the non-P8 decoders (RGBA8/DXT1/RGB16/
imported-palette) are a BUILD PREREQUISITE** — native decode must fully match UCC's coverage before the
redesign lands, so generic-UE1 stays honest and no coverage gap ever ships. *Rejected: ship DX-only now
with non-P8 as a follow-up; rejected: keep UCC-under-Wine as a non-P8 fallback.* The `undecodable`-row
behavior stays as the graceful floor for a genuinely corrupt/unparseable texture, NOT as an
accepted-format gap. Tracked as the prerequisite board item `[spike/implement] Native non-P8 texture
decoders` (inbox).

## 8. What carries over unchanged from today

- The **12-name color palette** + auto-derivation (`derive_colors`; quantize 64×64, keep names ≥12 %
  share, cap 3) — moves into the derived per-package index, still auto, still overridable.
- `search`/`list` default output = **bare `Package.Name` refs one-per-line** so the pipe into
  `brush poly set --texture -` is unbroken; human summaries/counts → stderr; `--json` for structure.
- The composed-search-path package discovery (`config.composed_search_files`, project overlay shadows
  game base, all extensions incl `.u`).
- Catalog writes atomic (temp + `os.replace`); per-**shard-file** writes need no cross-file lock (that
  is the whole point of sharding) — but the derived per-package index still writes under a per-package
  `flock` (concurrent decoders of the same package).

## 9. Non-goals (explicitly out)

- **Montage / contact-sheet batch viewing** (rejected — misattribution).
- **Per-user shared auto-applied classification** (rejected — not committed with the repo). Cross-project
  sharing is the explicit `classify clone`.
- **Semantic/embedding similarity** (rejected — heavier deps).
- **Auto-tagging** beyond colors (the LLM's own read of the pixels does the semantic work).
- **The parallel object/sound asset catalog** (separate spec — the "★ Asset catalog" `to-spec` item);
  it should **mirror these same *storage* mechanics** (lazy stat-cache, content-addressed sharded
  classifications, similarity). **Caveat (review R2#7):** it CANNOT mirror the *decode* path — native
  `utexture.py` covers textures only; meshes (mesh thumbnails) and sounds have no native decoder, so the
  asset catalog will still need the editor/UCC/container render seam this spec drops for textures. Note
  that in its spec; don't assume "drop the container" generalizes.

## 10. Open sub-choices (recommendations; flag for Andrzej / the review gate)

| # | Question | Recommendation |
|---|---|---|
| A | Perceptual-hash base: dHash vs pHash (before the color-signature combine, §7)? | **dHash** base + the 12-name palette distance combined; validate the weighting on a corpus sample. |
| B | Migration: auto-convert-on-read vs a one-shot `texture migrate` verb? | **Auto-convert-on-read is safe** (reuses the stored `image_hash`, no decode) provided it converts the whole catalog in one pass before any manifest removal (§4c). A one-shot verb is fine too; either way old-manifest removal is a **separate explicit step**, never in `gc`. |
| C | `gc` scope | **Derived per-user cache ONLY** — never touches tracked `texture-catalog/` files (the review caught §10-B's earlier "gc removes old manifests" as a footgun that would `rm` committed data). Pruning tracked classifications, if ever wanted, is a separate `--prune-classified` on a different verb. |
| D | Should `show` decode on demand if the package is present but not yet cached? | **Yes** — the whole point of the lazy model (removes the old "run sync first" error). |
| E | `--similar` default `--max`? | **20**, `--json`-friendly, `distance` surfaced. |
| **F** | **Scope: accept P8-only (Deus Ex) now, or require non-P8 decoders before build? (§7)** | **RESOLVED (Andrzej, 2026-07-19): require non-P8 decoders as a BUILD PREREQUISITE** (decisions.md addendum). Native decode must match UCC coverage before the redesign lands; non-P8 decoder port tracked as the prerequisite inbox item. `undecodable` rows remain only for genuinely corrupt textures. |

## 11. Test coverage (build must add)

- ref → pixel-hash → `images/<hh>/<hash>.png` resolution, **including a cross-package dup** (two refs,
  same hash, one cache file, one classification), and the **bare-hex key** (no `sha256:` prefix in
  filename/shard).
- lazy stat invalidation keyed on **realpath+size+st_mtime_ns**: unchanged → no re-decode; changed
  size/mtime → re-decode; **overlay-shadow collision** (two projects, same-stem package, different
  realpath) → two distinct index entries, no thrash/cross-serve (the schema-cache parity check).
- content-address dedup: two identical textures in different packages → one `images/` file.
- **undecodable texture** (simulate a corrupt/unparseable texture — a non-P8 texture will decode once
  the prerequisite lands): appears as an `undecodable` index row (enumerable in
  `list`/`search`), `show` gives the distinct "undecodable" error (≠ "not found"), never vanishes.
- **outdated-entry flow**: a ref classified under `H_old`, package re-decoded to `H_new` → the ref now
  shows **unclassified** (new hash, no classification); the `H_old` shard becomes an outdated entry that
  `classify list-outdated` surfaces **by its stored `ref`**, and `classify prune` removes; nothing is
  silently lost (the shard persists until pruned; `classify set` on an undecodable ref is a named error).
- similarity ranking: a known near-pair ranks above an unrelated texture; **color discrimination** (two
  flat textures, same luminance, different color → NOT ranked as near-identical, per the combined metric);
  `distance` surfaced in text + `--json`; `--similar` + `<terms>`/`--tag` → exit 2.
- classification round-trip through the sharded pixel-hash store; **shard is write-once per image**
  (no `refs` field); concurrent-agent disjoint writes (two hashes → two files) don't conflict; the
  derived `shard-index.json` roll-up matches a full shard scan and is stat-gated.
- `classify unset` (whole + per-field) removes/edits the shard.
- `classify clone`: keep-local (existing local classification untouched), skip-report, fills only
  unclassified; a cloned hash present in NO local package is not surfaced by `list --classified`.
- **migration (offline, no decode)**: an old name-keyed classified entry → the sharded hash-keyed file
  built **from the stored `image_hash`** (prefix stripped), metadata preserved; an old `removed`/`stale`
  entry whose texture no longer decodes **still migrates** (its stored hash survives); ALL entries
  convert before any manifest is removed; `gc` does NOT remove tracked manifests.
- **migration hash equivalence**: a FRESH native-decode of a texture produces a `pixel_hash`
  byte-identical to that texture's legacy stored `image_hash` (prefix stripped) — the executable guard
  that migrated classifications actually re-attach.
- error taxonomy: unknown ref, ambiguous 2-part ref, undecodable, cache-unreadable (`EACCES` ≠ ENOENT) —
  each named, non-zero, no traceback.
- `list`/`search --json` shape; `--unclassified` filter; bare-ref default output keeps the
  `brush poly set --texture -` pipe unbroken; empty stdin `show -` → exit 0.

## 12. Review resolutions (2026-07-19 cold gate, two reviewers)

Two cold reviewers (design/correctness + feasibility/ergonomics). Every finding resolved:

**A SECOND review gate ran 2026-07-19** on the revised spec; its findings (change-detection redesign,
non-P8 wording, migration hash-pin, + nits) are folded into §4a/§4b/§4c/§5/§7/§11.

| # | Finding | Resolution |
|---|---|---|
| R1-1 / HIGH | "`stale` eliminated" silently orphans classification + loses change-detection on pixel change | **REDESIGNED (Andrzej 2026-07-19)** — no derived `changed` status; a changed texture shows unclassified, the old classification becomes an "outdated entry" (shard whose hash no longer resolves), managed by `classify list-outdated`/`prune`; the shard stores a write-once `ref` for identification. §4b. |
| R2-2 / HIGH | Migration should reuse the stored `image_hash` (byte-identical), not re-decode (fragile/lossy) | **FIXED** — §4c migrates offline from the stored hash; `removed`/`stale` entries survive. |
| R1-3 / R2-1 / HIGH | Native decode is P8-only ≠ UCC coverage; non-P8 textures vanish; vs generic-UE1 direction | **FIXED + FLAGGED** — `undecodable` index rows keep them enumerable (§4a); P8 scope stated (§7); scope decision F raised to Andrzej. |
| R1-4 / MED-HIGH | Per-package index keyed by stem in cross-project cache → overlay-shadow collision/thrash; not really "like the schema cache" | **FIXED** — index keyed on realpath+size+st_mtime_ns like the schema cache (§4a). |
| R1-5 / MED | Sharded store → O(N) cold file-opens for `tags`/`search --tag`/`status` | **FIXED** — derived, stat-gated `shard-index.json` roll-up (§4a). |
| R1-6 / R2-3 / MED | `--similar` + broad queries reintroduce the full-corpus decode, un-instrumented; "lazy is cheap" overstated | **FIXED** — §5 acknowledges the cost, adds stderr progress + phash caching + auto-prewarm on first catalog-wide op. |
| R1-7 / MED | dHash alone is color-blind + weak on flat/tiling textures | **FIXED** — §7 metric = perceptual-hash ⊕ color-palette distance; framed as near-dup/look-alike, not semantic. |
| R1-8 / MED | `--similar` overloads `search`; mode interaction undefined | **FIXED** — mutually exclusive with lexical terms/filters, exit 2 otherwise (§5); dedicated-verb alt noted (Andrzej chose the flag). |
| R2-4 / MED | `gc` scope self-contradictory; §10-B would delete git-tracked manifests | **FIXED** — `gc` = derived-cache-only (§5, §10-C); legacy removal is an explicit migration step. |
| R2-5 / MED | `sha256:` prefix vs filename; `refs` field reintroduces a per-hash write conflict; two roots share the catalog glob | **FIXED** — bare-hex key (§4a); `refs` removed from the shard → write-once (§4b); glob disambiguation (§4b). |
| R2-6 / MED | Error taxonomy contradicts `utexture.resolve()` (all failures → `None`) | **FIXED** — §5 requires a new enumerate-and-decode layer over `textures()`/`decode_texture`, not `resolve()`. |
| R2-7 / LOW | Dropping `sync` strands a coupled surface; asset-catalog can't mirror decode | **FIXED** — coupled surface inventoried (§13); usage.md has an existing `## Texture catalog` section (usage.md:497) documenting the OLD sync loop — it must be REWRITTEN to the new lazy/`show`/`similar`/outdated loop (not added net-new) (§13); §9 asset-catalog decode caveat. |
| R2-8 / R1-9 / R1-10 / LOW | Missing `classify unset`; `--similar` distance; `--no-decode`; cloned-orphan reads; empty-stdin exit; no force-redecode | **FIXED** — `classify unset` + `prewarm --force` (§5); distance surfaced; empty-stdin exit-0; cloned-orphan read rule (§5/§11). |

## 13. Coupled surface the `sync` removal touches (build inventory — review R2-7)

Dropping `sync` is a rewrite of `texture_catalog.py`, not a one-verb delete. The build must reconcile:
`dispatch.py` (the ~55-line `sync` branch + ephemeral-container start path; the `classify set` "no
catalog → run sync" error), `cli.py` (the `tsync` parser), `texture.py` (`batchexport_textures` →
dead code, delete), tests (`test_texture_integration.py`, the sync tests in `test_dispatch.py`,
`test_cli.py`), any "run texture sync" error strings, `container_assets.py`'s comment, and the
`architecture.md` "Texture catalog" section (full rewrite). **usage.md has an existing `## Texture
catalog` section (usage.md:497) documenting the OLD sync loop — it must be REWRITTEN to the new
lazy/`show`/`similar`/outdated loop (not added net-new).** The old UCC/Wine/Docker texture path (`texture.py` batchexport + its container mount) is
retired for textures (but the container seam survives for the editor/preview and the future
mesh/sound asset catalog — §9).
