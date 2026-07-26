# Plan: the unified asset catalog

**Spec:** the split set — [`engine`](../specs/2026-07-26-asset-catalog-engine.md), [`class`](../specs/2026-07-26-asset-catalog-class-arm.md), [`texture`](../specs/2026-07-26-asset-catalog-texture-arm.md), [`audio`](../specs/2026-07-26-asset-catalog-audio-arm.md).
**Decisions:** [`direction/asset-catalog.md`](../direction/asset-catalog.md) (the owner's) and
[`rationale/`](../rationale/) (the agent's). **Not `decisions.md`** — that ledger is FROZEN;
[`rationale/MIGRATION.md`](../rationale/MIGRATION.md) maps the old dated citations.
**Review:** two rounds on this plan (4 cold reviewers, 2026-07-25) — all findings folded; §5 records them.
**Ephemeral:** scratch for sequencing this build; delete when the work lands.

> **SUPERSEDED BY THE SPLIT (2026-07-26). This plan sequences a spec that no longer exists as one
> document and must be re-cut PER ARM** — the class arm is buildable now, the texture arm has four
> open owner decisions, and the audio arms are blocked on a re-measurement spike. Everything below
> predates the split; treat it as raw material, not a sequence.
>
> **RE-CUT REQUIRED before building — the spec moved substantially on 2026-07-26.** This plan was
> reviewed against the pre-revision spec. The stale points fixed inline below are the anchors, the
> tracked-package count, the `decisions.md` supersession mechanism, the S11 direction edit (now done)
> and the S3 done-when. **What still needs re-sequencing, and is NOT yet in any slice:**
>
> - **§3c — procedural textures** are identified by a frozen per-class **parameter hash**; the declared
>   property set per class is new work in the texture arm, and `ScriptedTexture` is name-keyed with no
>   preview (`preview_state: scripted`).
> - **§4d — `masked`** is a texture fact, read as *export tag else resolved class default*. That makes it
>   **default-sourced**, so **prerequisite 1 (`schema_cache` v2) gates the TEXTURE arm too**, not only the
>   class arm — and P0 must land before S1, since §13 step 1's `DrawType` is default-sourced as well.
> - **§4c — `group`** comes from the export **Outer** (`pkg.name_of_ref(export["outer"])`), *not* from
>   `parse_pcx_stem`, which this plan deletes. An earlier version of this banner said to route it through
>   `parse_pcx_stem`; that was wrong.
> - **§6 — `class show` defaults**, including the `uprops.resolve_class_defaults` **provenance** change
>   (it currently discards which ancestor supplied a value), which is a shared-seam change, not an output
>   tweak.
> - **§5 — `search` now requires terms**, `--placeable` is dropped for `--include-abstract`, `--skeleton`
>   replaces the stdout stream and carries the artifact path, and truncation must be disclosed.
> - **§3b — `classify set` MERGES** (tags union, colours replace, conflicting description exits 2 with
>   `--replace` to override), `classify unset` gains `-` and named-tag removal, and `set` must report when
>   it writes an identity already classified under a different `ref`.
> - **`.unr` is DROPPED** from the package extension set (was S1 work); the **VO exclusion** becomes
>   per-substrate config plus `--include-vo`; the preview cache becomes its **own pool** with a recursive
>   sweep and index-orphan reclamation.
> - **Fixtures**: depend on the sibling formats spec's `pkgfixture` (synthetic `.utx`), plus the 34 tracked
>   `.u` packages. Do not build a writer here.
>
> Neither the spec revision nor this plan has been through a review round since
> (`board/inbox.md`).

Governing principle this plan must not drift from: **the tool lists, reports file facts, produces
pictures, and stores the classification it is handed. It never infers meaning.** The single
exception is texture colours (spec §4b).

---

## 0. Shape of the build

Thirteen slices, each a commit whose tests pass with **no NEW skips versus the pre-slice
baseline** (the baseline legitimately skips install-guarded tests when the gitignored Deus Ex
install is absent — demanding "zero skips" would be unmeetable and would invite deleting valid
tests). Order is value-first (spec §13): enumeration and ref-validation before previews, class
before texture, audio last.

**Every slice updates `usage.md` for what IT ships.** S3–S10 are each user-observable and each is
its own commit, so deferring all docs to S11 would leave `usage.md` describing a CLI that does not
exist for eight commits — against the repo rule that docs move in the same change. S11 keeps only
the cross-cutting sweep.

**Two sequencing constraints that are not obvious:**

1. **The `texture` noun is ONE argparse subtree routed to ONE dispatch branch** (`cli.py:1521-1566`
   → `dispatch.py:1213`), so it cannot host two implementations for even one commit. The seam is
   therefore **library-level, not CLI-level**: **S8a builds the texture adapter and asserts it
   through the catalog API with NO CLI change**, and **S8b repoints the noun and deletes the legacy
   subsystem in one commit**. Slices S3–S6 add the new verb family for **class, sound and music
   only**. Two verb implementations never coexist; two formats never coexist.
2. **P0 gates S2, not just S7.** `DrawType` is a class file-fact (spec §4) and is default-sourced, so
   the moment the class adapter reports it, every cold invocation pays `resolve_class_defaults`
   (~14.6 s corpus-wide) unless P0 has landed. P0 runs first.
3. **The `asset-catalog` default lands in S1, not S8b.** S5 makes `classify set` live for class,
   sound and music — so if the default flipped only at S8b, every shard authored in S5–S8a would be
   git-committed under `<root>/texture-catalog/classified/…` and orphaned by the flip. That is
   authored data, which the spec calls the product. Instead: **S1 gives the new engine the
   `asset-catalog` default, and the dying legacy texture branch hardcodes `texture-catalog`** until
   S8b deletes it. No migration guard is needed and none is added — a permanent "your dir has the old
   name" check would itself be the back-compat shim the rules forbid.

```
P0 schema_cache v2 (raw default tags)   → gates S2 onward
P1 non-P8 texture decoders              → gates S8a   [must be triaged onto the board first]
S1 engine core (index, cache, shards, locks, fixtures)
S2 kind adapters: enumeration + file facts
S3 CLI: list / show                     (class, sound, music)
S4 object-ref existence validation      ← fixes a live silent bug
S5 classification store + classify verbs
S6 search + ranking
S7 class arm: mesh decoder → uedcli/, class preview, size facts
S8a texture arm on the new engine
S8b delete the legacy texture subsystem
S9 audio phase (a): sound + music
S10 lifecycle: prewarm, cache gc, outdated / prune / clone
S11 docs
```

## 1. Module map

**New:** `uedcli/catalog/{__init__,index,store,previews,query}.py`,
`uedcli/catalog/adapters/{texture,klass,sound,music}.py`, `uedcli/umesh.py`,
plus a mesh render path (S7 decides whether that is a new module or the existing Rust core — §2 S7).

**Changed:** `config.py`, `schema_cache.py` (P0), `classindex.py` (`is_placeable` help text),
`cli.py`, `dispatch.py`, `packages.py`, `dxpkg.py`.

**Deleted — the grep-verified inventory (S8b).** The first draft of this plan under-listed it; these
are the real references:

| what | where |
|---|---|
| `texture_catalog.py` — everything **except** `assign_refs`, `derive_colors`, `nearest_color`, `PALETTE`, `PALETTE_NAMES`, `validate_colors`, `_norm_tags`, `image_hash` | `Manifest`, `TextureEntry`, `ExportedTexture`, `to_json`/`from_json`, `manifest_path`/`load_manifest`/`save_manifest`, `reconcile`, `bucket`, `status_counts`, `search`, `_score`, `_entries`, `all_tags`, `classify_set`, `_file_hash`, `parse_pcx_stem`, `_decode_exported`, `sync_package`, `_package_lock` |
| `texture.py` | the **whole module** — it is only `batchexport_textures` |
| `config.texture_images_root()` | + `test_config.py:593` |
| the sync branch and the **call site** at `dispatch.py:1292-1295` | NOT `stub.ephemeral_build_container` itself — it is shared with `substrate stub` (`dispatch.py:1418`, `stub.py:342`) |
| the "run `texture sync --package`" error string | `dispatch.py:1379` |
| `dispatch._load_all`'s top-level `*.json` glob | |
| `cli.py`'s `tsync` parser; `texture list --stale/--removed`; the `stale`/`removed` bucket vocabulary; `texture list`'s `ref\tWxH\tbucket\ttags` output; `texture search`'s "needs a query or --tag/--color" exit-2 | |
| tests | `test_texture_catalog.py`, `test_texture.py`, `test_texture_integration.py`, the **seven** texture tests + `_tex_project` fixture in `test_dispatch.py:937-1080`, `test_config.py:593`, the texture cases in `test_cli.py:407-417` and `test_cli_consistency.py` |
| comments | `stub.py:359`, `container_assets.py:9` |

**NOT deleted:** the on-disk `texture-catalog/` directory. It is **untracked and not gitignored**, so
`rm -rf` is irreversible — git cannot restore it. S8b stops reading it and tells the user it is
now dead; deleting it is the user's call. *(The first draft called it "tracked" in one place and
"untracked" in another; it is untracked, 70 manifests, 4,791 entries, 0 classified.)*

## 2. Slices

### P0 — `schema_cache` v2: persist **raw** class default tags
*Gates S2 onward.* `schema_cache` today caches discovery + own-property schema and explicitly no
defaults, so `DrawType`/`Mesh`/`MultiSkins`/`DrawScale`/`Collision*`/`PrePivot`/`Skin`/`Texture` all
come from `uprops.resolve_class_defaults`, memoized per-invocation only.

**The blob stores RAW per-class default TAGS, unrendered — not resolved or rendered values.**
`resolve_class_defaults` walks the whole super chain *across packages* and renders each tag through
`render_default_tag` against the **cross-package leaf schema union**, so a per-package blob holding
rendered text is stale the moment a parent package (`Engine.u`) changes under a child
(`DeusExDeco.u`), and its rendered enum/struct text is valid only for the leaf that produced it.
Chain-overlay and rendering stay in-process — the same split as `.disc`/`.prop`.
**Cache ALL default tags per class, with no property allowlist** — an allowlist scoped to the five
properties first identified would force a second `SCHEMA_CACHE_VERSION` bump when S7 needs
`DrawScale`, `CollisionHeight`, `Skin` and `Texture`.
**Named work this touches:** `PackageSchema.golden_bytes()` must include the new blob or the
frozen-golden guard stops covering defaults; the `schema_golden_fire_v1.marshal` fixture
(`test_schema_cache.py:26`); and the exact blob-suffix assertions at `test_schema_cache.py:119`
(`== [".disc"]`) and `:124-125` (`== [".disc", ".prop"]`).
**Done when:** the defaults path is byte-identical cache-on vs cache-off (mirroring
`test_schema_cache.py:560`); **rendering stays uncached** (the criterion that actually protects the
design — `resolve_class_defaults` renders each tag against the leaf schema union, so a cached
rendered value would be valid only for one leaf); a parent package change is reflected on the next
call **with the child's blob untouched** (correctness comes from the parent's own blob re-keying —
there is deliberately NO cross-package invalidation here, and an engineer who builds one has built
the very thing this design avoids); a cold second invocation resolves defaults without re-walking
bytecode.

### P1 — full native texture decode
*Gates S8a only.* **Now specced and review-gated** in its own right:
`specs/2026-07-25-native-texture-formats.md` (owner-decided; see `rationale/MIGRATION.md` for the old
2026-07-25 06:30 ledger citation); it sits on `to-plan.md`
as a `p1` and needs its own plan before S8a is scheduled. Two things changed since this plan first
called it "non-P8 decoders": layout is **derived from the data** rather than any per-game format
table (slot numbers are not portable between engines), and it is **not** DX-irrelevant — the
`bHasComp`/`CompMips` finding means 30 textures in the project's own `LUM_CoreTex.utx` are invisible
to uedcli today.

### S1 — engine core
Stat-keyed per-`(kind, package)` index with a **`v<N>/` path segment** (a version bump then leaves a
reclaimable orphan dir); `deps` stat-tuple list per row, re-stat'd on read; content-addressed preview
store; tracked shard store + per-project `shard-index` gated on `(file count, max mtime_ns, total
size)`; atomic writes; **two lock domains** — tracked shards under `<catalog>/.locks/`, derived cache
under `~/.uedcli/cache/catalog/.locks/`. Adapter protocol: `enumerate`, `identity`, `facts`, `preview`.

**Fixtures use REAL committed packages, not synthetic ones.** There is no UE1 package *writer* in the
tree (`upackage.py` is read-only; `native/pkg_write.py` assembles a container but knows nothing of
name tables, tagged-property blocks or back-patched `TLazyArray` absolute offsets), so hand-building
a `.u` with a mesh class would be a slice in itself — and it would have to invent the mesh layout
before S7 establishes it. The offline suite already does the right thing: `uned/UED22/` holds 214
**git-tracked** packages (`DeusEx.u` for classes, `DeusExDeco.u` for meshes, `DeusExSounds.u` for
sounds) and `tests/fixtures/{CoreTexWater,LUM_InfoPortraits}.utx` are committed — this is exactly how
`test_schema_cache.py:25` and `test_mesh_decode.py` already run offline. The **only** real gap is
`.umx`/`.uax`, and a `.umx` is a bare tracker module, trivially synthesizable.
**Done when (all offline):** index round-trips; overlay-shadow collision (same stem, different
realpath) yields two entries; the kind-keyed index survives indexing one package as two kinds; a
version bump orphans a whole dir; the shard-index gate catches a **deletion**; two projects get
separate roll-ups; the three `PKG_EXTS` definitions agree (new `dxpkg` assertion); the new engine
resolves its tracked root to `asset-catalog` while the legacy texture branch still reads
`texture-catalog`.

### S2 — kind adapters: enumeration + file facts
Texture enumeration **by descent from `Engine.Texture`**, not exact class match (49 stock
`FireTexture`/`WetTexture`/`WaveTexture` are invisible otherwise). **This couples the texture adapter
to `classindex`:** `utexture.textures()` is exact-match today and `utexture.py` carries its own
private package loader, so resolving an *imported* subclass means consulting the class index — and
**the `.u` that defines the subclass must enter that texture row's `deps`**, or the `.utx` index goes
stale when it changes.

Class via `classindex`; music from `.umx`. **Sound scope:** `.uax` + `.u` minus conversation-audio
packages, where **the VO package pattern is per-substrate CONFIGURATION, not code** — the only real
signal is the package name (`DeusExConAudio*`), and having the tool infer VO-ness from content would
violate the governing principle *and* hardcode a Deus Ex fact into a generic-UE1 tool. `--include-vo`
overrides.
`undecodable` and `preview_state` stay **separate** flags.
**Done when:** each adapter enumerates against the committed packages; a `.u` change invalidates a
`.utx` row that depended on it; VO exclusion is config-driven and `--include-vo` overrides; an
unparseable asset stays enumerable and flagged.

### S3 — CLI: `list` / `show` (class, sound, music)
Refs one-per-line; `--json` JSONL rows carrying `preview: <path>|null` **verified by `stat` at emit
time**, never trusted from the row. **`class list`/`class show` keep their existing OUTPUT SHAPES — and gain an
additive surface, which this slice enumerates flag by flag before code lands:**

- `--json` on **both** `class list` and `class show` (neither has it today) — spec §6 requires the
  build to state exactly what each emits, and S7's done-when presupposes `class list --json` exists.
- `class show` takes **multiple refs and `-`** (it takes exactly one FQCN today), and its output
  gains the catalog fields.
- `class list --package` already means *placeable classes defined in P* (filtered), NOT a plain
  corpus scope — documented, not silently redefined.
- **Spelling:** `class list` already expresses this axis as `--include-abstract`. A second
  `--placeable` spelling would be back-compat cruft on arrival — pick one and delete the other in
  the same commit.
- `--catalog-dir` is added to the three new nouns (it exists only on the texture verbs today).
- The `-`/stdin and empty-stdin-exit-0 conventions are exercised by a done-when, not assumed.

*(`--classified`/`--unclassified` cannot live here — there is no store until S5 — so they are S5's.)*
**Done when:** the three nouns list and show against committed packages; `class show` accepts
multiple refs and `-`, and empty stdin exits 0; `class list --json` and `class show --json` emit the
documented shape; `class list` stays offline and maps-free; **`class show` GAINS the resolved default
beside each category-bearing property (spec §6) — this slice's done-when previously said "no existing
`class` OUTPUT changes", which the 2026-07-26 spec revision supersedes**;
`usage.md` documents the three nouns in this commit.

### S4 — object-ref existence validation
Validate object-valued props (`AmbientSound`, `Song`, `OpeningSound`, …) at author time: exit 2
naming the offending ref instead of exiting 0 and shipping a silently broken level.

**Validate against raw package existence, NOT the kind-scoped enumeration.** Sound enumeration is
deliberately filtered (VO excluded), so an `AmbientSound=DeusExConAudio…` ref is valid in the game
and absent from `sound list` — validating against enumeration would exit 2 on correct content. The
check is an `upackage` export-table lookup: does this object exist in any package on the composed
path. **`Mesh` refs are out of scope here** (there is no mesh kind, and the decoder lands in S7) —
filed as a follow-on against S7.
**The selection rule must be stated, or two engineers build two different gates** (and the
over-eager one exits 2 on valid content, costing the author their edit): a property is validated
**iff the class schema declares it an `ObjectProperty`** — never a hardcoded property-name list.
`None`/empty values are exempt. `Mesh`-typed refs are excluded in this slice (no mesh kind yet).
The schema lookup is where P0's ordering pays off.

**Cost is a first-class criterion here, because this runs on the hot author path** (`actor add`,
ingest, the generators) against a composed path that includes ~10,200 `DeusExConAudio*` exports.
Measure it; if it is not sub-100 ms, back it with a name→package existence roll-up in the S1 index
(still pure enumeration, so no principle is violated).

**Tests must opt out of the autouse stub:** `conftest.py:76` no-ops `_validate_ingest_actors` /
`_validate_texture_ref`, so these regressions need the real path enabled explicitly.
**Done when:** a typo'd sound ref fails cleanly on the generator and ingest paths; a **VO** sound ref
validates while being absent from `sound list`; a valid ref is unaffected; the added cost on
`actor add` is measured and recorded in the commit message.

### S5 — classification store + `classify` verbs
`set` (single + `-` JSONL), `unset` (whole + per-field), `status`, `tags`. Pixel-hashed shards carry a
**write-once `ref`**; name-keyed paths are **casefolded** with the authored spelling in the payload.
This slice also owns **`--classified`/`--unclassified`** on `list`/`search` (they need the store).
**Done when:** round-trip per kind; `classify set -` writes N shards in one process, and empty stdin
exits 0; two agents writing different identities never touch one file; two spellings of a class name
→ one shard; `--classified`/`--unclassified` filter correctly; `usage.md` documents the loop.

### S6 — search + ranking
**This slice wires the `search` verb itself onto class, sound and music** (S3 delivered only
`list`/`show`), including the per-kind filters spec §5 names: `--drawtype` and the
placeable/abstract filter for `class` (spelled per S3's decision).
Implement spec §5b: identifier tokenization (case transitions, underscores, digit boundaries —
`ClenGrayMetal_A` → `clen gray metal a`), scored fields with weights (name > tags > description >
package/group), match mode, default cap.
**Done when:** the tokenization case passes (it needs no textures), and a **class/sound** ranking
regression over a zero-classification corpus passes. *(The spec's headline `texture search wall`
regression cannot live here — texture does not join until S8a — so it is asserted in S8a's
done-when instead.)*

### S7 — class arm
**Settle first: reuse the Rust rasterizer, or ship a Python one?** `preview_native.py` already
rasterizes textured, z-buffered scenes through the Rust core (`uedcli_native.render_frame`), so a new
Python render module would be uedcli's **third** rasterizer — and the **~300 ms/render measurement
that decisions 7 and 11 rest on is an artifact of choosing Python**. The spike already ships
`render.py`/`render_class.py`, so re-measuring is cheap.

**This slice MEASURES and REPORTS; it does not overturn the decision.** Decisions 7 (never render in
`list`/`search`) and 11 (single `iso` angle) are owner-decided (`direction/asset-catalog.md`)
and stand unless he supersedes them. If the Rust path makes rendering an order of magnitude cheaper,
that finding goes back to him and lands as a **revision of `direction/asset-catalog.md` plus a
`direction.md` reconcile** — not as a builder's judgement call mid-slice.

Productise `spikes/2026-07-25-native-mesh-decode/harness/umesh.py` into `uedcli/umesh.py` — it is a
**script, not a module**: `sys.path` bootstrapping, argv parsing, `raise SystemExit` on empty
geometry, silent `continue` on a bad wedge index, and a hard error on a non-empty `RemapAnimVerts`
that is correct for a spike but an unhandled crash for `class preview` over an unknown package. It
needs a real error taxonomy, a documented API (`render(mesh, skins, pose, size) -> Image`), and a
bounded fallback when a skin fails to resolve. The spike's test switches to importing the real module.

Then: `class preview` (`iso` default, `--angles front,back,left,right,top,bottom,iso`, `--out DIR`);
skins from class defaults (`MultiSkins[i]`/`Skin`) with the mesh's `Textures` as fallback; size facts
on `class show` (mesh bbox × `DrawScale`, `CollisionRadius`/`CollisionHeight`, `PrePivot`).
**Editor-icon detection is PER-SUBSTRATE CONFIGURATION, not code** — the same resolution S2 applies
to VO packages. The only available signal is a substrate-specific package/group name, so having the
tool decide what a texture *means* would both reintroduce the forbidden inference and hardcode Deus
Ex into a generic-UE1 tool. The icon-group pattern set is declared in the games config; the resolved
`Texture` ref is reported as a plain fact so an LLM can override the call. Classes matching it get
`preview_state: editor-icon`, skipped by `prewarm`. Measuring the fraction needs the real install →
**integration** test.
**Two engine questions, each with an owner and an outcome** (not open-ended "settle during"):
whether any placeable actor overrides `DrawType` per-instance — answered by a probe over the
install, and if yes the adapter reads the instance value; and whether frame 0 or an `Idle`
`StartFrame` reads better as the thumbnail frame — answered by rendering both for a sample and
picking one, recorded in the commit message. If either turns out to be a real choice rather than a
finding, it goes to the board rather than being decided here.
**Done when:** a committed-package mesh class renders; `DT_Brush`/`DT_None` report `no-mesh`; a
**skin package** change invalidates the thumbnail; a cold `class list --json` produces **no** artifact;
no `SystemExit` or bare traceback escapes on a malformed mesh.

### S8a — texture adapter on the new engine (LIBRARY-LEVEL, no CLI change)
Per §0 constraint 1 this slice touches **no argparse and no dispatch branch** — the legacy `texture`
noun keeps working untouched, and everything here is asserted through the catalog API. Native
on-demand decode; **colours pre-filled from the texture's own pixels, ordered by descending
share**, LLM-overridable (`colors_source: "set"` wins); `--similar` = phash ⊕ colour distance,
`--max 20`, `distance` surfaced, mutually exclusive with lexical terms (exit 2); the **error
taxonomy** layered over `textures()`/`decode_texture` (unknown ref / ambiguous 2-part ref /
undecodable / `EACCES` ≠ ENOENT), because `TextureResolver.resolve()` collapses every failure to
`None`.

**Pin the identity function with a committed golden** (ref → hex digest over `CoreTexWater.utx`) and
document it as **frozen**. Every tracked texture shard's path *is* `sha256(w,h,RGB)`, so any change
to the decode path — P1's non-P8 work, alpha/masked handling, palette index-0 semantics — silently
re-keys every shard: classifications read "unclassified" and become prunable outdated entries. This
is the one irreversibility that can lose authored work. P1 must therefore land **before** any texture
is classified, and the golden is what enforces it.
**Done when (asserted through the catalog API, not the CLI):** colour filtering works with an
**empty** classification store; subclass textures enumerate; similarity discriminates two flat
same-luminance different-colour textures; ranking puts wall textures first over a
zero-classification corpus (the spec §5b regression, re-homed from S6); the identity golden holds;
the legacy `texture` verbs still behave exactly as before this commit.

### S8b — repoint the `texture` noun and delete the legacy subsystem
One commit: point `cli.py`'s texture subtree and `dispatch.py`'s branch at the catalog engine, and
delete everything in §1's inventory. The default-root question is already settled — S1 gave the new
engine `asset-catalog` and the legacy branch its own hardcoded `texture-catalog`, so this commit
simply deletes the latter. **No migration guard is added**: the legacy dir holds no authored data,
and a permanent "your dir has the old name" check would be the back-compat shim the rules forbid.
**Done when:** the full texture verb family runs on the new engine; `bin/test` passes with **no new
skips versus baseline**; no deleted symbol survives anywhere (grep-verified); no shim exists;
`usage.md`'s texture chapter describes the new loop.

### S9 — audio: the `.umx` title sniffer + music's reduced family
Deliberately small: sound and music **enumeration, identity and the `classify` family already
landed** in S2/S3/S5/S6 — re-listing them here was duplication. What remains is the `.umx`
module-title sniffer (`IMPM` + a 26-byte name at a fixed offset — verified live: `Area51_Music` →
"Area 51", `Credits_Music` → "The Illuminati") and constraining `music` to its **reduced** family
(no `preview`/`prewarm`/`--similar` in the parser at all).
**Done when:** the title is extracted from a real stock `.umx` (**integration** — no `.umx` is
tracked, and a synthesized one would pin our own writer rather than the engine's convention), with
the offset convention pinned by that regression per the spike rule; `music preview`, `music prewarm`
and `--similar` are absent from the parser, not stubbed; `usage.md` covers both audio nouns.

### S10 — lifecycle
`prewarm [--package] [--force]`; **`cache gc [--previews]`** on the existing `cache` noun (wiring the
sweep already noted as deferred in `schema_cache.py`), treating previews as a distinct pool from
schema blobs. *(Spelled `--previews`, not `--catalog`: "gc the catalog" reads as though it touches
the tracked catalog, one line after the rule that it never touches tracked files.)*
`classify list-outdated` / `prune --outdated` / `clone --from`; `preview --skeleton` emitting a
fill-in JSONL row per previewed ref. Cold catalog-wide operations emit a **progress line to stderr**
(~50 s cold for the stock texture corpus) so the cost is never silent.
**Done when:** gc evicts an artifact and `list --json` then reports `preview: null`; gc never touches
tracked files; `clone` keeps local classifications and reports skips; the outdated flow works end to
end.

### S11 — docs: the cross-cutting sweep
*(Per-slice `usage.md` updates already landed with their slices — §0. What remains is what no single
slice owns.)* Replace
`architecture.md`'s "Texture catalog" section (`architecture.md:1875`/`:1891`); fix
**(DONE 2026-07-26 — `direction/projects-and-config.md` now states the `asset-catalog/` default, owner-confirmed; do NOT edit it again, and note `config.project_catalog_dir()` still returns `texture-catalog` until this plan changes it)**; update
`dev/docs/dev-runtime.md` and `dev/docs/deusex-assets-setup.md:95`; sweep the board files
(`to-spec`/`inbox`/`someday`/`to-build`) for texture-catalog references; add a `leveldesign/` page on
discovering and placing assets; delete this plan, the spec, and the superseded
`specs/2026-07-19-texture-catalog-redesign.md` **and `specs/2026-07-19-texture-show-for-llm.md`** (the
redesign spec says to delete the two together, and it is banner-superseded by a file that will no longer
exist).

## 3. Risks

| risk | mitigation |
|---|---|
| P1 gates S8a | it gates **only** S8a and is now specced + review-gated; S1–S7/S9–S10 proceed regardless |
| Texture identity is a frozen unversioned key | committed golden in S8a + P1 lands before any classification exists |
| S7 promotes script-grade code | S7 has explicit productisation items (error taxonomy, API shape, bounded fallbacks), not just a file move |
| A third rasterizer | S7 measures the Rust path first and REPORTS; decisions 7/11 change only by an owner-confirmed revision of `direction/asset-catalog.md` (NOT a `decisions.md` entry — that ledger is FROZEN) |
| Authored shards stranded by a dir rename | the `asset-catalog` default lands in S1, before any shard can be written (§0 constraint 3) |
| S8a/S8b seam | S8a is library-level only, S8b is the single CLI repoint + deletion commit |
| S8b's deletion breadth | the inventory in §1 is grep-verified; done-when demands zero skips |
| Concurrent sessions edit board/docs | commit by explicit path, never `-a` |

## 4. Not in this plan

Spectrograms, duration, `sound export` (audio phase b, behind the `.uax` decode spike); `Mesh`-ref
validation (follow-on to S7); similarity for non-texture kinds; mesh export; contact sheets (banned);
any tool-side inference of meaning or usage.

## 5. Plan-review round 1 (2026-07-25, 2 cold reviewers)

Folded: incomplete S8 deletion inventory (→ §1 grep-verified table, incl. `test_dispatch.py`'s seven
tests, `test_config.py:593`, `test_cli*.py`, the `dispatch.py:1379` string, `texture.py` as a whole
module, and the shared `ephemeral_build_container` **call site** only); incomplete `texture_catalog.py`
keep-list (→ eight symbols named); the `catalog` default flip was unslotted and would break the live
legacy arm (→ pinned to S8b, made loud); P0 gates S2 not just S7 (→ reordered); P0's blob must hold
**raw unrendered tags** and **all** properties, with `golden_bytes()`/fixture/suffix-assertion edits
named (→ P0 rewritten); synthetic `.u` fixtures are infeasible with no package writer (→ real
committed packages, per existing precedent); S4 must validate against raw package existence, not
kind-scoped enumeration, or VO refs fail validation, and `Mesh` is out of scope (→ S4 rewritten, plus
the `conftest.py:76` autouse-stub trap); S6's done-when was a texture criterion in a texture-free
slice (→ re-homed to S8a); S8 was not commit-sized (→ split S8a/S8b); `texture-catalog/` is untracked
so deleting it is irreversible and the plan contradicted itself (→ not deleted; §1 corrected); texture
identity needs a frozen golden (→ S8a); the spike code is script-grade and a Rust rasterizer already
exists (→ S7 productisation items + the settle-first question); texture subclass enumeration couples
to `classindex` and needs the defining `.u` in `deps` (→ S2); VO exclusion must be per-substrate
config, not inferred (→ S2); `.unr` belongs in S1 not S9; `cache gc --catalog` → `--previews`;
missing cold-cost stderr line, `--catalog-dir` on new nouns, and the `clone` regression (→ S3/S10);
short doc inventory (→ S11).

**Plan-review round 2 (2026-07-25, 2 cold reviewers).** Folded: S8a could not be a green commit
because the `texture` noun is one argparse subtree (→ S8a is library-level, S8b repoints and deletes
in one commit); shards authored in S5–S8a would be stranded by the S8b default flip (→ the
`asset-catalog` default moves to S1, the dying legacy branch hardcodes the old name, and the
migration guard is dropped as a shim); the `class` noun's spec-mandated additive surface
(`--json` on list/show, multi-ref + `-` on show, the per-kind filters) belonged to no slice (→ S3
enumerates it, S6 owns the `search` verb and filters, S5 owns `--classified`/`--unclassified`);
"zero skips" was unmeetable against a baseline with legitimate install-guard skips (→ "no new skips
versus baseline"); P0's done-when contradicted P0's design by demanding cross-package invalidation
the design deliberately avoids (→ reworded, plus the rendering-stays-uncached criterion that
actually protects it); S9 duplicated S2/S3/S5 and had no done-when (→ shrunk to the `.umx` sniffer +
music's reduced family, with an integration regression); S4's object-ref selection rule was
undefined and had no cost story on the hot author path (→ ObjectProperty-typed only, exemptions
stated, sub-100 ms criterion with an index-backed fallback); S7's editor-icon detection was
tool-side inference and a Deus Ex hardcode (→ per-substrate config, mirroring S2's VO resolution);
S7 authorized overturning two Andrzej-decided entries (→ it measures and reports, supersession goes
back to him); docs were deferred to a terminal S11 against the same-change rule (→ every slice
updates `usage.md`; S11 keeps the cross-cutting sweep); the fixture inventory was overstated at 214
(→ **34** tracked packages, and **no** tracked `.uax`/`.umx`, so those checks are integration-only);
`.unr` moved from S9 to S1. One reviewer also reported a collection failure in `test_normalize.py`
from a concurrent session's WIP — **not reproducible**: the suite collects 2374 tests cleanly.
