# Asset catalog — uedcli lists and shows, the LLM supplies meaning

## What we want

Level design by an LLM agent needs to **discover** what can be placed, not just place it. The asset
catalog is how it finds out what exists on the composed package search path, sees it, and records what
it turns out to be.

### uedcli reports facts; the LLM supplies meaning

uedcli does four things with an asset:

1. **lists** what exists on the composed search path;
2. **reports facts literally stored in the package** — image dimensions, mesh bounding box, collision
   radius/height, pivot, parent class, `DrawType`;
3. **produces the picture** — decodes a texture, renders a mesh;
4. **stores and queries the classification it is handed.**

It does not infer meaning — not what an asset is for, where it is used, whether it is "commonly
placed", or how relevant one asset is to another. The LLM looks, decides, and hands the answer back;
the tool records it. An LLM's finding, written into a description, is editable by hand; a derived
semantic signal is not.

- **`placeable` keeps one definition — a file fact**: the class is non-abstract and descends from
  `Actor`. This is also what keeps `class list` offline, map-free and fast.
- **Classes get no curated role/category taxonomy.** The superclass already says what a class is for
  (`ScriptedPawn`, `Decoration`, `Weapon`, `Mover`), and `--subclass-of` queries it. Curation is tags
  plus a description; the decoded file facts stand as read.

**The single exception is texture colours.** The tool pre-fills a small fixed palette of base colour
names per texture, ordered by descending share of the image. It reads nothing but that texture's own
pixels, and makes `texture search --color brown` useful on a fresh clone before anything is classified.
An LLM classification overrides it.

### One engine, four kinds

One catalog engine serves four kinds — **texture, class, sound, music** — each with its own CLI noun
carrying the same verb family: `list`, `search`, `show`, `preview`, `classify`, `tags`, `prewarm`.
"Unified" means one implementation, never a `--kind` selector on a generic `catalog` noun. A kind ships
a reduced family where the underlying artifact does not exist — `music` has no preview, so no
`preview`/`prewarm`/`--similar`.

The discovery verb is `search`, not `find` ([`conventions.md`](conventions.md) "`find` vs `search`"):
the catalog is a corpus queried by relevance, not a known set enumerated out of the trunk.

### `show` reports facts; `preview` produces the picture

- **`show`** returns the file facts plus whatever classification is stored. It renders nothing.
- **`preview`** returns image artifacts, and is the only producer. `list` and `search --json` report
  already-cached artifacts only, so no exploratory command triggers a long render.

**One asset, one image file.** No contact sheet, no montage, no numbered grid — misattribution
(classifying asset 7 with what was seen in cell 8) silently corrupts a catalog and is invisible
afterwards.

**Class thumbnails render natively.** The full UE1 mesh body decodes offline
([`packages.md`](packages.md)), so a thumbnail needs no editor, container or `umodel.exe`, and a native
render controls its own lighting. A class thumbnail takes its skins from the class defaults, not the
mesh's own texture array. `iso` (front-¾) is the default single shot; `--angles` opts into `front,
back, left, right, top, bottom, iso`. "Side" is spelled `left`/`right` because a mesh is not symmetric
in general.

### The audio arm classifies from the name and the LLM's own investigation

An LLM cannot listen, so a sound's classification rests on its ref name and what the LLM finds out
about it, with a **spectrogram as a secondary *category* cue** — tonal / broadband / impulsive /
speech-like, duration, loopability. A spectrogram supports category, never identity: "laughing" versus
"coughing" is not readable off one. **`sound export <ref> --out X.wav` is an opt-in path for human
audition**, never the primary one — routing thousands of assets through a human makes the human the
bottleneck.

### Identity: content hash where content exists, name where it does not

- **texture** → the exact pixel hash (`sha256` over width, height and raw RGB); a **procedural**
  texture with no stored pixels (`FireTexture`/`WetTexture`/`WaveTexture`/`ScriptedTexture`) → its
  name;
- **class** → `Package.Class`; **sound** and **music** → `Package.Name`.

The pixel hash earns its keep for textures: identical pixels dedupe across packages, and `classify
clone` can copy a classification by identity. Names key the rest because a class fingerprint over
default properties is brittle — any game patch would orphan the description — and because music cannot
be content-keyed: `TLazyArray` headers embed absolute file offsets, so a repacked-but-byte-identical
package hashes differently.

**There are no `stale`/`removed`/`changed` flags to maintain.** Change is a derived query, not stored
state: repaint a texture and its new pixels are a new identity that reads unclassified, while the old
classification becomes an outdated entry — a shard whose identity resolves to nothing on the current
search path. `classify list-outdated` surfaces it (by the write-once `ref` the shard stores) and
`classify prune` removes it.

### Two layers: content identity, and per-ref facts

A texture splits into two layers. **Layer 1 — content:** the identity above (pixel hash, or name for a
procedural texture) keys the classification; identical pixels are one classifiable thing, and the
preview is that bitmap. **Layer 2 — per-`Package.Name` facts:** attributes belonging to a particular
ref — read live from the package and cached in the derived index, shown by `show` and filterable, but
never part of identity and never written into the classification.

**A texture's GROUP is a stored fact.** UE1 subdivides a package with an optional Group, so a texture
is addressed `Package.Name` or fully `Package.Group.Name`. Ref assignment emits the 2-part form unless
there is an intra-package name collision, so the group vanishes from output for most textures —
including `CoreTexMetal.LadrBrwnMetal`, whose group is the reserved `Ladder`. In Deus Ex the group
decides whether a surface is climbable, so the catalog must answer "which textures are ladders"
directly: the group is stored as a per-texture fact, printed by `show`, filterable with `--group`. It
is a fact read from the package, not LLM-overridable, and not part of identity.

**`masked` is a texture fact, read from the package.** `Masked` is a property of the texture object,
set by the `Masked` checkbox on import; UE1 then ORs a texture's own flags into every surface it is
applied to, so a masked texture punches its palette-index-0 pixels into see-through holes with no
surface polyflag set — invisible to a surface-flag audit, and a hole into unbuilt space on a solid
face. The catalog stores `masked` as a per-texture fact read from the export's stored flag, never
inferred from the palette. Filterable with `--masked`; not part of identity.

### The classification store

The classification store is **git-tracked and sharded one file per asset**, so concurrent agents
editing disjoint assets never touch the same file — the same shape as the per-actor `.t3d`.

- **Batch-capable**: `classify set -` reads JSONL from stdin, one shard write per row, mirroring
  `actor add -`, so classifying thousands of assets is compute-bound not process-bound.
- **A byproduct of looking**: `preview --skeleton` emits a ready-to-fill row for exactly the refs just
  previewed.
- **`tags`** lists the vocabulary in use, to curb drift.
- **`classify clone --from <catalog|project>`** fills only identities unclassified locally, never
  overwrites local work, and reports what it skipped.

An existing catalog sitting at zero classified entries reflects that nothing ever made it possible to
*see* an asset — not that nobody will classify.

### Produce the picture, or a named error

Decoding is universal wherever the file itself says enough to be decoded, and a named error wherever it
does not. A guess that returns a plausible-but-wrong image is worse than a refusal, because nothing
downstream re-checks it.

**The stated limit:** a block-compressed texture whose alpha encoding the data cannot distinguish (BC2
versus BC3 — identical block sizes and mip chains) does not decode. It is a named error with no pixels,
stated wherever the "reads any texture from any engine" claim is made. The layout-arbitration mechanism
is [`packages.md`](packages.md)'s.

**A decode failure is a typed result, and the caller chooses the disposition** — a calibrated exception
to [`conventions.md`](conventions.md) "no silent half-answers", because an undecodable asset must stay
enumerable: a per-ref request exits 2 naming it; enumeration records an `undecodable` row and keeps
listing; a whole-level photo degrades that one surface and warns.

### Mechanics that hold across all four kinds

- A **lazily-built per-`(kind, package)` derived index**, gated on a `(realpath, size, st_mtime_ns)`
  stat tuple. No mandatory bulk `sync`; `prewarm` is the optional eager pass.
- A **content-addressed per-user preview cache** — regenerable, never committed, shared across
  projects.
- **Cache eviction lives on the existing `cache` noun** (`cache gc`). No per-catalog eviction verb.
- **Textures carry two hashes**: the exact pixel hash for identity, and a separate perceptual hash for
  similarity. `texture search --similar <ref>` ranks by perceptual + colour distance — a rough
  look-alike, not semantic search.
- **The legacy name-keyed texture catalog is deleted, not migrated** — it holds no authored data;
  colours re-derive from pixels on demand.

## Rejected

**The shape of the surface**
- **A single `catalog` noun with `--kind`** — deletes the `texture` verbs and rewrites every doc and
  pipe that names them, to buy a cross-kind query rarely wanted.
- **Shipping both surfaces** — two spellings of one operation.
- **Building the earlier texture-only redesign first and generalizing after** — specced and gated but
  never built.
- **One `show` verb with a `--preview` flag** — overloads one verb with two output shapes.
- **Rendering artifacts inline for the "cheap" kinds** — a per-kind asymmetry, and a cold listing would
  render hundreds of meshes.
- **A `catalog gc` verb** — a second maintenance surface over one cache root.
- **A mandatory eager `sync` pass**, and **keeping `sync` as a vestigial opt-in prewarm**.
- **Decoding through `UCC` under Wine** — keeps the container/Wine seam native decode removes.

**What the tool computes**
- **A tool-computed stock-map usage index**, **a class placement histogram**, **a derived "commonly
  placed" signal**, and **a curated-vs-derived override model for `placeable`** — rejected explicitly,
  with the build prerequisite they carried.
- **Curating a role/category taxonomy** over the class list — redundant with the class hierarchy, and
  it would give `--category` a second meaning.
- **Less classification machinery on the evidence of zero classified entries** — backwards: nothing was
  classified because seeing an asset was impossible.
- **Human/LLM-set colours only, no auto-derivation** — the free first pass is what makes colour search
  work on an unclassified catalog.
- **Colours as a pure objective field re-derived every pass** — would clobber human overrides.
- **Deciding an undistinguishable alpha encoding by "plausibility"** — a heuristic dressed as a
  measurement.

**Identity and storage**
- **Name-keying everything** — loses cross-package dedup and classification-by-identity for textures.
- **Content-hashing everything** — a class fingerprint over default properties is brittle, and music
  cannot be content-keyed.
- **A single hash-keyed `classifications.json`** — merge-hostile; **a per-package name-keyed
  manifest**; **a per-user shared store applied automatically** — classification is committed with the
  repo it describes.
- **Stored `stale`/`removed` flags**, **a derived `changed` status**, and **a durable ref→last-hash
  ledger** — the ledger reintroduces the per-identity write conflict sharding removes.
- **A mutable `refs` list on the shard** — same conflict; the shard's `ref` is write-once.
- **A defensive migration converting only the non-empty legacy entries** — of which there are zero.
- **One perceptual hash serving both identity and similarity** — a re-encode must not merge two
  distinct textures.
- **`clone` with incoming-wins, or erroring on conflict** — it keeps local work and reports skips.

**Producing the picture**
- **The container render harness as the thumbnail path** — it survives for real-lighting hero shots,
  but a thumbnail needs no game running.
- **Rendering several angles always** — a multi-angle default would put minutes into prewarming meshes.
- **An opt-in indexed contact sheet** — still depends on the model reading cell numbers correctly.
- **Semantic / embedding similarity search** — heavier dependencies, against the offline, Pillow-only
  ethos.
- **Mesh export (`.3d`/glTF)** — the decoder exists, but exporting is not a catalog need.

**Audio**
- **Metadata plus the name only** — leaves the LLM guessing from a bare ref name.
- **Clip export as the primary classification path** — makes the human the bottleneck; it survives as
  the opt-in `sound export`.

## Refs

[`conventions.md`](conventions.md) · [`packages.md`](packages.md) · `../architecture.md` "Texture
catalog" · `../spikes/2026-07-25-native-mesh-decode/`
