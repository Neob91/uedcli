# Asset catalog — uedcli lists and shows, the LLM supplies meaning

## What we want

Level design by an LLM agent needs to **discover** what can be placed, not just place it. The asset
catalog is how it finds out what exists on the composed package search path, sees it, and records
what it turns out to be.

### The tool does not infer

uedcli does exactly four things with an asset:

1. **lists** what exists on the composed search path;
2. **reports facts literally stored in the package** — image dimensions, mesh bounding box,
   collision radius/height, pivot, parent class, `DrawType`;
3. **produces the picture** — decodes a texture, renders a mesh;
4. **stores and queries the classification it is handed.**

It never infers meaning. Not what an asset is *for*, not *where it is used*, not whether it is
"commonly placed", not how relevant one asset is to another. The LLM looks, investigates, decides,
and hands the answer back; the tool records it.

The reason is reviewability. **A number the tool computed is unreviewable and uncorrectable** — a
reader cannot tell a good derivation from a bad one, and cannot fix it where it is wrong. An LLM's
finding, written into a description, is durable, reviewable and fixable by editing one line.

Two consequences worth stating outright:

- **`placeable` keeps ONE definition — a file fact**: the class is non-abstract and descends from
  `Actor`. Its help text says exactly that, rather than implying judgement. This is also what keeps
  `class list` offline, map-free and fast.
- **Classes get no curated role/category taxonomy.** The superclass already says what a class is for
  (`ScriptedPawn`, `Decoration`, `Weapon`, `Mover`), and `--subclass-of` already queries it.
  Curation collapses to **tags plus a description**; the decoded file facts stand as read — there is
  no general override of a class's file fact. *(The texture-colours pre-fill below is the one
  exception, and it is texture-only.)*

**The single deliberate exception is texture colours.** The tool pre-fills a small fixed palette of
base colour names per texture, **ordered by importance** (descending share of the image). It earns
the exception because it reads *nothing but that texture's own pixels* — reading the file, not
scanning the corpus — and because it makes `texture search --color brown` useful on a fresh clone
*before* anything has been classified. An LLM classification overrides it, and the override wins.

### One engine, four kinds

One catalog engine serves four kinds — **texture, class, sound, music** — each with **its own CLI
noun** carrying the same verb family: `list`, `search`, `show`, `preview`, `classify`, `tags`,
`prewarm`. **"Unified" means one implementation, never a `--kind` selector on a generic `catalog`
noun.** A kind ships a reduced family where the underlying artifact does not exist — `music` has no
preview, so it has no `preview`/`prewarm`/`--similar`.

The discovery verb is `search`, not `find`, per [`conventions.md`](conventions.md) "`find` vs
`search`": the catalog is a corpus queried by relevance, not a known set enumerated out of the trunk.

### `show` reports facts; `preview` produces the picture

- **`show`** returns the file facts plus whatever classification is stored. It renders nothing.
- **`preview`** returns image artifacts, and is the **only producer**. `list` and `search --json`
  report already-cached artifacts only, so no exploratory command can ever trigger a long render.

**One asset, one image file.** There is no contact sheet, no montage, no numbered grid — because
misattribution (classifying asset 7 with what was seen in cell 8) is the failure mode that silently
corrupts a catalog and is invisible afterwards.

**Class thumbnails render natively.** The full UE1 mesh body decodes offline
([`packages.md`](packages.md)), so a thumbnail needs no editor, no container and no `umodel.exe`; a
native render also controls its own lighting by construction. A class thumbnail takes its skins from
the **class defaults**, not the mesh's own texture array. `iso` (front-¾) is the default **single**
shot; `--angles` opts into `front, back, left, right, top, bottom, iso`. "Side" is deliberately
spelled `left`/`right`, because a mesh is not symmetric in general.

### The audio arm classifies from the name and the LLM's own investigation

An LLM cannot listen. So a sound's classification rests on **its ref name and what the LLM finds out
about it**, with a **spectrogram as a secondary *category* cue** — tonal / broadband / impulsive /
speech-like, duration, loopability. A spectrogram supports category, never *identity*: "laughing"
versus "coughing" is not readable off one. **`sound export <ref> --out X.wav` is an opt-in path for
human audition**, never the primary one — routing thousands of assets through a human makes the
human the bottleneck.

### Identity: content hash where content exists, name where it does not

- **texture** → the exact pixel hash (`sha256` over width, height and raw RGB); a **procedural**
  texture with no stored pixels (`FireTexture`/`WetTexture`/`WaveTexture`/`ScriptedTexture`) → its
  name, per the rule above (name where content does not exist);
- **class** → `Package.Class`; **sound** and **music** → `Package.Name`.

The pixel hash earns its keep for textures: identical pixels dedupe **across packages**, and
`classify clone` can copy a classification by identity. Names key the rest because a class
fingerprint over default properties is brittle — any game patch would orphan the curated description
— and because music *cannot* be content-keyed at all: `TLazyArray` headers embed **absolute file
offsets**, so a repacked-but-byte-identical package hashes differently.

**There are no `stale`/`removed`/`changed` flags to maintain.** Change is a derived query, not stored
state: repaint a texture and its new pixels are a new identity that simply reads **unclassified**,
while the old classification becomes an **outdated entry** — a shard whose identity resolves to
nothing on the current search path. `classify list-outdated` surfaces it (by the **write-once `ref`**
the shard stores for exactly this purpose) and `classify prune` removes it.

### Two layers: content identity, and per-ref facts

A texture splits into two layers. **Layer 1 — content:** the identity above (the pixel hash, or the
name for a procedural texture) keys the classification; identical pixels are deliberately one
classifiable thing, and the preview is that bitmap. **Layer 2 — per-`Package.Name` facts:** attributes
that belong to a particular ref — read live from the package and cached in the derived index, shown by
`show` and filterable, but never part of identity and never written into the classification.

**A texture's GROUP is a stored fact, not just a ref component.** UE1 subdivides a package with an
optional Group, so a texture is addressed `Package.Name` or fully `Package.Group.Name`. Ref assignment
emits the 2-part form unless there is an intra-package name collision, which means the group vanishes
from the output for most textures — including `CoreTexMetal.LadrBrwnMetal`, whose group is the reserved
`Ladder`. In Deus Ex the group is what decides whether a surface is climbable, so the catalog must be
able to answer "which textures are ladders" directly: the group is stored as a per-texture fact,
printed by `show`, and filterable with `--group` on `list`/`search`. It is a fact read from the
package, never a classification, so it is not LLM-overridable — and it is **not** part identity, since
identical pixels in two groups are deliberately one classifiable thing.

**`masked` is a texture fact, read from the package.** `Masked` is a property of the *texture object*,
set by the `Masked` checkbox when the texture is imported into UnrealEd; UE1 then ORs a texture's own
flags into every surface it is applied to. So a masked texture punches its palette-index-0 pixels into
see-through holes on any surface, with no surface polyflag set — which makes it invisible to any audit
of surface flags, and a hole into unbuilt space wherever it lands on a solid face. The catalog
therefore stores `masked` as a per-texture fact **read from the export's stored flag, never inferred**
from the palette or from derived colours: inference is forbidden by the governing principle, and a
texture may carry an index-0 colour without being imported masked. Filterable with `--masked`; not
part of identity.

### Classification is the product, not a side feature

The classification store is **git-tracked and sharded one file per asset**, so concurrent agents
editing disjoint assets never touch the same file and never merge-conflict — the same ethos as the
per-actor `.t3d`.

- **Batch-capable**: `classify set -` reads JSONL from stdin, one shard write per row, mirroring
  `actor add -`. A cold invocation costs real time, so per-ref processes would make classifying
  thousands of assets process-bound rather than compute-bound.
- **A byproduct of looking, never a bulk campaign**: `preview --skeleton` emits a ready-to-fill row
  for exactly the refs just previewed.
- **`tags`** lists the vocabulary in use, to curb drift.
- **`classify clone --from <catalog|project>`** fills only identities unclassified locally, never
  overwrites local work, and reports what it skipped.

That an existing catalog sits at zero classified entries is **not** evidence that nobody will
classify. Nothing has been classified because nothing ever made it possible — there has been no way
to *see* an asset.

### Produce the picture, or a named error — never a wrong pixel

Decoding is universal wherever the file itself says enough to be decoded, and a **named error**
wherever it does not. A guess that returns a plausible-but-wrong image is worse than a refusal,
because nothing downstream ever re-checks it.

**The stated limit:** a block-compressed texture whose alpha encoding the data cannot distinguish
(BC2 versus BC3 — identical block sizes, identical mip chains) **does not decode**. It is a named
error with no pixels. This limit is stated wherever the "reads any texture from any engine" claim is
made — in the docs, in the error text and in the code comment — never buried as a corner case. The
layout-arbitration *mechanism* is [`packages.md`](packages.md)'s.

**A decode failure is a typed result, and the caller chooses the disposition** — a calibrated
exception to [`conventions.md`](conventions.md) "no silent half-answers", because an undecodable
asset must stay *enumerable*: a **per-ref request** exits 2 naming it; **enumeration** records an
`undecodable` row and keeps listing; a **whole-level preview** degrades that one surface and warns.

### Mechanics that hold across all four kinds

- A **lazily-built per-`(kind, package)` derived index**, gated on a `(realpath, size, st_mtime_ns)`
  stat tuple. There is no mandatory bulk `sync` step; `prewarm` is the optional eager pass.
- A **content-addressed per-user preview cache** — regenerable, never committed, shared across
  projects.
- **Cache eviction lives on the existing `cache` noun** (`cache gc`). There is no per-catalog
  eviction verb.
- **Textures carry two hashes**: the exact pixel hash for identity, and a **separate perceptual
  hash** for similarity. `texture search --similar <ref>` ranks by perceptual distance combined with
  colour distance. It finds a rough look-alike; it is not semantic search.
- **The legacy name-keyed texture catalog is deleted, not migrated.** It holds no authored data, so
  per [`conventions.md`](conventions.md) it goes outright; colours re-derive from pixels on demand.

## Rejected

**The shape of the surface**

- **A single `catalog` noun with `--kind`** — it deletes the `texture` verbs and rewrites every doc
  and pipe that names them, to buy a cross-kind query that is rarely what is wanted.
- **Shipping both surfaces** — two spellings of one operation is exactly the permanent maintenance
  surface the no-back-compat rule exists to prevent.
- **Building the earlier texture-only catalog redesign first and generalizing it afterwards** — it
  was specced and gated but never built, so nothing is owed to it.
- **One `show` verb with a `--preview` flag** — overloads one verb with two output shapes.
- **Rendering artifacts inline for the "cheap" kinds** — a per-kind asymmetry the caller must
  memorize, and a cold catalog-wide listing would render hundreds of meshes on a first exploratory
  command.
- **A `catalog gc` verb** — a second maintenance surface over one cache root.
- **A mandatory eager `sync` pass**, and **keeping `sync` as a vestigial opt-in prewarm**.
- **Decoding through `UCC` under Wine** — keeps the container/Wine seam that native decode removes.

**What the tool computes**

- **A tool-computed stock-map usage index**, **a class placement histogram**, **a derived "commonly
  placed" signal**, and **a curated-vs-derived override model for `placeable`** — rejected
  *explicitly*, not deferred. They also carried an entire build prerequisite that dies with them.
- **Curating a role/category taxonomy** over the class list — redundant with the class hierarchy, a
  standing maintenance burden, and it would give `--category` a second meaning.
- **Less classification machinery, on the evidence that the existing catalog has zero classified
  entries** — backwards: nothing was classified because seeing an asset was impossible.
- **Human/LLM-set colours only, with no auto-derivation** — the free first pass is what makes colour
  search work on an unclassified catalog.
- **Colours as a pure objective field, re-derived on every pass** — it would clobber human
  overrides.
- **Deciding an undistinguishable alpha encoding by "plausibility"** — a heuristic dressed as a
  measurement, and it contradicts "the tool does not infer".

**Identity and storage**

- **Name-keying everything** — loses cross-package dedup and classification-by-identity for textures.
- **Content-hashing everything** — a class fingerprint over default properties is brittle, and music
  cannot be content-keyed at all.
- **A single hash-keyed `classifications.json`** — merge-hostile; **a per-package name-keyed
  manifest**; **a per-user shared store applied automatically** — classification is expensive work
  that must be committed with the repo it describes.
- **Stored `stale`/`removed` flags**, **a derived `changed` status**, and **a durable
  ref→last-hash ledger** to support one — the ledger would reintroduce the per-identity write
  conflict sharding exists to remove.
- **A mutable `refs` list on the shard** — same conflict; the shard's `ref` is write-once.
- **A defensive migration converting only the non-empty legacy entries** — of which there are zero.
- **One perceptual hash serving both identity and similarity** — a re-encode must not merge two
  distinct textures.
- **`clone` with incoming-wins, or erroring on conflict** — it keeps local work and reports skips.

**Producing the picture**

- **The container render harness as the thumbnail path** — it survives for real-lighting hero shots,
  but a thumbnail needs no game running.
- **Rendering several angles always** — a render is not free, so a multi-angle default would put
  minutes into prewarming the mesh classes.
- **An opt-in indexed contact sheet** — it still depends on the model reading cell numbers
  correctly, and misattribution corrupts the catalog silently.
- **Semantic / embedding similarity search** — heavier dependencies, against the offline,
  Pillow-only ethos.
- **Mesh export (`.3d`/glTF)** — the decoder exists, but exporting is not a catalog need.

**Audio**

- **Metadata plus the name only** — too thin; it leaves the LLM guessing from a bare ref name.
- **Clip export as the PRIMARY classification path** — human-grade quality, but it makes the human
  the bottleneck. It survives as the opt-in `sound export`.

## Refs

[`conventions.md`](conventions.md) · [`packages.md`](packages.md) ·
`../architecture.md` "Texture catalog" (the superseded name-keyed implementation) ·
`../spikes/2026-07-25-native-mesh-decode/`
