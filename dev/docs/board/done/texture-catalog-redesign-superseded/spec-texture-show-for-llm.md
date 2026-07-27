# Spec: surface a texture's decoded image to the LLM so it can classify

> ⚠️ **SUPERSEDED 2026-07-19** by
> [`spec.md`](spec.md), which re-designs
> the whole catalog (lazy native decode, content-addressed pixel-hash cache, sharded git-tracked
> classifications, `classify clone`, visual-similarity search) rather than adding `show` on top of the
> current UCC-sync / name-keyed model. The **workflow** half of this spec (batched distinct reads, no
> montage, per-ref write-back, trust auto-colors, enrich `list`/`search --json` + thin `show`) carries
> over unchanged; the **mechanism** half (ref→`<Package>/<stem>.png` resolution, "run `sync` first")
> is replaced. Kept for history only — do not build from this file.

**Status:** SUPERSEDED (see banner). ~~specced (revised after review gate), awaiting plan → build.~~
**Requested by:** Andrzej (2026-07-19), session `uedcli:textures`. A black-box CLI run found that
texture **classification is blind**: the write path works but nothing in the `texture` verb surface
lets the classifier *see* the texture it is naming. Andrzej decided to build the viewing capability
and made the load-bearing calls below.
**Ephemeral:** per the uedcli `CLAUDE.md`, this spec is scratch. The load-bearing decisions +
rejected alternatives are in the durable append-only [`dev/docs/decisions.md`](../../../decisions.md)
(entry **2026-07-18 22:25 UTC — surface texture image to the LLM…**); on build, fold the outcome
into `docs/usage.md` + `architecture.md` and delete/stale-mark this file.
**Review gate:** two cold reviewers ran on the first draft; their findings are folded in (see
**§Review resolutions** at the end). The biggest changes vs. draft 1: resolution is by
`ref → stem` (not reconstructing `<group>.<Name>`), the error taxonomy is errno-based, and the path
is surfaced through `search`/`list` (not only a standalone `show`).

---

## Who the consumer is (this frames every decision)

**The main consumer is an LLM, not a human at a GUI.** That single fact drives the design:

- An LLM **cannot** open an image viewer or hover a thumbnail. But the agent harness (Claude Code)
  **can read an image file** when handed its path — it renders the pixels into the model's context.
  So the missing capability is exactly *"given a texture, give me the path to its decoded image"*: the
  tool resolves the file, the harness does the seeing.
- The danger to avoid is a **composite montage** — a single grid image where the LLM must map each
  cell to its label by spatial position; an off-by-one silently misattributes tags to the wrong ref
  on a committed, downstream-trusted catalog. **Reading several *separate* image files in one turn is
  NOT that** — each image arrives as its own content block bound to its own ref token, with no spatial
  mapping to get wrong. So batching the *view* over distinct files is safe; only a composite grid is
  rejected. (Decision 1.)

## The problem, concretely

Today (`texture` verbs: `sync`, `list`, `search`, `tags`, `classify status|set`):

- The classification **write path already works** (`texture classify set <ref> --tags … --description
  … [--colors …]`), and `sync` already **auto-derives** up to 3 dominant named colors per texture from
  a fixed 12-name palette (`colors_source="auto"` until a human overrides). No LLM is needed for
  colors — it is pixel-histogram math.
- But **no verb surfaces the pixels.** `list`/`search`/`classify status` print text rows; none yields
  the image or even the path to its decoded PNG.
- The decoded PNGs **do exist** under the per-user cache `~/.uedcli/cache/textures/<Package>/`, but a
  user/LLM **cannot locate one by hand from a ref**, because the on-disk filename is the manifest
  **stem** (`<group>.<name>`, or bare `<name>`), which uses the texture's internal **Group**, not the
  package in the ref: ref `CoreTexWater.bluewater` → file `…/CoreTexWater/water.bluewater.png`.

Net: classification is **blind**. The one thing the classifier needs — a look at the texture — is
unreachable through the verb surface.

## How the catalog is actually keyed (verified — the resolution must honor this)

From `texture_catalog.py`:

- A manifest's `textures` dict is **keyed by PCX `stem`** (`<group>.<name>`, or bare `<name>` when the
  texture has no group). The decoded file on disk is literally `<root>/<Package>/<stem>.png`.
- Each entry stores a catalog **`ref`**: normally 2-part `Package.Name`, but **3-part
  `Package.Group.Name` when two textures in the package share a `Name` across groups** (`assign_refs`).
  So a ref is *not* always 2-part, and reconstructing `<group>.<Name>` from a parsed 2-part ref is
  wrong.
- Name matching in the catalog is **case-insensitive** (`assign_refs` lowercases names).

**⇒ The one correct resolution:** match the input ref (case-insensitively) against entries' stored
**`ref`** field, take that entry's **`stem`**, and build `<root>/<Package>/<stem>.png`. This is
collision-safe, handles 3-part refs and groupless textures automatically, and couples nothing by
string-reconstruction (the `stem` that names the file is the same `stem` that keys the manifest).

## Decisions (Andrzej, this session) — see `decisions.md`

1. **No composite montage; batched *distinct-file* reads are the blessed path.** The efficient loop is
   a query that returns many refs+paths at once (below); the harness reads them as separate image
   files in one turn and classifies each ref. *Rejected: a montage/contact-sheet grid image* — silent
   spatial misattribution on a trusted catalog. (Revised from draft 1's over-broad "one texture at a
   time," per review; the write path is still strictly per-ref, so misattribution has no foothold.)
2. **Per-ref write-back only.** Keep `classify set <ref> …` as the sole write; no batch/bulk classify.
   *Rejected: a batch JSON-map-via-stdin classify* — one ref per write keeps decide→write unambiguous.
3. **Trust auto colors.** The LLM sets only `tags` + `description`; the auto-derived `colors` stand
   (`colors_source="auto"`) unless it explicitly overrides a wrong one via `--colors` (→ `"set"`).
   *Rejected: making the LLM always set colors* — needless work duplicating the sync-time pixel math.
4. **Surface the path through the query verbs, not only a standalone verb** (Andrzej: "could `search`
   just return the path too automatically?"). The producer that *finds* textures also *delivers* their
   images, so classification is one call, not find-then-look-up.

## The change

### A. Shared resolver: ref → decoded-PNG path

One internal function `resolve_png_path(catalog, ref) -> Path` implementing the resolution above
(input `ref`, case-insensitive, → entry `stem` → `<root>/<Package>/<stem>.png`). Every surface below
uses it. Behavior on the three failure modes is a shared, **errno-based** taxonomy (critical — a naive
`os.path.exists()` returns `False` on a permission-denied cache and masks the wall as "not synced"):

| Case | Detection | Result |
|---|---|---|
| **Unknown ref** — no entry's `ref` matches | manifest lookup miss | clear error naming the value (`Texture not found: Foo.Bar`), exit non-zero |
| **Ambiguous 2-part ref** — input is `Package.Name` but that `Name` collided across groups (real refs are 3-part) | miss on 2-part, but ≥2 entries share the `Name` | error `Ambiguous ref 'Package.Name' — did you mean: Package.GroupA.Name, Package.GroupB.Name?` listing candidates, exit non-zero |
| **Known ref, PNG absent** | entry found; `open()` → `ENOENT` | error: catalog has the entry but its image isn't in the cache; hint `texture sync [--package P --force]`, exit non-zero |
| **Known ref, cache unreadable** | entry found; `open()`/`os.access` → `EACCES` | **distinct** error: the cache dir/file can't be read (permissions); do **not** hint `sync` (won't help); point at the cache path, exit non-zero |

### B. `search` / `list` carry the path (Decision 4) — the primary LLM seam

- **Default text output stays bare-ref-per-line** where it already is, so `search … | brush poly set
  --texture -` keeps working (`search` prints one `ref` per line; `list` prints its existing
  `ref⇥WxH⇥status⇥tags` rows). No breakage.
- **`--json` on `search` AND `list`** emits **JSONL — one object per line** (matches the
  one-item-per-line CLI convention), each:
  `{ref, png_path, width, height, colors, colors_source, status, tags, description}`.
  `png_path` is the resolved absolute path (or `null` + a `png_error` string carrying the errno-case
  message, so a batch producer degrades gracefully instead of aborting the whole query on one missing
  file). This gives the LLM the image path **plus** the metadata to decide — most importantly the
  current auto `colors`/`colors_source` (to judge a Decision-3 override) — in a single call.
- **`search` gains the status filters `list` already has** (`--unclassified`/`--classified`/`--stale`/
  `--removed`, mutually exclusive). *Reason:* the LLM's producer for "what still needs classifying" is
  `search --unclassified`, and today only `list` filters by status while only `search` emits clean
  ref-per-line — neither alone is a clean unclassified-refs producer. Aligning the filters onto
  `search` closes that gap (this is the find/query verb the CLI philosophy wants).

### C. `texture show <ref> [<ref> …]` — the single-/known-ref resolver

For when you already hold specific refs (not a search):

```
texture show <ref> [<ref> …]     # print resolved absolute PNG path(s), one per line
texture show -                   # read refs from stdin (name list), same output
texture show <ref> --json        # JSONL: full metadata objects (same shape as B)
```

Thin wrapper over the shared resolver (A). Multiple refs / stdin print one path per line (a set
operation — no `--union`-style flag). Empty stdin with `-` → clean no-op, exit 0. Same errno taxonomy.
`show` is convenience/completeness; **`search --json` is the main classification producer.**

### The intended LLM loop (document in `usage.md`)

```bash
# one producer call: the refs still to classify, each WITH its image path + metadata
texture search --unclassified --package CoreTexMetal --json
#   → {"ref":"CoreTexMetal.Area51Wall_A","png_path":"/…/CoreTexMetal/Metal.Area51Wall_A.png",
#      "colors":["grey"],"colors_source":"auto","status":"unclassified", …}
#   (the harness Reads each png_path — distinct files, one turn — and sees the pixels)
# then, per ref, one write each:
texture classify set CoreTexMetal.Area51Wall_A --tags metal,wall \
    --description "riveted metal wall panel"
#   (colors stay auto → no --colors unless the auto derivation is wrong)
```

## Adjacent fix (in scope — it misleads the same consumer)

- **`docs/usage.md` classify-set example is wrong** (verified at `usage.md:519-520`): it shows
  space-separated multi-values (`--tags metal wall … --colors grey`), but each flag takes a **single
  comma list** (`--tags metal,wall …`); the space form fails with `unrecognized arguments: wall`.
  Correct it when this lands.

## Open sub-choices (recommendations — flag for Andrzej)

| # | Question | **Recommendation** |
|---|---|---|
| A | Verb name for the direct resolver: `show` vs `view` vs `image`? | **`show`** — matches `class show`. |
| B | Should `show`/`search` also *open* a viewer for a human (`--open` → `xdg-open`)? | **No** for now (LLM-first prints the path). A thin `--open` can be added later; not core. |
| C | If the PNG is missing but the package is present, decode **on demand** instead of erroring? | **No — error + hint `sync`.** Decoding is `sync`'s job; on-demand gets cheap only once sync goes native (separate item). |
| D | Is JSONL (not a single JSON array) the right multi-ref shape? | **Yes — JSONL**, one object per line, matching the one-item-per-line convention. |

## Non-goals (explicitly out)

- Composite montage / contact-sheet image (rejected, Decision 1).
- Batch classify-via-stdin (rejected, Decision 2).
- Making the LLM set colors (rejected, Decision 3).
- **Native (non-UCC) `sync` decode** — separate inbox `[spec]` item; this feature only *reads* the
  cache `sync` populates, however sync produces it.
- **The root-owned `~/.uedcli/cache/textures` bootstrap permission wall** — separate inbox `[debug]`
  item. It is a **dependency/risk** here: the resolver reads that cache. The errno taxonomy (§A) is the
  contract at the boundary — it must *report* the wall distinctly, not *fix* it.
- **Material behavior tags** (masked/translucent/animated/env-map): a flat PNG + colors conveys visual
  appearance, not material flags. Classification is treated as **appearance-oriented**; if it should
  ever cover material behavior, that needs a separate metadata source and is out of scope here.

## Test coverage (build must add)

- Resolver: ref → correct path via `stem`, **including (a) the Group≠package grouped case, (b) a
  **groupless** texture (bare `<name>.png`), and (c) a 3-part collision ref** (golden manifest).
- Case-insensitive ref match (`coretexwater.BLUEWATER` resolves), path built from the **stored** stem
  casing, not the input.
- Unknown-ref error: named, non-zero, no traceback.
- Ambiguous 2-part ref (collided name): lists the 3-part candidates, non-zero.
- Known-ref-but-PNG-missing (`ENOENT`) vs cache-unreadable (`EACCES`): **distinct** messages,
  both non-zero (simulate `EACCES` with a chmod-0 dir or a monkeypatched `open`).
- `search --unclassified --json` / `list --json`: JSONL shape incl. `png_path` (and `png_path:null` +
  `png_error` when the file is missing, so the batch producer doesn't abort).
- `show -` stdin name list; empty stdin → exit 0 no-op.
- `search` status filters behave like `list`'s.

## Review resolutions (from the two cold reviewers)

1. **Resolution was wrong for 3-part refs / coupled artifacts by reconstruction** (both reviewers,
   send-back) → **fixed**: resolve `ref → stem → <Package>/<stem>.png` (§A, §"How the catalog is
   keyed"). Adds groupless + case-insensitive + ambiguous-ref handling and golden tests.
2. **Permission wall vs missing-PNG not distinguishable with `exists()`** (both, send-back) →
   **fixed**: errno-based taxonomy, `EACCES`≠`ENOENT`, wall doesn't hint `sync` (§A). Tested.
3. **Documented loop didn't run — `--unclassified` is a `list` flag, and `list` isn't clean
   ref-per-line** (R1 #2, R2 #3) → **fixed**: `search` gains status filters; the loop uses `search
   --unclassified --json` (§B).
4. **"One at a time" was dogmatic — batched distinct-file reads are safe** (both) → **fixed**:
   Decision 1 reframed to reject only the composite montage; `search --json` is the batch producer
   (§Consumer, §B). *(Andrzej-confirmed this direction, and asked to route the path through `search`.)*
5. **`--json` multi-ref shape undefined** → **fixed**: JSONL (sub-choice D, §B).
6. **Material-flag metadata insufficiency** (R2 minor) → **acknowledged** as a scoped non-goal
   (appearance-oriented classification).
7. **`list`/`search` `--json` "scope creep"** (R2) → it is now *core* (Decision 4), not a ride-along.
