# Spec: asset catalog — the AUDIO arms (sound + music)

**Status:** split out of the unified spec 2026-07-26. **BLOCKED — the corpus must be re-measured on the
composed search path before any of this is designed.** Every number the old §4a/§7 used came from walking
directories the tool does not load, and the scope rule built on them is both unnecessary and wrong.
**Ephemeral:** fold into `architecture.md` + `usage.md` on build, then delete.

> **Part of the split asset-catalog spec set** (split 2026-07-26 after two spec-gate rounds returned
> ~103 findings and the churn proved to be concentrated in the texture and audio arms — see
> `board/inbox.md`). The shared engine, storage layout, verb surface, decisions and prerequisites live in
> **board item `unified-asset-catalog`**, which every arm depends
> on and which is built first. Sibling arms:
> class (board item `the-asset-catalog-class-arm-needs-four-changes`) ·
> texture (board item `unified-asset-catalog`) ·
> [audio](spec.md).

---

## BLOCKER: the sound-corpus measurements do not hold on the composed path

Re-measured 2026-07-26 against the real configured path (`~/.uedcli/config.toml` →
`.../DX/{System,Textures,Sounds,Music}`, **119 package stems**):

| claim | on the composed path |
|-------------------------------------------------|---
| "**10,826** Sound exports on the composed path" | **747** |
| "~**10,200** conversation VO in `DeusExConAudio*.u`" | **0** — those packages exist only under `System.bak/` (18) and `SystemOk/` (18) |
| "Expected corpus ≈ **550** after exclusion" | **747** with no exclusion at all |
| `DeusExSounds.u` = 399 SFX | **399** ✅ (this one holds) |

A whole-install walk (mods included) gives 31,059 — which is where 10,826 came from.

**Three consequences, all of which invalidate the old design:**

1. **The VO exclusion is unnecessary.** It existed to prevent a 10k-line `sound list` dump. 747 rows is an
   ordinary listing. So the new per-substrate config key, `--include-vo`, and the excluded-count reporting
   were all surface bought with a number that does not occur on the path.
2. **The exclusion pattern is also WRONG.** The VO that *is* on the path is
   `LUM_ConversationsAudioMission20` (109 exports) and `TNM` (84). A `DeusExConAudio*` pattern matches
   neither, so the project's own conversation audio would leak into `sound list` while the machinery
   reported "excluded: 0".
3. **Two downstream arguments lose their basis:** plan S4's hot-path cost criterion ("a composed path that
   includes ~10,200 `DeusExConAudio*` exports", held to sub-100 ms), and the engine spec's
   ObjectProperty-validation worked example (validate against raw export tables *because* a VO ref would
   otherwise fail).

**RULED 2026-07-26 — spike first, then spec.** The owner's call: re-measure before designing any scope
rule, rather than dropping the exclusion outright or patching the pattern. So this arm stays blocked and the
next artifact is a spike, not a slice.

**Next action: a `[spike]`, not a spec.** Re-measure on the composed path — Sound export counts per
package, the group structure, how much is VO, and whether `sound list` needs any default filter at all.
Only then decide whether a config key is warranted. Do not design the scope rule first.

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

- **`.umx` titles:** an IT module's title is read at `IMPM`+26 (live-verified: `Area51_Music` → "Area 51",
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
