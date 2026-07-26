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
|--------------------------------------------------|--------------------------|---
| 2026-06-23 — uedctl is a generic UnrealEngine-1 tool | `direction/scope.md` | intent; its `Rejected` ("treating uedctl as a Deus Ex tool") carried over verbatim. Its `Refs:` cited `specs/2026-06-23-uedctl-new-level-authoring-design.md`, **deleted** — dropped rather than carried dangling |
| 2026-06-30 21:07 — config key is `game`, not `substrate` | `direction/scope.md` | intent; refines the above. Both `Rejected` bullets carried over |
| 2026-06-23 — Terminology: "level" = content, "map file" = the artifact | `direction/terminology.md` | intent; both `Rejected` bullets carried over. `Refs:` cited the same **deleted** new-level-authoring spec — dropped, not carried dangling |
| 2026-07-22 20:49 — actor `label` dimension | `direction/terminology.md` (glossary) + `direction/organization.md` (the feature, Task 5) | its "internals stay label-named pending a rename" clause did NOT survive — superseded below |
| 2026-07-25 18:40 — preview internals renamed `annotation*`; drawing keeps "label" | `direction/terminology.md` | supersedes the clause above; only the CURRENT answer is stated, which is what revise-in-place means |
| 2026-07-18 12:14 / 12:32 / 12:45 — actor folders (3 entries) | `direction/organization.md` | intent. All `Rejected` carried EXCEPT 12:14's "no `--folder` on the generators", which 2026-07-24 17:04 **reversed** — the reversed bullet is dead and was dropped, replaced by 17:04's rejection of the two-setter model |
| 2026-07-22 20:49 / 2026-07-23 05:58 / 2026-07-24 08:31 / 08:40 / 10:02 — actor labels (5 entries) | `direction/organization.md` | intent. Rejected carried. 05:58 #6 (fnmatch char class) **superseded** by 08:40 — only the current answer stated. 08:31's "bare duplicate stays a WARNING" **superseded** by 10:02 (now an error) |
| 2026-07-24 17:04 — generator-flag cleanup | `direction/organization.md` | intent; the reversal that kills 12:14 #8. All 3 `Rejected` carried |
| 2026-07-25 00:43 — folder/label stay under `actor`; add `list` | `direction/organization.md` | intent. **Never reconciled into `direction.md`** — it postdates everything that doc cited |
| 2026-07-24 21:57 — no back-compat cruft | `direction/conventions.md` | intent; both `Rejected` carried |
| 2026-07-24 21:58 — board triage (items 1, 3) | `direction/conventions.md` | items 1+3 only (the `class show` degrade, the `.ppm` escape hatch); items 2/4/5/6 belong to other topics and are NOT consumed here |
| 2026-07-25 00:43 — `find` vs `search` naming rule | `direction/conventions.md` | intent; `Rejected` carried |
| 2026-07-25 10:18 — schema-aware `movers.is_mover` | `direction/conventions.md` | intent; all four `Rejected` carried, incl. the silent-`False` trap promoted into *What we want* |
| 2026-06-26 12:41 — error, never fallback | `direction/conventions.md` | intent; 3 of 5 `Rejected` carried (2 belong to other topics) |
| 2026-06-25 11:04 — actor-name resolution | `direction/conventions.md` (the batch rule) + `rationale/` (the implementation bullets) | its `Refs:` cited `specs/2026-06-24-uedctl-actor-name-resolution-design.md`, **deleted** — dropped |
| 2026-07-18 08:33 — exact-miss vs glob-miss | `direction/conventions.md` | intent; `Rejected` carried |
| 2026-07-24 16:28 — `brush poly find` skips non-brushes | `direction/conventions.md` | the calibrated exception; no `Rejected` block in the entry |
| 2026-07-24 18:50 — an inert flag ERRORS | `direction/conventions.md` | its superseded warn-and-continue recorded as a `Rejected` bullet |
| 2026-07-18 14:03 — compose-pipe (items 1–4) | `direction/conventions.md` | intent; 3 `Rejected` carried. Items 5–6 are CSG-order, other topic |
| 2026-06-25 10:36 + 2026-07-11 23:19 — `actor find`; drop `actor list` | `direction/conventions.md` | the one-query-verb rule; find-specific bullets belong to an actor-verbs topic |
| **2026-07-25 18:15 — `--class-exact` → `--exact-class`** | **`rationale/cli.md`** | **Andrzej ruled 2026-07-26: NOT direction.** It is an argparse implementation trap (deleting a shim re-opens prefix abbreviation), so it lands in `rationale/` keyed to the CLI module. All three `Rejected` carried there. **Never reconciled into `direction.md`** |
| *(remaining entries populated by Tasks 5–7)* | | |

### Direction/code deltas created by the `organization` confirmation (2026-07-26)

Three places where confirmed direction now leads the tool. Not bugs introduced here — two are
pre-existing divergences the confirmation surfaced, one is new intent.

1. **`--tree stash|prefab` is REJECTED for label verbs, but direction says accept.** Andrzej's
   2026-07-23 05:58 #5 ruling already said allow; `dispatch.py:348-358`
   (`_reject_nonlevel_target_for_labels`) rejects, its own docstring calling it "a plan scope-cut
   … deferred". `cli.py:439` advertises "Level-only". **Andrzej ruled 2026-07-26: the ruling
   stands, the code is wrong.** The sibling *folder* guard is already parked on `board/inbox.md`;
   this label one was not.
2. **`stash apply` / `prefab apply` mint no batch label.** New ruling, 2026-07-26: they must mint
   `prefab-<name>-<rand>` / `stash-<id>-<rand>`, always, additive with an explicit `--label`,
   with the source name sanitised into `[A-Za-z0-9_+-]`. `actor duplicate` already does the
   equivalent (`dispatch.py:4066`); placement does not.
3. **`actor folder list` / `actor label list` do not exist.** Confirmed as direction anyway —
   direction states intent, not status, and the gap to `architecture.md` is expected by design.
   On `board/to-spec.md`.

Also corrected in passing: `direction.md` documented **`actor label set`**, a sub-verb Andrzej's
2026-07-23 ruling explicitly refused and the code has never had. The same error is repeated inside
the frozen ledger's 2026-07-24 17:04 entry — noted so nobody re-copies it.

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
