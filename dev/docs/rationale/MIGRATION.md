# Ledger migration — inventory and dispositions

This file records what happened to every entry of the retired `dev/docs/decisions.md`, and the
measured scope of the citation migration. **It outlives the migration**: it is the only map from an
old dated citation (`decisions.md 2026-07-21 12:06 UTC`) to where that reasoning now lives.

Plan: [`../plans/2026-07-26-docs-restructure-plan.md`](../plans/2026-07-26-docs-restructure-plan.md).
Spec: [`../specs/2026-07-25-docs-restructure.md`](../specs/2026-07-25-docs-restructure.md).
(Both are ephemeral and get deleted when the work lands — this file is what survives.)

---

## Inventory at `ae7967e` (2026-07-26)

**These numbers govern, not the spec's.** The spec's figures were measured before `6900e34`
(the profile-generators merge) and have drifted materially — which is why the plan requires a
re-measurement after the freeze rather than trusting them.

**Measure the TRACKED tree, not the working tree.** Use `git ls-files -z | xargs -0 grep -l …`,
not a bare `grep -r`. The link checker walks `git ls-files`, so a target derived from working-tree
counts can never be driven to zero — the citation pass would chase files the tooling cannot see.
Two untracked spike directories (`spikes/headless-materialize/`, `spikes/levelbuild-friction/`)
inflated the first pass of this table by exactly that mechanism; they belong to another session and
`rules/spikes.md` says their harnesses should be committed.

**Expect these to keep moving**, and re-measure at the top of each task rather than trusting a
number written here: this restructure itself adds citations (the freeze banner, the two tree
READMEs, this file), so the `decisions.md` count rises before it falls.

| Measure | Spec said | **Measured** |
|-------------------------------------|-----------|---
| `CLAUDE.md` lines | 671 | **655** — 671 + ~34 (confirmation rule + router rows) − 74 moved to `rules/` |
| `direction.md` lines | 392 | 392 |
| `decisions.md` lines | 8,985 | **8,993** (Task 1's freeze banner) |
| Ledger entries (`^## \d{4}-`) | 227 | 227 |
| — naive `^## ` | 229 | 229 — the two extras are `## Format` and a heading **inside a fenced block** |
| `**Rejected:**` blocks | 83 | 83 |
| Files citing `decisions.md` | 171 | **177** tracked (176 excl. itself) |
| Files citing `direction.md` | 45 | **50** tracked (49 excl. itself) |
| `spikes/` citers | 31 | **31** tracked (33 in the working tree — 2 untracked dirs) |
| `specs/` citers | 62 of 64 | 62 of 64 |
| `plans/` citers | 18 of 23 | **19 of 24** |
| `unrealed/*.md` evidence sites | 7 (plan corrected to 6) | **8** — both corrections were wrong |
| Bare dated refs, no literal `decisions.md` | ~17–19 | **21** tracked |

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

### Bare dated refs — 21 tracked (22 in the working tree)

Definition: matches `\(?[Dd]ecisions?\b[^)]{0,40}[0-9]{4}-[0-9]{2}-[0-9]{2}` and contains **no**
literal `decisions.md`, so a filename grep cannot see it.

```
dev/docs/board/to-spike.md                     uedctl/normalize.py
dev/docs/specs/2026-07-17-game-actor-relative-poses.md   uedctl/preview_game.py
dev/docs/spikes/levelbuild-friction/README.md   uedctl/rotation.py
  ^^ UNTRACKED (another session's spike) — not in the checker's git ls-files set
dev/docs/unrealed/commands.md                   uedctl/stash_register.py
uedctl/cli.py                                   uedctl/tests/test_apply.py
uedctl/level_select.py                          uedctl/tests/test_brush_merge.py
uedctl/native/materialize.py                    uedctl/tests/test_class_discovery.py
uedctl/tests/test_env_level_and_echo.py         uedctl/tests/test_generators.py
uedctl/tests/test_level_select.py               uedctl/tests/test_level_verbs.py
uedctl/tests/test_normalize.py                  uedctl/tests/test_stashlib.py
uedctl/tests/test_trunk_verbs.py                uedctl/tests/test_uprops.py
```

### `CLAUDE.md "<moved section>"` citations — DONE (retargeted 2026-07-26)

All four citations of the three *moved* sections were retargeted in the rules-split commit:

```
uedctl/editor.py:267              -> dev/docs/rules/background-work.md
uedctl/tests/test_polyalign.py    -> dev/docs/rules/spikes.md "pin the finding"
uedctl/tests/test_engine_facts.py -> dev/docs/rules/spikes.md
uedctl/tests/test_mesh_decode.py  -> dev/docs/rules/spikes.md
dev/docs/board/to-build.md:256    -> dev/docs/rules/spikes.md "Commit the harness"
```

`grep -rn 'CLAUDE\.md "' uedctl bin pyproject.toml` now returns exactly one file —
`uedctl/editor.py:40`, citing "never let a Python exception reach the CLI user", a section that
**stays resident**. Citations of resident sections are correct and must not be retargeted.

**Lesson for Task 8:** the class must be re-derived **by section title**, not by grepping the
`CLAUDE.md "` prefix — two of these four were worded differently and that prefix missed them. The
spec's count of 4 was right by luck, not by method.

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

---

## Review record — Tasks 1–3

`CLAUDE.md` "Review gates" requires every finding's disposition to be recorded somewhere durable
rather than left in chat. The commit messages are one-liners by house rule, so the record is here.

**Both rounds returned no structural finding.** Findings fixed in the batch: the checker's
fragment-stripping bug (same-directory `file.md#anchor` links were silently skipped, including a
live citation into `decisions.md`); `_on_deck`'s wrong resolution base (no backticked reference
resolved, so the exemption boundary was inert); the deleted-doc check's missing allowlist (it would
have failed at Task 10 with ~108 offenders, including on the two files whose job is to say where
the ledger went); duplicate-heading anchors (`#procedure-1` read as broken — a false positive on
correct content in nine docs); `_anchors` not stripping code fences (phantom anchors from code
samples); self-tests that re-implemented the assertion logic instead of driving the real gate
(proven worthless by mutation — gutting the check left 476 tests green); three false claims in the
rewritten `dev-runtime.md`; and broken relative paths in three files this batch itself created.

**Deferred, with reason:**

- **The prose-citation check was not implemented.** Task 3 asked for three failure modes; two
  shipped. A naive version returns ~2,700 unresolvable backticked strings, most legitimately not
  paths, so it would be a false-positive generator — the one thing that reliably gets a check
  deleted. The narrow version (backticked strings containing `/` **and** a known suffix) is worth
  building **before Task 8**, which retargets ~177 files with no prose check behind it. Until then,
  every downstream "the link checker passes" is weaker than the plan assumes. Tracked as an open
  `p1` on `board/inbox.md` ("the dominant citation form is prose").
- **Setext headings** (`Title` over `====`) are invisible to the anchor check. Two accidental hits,
  both in a spike doc; latent only.
- **`_on_deck` over-collects** (~28 entries, including non-ephemeral files). It can only ever
  *remove* an exemption, never add one, so the effect is more checking rather than less.
