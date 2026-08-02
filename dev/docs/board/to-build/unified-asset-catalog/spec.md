# Spec: asset catalog — the TEXTURE arm

**Ephemeral** (scratch, per `CLAUDE.md`). The durable homes are
[`direction/asset-catalog.md`](../../../direction/asset-catalog.md) (the owner's decisions) and
[`rationale/`](../../../rationale/) (the agent's). Fold the outcome into `architecture.md` +
`docs/usage.md` on build, then delete.

**This file replaces the earlier engine+split-index `spec.md` for the texture arm.** The class arm
shipped (board item `asset-catalog-class-arm-standalone-spec`, merged); the shared-engine pieces it
deferred (derived per-`(kind,package)` index, the content-addressed preview pool, the shard-index
roll-up, `classify prune`/`list-outdated`) stay tracked as their own engine board items and are **not**
texture-arm work. `spec-texture-arm.md` (2026-07-28) is superseded by this file and should be dropped.

**Source of the identity model:** `questions/four-open-catalog-decisions.md` `## Answer` (owner ruled
2026-08-02). This spec folds every ruling there as settled. The one part that answer defers — re-keying
a classification across a pixel edit — is `questions/texture-rekey-across-a-pixel-edit.md`, open, and
blocks only the lifecycle slice.

---

## 0. Goal

Give the `texture` noun the same verb family the `class` noun already has — `list`, `show`, `preview`,
`search`, `classify set·unset·status·tags`, `prewarm` — over every texture on the composed package
search path, so an LLM agent can see a texture, read its facts, and record what it is. The legacy
manifest catalog (`texture sync` + `texture_catalog.py`) is **deleted**, not migrated (it holds no
authored data; no back-compat cruft, `conventions.md`).

The governing principle holds: the tool lists, reports facts stored in the package, produces the
picture, and stores the classification it is handed — it **never infers meaning**. The single
exception is texture colours (§6), pre-filled from the texture's own pixels.

## 1. What the engine already provides vs what is texture-new

The plan builds only the **texture-new** column. The left column is shipped and reused.

| Already provided (reuse) | Where | Texture-new (build) |
|---|---|---|
| Decode seam: ref → typed `DecodedTexture` \| `TextureError` (12 named cases incl. `no-mip-data`, `ambiguous-alpha`) | `utexture.TextureResolver.resolve` | Enumerate `Engine.Texture` **descendants** per package → refs |
| Shard-store shape: git-tracked one-file-per-asset, atomic write, per-shard flock, tag normalize + `tag_vocabulary`, ranked `score`, `load_all`/`classified_refs` | `class_catalog.py` | Rewrite `texture_catalog.py` as this store, **keyed by identity** not ref; payload adds `identity` + `colors` |
| CLI verb wiring: set/unset/status/tags, JSONL batch `-`, search, prewarm, show, `list --classified/--unclassified/--json` | `cli/commands/classes.py` | Rewrite `cli/commands/texture.py` + `cli/parsers/texture.py` to mirror it for `texture`; delete `sync`/`--stale`/`--removed` |
| Seams: `resources.texture_resolver`, `resources.catalog_dir`, `resources.class_index`, `config.composed_search_files`, `rendering.write_png`, `config.self_ignoring_dir` | `cli/resources.py` | Layer-1 identity `sha256(w,h,RGB)`; Layer-2 facts (group, masked); colour pre-fill; PNG preview |
| The `conventions.md` third-stdin (JSONL) carve-out | landed | — |

## 2. The two-layer identity model (settled, four-open `## Answer` §1–2)

A texture splits into two layers. **Layer 1 is the classification key; Layer 2 is ref-scoped info shown
alongside.**

**Layer 1 — content (the classifiable thing).**

- **Identity = `sha256(w, h, RGB)`** over mip 0's pixels only: the byte stream
  `uint32_le(width) ‖ uint32_le(height) ‖ rgb` where `rgb` is `width*height*3` row-major bytes from
  `DecodedTexture.rgb`. The **mask is not in identity**. This framing is the agent's call, **frozen**
  once shards exist, and pinned by a committed golden — a decode change that shifts it silently re-keys
  every tracked shard.
- Identical pixels are deliberately **one** classifiable thing. Two differently-named refs with
  identical pixels resolve to one identity, one preview, one shard (cross-package dedup).
- **A procedural texture has no pixels and is name-keyed instead.** `FireTexture`/`WetTexture`/
  `WaveTexture`/`IceTexture`/`ScriptedTexture` serialize mips with `DataCount == 0`; the decoder returns
  `TextureError(case="no-mip-data")`. Its identity is its **name** (`Package.Name`, casefolded), per
  `asset-catalog.md` "content hash where content exists, name where it does not". So water and fire are
  enumerable, referenceable, and classifiable — the old "permanently unclassifiable" defect is gone.
- The preview (§5) **is this bitmap** — opaque RGB, mip 0, native size, mask not applied.

**Layer 2 — per-`Package.Name` facts, read live from the package, not stored in the classification:**

- **`masked`** — the effective `bMasked` flag, already computed by `DecodedTexture.b_masked`
  (export tag, else resolved class default; `None` when no code package resolves the default).
- **`group`** — the export's **Outer** name (`Package.name_of_ref(export["outer"])`), or null when the
  ref is 2-part. This is where `Ladder`-group membership lives.
- Plus `width`, `height`, `format` (`layout`/`format_code` from the decode).

Layer 2 is **not part of identity and not stored in the shard**. `show` prints it; `--group`/`--masked`
filter on it. So a masked grille and its opaque-pixel twin share one Layer-1 classification while their
masked-ness shows as distinct Layer-2 facts.

**Editor-icon sprites are ordinary textures** (four-open `## Answer` §4) — no icon-group detection,
counted honestly as unclassified until classified.

## 3. The shard store

Rewrite `uedcli/texture_catalog.py` mirroring `class_catalog.py`'s shard/lock/atomic-write shape, but
**keyed by identity**. Shared no code (that is `class_catalog`'s own rule; a private copy of the tag
normalizer).

- **Payload** — `{kind: "texture", identity, ref, tags, description, colors}`:
  - `identity` — the Layer-1 key (64-hex sha256, or the casefolded `Package.Name` for a procedural).
    Equals the shard's path key.
  - `ref` — **write-once** authored `Package[.Group].Name` that produced this identity, kept for
    outdated-tracking (`asset-catalog.md`). The first classifier's ref wins; a later differently-named
    ref with the same pixels does not overwrite it (and, per §4, refuses).
  - `tags`, `description` — as the class arm.
  - `colors` — ordered list of palette colour names (§6). Absent ⇒ derive live.
- **Path** — under `<catalog>/classified/texture/`: a hash identity at `<hh>/<hash>.json` (first two
  hex as a fan-out dir, so one dir never holds thousands); a name identity under `name/<package>/<name>.json`
  (every segment casefolded). `classified_identities(catalog_dir)` globs both and returns the identity
  set. The exact layout is the agent's call, pinned by tests.
- **Atomic + locked** exactly as `class_catalog`: temp + `os.replace`, per-shard flock under
  `<catalog>/.locks/` (`config.self_ignoring_dir`).

Because the key is the identity, mapping a **ref → classified?** requires **decoding** the ref to get
its identity, then testing shard presence. Plain `texture list` (refs only) does not decode; `--json`,
`--classified`, `--unclassified`, and `status` do (see §4). `prewarm` warms that path.

## 4. Verb surface

`--catalog-dir` stays on every verb (project-less use). Inherited rules: producers print one item per
line to stdout, summaries to stderr; `-` reads from stdin; empty stdin is a clean exit-0 no-op; a
request it cannot fully satisfy exits 2 naming the value; no Python exception reaches the user.

| Verb | Behaviour |
|---|---|
| `texture list [--package P] [--classified\|--unclassified] [--group G] [--masked] [--json]` | Enumerate `Engine.Texture` descendants, sorted by ref, one per line. `--json` = JSONL `{ref, identity, classified, group, masked, preview}` (`preview` = a cached path or null — never rendered here). `--classified/--unclassified`, `--group`, `--masked` decode each ref to get identity/facts. |
| `texture show <ref>… \| -` | Layer-2 facts (w, h, format, group, masked) + Layer-1 identity + stored classification (tags, description, colors), one block per ref; `--json`. `-` reads a newline ref list. |
| `texture preview <ref>… \| - [--out DIR]` | The sole image producer (§5). `<ref>\t<path>` lines; `--skeleton` switches the stream to JSONL `{ref, preview, tags:[], description:"", colors:[…]}` (the ready-to-fill row; colours pre-filled). |
| `texture search <terms…> [--tag T] [--package P] [--classified\|--unclassified] [--group G] [--masked] [--color C] [--json]` | Ranked discovery (`class_catalog.score`, reused). **Terms required**; term-less exits 2 pointing at `list`. `--color` filters (§6). |
| `texture classify set <ref> --tags … --description … [--colors …] \| - [--force]` | Record classification against the ref's **identity**. Over an existing shard **refuses, exit 2 naming it; `--force` replaces** (four-open `## Answer`; `safety.md`). `-` reads JSONL `{ref, tags?, description?, colors?}`, one shard per row, all-or-nothing validation like the class batch. |
| `texture classify unset <ref>… \| - [--tags[=T,…]\|--description\|--colors\|--all]` | Undo, operating on the ref's identity shard. Field clears mirror `class classify unset`; `--colors` clears the colour override (search falls back to live-derive). |
| `texture classify status [--json]` | Of the textures on the path, how many have a shard (intersection, so the ratio never exceeds the total). Decodes to map ref→identity. → stdout. |
| `texture classify tags [--json]` | The tag vocabulary in use (reused `tag_vocabulary`). → stdout. |
| `texture prewarm [--package P] [--force]` | Decode every texture ahead of an offline session (warms ref→identity; and, once the engine preview pool lands, previews). Progress → stderr. |

**Refuse-over-existing differs from the shipped `class classify set`, which union-merges tags.** The
2026-08-02 ruling is texture-scoped in origin but a general safety call; this spec implements it as
given for `texture`. The divergence is flagged as a NOTE, not silently reconciled — the owner may want
`class` aligned later (out of scope here; do not touch the class item).

**`--similar REF` is deferred.** Ranking by perceptual distance needs a **persisted** phash (re-decoding
the whole corpus per call is ~50 s, measured) — that store is the engine's derived index, a separate
deferred board item. Ship `list`/`search` without `--similar`; file it as its own texture follow-on.

## 5. Preview

`preview` decodes the ref via `TextureResolver.resolve`:

- `DecodedTexture` → a Pillow RGB image from `rgb` at `width`×`height` (mip 0, **mask not applied** — the
  preview is the Layer-1 bitmap), written with `rendering.write_png(img, args.out)`. Mirrors
  `class preview`'s write path; the content-addressed preview **pool** is the deferred engine item, so
  `list --json`'s `preview` is null until it lands (exactly as `class list --json` today).
- `TextureError` → a **named error**, disposition per `direction/asset-catalog.md`: a **per-ref** request
  exits 2 naming the ref and case; **enumeration** records the case and keeps listing. A procedural
  (`no-mip-data`) is a named "no bitmap to preview" note, not a crash. **`ambiguous-alpha`** (a BC2/BC3
  chain with no code to separate them) is a named error, never a guessed pixel — this limit is stated in
  the error text and the module comment, per `asset-catalog.md`.

## 6. Colours — the one inference exception (settled, §4b / `asset-catalog.md`)

Pre-fill a small **fixed named palette** per texture, ordered by descending share of the image:

- Assign each mip-0 pixel to the nearest palette colour (RGB distance), rank names by pixel share, keep
  the top few. The palette and the top-N are the agent's call, pinned by a golden.
- Stored in the shard's `colors` on `classify set` when the row omits `colors` (the pre-fill); an
  LLM-supplied `colors` **overrides** and wins.
- `texture search --color C`: match against stored `colors` for a classified texture, else **derive
  live** from pixels — so colour search works on a fresh clone before any classification (`asset-catalog.md`).

It earns the exception because it reads only the texture's own pixels, never the corpus.

## 7. Edge cases & errors

- **Bad ref** (bare/over-dotted, unknown package/texture) → the `TextureError` ref-layer case, exit 2
  naming it. Reused verbatim; the arm mints no new decode case.
- **Undecodable but real** texture (`unverified-format`, `ambiguous-alpha`, `size-mismatch`, …) stays
  **enumerable** in `list` (recorded, not dropped) and its identity is unavailable, so it reads
  unclassified; a per-ref `show`/`preview`/`classify` on it exits 2 naming the case.
- **Procedural** texture: enumerable, name-keyed, classifiable; `preview` says it has no bitmap.
- **`classify` on an undecodable non-procedural ref** exits 2 (no identity to key on) naming the case.
- **Empty stdin** on any `-` verb → exit 0, nothing written.
- **`--json`/`--classified`/`status` when no code package resolves defaults**: identity still computes
  from pixels; `masked` reports `null` (not `false`) per the decode seam's rule.

## 8. Tests (offline; read `dev/docs/rules/tests.md`)

Synthetic `.utx`/`.u` fixtures written by the test (the same approach the sibling class-arm tests use),
plus `-m integration` for the real corpus. Cover:

- **Identity:** the frozen `sha256(w,h,RGB)` golden (a fixed w/h/RGB → a pinned hex); mask change does
  **not** change identity; two differently-named refs, identical pixels → one identity; a procedural
  (`no-mip-data`) → its casefolded `Package.Name` identity.
- **Enumeration:** `Engine.Texture` **descendants** are listed (a `FireTexture` export appears), a
  non-texture export does not; sorted by ref; an undecodable export stays listed.
- **Layer-2 facts:** `group` = the export Outer (a grouped texture reports its group, a 2-part ref
  reports null); `masked` from `b_masked` (tag, else default, else null); `--group`/`--masked` filter.
- **Shard store:** round-trip payload `{kind,identity,ref,tags,description,colors}`; identity path
  fan-out; `classify set` over an existing shard **exits 2**, `--force` replaces; two identical-pixel
  refs → the second `set` refuses and the stored `ref` is the first; `-` JSONL writes N shards
  all-or-nothing; `unset --colors` clears the override.
- **Colours:** pre-fill order matches a golden; an LLM `colors` overrides; `--color` matches a
  classified texture's stored colour and live-derives for an unclassified one.
- **Preview:** `DecodedTexture` → a PNG of the right size, mask not applied; a per-ref procedural /
  undecodable request exits 2 naming the case; `ambiguous-alpha`'s error text states the limit.
- **CLI:** `show` vs `preview` shapes; `--skeleton` replaces the stream with the ready-to-fill JSONL
  carrying the preview path + pre-filled colours; `list --json` carries `preview: null` when uncached;
  `search` term-less exits 2; empty stdin → exit 0.
- **Legacy removed:** `texture sync`, `--stale`, `--removed`, and the manifest module are gone (no
  parser entry, no import).

## 9. Non-goals (this arm)

- The content-addressed preview **pool**, the derived per-`(kind,package)` index, the shard-index
  roll-up, and `classify prune`/`list-outdated` — deferred **engine** board items, not texture work.
- **`--similar`** / perceptual hash — deferred (needs the persisted index; §4).
- **Migration** of the legacy catalog (deleted; `conventions.md`).
- **Mask-applied / RGBA previews** — the preview is the Layer-1 opaque bitmap; masked-ness is a fact.

## 10. Direction folds still owner-gated

These are **approved** (four-open `## Answer`, 2026-08-02) but land in `direction/` only with the
owner's `Confirmed:` trailer — a separate fold, not this build, and **not** done by the builder:

- `texture-group-is-a-first-class-fact` — group as a Layer-2 fact, `--group`, not identity.
- `texture-masked-is-a-stored-fact` — `masked` (read from the export), `--masked`, not identity.
- `direction-asset-catalog-md-reword-the-class` — the line-34 no-override reword.
- `asset-catalog-says-the-tool-produces-the` — the `packages.md` correction: a code-less compressed
  chain is ambiguous BC1-vs-P8 → named error, never a wrong pixel.

## 11. Open owner decision

`questions/texture-rekey-across-a-pixel-edit.md` — a pixel edit re-keys the classification and
`prune --outdated` would delete a still-accurate description, with no re-key path. Blocks only the
lifecycle work (which is a deferred engine item anyway), so the first texture slices proceed without it.
