# To plan

Specced work awaiting an implementation **plan** (`dev/docs/plans/`). See [`README.md`](README.md).
Tag: `[plan]`.

---

- [ ] `p1` `[plan]` **`actor preview --faces {wire,flat,textured}` — solid and textured brush faces.**
  Spec: [`../specs/2026-07-26-actor-preview-textured-faces.md`](../specs/2026-07-26-actor-preview-textured-faces.md).
  **Spec gate: PASSED.** Multiple cold rounds; no structural finding in any of them, and every round's
  findings are folded into the sections themselves.

  **What it is.** `actor preview` draws a wireframe schematic today. `flat` fills each brush face in
  its CSG hue; `textured` paints each face with its real texture through the face's authored UV frame
  (`Origin`/`TextureU`/`TextureV`/`Pan`). Model-side, host-only, pure Python — no editor, no
  container, no lighting. It exists because **every** texture-frame defect in
  `../spikes/levelbuild-friction/agent-reports.md` (mirrored lettering, the half-shifted sheet, the
  wrapped door trim, a cut-out texture on a solid face) was invisible in `actor preview` and cost a
  full materialize + render cycle to find.

  **BUILD ORDER IS FIXED — this builds SECOND.** It consumes the mip-pyramid accessor and the
  `bMasked` flag that `to-build.md`'s **Native texture decode** item delivers in its slice `S2b`.
  Neither exists until that lands. Do not start a plan that assumes today's `TextureResolver`.

  **What the planner must carry over** (all settled in the spec, none of it re-derivable cheaply):
  the per-face mip rule (from the face's own screen-space UV gradients — two earlier drafts derived it
  from a view-global projection gain and both were measured wrong); the masking gate
  (`poly.flags | actor PolyFlags` OR the texture's `bMasked`) and the corpus measurement behind it —
  464 of 2,669 textures use palette index 0 while unmasked, and 13 flat colour swatches are 100 %
  index 0, so an ungated version renders them as nothing; the CSG cull (a subtract shows only its far
  faces, movers exempt via `movers.is_mover`); the even-odd scanline choice (0.1–0.6 % of real faces
  are concave, and a triangle fan bleeds outside them); and the refuse-don't-degrade failure table.

  **Owner rulings live in this spec and are ALSO parked on `inbox.md`** as one `[OWNER — confirm]`
  item, because the spec is ephemeral and deleted on build. Five of them: subtract-far-faces, the
  class-hierarchy load, refusal semantics, no cost ceiling, and choose-visual-constants-by-render.

- [ ] `p1` `[plan]` **`actor move` over a SET (`-`/stdin), `--by`-only for multi-actor.** Spec written +
  **cold-review gate PASSED** (2 reviewers, no blockers, all findings folded in):
  [`../specs/2026-07-25-actor-move-set.md`](../specs/2026-07-25-actor-move-set.md). Brings `move` to the
  `actor rotate`/`brush scale` set contract (`names… | -`); `--by` any count, `--to` rejects >1 (exit 2),
  dedupe, empty-stdin no-op, no `--pivot`. Decisions: `decisions.md` 2026-07-25 00:43 UTC. Breaking:
  positional `name`→`names` + `args["name"]`→`args["names"]` save shape (unreleased, no shim) — the spec
  §5 lists the existing tests to migrate/remove (incl. the "move does NOT accept `-`" test). Small, well-
  scoped; next action is a plan (or build directly given the sibling-mirror is so close).

> **Native texture decode** — PLANNED 2026-07-25, moved to `to-build.md`
> (`../plans/2026-07-25-native-texture-formats-plan.md`).

- [ ] `p2` `[plan]` **`brush poly find --facing` component-predicate grammar + brush-SET input.** Spec written
  + **both cold-review gates passed** (findings resolved inline — the polarity-symmetry claim corrected (ALL
  asymmetric predicates are flip-dependent), `visible_normal` now inverse-transpose(`actor_linear`) so it is
  correct under scale/shear/reflection and unifies `list_polys`+`find_faces`, full test-migration plan):
  [`../specs/2026-07-24-facing-selector-grammar.md`](../specs/2026-07-24-facing-selector-grammar.md).
  Replaces `--facing`'s single geometric axis token (`+X..-Z`/`slant`, polarity-BLIND — returns a subtract
  room's CEILING for `+Z`) with predicates on the face *visible normal* `(nx,ny,nz)` (`;`=AND, `:`=axis:spec,
  `,`=OR, `..`=range; pose-grammar delimiters), presets `flat`/`wall`/`ramp` (polarity-free) + polarity-aware
  `floor`/`ceiling`. Also makes `brush poly find` take a brush SET (`nargs="+"`/`-` stdin, dedup, warn-skip
  non-brush) — addresses the single-brush note at `inbox.md` item 5 (the geometric `--coplanar` cross-brush
  find stays a separate spec). Ships a committed engine-facts regression pinning the verified subtract
  normal-flip (`tests/fixtures/brush_subtract.t3d`). Drops the old axis tokens (hard break; migrates
  `test_query.py`/`test_polyalign.py`/`test_cli.py`, removes the now-dead `_FACING_NEG`). Decisions:
  `decisions.md` 2026-07-24 16:27/16:28 UTC. (Andrzej, 2026-07-24.)

- [ ] `p2` `[plan]` **Composable `actor find` — stdin name-set input for full boolean queries.** Spec
  written + **two cold reviews folded** (the `--exclude` semantics changed from "subtract the piped set"
  (`M∖P`) to a **grep/universe model**): [`../specs/2026-07-24-composable-find.md`](../specs/2026-07-24-composable-find.md).
  Makes `actor find` accept a name set on stdin (`-`) so filters COMPOSE into full boolean queries —
  today `--label` (and every other dimension) ORs within itself, so "label X AND Y" is inexpressible.
  Model: the piped set is the **universe**, the filters are the **predicate**, `--exclude` negates.
  Sub-choices resolved in `decisions.md` 2026-07-24 10:02 UTC: negation spelled `--exclude`; the
  no-filter `find -` identity/validator form KEPT (base of the union re-normalization
  `… | sort -u | find -`); an unknown piped name is a **strict all-or-nothing exit 2**. Orthogonal to
  actor-labels — it benefits every filter dimension and changes no filter's OR-within semantics.
  **One soft confirm outstanding:** the grep/universe model is recorded as the working model pending
  Andrzej's final yes (`decisions.md` 10:02). Otherwise ready to plan. (Andrzej, 2026-07-24.)

- [ ] `p2` `[plan]` **Corpus brush-idiom study — ground the construction craft in real levels.** Spec
  written + **both cold-review gates passed (2026-07-24), findings folded** (classifier-first + self-
  consistency gate; three-way reproducibility split (existing-generator / missing-builder / freehand);
  `level import` demoted from blocker to convenience — pilot uses the proven `MAP EXPORT`->trunk route;
  new `brush build extrude` prerequisite surfaced; quant-first / wireframes-secondary; pilot delivers
  harness+method only with durable numbers gated on the scaled run; behavioral acceptance eval as the
  done-condition): [`../specs/2026-07-24-corpus-brush-idioms.md`](../specs/2026-07-24-corpus-brush-idioms.md).
  Extracts ONLY the brush-construction idiom vocabulary (shape alphabet + composition grammar +
  complexity/BSP budget) from the retail DX maps, UE1 (Unreal Gold SP primary; UT99 sparingly) as the
  differential control, output as **generator reverse-mapping**; grounds
  `leveldesign/general/brush-shapes.md`/`geometry-and-bsp.md`/`design-craft.md`. Decisions: `decisions.md`
  2026-07-24 19:49 UTC + review-refinements addendum. **A few review-driven changes await Andrzej's yes
  before planning** (extrude-generator priority; find-spatial unpark timing; interim-route acceptance).
  Owns the shared `MAP EXPORT`->trunk harness that the `2026-07-19` item (Half B2, dimensions) consumes —
  don't fork. Stands up per-game install scripts + gitignored `dev/games/` for the UE1 control. Surfaces
  uedcli gaps (`brush identify` + reverse-mapping + `brush stats` -> `inbox.md`; `brush build extrude`
  -> specced, plan-reviewed, and now **on-deck in `to-build.md` #12** together with `brush build
  revolve`, so this study's bucket-(a) vocabulary must include both).
  (Andrzej, 2026-07-24.)

- [ ] `p2` `[plan]` **Level-design best-practices docs + AI-skills plugin.** Spec written +
  cold-review-gated + revised: [`../specs/2026-07-19-leveldesign-docs-skills.md`](../specs/2026-07-19-leveldesign-docs-skills.md).
  Three deliverables: (A) verb-first rewrite of the `leveldesign/` guides (GUI-equivalent notes
  retained, per-guide retention checklist); (B) a measurement spike for DeusEx human-scale numbers
  (offline class-defaults + a MAP-EXPORT map-geometry corpus + player collision cylinder + object
  sizes); (C) a Claude Code skills plugin at `claude/plugins/uedcli/` (repo-as-marketplace;
  distribution blocked on the uedcli-own-repo move — interim dev via a `.claude/skills` symlink). Needs
  a build plan sequencing A+B then C, with the two cold-reviewer gates. (Andrzej, 2026-07-19.)

- [ ] `p1` `[plan→build]` **uedcli as a global CLI over multiple projects (config + projects +
  layered assets).** **BIG PRIORITY.** Spec + **plan** written, both cold-reviewed (findings folded):
  `specs/2026-06-29-…-design.md`, `plans/2026-06-29-…-plan.md`. **Foundation BUILT + tested +
  reviewed** (commits `817bdc42b`, `0eec5f293`): slice A pyproject/pipx (also fixes the `PIL` bug),
  slice B `config.py` (39 tests, unwired → suite green). **Remaining slices C–H DEFERRED/GATED** —
  see `inbox.md` (slice C needs a `packages.py` consumer refactor; 2 open decisions:
  migration, container mounts). Original spec ref:
  `specs/2026-06-29-uedcli-global-cli-projects-design.md`. Turns uedcli from a repo-bound tool into
  a `pipx`-installed CLI operating on many project dirs. Core: tool/substrate/project/session
  **separation**; **two config files** — `~/.uedcli/config.toml` (per-user base substrate, ABSOLUTE
  colon-glob `paths=`) + `<project>/uedcli.toml` (project overlay, RELATIVE globs + a uuid `id`);
  **layered resolution** (project shadows base; `--explain-paths`); **central per-project state**
  `~/.uedcli/projects/<id>/{store,locks,tmp,shots}` (sessions move OUT of the content tree — apply
  still writes the `.dx`/T3D artifact INTO it); **content-addressed texture store**
  `~/.uedcli/textures/{packages/<pkg-hash>.<schema>/index.json, data/<pixel-hash>.png}` (dedup +
  explicit `texture gc`). Replaces hardcoded `substrate_search_dirs` + `host_repo_root`; new verbs
  `project init/ls/rm`, `config`, `texture gc`. **GATED on 3 decisions for Andrzej (spec §10):**
  (1) base-catalog cross-machine sharing — moving the base catalog to per-user `~/.uedcli/` is a
  **sharing regression** vs today's tracked/committed catalog; (2) migration carry-vs-drop of
  in-flight sessions; (3) overlay container-mount strategy (programmatic `docker run` bridge vs
  decontainerize-first). Resolve those, then plan — likely sliced: **(a) pipx packaging** (also fixes
  the `No module named PIL` host-interpreter bug — self-contained, do first), (b) project/config
  resolution + `uedcli.toml`/`config.toml`, (c) content-addressed texture store, (d) container overlay.
  **⚠ STALE — re-spec before building.** The 2026-06-29 spec behind this predates three superseding
  decisions and must be reconciled first, not built as-written: (1) **no project `id`, no central
  `~/.uedcli/projects/<id>/` state, no session store** (2026-07-05 in-tree-state / git-trunk / no-id
  decisions — `direction.md`); (2) **`project init/ls/rm` reduce to `project show`** (name→id
  registry + uuid minting are gone); (3) the **project-layout reorg** — free `uedcli.toml` at the repo
  root + in-repo gitignored `.uedcli/` for throwaway state + free relative tracked dirs — now BUILT
  and closed out (2026-07-18; `done.md` tail): decisions.md 2026-07-17 20:58 UTC (no scaffold verb —
  `project` stays `project show` only; tool-install assets go package-relative, and how they ship
  under pipx/Nuitka belongs to THIS item's re-spec). Re-spec against current `direction.md` +
  `architecture.md` before planning.

> **Unified asset catalog** — PLANNED + reviewed 2026-07-25, moved to `to-build.md`
> (plan `../plans/2026-07-25-unified-asset-catalog-plan.md`).

- [ ] `p2` `[plan]` **Adopt `EXEC <file>` batch driving for write-only editor sequences.** Spike
  PROVEN (`spikes/2026-07-18-exec-file-console-batch/results.md`, 8/8 probes live-confirmed;
  regression `test_driver_integration.py::test_exec_file_runs_script_and_continues_past_errors`;
  facts in `unrealed/commands.md` "`EXEC <file>`" + `quirks.md`): the console `EXEC Z:\work\<file>`
  verb runs a command script — in order, LF or CRLF, continue-on-error, nested OK, **executes
  THROUGH the GC `xmessage` dialog** that stalls typed commands, ~6× less drive overhead (6 cmds:
  7.05s typed vs 1.20s scripted). No open design question — the adoption shape is fixed by the
  spike's "Adoption implications": batch the **write-only** materialize runs (`OBJ LOAD`s → import →
  `MAP REBUILD` → `LIGHT APPLY` → `MAP SAVE`) into one `EXEC` submission with a **completion-marker
  last line** (a final `MAP EXPORT FILE=Z:\work\<uuid>-done.t3d`, host polls for it); crash detection
  stays liveness-based; **read-back steps** (`EDIT COPY`, export-and-parse) keep per-command
  round-trips. **What the plan must sequence/scope:** which `driver.py`/`writes.py`/`materialize.py`
  seams batch first (the contiguous write-only spans), the marker-poll + liveness-during-poll loop,
  and per-`EXEC` error/GPF handling (no per-command feedback). **Composes with — does not block, and
  is not blocked by — the warm-editor spec** (`specs/2026-07-18-warm-editor-materialize.md` §10): a
  per-build win on BOTH warm and ephemeral paths; the completion poll is `wine_ctl`-based so it still
  refreshes the §4.5 idle marker. Andrzej-initiated. (Triaged from inbox 2026-07-19.)
