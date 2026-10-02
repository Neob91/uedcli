# Spike: sound-corpus-remeasure

Board item: `board/to-spike/sound-corpus-remeasure`. Re-measure the SOUND corpus on uedcli's real
composed search path, decide whether `sound list` needs a default filter, and unblock the audio-arm
spec.

Harness: `measure.py` (this dir). It drives the tool's OWN resolver
(`config.composed_search_files`) and enumerates `Sound` exports via `upackage.load_package`, so it
measures only what the tool would load. Run:

```
python3 measure.py --root <DeusEx-install>        # or UEDCLI_DX=<install>, or --config <toml>
python3 measure.py --root <install> --check       # assert the stable retail-content facts
```

## The corpus is INSTALL-LAYOUT-dependent — this is the whole finding

The board captured two contradictory prior measurements: the old design's ~10,826 sounds / ~10,200
`DeusExConAudio*` VO, and a re-measurement's **747 / zero VO**. Both are real. They differ by where
the install keeps the conversation-audio code packages:

- **`DeusExConAudio*.u` in `System/`** (stock GOG retail layout) → they are ON the composed path.
- **`DeusExConAudio*.u` relocated to `System.bak/` or `SystemOk/`** (the re-measurer's install) →
  OFF the path; only 747 SFX-ish exports remain.

The re-measurement concluded the VO "does not occur on the path". That was true only of that one
install. It is NOT a property of the tool or of a stock install.

## Measured here (stock GOG "DeusEx GOTY", `dev/games/dxreal`)

Composed path = `{System, Sounds, Music, Textures}`, **131 package stems**.

| metric | measured |
|-----------------------------------------------|---------:|
| TOTAL `Sound` exports on the composed path | **10,629** |
| in 18 `DeusExConAudio*.u` packages (VO) | **10,079** |
| in `DeusExSounds.u` (SFX) | **399** |
| in `Ambient.uax` (SFX) | 85 |
| in `MoverSFX.uax` (SFX) | 66 |
| **non-VO total** (10,629 − 10,079) | **550** |
| full cold enumeration of all 131 packages | **481 ms** |

The old design's numbers were essentially right for this layout: 10,629 ≈ its 10,826, 10,079 ≈ its
~10,200 VO, and **550 = its "≈550 after exclusion" exactly**. So the exclusion motivation (a stock
`sound list` would dump ~10k VO rows) was real, not invented.

### `DeusExSounds.u` group (Outer) structure — 399 across 10 groups

`Weapons 91, Generic 85, Animal 57, Player 56, Robot 40, Special 38, UserInterface 17,
Augmentation 7, Pickup 5, NPC 3`. Matches the spec's surviving claim. The `DeusExConAudio*` VO
packages are **flat** — every sound at the package root, no group.

### VO identification

VO is identifiable **by package name**: on stock DX it is exactly the `DeusExConAudio*` packages
(flat, root-group, 10,079 sounds). It is NOT distinguishable by a per-sound name pattern, and NOT by
group (the grouped package is the SFX one). A mod ships its VO in its own packages (the re-measurer
saw `LUM_ConversationsAudioMission20`, `TNM`), so no single hardcoded prefix covers every substrate.

### Bare-name collisions

None: every `Sound` bare name is unique within its package (399 distinct in `DeusExSounds`, all VO
packages flat and distinct). The `Package.Name` identity (decision 4) is collision-free on this
substrate. The 2-part-vs-3-part collision risk is **latent, not live** — unchanged from the spec.

### `.umx` music titles

All **35** reachable `.umx` are **Impulse Tracker** modules; the embedded song title reads at the
`IMPM` magic + 4 (26-byte field). 35/35 gave a plausible title, including the spec's live-verified
trio (`Area51_Music`→"Area 51", `Credits_Music`→"The Illuminati", `Area51Bunker_Music`→"Begin the
End"). No S3M/XM/MOD container is reachable here, so those magics/offsets stay integration- or
fixture-only, as the spec already states. The sniffer dispatches on magic and returns
`(title, format)`, reporting `format="unknown"` (never a blank title) on an unrecognised container.

## What could NOT be measured here

- **Mod VO packages** (`LUM_ConversationsAudioMission20`, `TNM`): not present in this environment
  (only `LUM_Core.u` code and a `LUM_InfoPortraits.utx` texture fixture exist). Their counts (the
  board cited 109 and 84) are taken on the re-measurer's word, UNMEASURED here. This does not gate
  anything — see the scope rule.
- **S3M / XM / MOD** `.umx` titles: no such container reachable.

## Scope rule — SETTLED: `sound list` takes NO default filter

Grounded in the CLI conventions (`CLAUDE.md`, `direction/conventions.md`), not in a corpus size:

- A **producer verb prints its whole set** to stdout, one item per line, count to stderr. A default
  filter that hid 10,079 rows would be exactly the "partial result plus a warning that scrolls away"
  the no-silent-half-answers rule forbids.
- **Narrowing is composition, not a per-verb flag.** SFX-only is `sound list | grep -v
  '^DeusExConAudio'`, or a structured `sound list --package <glob>` selector — never a hidden
  default. VO-vs-SFX is a package-name fact the caller filters on; the tool does not decide which
  packages are "VO to hide".
- Cost is not a reason to filter: 10,629 sounds enumerate in **481 ms cold**.

**Consequence — the old design's audio surface dies, as the spec wanted, but for the corrected
reason.** Drop the per-substrate VO config key, `--include-vo`, and the excluded-count reporting. The
spec's stated justification ("747 is an ordinary listing") is FALSE on a stock install (10,629); the
correct justification is "a producer prints its set; composition narrows." Because there is no
hardcoded VO pattern at all, the "the `DeusExConAudio*` pattern misses `LUM_`/`TNM`" objection is
moot — there is no pattern to be wrong.

## Survives with no further spike (phase a — buildable now)

Name-keyed identity (`Package.Name`), the full `classify` family for BOTH audio kinds, enumeration /
ref-names / group structure, and the `.umx` IT/S3M/XM title sniffer. None needs sample decoding.

## Waits (phase b — behind a separate `.uax`-decode spike)

`sound preview` (spectrogram), duration/rate/channels/loopability, and opt-in `sound export <ref>
--out X.wav`. Unchanged. `sound preview` must be ABSENT from phase (a), as `music`'s permanently is.

## Pinning (spikes.md)

`measure.py --check` asserts the **stable retail-content facts** — the three golden IT titles,
all reachable `.umx` = IT, and the `DeusExSounds` 10-group structure — and exits 3 on drift.
Install-layout-dependent TOTALS are reported, never asserted. The permanent home is a fixture-built
`.umx`-title test added at build time (the spec's test-coverage section records it as the one
required audio test); it is fixture-based because the corpus lives outside the repo and the offline
suite has no mounted install.
