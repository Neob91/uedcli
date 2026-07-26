# Ledger migration — inventory and dispositions

This file records what happened to every entry of the retired `dev/docs/decisions.md`, and the
measured scope of the citation migration. **It outlives the migration**: it is the only map from an
old dated citation (`decisions.md 2026-07-21 12:06 UTC`) to where that reasoning now lives.

Plan: `plans/2026-07-26-docs-restructure-plan.md`. Spec: `specs/2026-07-25-docs-restructure.md`.

---

## Inventory at `0e4783f` (2026-07-26)

**These numbers govern, not the spec's.** The spec's figures were measured before `6900e34`
(the profile-generators merge) and have drifted materially — which is why the plan requires a
re-measurement after the freeze rather than trusting them.

| Measure | Spec said | **Measured** |
|-------------------------------------|-----------|---
| `CLAUDE.md` lines | 671 | **717** (Task 1 added the confirmation rule) |
| `direction.md` lines | 392 | 392 |
| `decisions.md` lines | 8,985 | **8,993** (Task 1's freeze banner) |
| Ledger entries (`^## \d{4}-`) | 227 | 227 |
| — naive `^## ` | 229 | 229 — the two extras are `## Format` and a heading **inside a fenced block** |
| `**Rejected:**` blocks | 83 | 83 |
| Files citing `decisions.md` | 171 | **175** (174 excl. itself) |
| Files citing `direction.md` | 45 | **50** (49 excl. itself) |
| `spikes/` citers | 31 | **33** |
| `specs/` citers | 62 of 64 | 62 of 64 |
| `plans/` citers | 18 of 23 | **19 of 24** |
| `unrealed/*.md` evidence sites | 7 (plan corrected to 6) | **8** — both corrections were wrong |
| Bare dated refs, no literal `decisions.md` | ~17–19 | **22 files** |

### `unrealed/` evidence sites — 8, not 6

```
package-format.md:65, :88, :184
quirks.md:262, :443
rendering.md:127
leveldesign/kb/geometry-builders.md:71, :77     <- NEW, arrived with 6900e34
```

The plan "corrected" the spec's 7 down to 6 by reclassifying `commands.md:212` as a bare dated ref
(right), but did not know about the two `geometry-builders.md` sites the profile-generators work
added (wrong). Net: 8.

### Bare dated refs — 22 files

Definition: matches `\(?[Dd]ecisions?\b[^)]{0,40}[0-9]{4}-[0-9]{2}-[0-9]{2}` and contains **no**
literal `decisions.md`, so a filename grep cannot see it.

```
dev/docs/board/to-spike.md                     uedctl/normalize.py
dev/docs/specs/2026-07-17-game-actor-…md        uedctl/preview_game.py
dev/docs/spikes/levelbuild-friction/README.md   uedctl/rotation.py
dev/docs/unrealed/commands.md                   uedctl/stash_register.py
uedctl/cli.py                                   uedctl/tests/test_apply.py
uedctl/level_select.py                          uedctl/tests/test_brush_merge.py
uedctl/native/materialize.py                    uedctl/tests/test_class_discovery.py
uedctl/tests/test_env_level_and_echo.py         uedctl/tests/test_generators.py
uedctl/tests/test_level_select.py               uedctl/tests/test_level_verbs.py
uedctl/tests/test_normalize.py                  uedctl/tests/test_stashlib.py
uedctl/tests/test_trunk_verbs.py                uedctl/tests/test_uprops.py
```

### `CLAUDE.md "<moved section>"` citations — recheck at Task 8

A `grep -rn 'CLAUDE\.md "'` over `uedctl`/`bin`/`pyproject.toml` returns **3** files, and one of
them cites a section that **stays resident**:

```
uedctl/editor.py       "Background / long-running work"   -> MOVES to rules/background-work.md
uedctl/editor.py       "never let a Python exception…"    -> STAYS (Code & CLI conventions)
uedctl/tests/test_polyalign.py  "Spikes: pin the finding" -> MOVES to rules/spikes.md
```

The spec's list of four included `test_engine_facts.py:3` and `test_mesh_decode.py:3`, which this
pattern does not return — their citation is worded differently. **Task 8 must re-derive this class
by section title, not by the `CLAUDE.md "` prefix.** Only citations of the three *moved* sections
(`spikes`, `tests`, `background-work`) need retargeting; citations of resident sections stay.

### Files referenced from `to-build.md` — the exemption boundary

`specs/`+`plans/` are exempt from retargeting and from the link checks, **except** files referenced
from `to-build.md` in any form (markdown link *or* backticked path), which are about to be executed.
Re-derive this list at Task 8 against the live `to-build.md` — it now includes this restructure's own
spec and plan.

---

## Dispositions

One row per ledger entry. `dropped` and `superseded-dead` each need a named reason;
`superseded-dead` must name the superseding entry. Both columns need Andrzej's sign-off before
either old file is deleted.

| Entry | Disposition | Reason / superseder |
|-------|-------------|---
| *(populated by Tasks 4–7)* | | |
