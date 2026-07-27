# Ledger migration — inventory and dispositions

This file records what happened to every entry of the retired `dev/docs/decisions.md`, and the
measured scope of the citation migration. **It outlives the migration**: it is the only map from an
old dated citation (`decisions.md 2026-07-21 12:06 UTC`) to where that reasoning now lives.

The spec and plan live in board item `docs-restructure-is-complete`. (Both are ephemeral and get
deleted when the work lands — this file is what survives.)

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
dev/docs/board/to-spike.md                     uedcli/normalize.py
dev/docs/specs/2026-07-17-game-actor-relative-poses.md   uedcli/preview_game.py
dev/docs/spikes/levelbuild-friction/README.md   uedcli/rotation.py
  ^^ UNTRACKED (another session's spike) — not in the checker's git ls-files set
dev/docs/unrealed/commands.md                   uedcli/stash_register.py
uedcli/cli.py                                   uedcli/tests/test_apply.py
uedcli/level_select.py                          uedcli/tests/test_brush_merge.py
uedcli/native/materialize.py                    uedcli/tests/test_class_discovery.py
uedcli/tests/test_env_level_and_echo.py         uedcli/tests/test_generators.py
uedcli/tests/test_level_select.py               uedcli/tests/test_level_verbs.py
uedcli/tests/test_normalize.py                  uedcli/tests/test_stashlib.py
uedcli/tests/test_trunk_verbs.py                uedcli/tests/test_uprops.py
```

### `CLAUDE.md "<moved section>"` citations — DONE (retargeted 2026-07-26)

All four citations of the three *moved* sections were retargeted in the rules-split commit:

```
uedcli/editor.py:267              -> dev/docs/rules/background-work.md
uedcli/tests/test_polyalign.py    -> dev/docs/rules/spikes.md "pin the finding"
uedcli/tests/test_engine_facts.py -> dev/docs/rules/spikes.md
uedcli/tests/test_mesh_decode.py  -> dev/docs/rules/spikes.md
dev/docs/board/to-build.md:256    -> dev/docs/rules/spikes.md "Commit the harness"
```

`grep -rn 'CLAUDE\.md "' uedcli bin pyproject.toml` now returns exactly one file —
`uedcli/editor.py:40`, citing "never let a Python exception reach the CLI user", a section that
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
`superseded-dead` must name the superseding entry. Both columns need the owner's sign-off before
either old file is deleted.

| Entry | Disposition | Reason / superseder |
|--------------------------------------------------|--------------------------|---
| 2026-06-23 — uedcli is a generic UnrealEngine-1 tool | `direction/scope.md` | intent; its `Rejected` ("treating uedcli as a Deus Ex tool") carried over verbatim. Its `Refs:` cited `specs/2026-06-23-uedcli-new-level-authoring-design.md`, **deleted** — dropped rather than carried dangling |
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
| 2026-06-25 11:04 — actor-name resolution | `direction/conventions.md` (the batch rule) + `rationale/` (the implementation bullets) | its `Refs:` cited `specs/2026-06-24-uedcli-actor-name-resolution-design.md`, **deleted** — dropped |
| 2026-07-18 08:33 — exact-miss vs glob-miss | `direction/conventions.md` | intent; `Rejected` carried |
| 2026-07-24 16:28 — `brush poly find` skips non-brushes | `direction/conventions.md` | the calibrated exception; no `Rejected` block in the entry |
| 2026-07-24 18:50 — an inert flag ERRORS | `direction/conventions.md` | its superseded warn-and-continue recorded as a `Rejected` bullet |
| 2026-07-18 14:03 — compose-pipe (items 1–4) | `direction/conventions.md` | intent; 3 `Rejected` carried. Items 5–6 are CSG-order, other topic |
| 2026-06-25 10:36 + 2026-07-11 23:19 — `actor find`; drop `actor list` | `direction/conventions.md` | the one-query-verb rule; find-specific bullets belong to an actor-verbs topic |
| **2026-07-25 18:15 — `--class-exact` → `--exact-class`** | **`rationale/cli.md`** | **Owner ruled 2026-07-26: NOT direction.** It is an argparse implementation trap (deleting a shim re-opens prefix abbreviation), so it lands in `rationale/` keyed to the CLI module. All three `Rejected` carried there. **Never reconciled into `direction.md`** |
| 2026-06-18 store-centric model · 2026-07-05 14:58 git-branches-replace-sessions · 2026-07-18 23:01 T3D-tree invariant · 2026-07-18 08:08/08:26 delta writes · preview tiers (2026-07-13, 07-16 12:13, 07-17 18:46) | `direction/trunk-and-editor.md` | intent. Three sentences `direction.md` left in the FUTURE tense about finished work were rewritten to the present — `session.py`/`replay.py`/`merge.py` no longer exist |
| 2026-07-24 16:48/16:59/17:19/18:49 — `level import` | `direction/trunk-and-editor.md` (new section) | **had NO home**: no `direction.md` section covered it, so the migration map could not carry it. Owner ruling 2026-07-26 placed it here |
| 2026-06-18 full re-import · 2026-06-23 drop `--reapply`/`--continue` · 2026-07-05 15:54/16:06/17:11 · 2026-07-14 17:35 · 2026-07-25 02:15 typed compare · 2026-07-25 03:07 mover `Saved*` · 2026-07-17 byte-identity · 2026-07-18 21:52/22:18 warm editor | `direction/materialize.md` | intent. 2026-07-25 00:36's class-default CONTRACTION is stated nowhere — superseded in mechanism by 02:15; only the current answer survives. A "four emitters still test against a constant" caveat was dropped as board status, not intent |
| 2026-06-23 new-level guards · 2026-07-05 16:06/17:11 · 2026-07-12 12:15 ingest uniquify · 2026-07-18 07:53/08:08/08:26 · 2026-07-24 16:48 | `direction/safety.md` | intent. **Two dead promises removed**: `direction.md` still offered a binary backup (deleted 2026-07-05 16:06) and a git-repo/dirty pre-flight belonging to a mode deleted 2026-07-05 15:54. Three rulings it states (atomic rank, illegal empty rank, lost-update detection) are UNBUILT and lived only in an ephemeral spec |
| 2026-06-23 13:39 dev-doc system · 2026-07-14 14:30 host-native venv · 2026-07-24 21:58 item 5 · 2026-07-25 17:20/17:58/18:42 gate + worktrees | `direction/process.md` | intent. Carries **no reviewer counts** (`CLAUDE.md` forbids restating them) and **no standing worktree exception** — owner ruling 2026-07-26: an exception is declared live, never recorded as a rule |
| 2026-07-18 10:02 unified core · 2026-07-25 03:40 native mesh decode · 2026-06-26 12:41/14:10 schema source · 2026-07-25 06:30/11:20/17:45 texture layout | `direction/packages.md` | intent. The texture-format cluster was **never reconciled into `direction.md` at all**; only the settled AD2 limit (code-less BC2/BC3 does not decode) is stated. Cache mechanism → `rationale/` |
| 2026-06-21 fs isolation + stubbing · 2026-06-22 bake UED22 · 2026-07-14 02:20–19:21 asset wiring · 2026-07-17/07-18 warm containers | `direction/containers.md` | intent. **A dead claim removed**: `direction.md`'s "content is a separate concern" named a code-vs-content *wiring* split whose code (`split_dirs`, `substrate_code_dirs`) was deleted 2026-07-14 19:21. The stub rationale was also corrected — the cause is mesh layout + `Engine`/`Core` divergence, not the package version |
| 2026-06-24 14:30 generator pattern · 2026-06-25 movers · 2026-07-21 12:06 one-brush-per-shape · 2026-07-24 16:32/17:04/17:56/18:12/18:33 · 2026-07-25 00:14/01:05/02:30 profiles + UU | `direction/generators.md` | intent. Ten live rulings `direction.md` never carried, incl. that generators are **not project-free** (they validate class/texture existence), `--base-name`, `--origin`/`--pivot`, and the non-brush refusal |
| 2026-06-29/06-30 global CLI · 2026-07-05 in-tree state · 2026-07-14 03:30/12:00/17:35 · 2026-07-17 20:58 layout reorg | `direction/projects-and-config.md` | intent. **CORRECTS the stale load contract**: `direction.md` still claimed materialize wires the whole composed search path with "no per-level derivation", superseded 2026-07-14 17:35 — the explicit preload is O(level) |
| *(asset-catalog HELD — two arbitration items still `[decide]` on `board/inbox.md`)* | | |

### Full entry index — 227 entries, machine-assigned by keyword

**This is a SKELETON, not a verified disposition.** The topic column is a keyword guess, produced
mechanically so the remaining work is bounded and visible rather than unknown. A row is only
authoritative once a topic's own sweep has claimed it (the rows above) or a human has checked it.
`?` means the keyword pass found nothing — those need reading. **No entry may be dropped, and
neither old file may be deleted, on the strength of this table alone.**

| Date | Entry | Guessed topic |
|------|-------|---
| 2026-06-21 | Container filesystem isolation (drop the `/repo` mount) | `containers` |
| 2026-06-21 | Deus Ex package "stubbing" (v68→v69 round-trip, integrated into uedcli) | `packages` |
| 2026-06-22 | Package stubbing: body-stripping, temp-name, shallow closure (refines 2026-06-21) | `packages` |
| 2026-06-22 | noVNC viewport drag: an x11vnc `-pipeinput` abs→rel bridge | `?` |
| 2026-06-22 | Full `texture` tool: an offline, hash-versioned texture catalog | `packages` |
| 2026-06-22 | Texture catalog: review-driven refinements (extends the entry above) | `packages` |
| 2026-06-22 | Bake UED22 directly to `/opt/UED22`, drop the boot-time assembly | `?` |
| 2026-06-22 | Texture catalog: a fixed named-color palette (supersedes the hex color bits) | `packages` |
| 2026-06-22 | Texture catalog: round-2 review fixes (stem identity, color provenance) | `packages` |
| 2026-06-23 | Drop `level apply --reapply` and `--continue` | `?` |
| 2026-06-23 | New-level authoring: `level apply --out`, dual-mode target, name guards | `safety` |
| 2026-06-23 | New-level authoring: uniform state-tree format + explicit commit choice (extends above) | `packages` |
| 2026-06-23 | New-level authoring: drop the bound target, `name` is the sole identity (extends above) | `?` |
| 2026-06-23 | New-level authoring: explicit `--to-map-file`/`--to-t3d-tree` mode flags | `?` |
| 2026-06-23 | uedcli is a generic UnrealEngine-1 tool (DeusEx is a baked-in substrate, not the scope) | `scope` |
| 2026-06-23 | Terminology: "level" = content, "map file" = the binary artifact | `terminology` |
| 2026-06-23 | New-level authoring: four-reviewer-fleet resolutions | `process` |
| 2026-06-23 13:39 UTC | Dev-doc system: add `direction.md`, UTC-stamp decisions, doc-upkeep rules | `process` |
| 2026-06-23 13:51 UTC | New-level authoring: second-fleet hardening | `?` |
| 2026-06-18 | Store-centric model (pivot from editor-centric) | `?` |
| 2026-06-18 | FULL RE-IMPORT as the materialize strategy (over suffix-rebuild) | `materialize` |
| 2026-06-21 | Class qualification via `OBJ LIST` (not `OBJ DEPENDENCIES` positional match) | `?` |
| 2026-06-24 08:50 UTC | `level doctor` BSP-issue detector is static-only; live "deep" mode deferred | `?` |
| 2026-06-24 09:07 UTC | Reimplement UnrealEd's BSP/CSG build OFFLINE in uedcli (faithful, editor-verified) — sup | `?` |
| 2026-06-24 12:40 UTC | BSP-issue ground truth = D0+D1 (editor drop-warnings + saved-build reader); the fully-of | `?` |
| 2026-06-24 14:30 UTC | Generator pattern: `brush build`, `actor build`, `stash intersect`/`deintersect` | `generators` |
| 2026-06-25 10:36 UTC | `actor find`: separate verb, group-membership semantics, OR/AND combining, case-insensit | `?` |
| 2026-06-25 11:04 UTC | Case-insensitive actor-name resolution via resolver helpers, not dict key change | `?` |
| 2026-06-25 12:17 UTC | Mover support: offline keyframe authoring | `generators` |
| 2026-06-26 10:53 UTC | `actor prop`: model-side property set/clear (replaces the `actor set` stub) | `packages` |
| 2026-06-26 | `uedcli deusex con`: high-level conversation source ↔ `.con` | `?` |
| 2026-06-26 12:41 UTC | Property validation: sole `.u` parse, error-not-fallback, normalize key casing to `.u` | `?` |
| 2026-06-26 | `deusex con`: remaining `.con` field semantics resolved (supersedes "MoveCamera under-de | `packages` |
| 2026-06-26 14:10 UTC | Class-property schema parses the game's REAL `.u`, never the stub cache | `packages` |
| 2026-06-26 | `deusex con`: conversation `id` is internal-only — DROP the persisted/stable-id rule | `?` |
| 2026-06-27 | De-containerization investigation: native-first is feasible; stub rationale corrected; D | `packages` |
| 2026-06-28 18:52 UTC | `Location` is canonical in the typed field only; drop the `props` mirror | `?` |
| 2026-06-29 | Class-property schema source is the configured `paths`, not a hardcoded schema search li | `packages` |
| 2026-06-29 05:18 UTC | Global-CLI: drop migration; container overlay = dynamic mount + dynamic ini Paths | `containers` |
| 2026-06-29 05:18 UTC | `actor prop`: fold typed + enum-value + array-bounds validation into v1 | `?` |
| 2026-06-29 06:02 UTC | Ditch the in-repo ignored `.uedcli/`; a project gets a TRACKED `.uedcli/` config dir | `projects-and-config` |
| 2026-06-29 06:48 UTC | Prefab naming (slashes/subdirs) + texture model: classification in-project, images in ho | `packages` |
| 2026-06-29 08:09 UTC | The `.con` conversation tool is a STANDALONE `dxconcli` prod tool, not `uedcli deusex co | `?` |
| 2026-06-30 06:18 UTC | Project layout: the project dir IS the (conventionally-named) `uedcli/` dir; project roo | `projects-and-config` |
| 2026-06-30 18:47 UTC | Global-CLI rulings: home stays `~/.uedcli/`; substrate = game (one install, many games); | `scope` |
| 2026-06-30 21:07 UTC | Config key is `game`/`[games.*]` (user-facing), not `substrate` | `scope` |
| 2026-07-01 04:26 UTC | No per-game editor image: one shared UED22, game paths wired into the ini at launch | `containers` |
| 2026-07-01 04:33 UTC | Ditch the `container` config key/knob: container instances are ephemeral and derived | `scope` |
| 2026-07-01 04:36 UTC | No default game: every project declares `game` explicitly | `projects-and-config` |
| 2026-07-01 06:16 UTC | Editor loads stubs via an override `Paths=` entry; raw `paths` are analysis-only | `packages` |
| 2026-07-01 06:16 UTC | DEFER replacing sessions with git branches; spike its viability first | `trunk-and-editor` |
| 2026-07-01 07:05 UTC | Git-merge-on-T3D-tree spike: viable; the shared `order` file is the one blocker | `?` |
| 2026-07-01 07:20 UTC | Paths-precedence spike: shadowing is enforced HOST-SIDE at apply; editor `Paths` order o | `containers` |
| 2026-07-01 07:45 UTC | Walk-up project discovery is by SCHEMA (any dir name), not conventional-`uedcli/`-only | `packages` |
| 2026-07-05 14:58 UTC | Project state goes fully in-tree; git feature branches replace the session store; `~/.ue | `trunk-and-editor` |
| 2026-07-05 15:11 UTC | Order-key scheme: `(order_value, random-id)` tiebreak; random-suffix actor names; duplic | `?` |
| 2026-07-05 15:54 UTC | Git-branch model: `level apply`→a pure `level materialize`; uedcli reads/writes only (gi | `materialize` |
| 2026-07-05 16:06 UTC | `level materialize` refuses to overwrite; guards A/B + backup dropped; H3 kept | `materialize` |
| 2026-07-05 16:48 UTC | Layout/ordering clarifications: `actor.t3d` (name lives only in the dir); tiebreak sorts | `projects-and-config` |
| 2026-07-05 17:11 UTC | Git-native spec review resolutions: materialize dup-order warn, `level materialize --ove | `materialize` |
| 2026-07-05 19:07 UTC | Level targeting: a machine-local "selected level" via `level select` | `?` |
| 2026-07-05 19:28 UTC | Drop the `--level` per-command override; `level select` is the sole level source | `?` |
| 2026-07-05 19:50 UTC | Add `level status`: a thin read-only per-level dashboard | `?` |
| 2026-07-05 22:52 UTC | `dxconcli` object transfer: one explicit `transfer` verb + a `give`-spawn sugar (drop `g | `?` |
| 2026-07-05 23:00 UTC | `level materialize` load contract: load the whole composed search path (no per-level der | `materialize` |
| 2026-07-06 05:12 UTC | Git-native editor identity: a per-COMMAND ephemeral container; materialize hard-errors w | `materialize` |
| 2026-07-06 12:01 UTC | `level preview` is a batch SHADED-SNAPSHOT renderer, not a live VNC handoff | `trunk-and-editor` |
| 2026-07-06 12:05 UTC | `dxconcli`: labels are first-class (ConEdit parity); fragments are a DRY convenience, no | `organization` |
| 2026-07-06 12:59 UTC | `level preview` snapshot-renderer: CLI grammar, no auto-frame, full RMODE set, roll omit | `trunk-and-editor` |
| 2026-07-06 14:30 UTC | `level preview` renders NATIVELY (offline rasterizer), not by driving the editor's displ | `trunk-and-editor` |
| 2026-07-06 15:58 UTC | REVERSE: `level preview` is the EDITOR-screenshot version (per-boot mode; radii/show-fla | `trunk-and-editor` |
| 2026-07-07 07:39 UTC | `stash intersect`/`deintersect` re-point onto a per-command ephemeral editor (slice 4) | `generators` |
| 2026-07-07 12:11 UTC | Mover keyframe offsets are world-additive under `BaseRot≠0`; the caution is dropped | `generators` |
| 2026-07-11 23:19 UTC | Drop `actor list`; `actor find` is the sole name-query verb | `?` |
| 2026-07-12 03:06 UTC | `--target KIND/NAME`: generic content-verb targeting (level/stash/prefab), driven by pre | `?` |
| 2026-07-12 07:37 UTC | `level preview` posing is unrenderable headless; replace POS@ROT with brush auto-frame | `trunk-and-editor` |
| 2026-07-12 12:15 UTC | Ingest of user-concatenated T3D must uniquify per-actor, not Name-key-collapse | `safety` |
| 2026-07-12 12:15 UTC | `brush build`/`actor build` name flag is `--base-name` (a stem), not `--name` | `generators` |
| 2026-07-13 19:01 UTC | `level preview` renders IN-GAME via a uplayctl-style TCP link (game replaces the editor  | `trunk-and-editor` |
| 2026-07-13 19:11 UTC | In-game preview: no uplayctl dependency (port minimal); single `Screenshot <LOC> <ROT>`  | `trunk-and-editor` |
| 2026-07-13 20:38 UTC | In-game preview: spec-gate resolutions (grammar, freeze/noclip, capture, spawn, cache) | `trunk-and-editor` |
| 2026-07-14 00:55 UTC | `qualify_level_textures` correlates blocks to brushes by CONTENT, not position; "semisol | `materialize` |
| 2026-07-14 01:40 UTC | Materialize post-verify: LevelInfo-name + float32-coords + poly-Normal are round-trip no | `materialize` |
| 2026-07-14 02:20 UTC | Asset wiring: config lists bare DIRS (not globs); full cutover to config-driven /resourc | `containers` |
| 2026-07-14 02:55 UTC | Paths generation is ONE mechanism for ALL editor search dirs, UED22 included | `containers` |
| 2026-07-14 03:30 UTC | Asset wiring, finalized: editor+game share the mounts; code-vs-content split; schema fol | `packages` |
| 2026-07-14 12:00 UTC | Bare `*` Paths DOESN'T WORK (UE1 needs `*.<ext>`); use per-dir-per-ext — SUPERSEDES the  | `containers` |
| 2026-07-14 13:30 UTC | Asset wiring Part C: retire the static compose mounts + entrypoint sed; build container  | `scope` |
| 2026-07-14 14:30 UTC | uedcli runs HOST-NATIVE in a dev venv (retire the uedcli-dev container); asset paths nee | `process` |
| 2026-07-14 17:35 UTC | Materialize OBJ-LOADs only the LEVEL's referenced packages, not the whole composed insta | `materialize` |
| 2026-07-14 17:40 UTC | Stub-build + texture-sync discovery config-driven; ONE uniform `resource_mounts` for cod | `scope` |
| 2026-07-14 19:21 UTC | ONE uniform mount set for ALL containers (editor/preview/texture/stub); retire the code- | `trunk-and-editor` |
| 2026-07-16 03:03 UTC | Native `level materialize` ships MINIMUM-VIABLE paths (nav actors + empty `ReachSpecs`); | `materialize` |
| 2026-07-16 12:13 UTC | `level preview` becomes two-backend: `--native` (offline Rust rasterizer, DEFAULT) + `-- | `trunk-and-editor` |
| 2026-07-16 15:20 UTC | Native `level materialize` builds COLLISION HULLS (`bspBuildBounds`); this — not zones — | `materialize` |
| 2026-07-16 17:30 UTC | Native `TestVisibility` zones ported (leaves/flood/ZoneActor); CSG-geometry parity is th | `?` |
| 2026-07-16 15:49 UTC | the `--game` preview container wires its packages/ini from the uedcli config (composed s | `trunk-and-editor` |
| 2026-07-16 | native CSG classifier is POINT-IN-SOLID, not rebuilt-BSP propagation | `asset-catalog` |
| 2026-07-17 04:36 UTC | Native byte-identity ⇒ port UnrealEd's INCREMENTAL `bspBrushCSG` (supersedes the scope o | `materialize` |
| 2026-07-17 04:36 UTC | Delete the synthetic leaf-bounding scaffold once the faithful CSG lands | `?` |
| 2026-07-17 04:36 UTC | Byte-identity scope + FP-feasibility stance + the same-trunk editor oracle | `materialize` |
| 2026-07-17 18:00 UTC | Phase-0 feasibility resolved: FP is SSE-scalar, byte-identity is GO (supersedes the "pro | `materialize` |
| 2026-07-17 21:30 UTC | First byte-identity increment: the incremental `bspBrushCSG` core lands as a SEPARATE, F | `materialize` |
| 2026-07-17 06:57 UTC | `--game` preview: one warm reusable container + bind-mounted, hash-named map delivery | `trunk-and-editor` |
| 2026-07-17 07:30 UTC | (supersedes the 2026-07-17 06:57 warm-container entry, in part) per-user identity + `mat | `materialize` |
| 2026-07-17 18:46 UTC | `level preview` default backend flips to `--game`; `--native` becomes opt-in | `trunk-and-editor` |
| 2026-07-17 21:10 UTC | Native lit build ships through the `bspcsg` CSG core (cleaner BSP → clearer light LOS) | `?` |
| 2026-07-17 20:58 UTC | Project layout reorg: a free `uedcli.toml` at the repo root; in-repo gitignored `.uedcli | `projects-and-config` |
| 2026-07-18 07:53 UTC | Texture per-package flock is CATALOG-adjacent (`<catalog>/.locks/`), not project-derived | `safety` |
| 2026-07-18 08:08 UTC | Trunk saves are DELTA writes under a per-level flock; concurrent disjoint edits compose | `trunk-and-editor` |
| 2026-07-18 08:26 UTC | Trunk delta writes, completed: content-diff writes + atomic per-actor files + dotted-lev | `trunk-and-editor` |
| 2026-07-18 08:33 UTC | `actor show`: exact-name miss is a named error; glob miss stays empty rc-0 | `?` |
| 2026-07-18 10:02 UTC | `actor prop set|unset|get` subcommands, dot-paths, default-value fallback (spec `specs/2 | `containers` |
| 2026-07-18 10:30 UTC | `actor prop` subcommands: spec review-gate rulings (amends 10:02) | `?` |
| 2026-07-18 11:47 UTC | `actor prop` subcommands BUILT; the §9 probe + two engine facts (closes the 10:02/10:30  | `?` |
| 2026-07-18 12:14 UTC | Actor "folders": hierarchical, per-actor-sidecar, uedcli-only (the groups overhaul) (spe | `organization` |
| 2026-07-18 12:32 UTC | Actor folders: spec review-gate resolutions (amends 12:14) | `organization` |
| 2026-07-18 12:45 UTC | Actor folders: the `// uedcli-folder:` interchange carrier + R2/R5/R6 rulings (closes th | `organization` |
| 2026-07-18 12:36 UTC | `actor prop` build: 3-reviewer gate findings resolved (amends 11:47) | `process` |
| 2026-07-18 14:03 UTC | Unattended build batch: compose-pipe, CSG-order, scale (3 specs) | `?` |
| 2026-07-18 21:30 UTC | Persistent package-schema cache (v1 discovery; phased) (spec `specs/2026-07-18-package-s | `packages` |
| 2026-07-18 22:10 UTC | Schema cache v1: split discovery/props on-disk blobs (amends 21:30, build refinement) | `packages` |
| 2026-07-18 19:41 UTC | `class list`/`show` follow-ups: O(n²) abstract decode; cache-write errors SURFACE; `--al | `packages` |
| 2026-07-18 20:09 UTC | `brush build staircase` redo: box-per-step, watertight, floor-anchored | `generators` |
| 2026-07-18 20:54 UTC | `event graph`: unset-Tag not matchable; lint is advisory (exit 0) | `?` |
| 2026-07-18 21:40 UTC | `poly align` v1 scope + face-selection grammar (Andrzej-decided) | `?` |
| 2026-07-18 21:52 UTC | Warm per-user EDITOR container for `level materialize` (ephemeral becomes the fallback)  | `materialize` |
| 2026-07-18 21:59 UTC | `class list`/`show`: kill overloaded `--all`; `--depth all` + `--include-non-actor`/`--i | `?` |
| 2026-07-18 22:18 UTC | Warm editor: spec review-gate rulings (amends 21:52) | `materialize` |
| 2026-07-18 22:25 UTC | Surface a texture's decoded image to the LLM for classification (Andrzej-decided; spec ` | `packages` |
| 2026-07-18 23:01 UTC | INVARIANT: stash, prefab, and trunk MUST share ONE T3D tree format | `trunk-and-editor` |
| 2026-07-18 23:01 UTC (addendum) | unify-T3D-trees sub-choices (Andrzej-decided) | `?` |
| 2026-07-19 03:58 UTC | Texture catalog redesign: lazy native decode, content-addressed cache, similarity (Andrz | `packages` |
| 2026-07-19 08:58 UTC | Port `bspValidateBrush` coplanar surf-link into the native incremental CSG (`bspcsg.rs`) | `?` |
| 2026-07-19 08:58 UTC | Port `bspValidateBrush` coplanar surf-link into the native incremental CSG (`bspcsg.rs`) | `?` |
| 2026-07-19 (water-cluster triage) | WaterZone authoring, doctor `fallthrough`, and poly-flag verb naming (Andrzej-decided) | `?` |
| 2026-07-19 (level-design docs + AI-skills plugin) | verb-first craft guides shipped as a Claude Code plugin (Andrzej-decided) | `?` |
| 2026-07-19 (addendum) | Move uedcli into its own CLI-only repo; plugin distribution blocked on that move (Andrze | `?` |
| 2026-07-19 12:30 UTC | Extend `--target KIND/NAME` to the read verbs (race escape hatch); skip generators (Andr | `generators` |
| 2026-07-19 19:28 UTC | Rotation CLI input is UNREAL ROTATION UNITS, not degrees (Andrzej-decided) | `?` |
| 2026-07-19 13:30 UTC | `actor find`: rename `--class` → `--class-exact`, add `--subclass-of` (Andrzej-decided) | `?` |
| 2026-07-20 00:00 UTC | Move `actor scale`/`actor apply-transform` → `brush scale`/`brush apply-transform` (Andr | `?` |
| 2026-07-20 00:30 UTC | Drop `class show`'s schema-cache seed so its prop walk uses the warm cache (~2.4× warm w | `packages` |
| 2026-07-20 13:48 UTC | `mover key` gains a `--from-base` base-relative coordinate frame | `generators` |
| 2026-07-20 15:24 UTC | `mover key` keyframe model: index-addressed create-or-edit + required frame (SUPERSEDES  | `generators` |
| 2026-07-20 16:18 UTC | `mover key`: `count` owns `NumKeys` (settable); `move`/`rotate` edit-only (SUPERSEDES th | `generators` |
| 2026-07-20 21:30 UTC | Level is the ambient `$UEDCLI_LEVEL`; rename `--target`→`--tree`; drop `level select` | `?` |
| 2026-07-21 12:06 UTC | `brush build` emits ONE non-convex brush actor + `doctor` becomes T-junction-aware | `generators` |
| 2026-07-21 12:22 UTC | Addendum to the 12:06 single-brush decision: native-convex caveat + spiral split (post-r | `?` |
| 2026-07-21 13:42 UTC | Brush-cluster confirmations (Andrzej): unified `--from-t3d`, preview knobs, spiral split | `trunk-and-editor` |
| 2026-07-21 14:17 UTC | `brush preview` §4/§5 finalization: UED brush palette + `--zoom-factor` default | `trunk-and-editor` |
| 2026-07-21 14:34 UTC | `brush preview` highlight = brush's own hue emphasized, not red | `trunk-and-editor` |
| 2026-07-21 16:41 UTC | `brush preview` → `actor preview`: rename + point-actor rendering + `--show-collision` | `trunk-and-editor` |
| 2026-07-21 17:10 UTC | `actor preview` review-gate resolution + range overlays | `trunk-and-editor` |
| 2026-07-21 17:40 UTC | `actor preview` sprite/radii facts pinned (spike resolved, source-exact) | `trunk-and-editor` |
| 2026-07-21 18:10 UTC | brush-cluster same-page confirmations (Andrzej) | `?` |
| 2026-07-22 05:29 UTC | `actor preview` labels enum + unified `--highlight` | `organization` |
| 2026-07-22 06:21 UTC | point-actor highlight: corner brackets, not a spotlight disc | `?` |
| 2026-07-22 08:28 UTC | spiral staircase: wedge treads + central column, monotonic helix | `?` |
| 2026-07-22 09:54 UTC | granular `--labels` grammar + density-aware label placement | `organization` |
| 2026-07-22 20:49 UTC | Actor `label` dimension (flat, multi-valued, uedcli-side); preview `--labels`→`--annotat | `organization` |
| 2026-07-23 05:58 UTC | Resolve the actor-`label` sub-choices (grammar, no `set`, `--tree`, patterns) | `organization` |
| 2026-07-24 08:31 UTC | `actor duplicate` ALWAYS mints `dup-<rand>`; `--label` is purely additive | `organization` |
| 2026-07-24 08:40 UTC | `--label` patterns drop char-class; `*`-only, matching folder | `organization` |
| 2026-07-24 10:02 UTC | `actor duplicate` REQUIRES `--by` or `--at` (no same-location default) | `?` |
| 2026-07-24 10:02 UTC | Composable `find` sub-choices: `--exclude`, keep `find -`, strict unknowns | `?` |
| 2026-07-22 21:18 UTC | `actor preview --split`: deterministic non-shadowing number groups | `trunk-and-editor` |
| 2026-07-23 00:00 UTC | `--split` groups are LOAD-BALANCED, not first-pane-packed | `?` |
| 2026-07-23 06:01 UTC | preview legend: reserve room + draw once per filmstrip; `--brush-colors` | `trunk-and-editor` |
| 2026-07-23 10:00 UTC | replace `--split` with `--breakdown`; `--zoom-poly` → `--zoom` | `?` |
| 2026-07-23 12:22 UTC | `--breakdown` is a near-square GRID, not a horizontal filmstrip | `?` |
| 2026-07-23 12:43 UTC | on-face numbers: largest-inscribed-box placement at 75%; harder focus dim | `?` |
| 2026-07-23 13:13 UTC | on-face numbers omit by ON-SCREEN readability; opacity 0.70/0.6 | `?` |
| 2026-07-23 13:26 UTC | dim non-focused brushes by COMPOSITING, not fade-to-bg + opaque paint | `?` |
| 2026-07-23 15:22 UTC | on-face number decals reposition to avoid screen overlap | `?` |
| 2026-07-23 16:03 UTC | cap the anti-overlap shrink at 60% of full size | `?` |
| 2026-07-23 19:05 UTC | decal overlap: minimal reshuffle + white keyline + lower opacity (supersedes the elabora | `?` |
| 2026-07-23 20:03 UTC | size on-face numbers in a fixed 2-digit slot (single digits scale like double) | `?` |
| 2026-07-23 20:14 UTC | breakdown SCENE overview: paint actor NAMES on-face (not just a legend) | `?` |
| 2026-07-24 05:27 UTC | breakdown: ditch the legend, label every brush on-face, minimal 16px pad | `organization` |
| 2026-07-24 06:43 UTC | breakdown SCENE overview is label-free (removed on-face names) | `organization` |
| 2026-07-24 16:27 UTC | `--facing` becomes component predicates on the visible normal (pose-grammar delimiters) | `?` |
| 2026-07-24 16:28 UTC | `brush poly find` takes a brush SET (`nargs`/`-`), warns (not errors) on non-brushes | `?` |
| 2026-07-24 16:32 UTC | `intersect`/`deintersect` reframed: in-tree brush-SET merge with a uniform background (n | `generators` |
| 2026-07-24 16:48 UTC | `level import`: native (editor-less) `.dx`/`.unr` → T3D-tree ingestion | `trunk-and-editor` |
| 2026-07-24 16:59 UTC | `level import`: two cold reviews refine the fidelity/validation design | `trunk-and-editor` |
| 2026-07-24 17:04 UTC | generator-flag cleanup: `--folder`/`--label` move to the generators (OFF `actor add`); ` | `organization` |
| 2026-07-24 17:19 UTC | `level import`: decode faithfully, do NOT member-diff structs (reconcile at compare) | `trunk-and-editor` |
| 2026-07-24 17:56 UTC | `intersect`/`deintersect` RE-CENTER the result so it is movable; `actor add` gets no pos | `generators` |
| 2026-07-24 18:12 UTC | `intersect`/`deintersect` refinements: no `--split`, single `--pivot`, center default co | `generators` |
| 2026-07-24 18:33 UTC | `--pivot` flag APPROVED (reinstated after the erroneous 18:12 retraction) | `?` |
| 2026-07-24 18:50 UTC | `class list --include-abstract` ERRORS (exit 2) where it can't act, not a warning | `?` |
| 2026-07-24 18:49 UTC | `level import`: decode-time UCC-exact render (supersedes 17:19) + strict validation | `trunk-and-editor` |
| 2026-07-24 19:01 UTC | `actor preview` param cleanup: `--layout`, `--frame`, `--show`; breakdown gives point ac | `trunk-and-editor` |
| 2026-07-24 19:49 UTC | Corpus study: extract ONLY brush-construction idioms from real levels | `?` |
| 2026-07-24 21:44 UTC | `actor find --within-bbox` BUILT (containment; the rest of find-spatial stays parked) | `?` |
| 2026-07-24 21:46 UTC | `uedcli docs` serves the user-facing docs from the CLI (tool documents itself) | `?` |
| 2026-07-24 21:57 UTC | NO BACK-COMPAT CRUFT: uedcli is unreleased, so a removed thing is DELETED | `conventions` |
| 2026-07-24 21:58 UTC | Board triage of the cheap-item shortlist (10 items) | `process` |
| 2026-07-24 22:28 UTC | `uedcli docs`: a README folds to its directory's topic key (root → `index`) | `?` |
| 2026-07-25 | `Rotation` folded at COMPARE time; the underlying class-default bug class opened | `?` |
| 2026-07-25 | `intersect`/`deintersect` BUILT: the editor's wrap/builder cubes COINCIDE (spec §4 corre | `generators` |
| 2026-07-25 00:14 UTC | `brush build extrude` + `brush build revolve`: the 2D-profile generator family (Andrzej- | `generators` |
| 2026-07-25 00:36 UTC | Class-default contraction at the compare seam; the write side NEVER omits to mean zero | `?` |
| 2026-07-25 01:05 UTC | `brush build revolve` has NO `--pivot` flag: the axis IS the profile's `v` axis (Andrzej | `generators` |
| 2026-07-25 00:43 UTC | `actor move` takes a SET (`-`/stdin); `--by` any count, `--to` one actor | `?` |
| 2026-07-25 00:43 UTC | Folder/label stay under `actor`; add `folder list` + `label list` (no top-level promotio | `organization` |
| 2026-07-25 00:43 UTC | `find` vs `search`: a naming RULE, not a rename | `conventions` |
| 2026-07-25 01:40 UTC | Profile-generator spec: cold-review refinements (D1–D10 unchanged) | `generators` |
| 2026-07-25 03:40 UTC | The unified asset catalog: one engine, four kinds (Andrzej-decided) | `asset-catalog` |
| 2026-07-25 03:40 UTC | UE1 meshes decode and render natively; `umodel.exe` is not needed to READ a mesh | `packages` |
| 2026-07-25 02:30 UTC | Profile-generator BUILD PLAN: cold-review refinements + D11/D12 | `generators` |
| 2026-07-25 05:10 UTC | The tool does NOT infer: uedcli is a faithful data layer, the LLM supplies meaning (Andr | `?` |
| 2026-07-25 02:15 UTC | The H3 post-verify compares TYPED effective values, not canonicalized text; contraction  | `materialize` |
| 2026-07-25 03:07 UTC | mover `SavedPos`/`SavedRot` are stripped as computed, NOT authored into the trunk | `materialize` |
| 2026-07-25 03:05 UTC | UnrealEd's 2D shape editor yields ONE brush: attested, not open (Andrzej) | `?` |
| 2026-07-25 06:30 UTC | Texture decode derives layout from the DATA; no per-game format table (Andrzej-decided) | `packages` |
| 2026-07-25 10:20 UTC | The profile verbs rely on `actor add`'s validation; the "0.4 uu collapse" premise was FA | `generators` |
| 2026-07-25 11:20 UTC | Addendum to "texture decode derives layout from the DATA" (2026-07-25 06:30): three meas | `packages` |
| 2026-07-25 10:18 UTC | `movers.is_mover` goes schema-aware: ONE predicate, and `level doctor` may require the g | `conventions` |
| 2026-07-25 11:31 UTC | `map_save`'s write verification: four stacked signals, and liveness by sentinel not exit | `?` |
| 2026-07-25 17:20 UTC | The review gate is LOOSENED: Opus reviewers, three moments, a hard 2-round ceiling (Andr | `process` |
| 2026-07-25 17:45 UTC | Texture layout arbitration is a tiebreak-and-veto; `format-disagreement` is deleted, and | `packages` |
| 2026-07-25 17:58 UTC | Feature work moves to git WORKTREES; the repo-root `CLAUDE.md` is DELETED; docs get a 1- | `process` |
| 2026-07-25 18:42 UTC | Review-gate headcount: 2 Opus (3 for specs), Haiku only in the trivial tier | `?` |
| 2026-07-25 18:15 UTC | `--class-exact` is renamed `--exact-class`, because deleting the `_RemovedFlag` shims re | `?` |
| 2026-07-25 18:40 UTC | The preview-annotation internals are renamed `annotation*`; the drawn-text machinery KEE | `organization` |

### Direction/code deltas created by the `organization` confirmation (2026-07-26)

Three places where confirmed direction now leads the tool. Not bugs introduced here — two are
pre-existing divergences the confirmation surfaced, one is new intent.

1. **`--tree stash|prefab` is REJECTED for label verbs, but direction says accept.** the owner's
   2026-07-23 05:58 #5 ruling already said allow; `dispatch.py:348-358`
   (`_reject_nonlevel_target_for_labels`) rejects, its own docstring calling it "a plan scope-cut
   … deferred". `cli.py:439` advertises "Level-only". **Owner ruled 2026-07-26: the ruling
   stands, the code is wrong.** The sibling *folder* guard is already parked on `board/inbox.md`;
   this label one was not.
2. **`stash apply` / `prefab apply` mint no batch label.** New ruling, 2026-07-26: they must mint
   `prefab-<name>-<rand>` / `stash-<id>-<rand>`, always, additive with an explicit `--label`,
   with the source name sanitised into `[A-Za-z0-9_+-]`. `actor duplicate` already does the
   equivalent (`dispatch.py:4066`); placement does not.
3. **`actor folder list` / `actor label list` do not exist.** Confirmed as direction anyway —
   direction states intent, not status, and the gap to `architecture.md` is expected by design.
   On `board/to-spec.md`.

Also corrected in passing: `direction.md` documented **`actor label set`**, a sub-verb the owner's
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
