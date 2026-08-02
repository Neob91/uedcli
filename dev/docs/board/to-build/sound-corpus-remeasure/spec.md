# Spec: asset catalog — the AUDIO arms (sound + music)

**Status:** split out of the unified spec 2026-07-26. **BUILDABLE (phase a)** — the corpus was
re-measured by the `sound-corpus-remeasure` spike (`dev/docs/spikes/sound-corpus-remeasure/`,
2026-08-02) and the scope rule is settled: `sound list` takes NO default filter. Phase (b)
(sound preview / spectrograms) still waits on a separate `.uax`-decode spike.
**Ephemeral:** fold into `architecture.md` + `usage.md` on build, then delete.

> **Part of the split asset-catalog spec set** (split 2026-07-26 after two spec-gate rounds returned
> ~103 findings and the churn proved to be concentrated in the texture and audio arms — see
> `board/inbox/`). The shared engine, storage layout, verb surface, decisions and prerequisites are
> documented in **board item `unified-asset-catalog`**. But this audio arm grounds on the **shipped class
> arm** (private copies of its shard store and CLI; `resources.class_index` for the enumeration seam), so
> it is NOT build-order-blocked on the unbuilt `unified-asset-catalog` texture arm — that dependency is a
> design reference, not a build gate. Sibling arms:
> class (board item `the-asset-catalog-class-arm-needs-four-changes`) ·
> texture (board item `unified-asset-catalog`) ·
> [audio](spec.md).

---

## RESOLVED: the corpus size is INSTALL-LAYOUT-dependent; the scope rule does not turn on it

Re-measured 2026-08-02 by the `sound-corpus-remeasure` spike, driving the tool's own resolver
(`config.composed_search_files`) over a **stock GOG "DeusEx GOTY"** install
(`dev/games/dxreal`, `{System,Sounds,Music,Textures}`, **131 package stems**):

| metric | measured (stock GOG) |
|-----------------------------------------------|---------:|
| TOTAL `Sound` exports on the composed path | **10,629** |
| in 18 `DeusExConAudio*.u` packages (VO) | **10,079** |
| `DeusExSounds.u` (SFX, 10 groups) | **399** |
| `Ambient.uax` + `MoverSFX.uax` (SFX) | 85 + 66 |
| **non-VO total** | **550** |
| full cold enumeration of all 131 packages | **481 ms** |

**Both prior measurements were real; they came from different install layouts.** The 747/zero-VO
re-measurement was taken on an install whose `DeusExConAudio*.u` had been relocated to `System.bak/`
and `SystemOk/` — OFF the composed path. On a **stock retail install those packages sit in
`System/`**, so the VO IS on the path and the corpus is ~10.6k, matching the OLD design's numbers
(10,629 ≈ 10,826; 10,079 ≈ ~10,200 VO; **550 = the "≈550 after exclusion" exactly**). So:

1. **The old design's exclusion MOTIVATION was correct** — a stock `sound list` would print ~10k VO
   rows. The spec's earlier claim that "747 is an ordinary listing, so the exclusion is unnecessary"
   is FALSE on a stock install.
2. **VO is identifiable only by PACKAGE NAME** (stock: the `DeusExConAudio*` packages, flat/root
   group, 10,079 sounds), not by a per-sound name pattern and not by group. A mod ships VO in its own
   packages (`LUM_ConversationsAudioMission20`, `TNM` on the re-measurer's install — not reachable in
   the spike environment, so their counts are unverified here). No single hardcoded prefix covers
   every substrate.
3. **Two downstream arguments KEEP their basis on a stock install:** plan S4's hot-path cost
   criterion (the ~10k VO exports ARE on the path here — enumerated in 481 ms), and the engine spec's
   ObjectProperty-validation worked example (a VO ref resolves against those export tables, which are
   present).

### Scope rule — SETTLED: `sound list` takes NO default filter

Decided on the **CLI conventions**, not on a corpus size (which is install-dependent and cannot found
a rule):

- A **producer verb prints its whole set** to stdout, one item per line, count to stderr
  ([`direction/conventions.md`](../../../direction/conventions.md)). A default filter hiding 10,079
  rows is exactly the "partial result plus a warning that scrolls away" the no-silent-half-answers
  rule forbids.
- **Narrowing is composition, not a hidden default.** SFX-only is `sound list | grep -v
  '^DeusExConAudio'`, or the structured `sound list --package NAME` selector — never a filter the tool
  applies for you.
- **`--package NAME` takes an EXACT package name, not a glob, and is repeatable** (`--package A
  --package B` = the union). This mirrors [`conventions.md`](../../../direction/conventions.md) "`find`
  = deterministic selector, not fuzzy": the verb prints its whole set by default; a `--package` narrows
  it deterministically to named packages. An unknown package exits 2 naming it (no silent empty result).
- Cost is not a reason to filter: the full corpus enumerates in **481 ms cold**.

So the old audio surface **dies as the spec always wanted — but for the corrected reason.** Drop the
per-substrate VO config key, `--include-vo`, and the excluded-count reporting. Because there is no
hardcoded VO pattern at all, the "the `DeusExConAudio*` pattern misses `LUM_`/`TNM`" objection is moot
— there is no pattern to be wrong.

---

## What survives the re-measurement

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

**`classify set` over an existing shard REFUSES (exit 2 naming the ref); `--force` replaces it.** This
holds for both audio kinds and applies to every field (tags and description alike): a `set` on an
already-classified sound/music does not union-merge — it stops and names the ref, and only `--force`
overwrites the stored shard. Rationale: never silently overwrite authored classification
([`direction/safety.md`](../../../direction/safety.md); owner ruling 2026-08-02, one rule across
texture/class/sound/music). This is the aligned behaviour, so the audio arm does NOT reuse the shipped
class arm's union-merge `merge_set`; it reuses the store's shard/lock/atomic-write shape but writes with
refuse-or-`--force` semantics. The class arm is being brought to the same rule under board item
`align-class-classify-set-to-refuse` (separate work — do not touch it here). Under the JSONL batch `-`,
`--force` governs every row; without it, the first row hitting an existing shard fails the whole batch
(all-or-nothing validation, like the class batch), writing nothing.

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

---

## Test coverage — audio arms

Read `dev/docs/rules/tests.md` and `dev/docs/rules/spikes.md` first. **`rules/spikes.md` requires every checkable
finding to be pinned by a committed regression or it rots** — the `.umx` title read is the one live-verified
audio finding and currently has no test anywhere.

- **`.umx` titles:** an IT module's title is the 26-byte name field at `IMPM`+4 (live-verified: `Area51_Music` → "Area 51",
  `Credits_Music` → "The Illuminati", `Area51Bunker_Music` → "Begin the End"); an S3M's and an XM's from
  their own header fields; an unrecognised container reports `title: null` **plus** a `format` fact naming
  what was found, never a blank that reads as "no title". Only IT is reachable here (35 `.umx`, all DX), so
  the S3M/XM/MOD offsets are integration-only or fixture-built.
- **Sound scope:** whatever the re-measurement spike concludes — including, if it concludes so, *no*
  default filter at all. If a filter survives, test that an excluded ref is still reachable by name through
  `show`/`classify`, and that the excluded count is reported.
- **Identity collision:** sound identity is `Package.Name`, but sounds carry an Outer **group** —
  `DeusExSounds.u` has 399 sounds across 10 groups (`Weapons` 91, `Generic` 85, `Animal` 57, `Player` 56).
  Two same-named sounds in different groups of one package would silently share one shard. Textures get an
  explicit 2-part-else-3-part collision rule; **sound/music need the same rule or a stated reason not to.**
  Latent, not live, on this substrate (399 distinct bare names).
- **`sound preview` does not exist in phase (a)** — its artifact is the spectrogram, which is phase (b)
  behind the `.uax` decode spike. Assert it is absent from the parser, as `music`'s permanently is.
