# Corpus brush-idiom study — grounding the construction craft in real levels

**Status:** spec (ephemeral — fold findings into `leveldesign/general/*` + the harness/dataset into
`spikes/` on completion; delete this spec after). **Both cold-review gates passed (2026-07-24);
findings folded** — §2/§3/§7/§8/§9 were revised (classifier-first, three-way reproducibility split,
`level import` demoted to a convenience, extrude-generator prerequisite, behavioral success eval).
A few review-driven changes need Andrzej's yes before planning — see the chat handoff / §7 gap 6, §8.
**Decisions ledger:** [`decisions.md` 2026-07-24 19:49 UTC](../decisions.md) (D1–D7 are Andrzej's,
from the speccing Q&A) + the 2026-07-24 review-refinements addendum.
**Board item:** [`to-plan.md`](../board/to-plan.md) — "Corpus brush-idiom study" (references this spec).
**Key dependency (de-risked, no longer a hard block):** offline `.dx`→T3D import (`level import` /
[`specs/2026-07-24-level-import.md`](2026-07-24-level-import.md)) — unbuilt; the pilot uses the proven
`MAP EXPORT`→trunk route instead. See §7.1.
**Related (complementary, NOT duplicative):**
[`specs/2026-07-19-leveldesign-docs-skills.md`](2026-07-19-leveldesign-docs-skills.md) part (B) is a
MAP-EXPORT map-geometry corpus for **human-scale (dimension) measurement** — the dimensions this spec
*excludes* (§1). Different axis, same raw material: the two should **share one extraction harness**
(brush geometry out of the real maps), splitting only at what they measure. Coordinate, don't fork.

---

## 1. What this is, and the one thing it extracts

**Goal.** Distill a set of **level-construction best practices** from the real shipped Deus Ex (and,
as a control, Unreal 1 / UT99) levels, expressed so an LLM driving `uedctl` builds geometry the way
those levels were actually built — and, critically, does **not** overbuild (no 20,000-vertex brush).

**Scope — deliberately narrow (Decision D1).** The corpus's *unique* value is the knowledge an LLM
neither already knows nor can derive from first principles: **the brush-construction idiom
vocabulary**, and only that. Three parts:

1. **Shape alphabet** — the small set of brush primitives real geometry is actually made of, and how
   often each appears.
2. **Composition grammar** — how those primitives assemble into features (subtract-then-detail; how
   arches, stairs, curves, tubes are built from primitives; sheet usage for grates/glass/water;
   semisolid-vs-solid choices; brush/CSG ordering).
3. **Complexity / BSP-safety budget** — how simple real brushwork stays, and the discipline that
   keeps BSP from tearing. Per-brush poly/vertex count is only a *supporting* stat here: BSP tearing
   is a **whole-map compile** property, so the load-bearing, extractable signals are (i) the compiled
   world **node:poly ratio** (target ~2:1 per `geometry-and-bsp.md`; the world `UModel` body is
   decoded by `native/umodel.parse_model_body`) and (ii) the **on-grid fraction** of brush vertices
   (are FPoly coords on the power-of-two grid — directly readable). These are the one *number*
   family in scope: complexity/safety ceilings, **not** dimensions. **Framing rule:** a ceiling
   derived from shipped (good) maps is *descriptive* ("real brushes sit under X"), never a *validated
   safe bound* against the LLM's generative failure mode — state it as the former.

**Explicitly OUT of scope, and why:**

- **Dimensions / spacing** (corridor widths, ceiling heights, pathnode spacing). Derivable from the
  already-decoded DX player cylinder (40×95, `MaxStepHeight` 25, `JumpZ` 300 — see
  `leveldesign/deusex/human-scale.md`) plus `16 uu = 1 ft`. *Legal* clearance is first-principles;
  *idiomatic* feel-spacing is exactly the "measurements" Andrzej does not want.
- **Lighting distributions / mood.** The felt/atmosphere layer; an LLM already has it, and it is not
  construction.
- **Design philosophy** (multi-path, problems-not-puzzles, environmental storytelling). The most
  written-about design canon there is — an LLM has absorbed it as prose. Re-deriving it from the
  corpus is low marginal value. (Nuance that *justifies* the narrowing rather than contradicting it:
  knowing the philosophy as prose does not constrain geometry at build time — the LLM can recite
  "DX loves vent alt-paths" and still build the vent as a gnarly 400-vertex tube. Construction
  idioms are the thing that **operationalizes** everything it already knows.)

## 2. Method — a scripted classifier first, wireframes for the grammar

**Where the risk actually lives (revised after cold review).** The spine is not the vision pass — it
is the **scripted geometry classifier + brush→generator reverse-mapper**. The wireframe is the right
modality for *reading composition*, but it is the more-blocked, later pass; the scripted classifier
is nearly dependency-free and every headline number rests on it. So the delivery order is
**quantitative first, wireframes second** — even though wireframe is the correct modality for the
composition grammar. (The earlier "wireframe-primary" title oversold vision.)

**Why not screenshots.** For *construction*, a textured screenshot **hides** the answer — textures
paper over where one brush ends and the next begins. The wireframe is the skeleton, and the skeleton
*is* the construction knowledge. `actor preview` renders it CSG-colored (added blue / subtracted gold
/ semisolid coral / nonsolid green / mover magenta), `--view top`/`iso` + `--layout quad`. **Verified
safe on real maps:** `preview.py` draws each brush's authored polys directly (`enumerate(actor.brush.
polys)`), it does **not** invoke the native CSG core — so scaled and concave brushes (which the native
core rejects/mis-fills) render fine here. A lit screenshot (`level preview --game`) is occasional
ground-truth only.

**The actionable bridge — generator reverse-mapping (scoped honestly).** For each real brush, recover
what would (re)produce it. Recoverability is uneven, so the promise is tiered:

- **Robust (per brush actor):** CSG **op**, **solidity**, **shape class**, and — because each CSG op
  leaves its own brush actor in order — the **build order / composition grammar** (subtract-then-add,
  how features assemble). These survive regardless of param precision.
- **Best-effort:** exact **params**. Axis-aligned boxes recover exactly; prisms/cones (facet count,
  radius, angle-offset) recover approximately; vertex-edited-after-generation brushes not at all.

So the output is *"here are the ~N brush idioms that build most DX geometry — each with its op/shape/
order (robust) and its `brush build` params (exact for boxes, approximate for prisms)."* State the
exact-param limit; do not claim a unique generator invocation for every brush.

**The three-way reproducibility split (NOT one "freeform" bucket).** The single most actionable
finding — and a correctness trap if collapsed. `brush build` exposes only a curated **subset** of
UnrealEd's builders, and has **no arbitrary-polygon extrude/prism** generator at all (see §7 gap 6) —
yet the 2D-shape→extrude workflow is *the* canonical UE1 brush method, so many real brushes use it.
Classify every real brush into exactly one of:

- **(a) reproducible by an existing `uedctl` generator** (`cube/cylinder/cone/sheet/staircase/spiral`).
- **(b) reproducible only by a builder `uedctl` lacks** — hollow-cube, hollow/tube cylinder, curved
  stair, and above all **arbitrary-polygon extrude**. This bucket is *capability-gap evidence*, the
  highest-value output: "DX leans heavily on extrude → build the verb." Route it to `inbox.md`.
- **(c) genuinely freehand / vertex-edited** — real non-generatable geometry.

"Freeform frequency" as a single number is **forbidden** — it would conflate (b), a uedctl tooling
gap, with (c), a craft fact, and inflate both. Report the three separately. Bias classification toward
(c) only when params truly don't reproduce within tolerance; prefer tagging (b) when a known missing
builder would.

**Two passes.**

- **Quantitative (scripted, no vision) — the primary deliverable.** Parse each map's brushes →
  per-brush shape class, poly/vertex counts, CSG op, solidity flags, on-grid fraction, the (a)/(b)/(c)
  reproducibility class, and best-effort generator params; plus the whole-map node:poly ratio. This
  builds on the existing `classify_brush()` (`preview.py:273`, today CSG-op-for-coloring only) — the
  *shape* classifier is the new part.
- **Qualitative (vision, on wireframes) — secondary.** Read CSG-colored per-feature wireframes for the
  composition grammar counts can't express (how arches/stairs/curves assemble, sheet tricks,
  detail-with-a-handful-of-brushes).

**General-vs-DX by differential (Decision D4).** Run the same extraction over the UE1 control. Brush
construction is mostly engine-general, so the control's role is narrow: **confirm** an idiom is
general (present in both) and **isolate** the thin DX-specific layer. **Weight Unreal Gold
single-player as the primary control** — it is the true construction analogue; **UT99 is arena
(deathmatch)** and its idioms (big open subtracts, different sheet/zone usage, sparse detailing)
differ for *genre*, not *engine*, reasons. Use UT99 sparingly and **flag the genre-vs-engine
confound** whenever an idiom appears in DX + UT99 but not Unreal SP — do not launder arena idioms into
`leveldesign/general/`. General findings land in `leveldesign/general/`; DX-only in `leveldesign/deusex/`.

## 3. Deliverables

**The pilot and the scaled run deliver different things — this resolves the §3-vs-§4 tension.** The
pilot validates *method*; only the scaled run earns durable KB numbers.

**Pilot deliverables:**

1. **Validated extraction harness** — committed as durable spike evidence under `dev/docs/spikes/<slug>/`
   (per `CLAUDE.md`: harness code lives beside the spike markdown, never in `_scratch/`). Includes the
   shape classifier + reverse-mapper, and — as its **first, dependency-free acceptance gate** — a
   **self-consistency round-trip**: feed uedctl's *own* generators (`brush build cube/cylinder/…`) →
   emit polys → classify → recover params → compare to the known input. A classifier bug otherwise
   fakes every headline number, so this gate precedes any corpus claim (§8).
2. **Method write-up + a small pilot dataset** (4 DX maps + control) — per-brush JSON (shape class,
   counts, CSG op, solidity, on-grid, the (a)/(b)/(c) reproducibility class, best-effort params) +
   the (b)-bucket missing-builder evidence routed to `inbox.md`. Throwaway wireframe PNGs stay in
   `_scratch/`. **No durable craft-doc numbers yet.**

**Scaled-run deliverables (gated on the pilot proving the method):**

3. **Revisions to the existing craft KB** (Decision D3) — **ground the docs that already exist**, do
   not author a parallel one. Target files: `leveldesign/general/brush-shapes.md`,
   `leveldesign/general/geometry-and-bsp.md`, and the composition section of
   `leveldesign/general/design-craft.md`; the thin DX layer into `leveldesign/deusex/`. Each grounded
   claim carries the `📊` marker (§6) and cites the dataset spike. `human-scale.md`, `lighting.md`,
   `design-philosophy.md` are left as-is (out of scope). **Doc-target split:** the raw corpus
   *evidence* (tables, N, distributions) belongs **dev-side** under `dev/docs/unrealed/leveldesign/kb/`
   (or the spike); the **curated user docs** (`docs/leveldesign/`) get only the distilled prose + a
   citation — so evidence-carrying detail doesn't bloat the user-facing craft guides.

4. **Behavioral acceptance eval** (the study's real done-condition — see §9) — proof the idioms
   change build behavior, not just that numbers were emitted.

**Independent of both:** per-game install scripts + gitignored game dir (Decision D4) — see §5.

## 4. Corpus & pilot scope (Decision D5)

**Corpus available locally:** all 120 retail DX `.dx` maps (`/DX/Maps/`), plus DX mod campaigns
(2027, IWR, TNM2). **UE1 control is NOT local** and is sourced free (§5).

**First pass is a pilot** — validate the whole pipeline end-to-end on a few archetype areas before
any scaling:

- **DX archetypes:** `01_NYC_UNATCOHQ` (interior base/office), `06_HongKong_WanChai_Street`
  (dense urban + vertical), `04_NYC_NSFHQ` (industrial / multi-path), `11_Paris_Cathedral`
  (monumental vertical).
- **UE1 control:** a handful of Unreal Gold maps + a couple of UT99 maps (picked for construction
  variety, not archetype-match — the differential is about technique, not what an office looks like).

Scaling past the pilot (more maps, full aggregate distributions) is a follow-up, gated on the pilot
proving the harness and the reverse-mapping are sound.

## 5. Game-install infrastructure (Decision D4)

Andrzej: reproducible **per-game setup scripts**, one per game, each installing its game into a
**gitignored** dir in the repo — "ideally a few scripts, each setting up its own game for dev
purposes."

- **Install root:** `Tools/uedctl/dev/games/` (beside the existing `dev/scripts/`), with a committed
  `.gitkeep`; the installed game trees themselves are gitignored.
- **Source (legitimate, free):** Epic has officially sanctioned free preservation of **Unreal Gold**
  and **UT99 GOTY** on the Internet Archive via the OldUnreal non-profit (with Epic's permission).
  Scripts pull from archive.org / the OldUnreal installers. *Safety note for the script:* avoid the
  archive.org "Reviews"-section links (flagged phishing); use the item files / OldUnreal installer
  directly.
- **Scripts:** `install-unreal.sh`, `install-ut99.sh` (and document the existing DX install as the
  same pattern). Each is idempotent, writes only under `dev/games/<game>/`, and verifies the maps
  landed.
- These UE1 maps become the control corpus's substrate; `uedctl.toml`/`~/.uedctl/config.toml` point a
  `game` at them for import + preview.

## 6. Confidence marker (Decision D7)

The KB already marks `✅` (live-verified against binary/editor), `🔬` (live-probed), and `📖`
(community-tutorial lore). Add **`📊` = measured-from-corpus**, used **narrowly** for the
complexity/BSP-budget + reproducibility facts (node:poly ratio, on-grid fraction, per-brush count
ceilings, shape-frequency, the (a)/(b)/(c) split shares) — each `📊` claim carries its **N (map count)
and range/median**, so a figure from 4 pilot maps never masquerades as ground truth (which is why
durable-doc grounding waits for the scaled run — §3). `📊` is **not** used for dimensions (out of
scope), nor as a *safe bound* — a corpus ceiling is descriptive ("real brushes sit under X"), not a
validated limit (§1.3). Shape/composition prose stays qualitative unless a specific count backs it.

## 7. uedctl capability gaps this surfaces

The study both **depends on** and **prototypes** uedctl capabilities. Flagged to the board (§8):

1. **Offline `.dx`→T3D import (`level import`) — LATER CONVENIENCE, not a hard blocker (revised).**
   Spec'd but unbuilt (`specs/2026-07-24-level-import.md`; no `uedctl/mapimport.py`), and itself gated
   on an actor-order spike — a big, still-moving piece. The pilot does **not** wait on it: the
   **editor `MAP EXPORT` → T3D route is already proven** — it is `level import`'s *own* test oracle
   (`store_export.export_dx_level`) and the sister spec `2026-07-19` (Half B2) already budgets a
   one-time `MAP EXPORT` of `DX/Maps/*.dx` into a trunk corpus. So the interim route **is** the
   pilot's route now; `level import` later just removes the editor round-trip. (For pure brush
   geometry, the offline `native/umodel` + T3D parsers may even read the `.dx` directly — to confirm
   during the harness build.)
2. **Brush shape classification (`brush identify` / `classify`) — NEW; builds on existing code.**
   Given a brush's polys/verts, name its shape against the generator vocabulary (`cube`/`cylinder`/
   `cone`/`sheet`/`staircase`/`spiral`) or route it to bucket (b)/(c) (§2). `classify_brush()`
   (`preview.py:273`) already classifies CSG-op-for-coloring — the **shape** identity is the new part,
   layered on it (not a from-scratch prototype). `brush poly/vertex list` give raw geometry, not a
   shape.
3. **Brush→generator reverse-mapping — NEW (the deliverable's spine).** Emit the `brush build
   <shape> --params…` that reproduces a given brush (exact for boxes, approximate for prisms/cones —
   §2), or route to bucket (b)/(c). No verb today; prototyped in the harness; a strong candidate for a
   `uedctl` verb (`brush identify --as-generator`).
4. **Spatial subset selection in `actor find` — `--within-bbox` now BUILT.** Carving "a region" out of
   a big map for per-feature wireframes is `actor find --within-bbox X0,Y0,Z0,X1,Y1,Z1 | actor preview
   -` — **built + tested 2026-07-24** (full containment; `decisions.md` 2026-07-24 21:44 UTC), the
   `--within-bbox` slice of [`specs/2026-07-24-find-spatial.md`](2026-07-24-find-spatial.md). This
   **replaces** the abandoned auto-clustering approach (global AABB connected-components collapsed a
   subtractive DX interior to one blob — negative result in
   [`spikes/2026-07-24-corpus-brush-idioms/`](../spikes/2026-07-24-corpus-brush-idioms/)). The looser
   `--overlapping-bbox` (grab straddling brushes) is a deferred `to-spec.md` item; `--near`/
   `--overlapping <actor>`/`--within-brush` remain parked. Region-select is no longer a gap.
5. **Brush complexity stats aggregation — minor.** Per-map poly/vertex + node:poly + on-grid stats.
   Scriptable from `brush poly list`/`model.py`/`native.umodel`; a dedicated `brush stats` verb is a
   nice-to-have, not a blocker.
6. **Arbitrary-polygon extrude / prism generator — NEW; likely a PREREQUISITE for an honest headline.**
   `brush build` has six shapes and **no 2D-shape→extrude** — the canonical UE1 method. Without it,
   every extruded profile falls into bucket (b), and the "reproducible only if we add an extrude verb"
   share is large. The study *quantifies the case* for this verb (that's a real output); but if the
   (b) share is dominated by extrudes, adding the generator early is what makes bucket (a) — and thus
   the actionable reverse-mapping — cover most real geometry. Flag as the top capability gap this
   study surfaces.

## 8. Board & sequencing

- **This spec's referencing item →** `to-plan.md` ("Corpus brush-idiom study"). (Per the convention
  added to `board/README.md`: *every new spec carries a board item that references it.*)
- **Gaps 2, 3 (+ 5 minor) →** `inbox.md` as raw capture. **Gap 6 (`brush build extrude`) →**
  `to-spec.md` (triaged forward — it needs its own spec). Gap 1 (`level import`) and gap 4
  (`find-spatial`) stay tracked by their own existing specs.
- **Shared-harness ownership (resolves the fork risk).** The `MAP EXPORT`→trunk brush-extraction
  harness is shared with `2026-07-19` (Half B2), and both are unbuilt. **This spec owns building the
  shared harness** (brush geometry out of the real maps); the `2026-07-19` human-scale pass **consumes**
  it and adds only its dimension measures. Record this so two divergent harnesses aren't built in
  parallel; if sequencing conflicts, spin a joint `[spike]`.
- **Sequencing (revised — de-risked, no hard block on `level import`):**
  1. **Classifier self-consistency gate FIRST — dependency-free.** Build the shape classifier +
     reverse-mapper and validate them round-trip against uedctl's *own* generators (§3.1). Needs no
     import, no container, no find-spatial, no game installs. This de-risks the spine before any
     corpus claim.
  2. **Game-install scripts + UE1 control** — independent, land in parallel.
  3. **Pilot extraction** via the proven `MAP EXPORT`→trunk route (§7.1) over the 4 DX maps + control;
     quantitative pass primary, hand-selected wireframes secondary (§7.4). Emit the pilot dataset +
     the (b)-bucket missing-builder evidence.
  4. **Method-validation checkpoint** — does the classifier hold on real geometry? Is the (b) share
     dominated by extrudes (→ prioritize gap 6)?
  5. **Only then**, gated on the pilot: scaled run → durable craft-doc grounding + the behavioral
     acceptance eval (§9).

## 9. Success criterion, open questions & risks

**Success criterion (the real done-condition).** The whole justification (§1) is that idioms
*operationalize* what the LLM already knows and *prevent overbuilding*. That is testable, and nothing
short of it proves value: define a small **behavioral acceptance eval** — a handful of build tasks
(build an arch, a stair, a detailed room, a tube) done by an LLM **with vs. without** the grounded
idioms, scored on brush count, bucket-(c) freehand rate, and on-grid discipline against the corpus
distributions. A pilot that emits numbers but doesn't move build behavior has **not** succeeded.

**Open questions / risks:**

- **Build-order fidelity.** Composition grammar depends on **CSG/brush order** (the add/subtract
  sequence). The `MAP EXPORT`/`level import` export-table order must be **proven** to match the map's
  true build order before drawing composition conclusions (the `level import` spec flags the same
  order question).
- **Extraction reads geometry, not a rebuild — so the native-core caveats don't bite it.** The
  classifier reads authored polys; `actor preview` also draws polys directly (§2, verified) — so
  scaled/concave brushes are fine for *extraction and wireframing*. The native caveats (concave
  mis-fill, scaled-brush reject — `board/inbox.md`) only affect `--native` *rebuild* preview, which
  this study doesn't rely on.
- **The (b)/(c) boundary is the correctness-critical call.** A too-eager classifier that forces a
  bucket-(b) missing-builder brush (esp. an extrude) into (a), or a genuine (c) into (b), corrupts the
  headline. Bias: tag (a) only on a real param match; prefer (b) when a *known* missing builder
  explains the shape; reserve (c) for geometry no builder produces. The self-consistency gate (§3.1)
  checks (a)-precision; (b)/(c) separation needs spot-checks against hand-labeled brushes.
