# Plan: audio arm (sound + music) — PHASE A

Ephemeral, per `CLAUDE.md`. Build per [`rules/building-features.md`](../../../rules/building-features.md):
a feature worktree, committing per slice; user docs (`docs/usage.md`) updated in the same change; then
checks + `bin/test` + a by-hand exercise + one subagent review, and squash-merge as one commit.

Scope is **phase (a) only** — everything that needs no sample decoding. Phase (b) is DEFERRED behind a
separate `.uax`-decode spike and is NOT planned here (see "Deferred" at the end).

Grounding: the enumeration and sniffer are proven in the spike harness
(`dev/docs/spikes/sound-corpus-remeasure/measure.py`); the store and CLI mirror the shipped **class
arm** (`uedcli/class_catalog.py`, `uedcli/cli/commands/classes.py`, `uedcli/cli/parsers/classes.py`).
The composed path already loads `.uax`/`.umx` — they are in `config.PKG_EXTS` (`config.py:46`) — so no
search-path change is needed (and none is allowed, spec §7 "`.unr` dropped").

Two nouns, `sound` and `music`, each carrying the catalog verb family, mirroring `class`/`texture`.
`music` ships the REDUCED family (no `preview`/`prewarm`/`--similar`, as `music` permanently lacks a
picture). `sound` ships no `preview`/`prewarm` in phase (a) either — there is nothing persistent to warm
(identity is name-based, needs no decode) and `preview` is the phase-(b) spectrogram. Sharing one
kind-parametrised command module vs two is the builder's call, pinned by tests; the plan assumes a
shared `cli/commands/audio.py` keyed by `kind` with per-noun parsers.

---

## Identity, group, and the collision rule (settled here, pinned by a fixture)

Identity is name-based (`direction/asset-catalog.md`; spec decision 4): a sound/music ref keys to
**`Package.Name`** (casefolded), NOT its group. But a `Sound` export carries an Outer **group**
(`DeusExSounds.u`: 399 sounds across 10 groups). Two same-named sounds in different groups of one
package would silently share one shard.

Rule (the texture arm's 2-part-else-3-part rule, applied to audio): **identity = `Package.Name` when
that bare name is unique within its package, else the full dotted `Package.Group.Name`.** Latent, not
live on Deus Ex (399 distinct bare names — spike), so it is fixture-tested, not corpus-tested. `list`
prints the full addressable dotted ref (`Package.object_path`); `show`/`classify` accept either the
dotted ref or the 2-part identity and resolve to the same shard.

---

## Slices

Each slice: the change, the tests (offline, synthetic `.uax`/`.umx`/`.u` fixtures written by the test —
the class/texture-arm approach; real-corpus checks marked `-m integration`), and a by-hand verify.

### A1 — audio enumeration index (name-keyed identity + group)

New `uedcli/audioindex.py`: enumerate over `config.composed_search_files` (config.py:450) the exports of
class **`Sound`** (kind `sound`) and class **`Music`** (kind `music`), via `upackage.load_package`
(upackage.py:177) + `Package.object_class_name` (upackage.py:159); ref = `Package.object_path`
(upackage.py:117); group = the middle dotted segment(s). This is `measure.py:_sound_exports`
(lines 65-80) promoted into the tool, generalised over the class name. Apply the collision rule above to
compute each ref's identity. Add a mockable `resources.audio_index(project, kind)` seam mirroring
`resources.class_index` (resources.py:218), so CLI tests run offline.

- **Tests:** a synthetic `.uax` with two `Sound` exports in different groups → both enumerated with
  their dotted refs and parsed groups; a `Music` export in a `.umx` → enumerated for kind `music`; a
  non-`Sound`/`Music` export is not listed; the collision rule promotes two same-bare-name sounds in
  different groups to distinct 3-part identities; `-m integration`: `DeusExSounds` yields 399 sounds in
  the golden 10-group structure (`measure.py:_GOLDEN_DEUSEXSOUNDS_GROUPS`, lines 215-218).
- **Verify:** against `dev/games/dxreal`, `bin/uedcli sound list --package DeusExSounds` prints 399
  dotted refs; count on stderr.

### A2 — the `.umx` embedded-title sniffer

New `uedcli/umxtitle.py`: `sniff_title(buf: bytes) -> (title: str | None, format: str)`, dispatching on
magic — the spike's proven reader (`measure.py:_umx_title`, lines 84-103). Offsets:

| format | magic | title field |
|--------|--------------------|---
| IT | `IMPM` | 26 bytes at magic **+4** |
| S3M | `SCRM` | 28 bytes at magic **−0x2C** |
| XM | `Extended Module: ` | 20 bytes at magic **+17** |

On an unrecognised container return `(None, "unknown")` — never a blank title that reads as "no title"
(spec §7). Only **IT** is reachable/live-verified here (all 35 DX `.umx` are IT); S3M/XM/MOD stay
fixture- or integration-only (honest gap, spike "What could NOT be measured").

- **Tests:** the three golden IT titles (`Area51_Music`→"Area 51", `Credits_Music`→"The Illuminati",
  `Area51Bunker_Music`→"Begin the End", `measure.py:_GOLDEN_UMX_TITLES` lines 210-214) from committed
  fixture bytes; a hand-built **S3M** and **XM** fixture read their own title fields; an unrecognised
  blob → `(None, "unknown")`; `-m integration`: all reachable `.umx` sniff as IT with a plausible title.
- **Verify:** `bin/uedcli music show DeusExMusic.Area51_Music` (or the real ref) prints `title: Area 51`
  and `format: IT`.

### A3 — the audio classification store (refuse + `--force`)

New `uedcli/audio_catalog.py`, mirroring `class_catalog.py`'s shard / per-shard flock / temp+`os.replace`
shape (`shard_path` :92, `ClassShard` :103, `save_shard` :126, `shard_lock` :138, `unset` :189,
`classified_refs` :231, `tag_vocabulary` :245, `score` :257) — a **private copy**, not an import (the
class module's own rule). Shards under `<catalog>/classified/<kind>/…` where `kind ∈ {sound, music}`;
payload `{kind, ref, tags, description}` keyed by the identity (A1). `resources.catalog_dir`
(resources.py:231) is reused unchanged.

The one deliberate divergence from the class engine: **`set` REFUSES an existing shard; `--force`
replaces it** (spec §7; `direction/safety.md`). So instead of `class_catalog.merge_set`'s tag
union-merge (class_catalog.py:153), write `set_shard(prior, ref, *, tags, description, force) -> Shard`
that raises (exit 2 naming the ref, printing the stored payload) when `prior is not None and not force`,
and otherwise writes exactly the supplied tags/description. No union, no per-field merge.

- **Tests:** round-trip `{kind,ref,tags,description}`; a second `set` over an existing shard **raises**
  (→ exit 2) and leaves the shard unchanged; `--force` replaces it wholesale (tags NOT unioned);
  `unset` field clears mirror `class_catalog.unset` (`--tags`, bare `--tags`, `--description`, `--all`
  deletes the shard); `tag_vocabulary` counts; `classified_refs` globs the identity set; the write-once
  `ref` keeps its authored spelling.
- **Verify:** covered via A4 by-hand.

### A4 — the `sound` noun (list · show · search · classify)

New `cli/parsers/sound.py` + shared `cli/commands/audio.py`; register in `cli/main.py` (mirroring
lines 44/48) and route in `cli/dispatch.py` (mirroring `class` at :87). Verbs mirror
`cli/commands/classes.py`:

| verb | behaviour |
|-------------------|---
| `list` | enumerate every sound ref, one dotted ref per line, count → stderr. `--package NAME` (**exact, repeatable**, unknown → exit 2 naming it), `--classified`/`--unclassified` (shard presence), `--json` (`{ref, identity, group, classified}`). NO default filter. |
| `show <ref>… \| -` | facts (package, group, identity) + stored classification (tags, description), one block per ref; `--json`; `-` reads a newline ref list. |
| `search <terms…>` | ranked discovery over ref + stored tags/description (reused `score`, class_catalog.py:257); terms REQUIRED, term-less → exit 2 pointing at `list`; `--tag`, `--json`. |
| `classify set <ref> --tags … --description … \| - [--force]` | record against identity; refuse-or-`--force` (A3); `-` reads JSONL `{ref, tags?, description?}`, all-or-nothing (mirror `_classify_set_batch`, classes.py:392). |
| `classify unset <ref>… \| - [--tags[=…]\|--description\|--all]` | mirror `_classify_unset` (classes.py:439). |
| `classify status [--json]` | classified / total on the path (intersection, classes.py:476). |
| `classify tags [--json]` | tag vocabulary (classes.py:490). |

Inherited conventions: producers print the whole set to stdout; empty stdin → exit 0 no-op; a bad ref
exits 2 naming it, never a traceback (every path regression-tested, `CLAUDE.md`).

- **Tests** (via `test_cli` with the `resources` seams patched to a fixture corpus + tmp catalog dir):
  `list` prints every ref with no default filter; `--package NAME` is exact (a glob-looking value matches
  nothing → exit 2, not a fuzzy match) and repeatable (union of two); unknown `--package` exits 2;
  `--classified/--unclassified/--json` shapes; `set` then a second `set` exits 2, `--force` replaces;
  JSONL `-` writes N shards all-or-nothing (one bad row writes nothing); empty stdin → exit 0; `search`
  term-less exits 2; a bad ref exits 2 naming it (no traceback).
- **Verify:** on `dev/games/dxreal`: `sound list | wc -l` = the full corpus (not a filtered subset);
  `sound list --package DeusExSounds --package Ambient` unions the two; classify a ref, re-classify →
  refused, `--force` → replaced; `sound show` on that ref shows the stored tags.

### A5 — the `music` noun (reduced family + embedded title)

New `cli/parsers/music.py`; reuse `cli/commands/audio.py` with `kind="music"`; register + route as A4.
Same family MINUS `preview`/`prewarm`/`--similar` (none exists for music). `music show`/`list --json`
additionally carry the **embedded title + format** from A2's sniffer (read live from the `.umx`, not
stored). Assert `music` has no `preview` sub-parser (as the class arm asserts its own absences).

- **Tests:** `music list` enumerates `Music` refs; `show`/`list --json` carry `{title, format}` from a
  fixture `.umx` (IT golden; an S3M/XM fixture; an unrecognised blob → `title: null, format: "unknown"`);
  `classify set`/refuse/`--force`/`unset`/`status`/`tags` as A4; `music preview`/`music prewarm` are
  absent from the parser (exit 2 "invalid choice").
- **Verify:** `music list` on `dev/games/dxreal` lists the module refs; `music show <ref>` prints the IT
  title.

### A6 — user docs + final verification

- `docs/usage.md`: add the `sound` and `music` nouns and their verbs/flags/output (the reduced music
  family; `--package NAME` is exact+repeatable; `classify set` refuses without `--force`). Keep it short
  and plain (`CLAUDE.md` "Documentation"). No `docs/leveldesign/` craft claim is added (none needed; new
  craft knowledge would need owner approval — out of scope).
- Fold-back on merge (per `rules/documentation.md`, specs are ephemeral): the enumeration/identity/sniffer
  facts land in `dev/docs/architecture.md` (audio arm) and the `.umx`-title offsets in
  `dev/docs/unrealed/` cited from `umxtitle.py`. **These `dev/docs/` writes are owner-gated** — propose
  the exact text and wait; do not write them as part of the build.
- Run `bin/test` (offline green; note that `-m integration` corpus checks need `dev/games/dxreal`), read
  the whole diff, exercise both nouns by hand, one subagent review, then `git mv` the item to `done/` and
  squash-merge.

---

## Honest gaps carried from the spike (fixture-only, not corpus-verified here)

- **Mod VO packages** (`LUM_ConversationsAudioMission20`, `TNM`) are not in this environment. The arm
  needs no VO pattern at all (spec: no default filter, no hardcoded prefix), so nothing depends on them;
  no test asserts their counts.
- **S3M / XM / MOD `.umx`** are not reachable — only IT is live-verified. Their sniffer offsets (A2) are
  pinned by **hand-built fixtures**, flagged in the test as fixture-only, exactly as the spike states.

## Deferred — phase (b), behind a separate `.uax`-decode spike (listed, NOT planned)

`sound preview` (spectrogram), duration / sample-rate / channels / loopability, and opt-in
`sound export <ref> --out X.wav`. Also `sound prewarm` (nothing persistent to warm until the engine's
derived index / preview pool lands — a separate engine board item). `sound preview` MUST stay absent
from the phase-(a) parser, as `music`'s preview permanently is (spec §7 / test-coverage). None of this is
buildable without the `.uax` decoder; file it as its own item when the decode spike is scheduled.
