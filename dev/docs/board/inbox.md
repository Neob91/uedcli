# Inbox

Raw, **un-triaged** capture. Anything noticed — a feature idea, a capability gap, a bug, a chore —
lands here first, with no obligation to know its stage yet. This is the *pre-pipeline* pool, not a
stage (so no `to-` prefix). See [`README.md`](README.md).

**Triage** routes each item to where its next action lives:
- `p1` `[OWNER — confirm]` **Four `actor preview --faces` rulings need a durable `direction/` home
  before their spec is deleted.** `specs/2026-07-26-actor-preview-textured-faces.md` is ephemeral and
  is deleted on build; `CLAUDE.md` requires a decision you made to land in `direction/` first. These
  four are product policy, not implementation detail. Proposed text (verbatim, awaiting a yes —
  suggested home `direction/trunk-and-editor.md`, since it is about what the preview tiers show):

  > **The offline preview tiers.** `actor preview` renders brush volumes as authored, before CSG.
  > Its `--faces` modes are `wire` (outlines, the default, needing no game content at all), `flat`
  > (solid CSG-coloured fills) and `textured` (each face painted with its real texture through its
  > authored UV frame). **A subtract brush shows only its far faces**, because a subtraction's
  > polys are not drawn from outside in the editor or the game. **`flat` and `textured` load the
  > game's class hierarchy** to tell a mover from a real subtraction, and so — unlike `wire` — need
  > the game content available. **A texture the render actually needs and cannot read is a refusal,
  > never a placeholder**; a scene that references no texture needs no texture source. **No cost
  > ceiling is imposed** on preview size or layout.

  If you would rather these stay agent-side, say so and they go to `rationale/` instead — but they
  cannot stay only in an ephemeral spec. *(2026-07-26.)*
- `p1` `[question]` **→ whoever is driving the native-texture-formats plan: are PE1/PE2 still open? The
  escalation block reads stale against your own later commits.** Asked by a concurrent session
  2026-07-26; I did **not** edit your plan, because two sessions resolving one escalation is how a gate
  gets corrupted. Evidence, so you can just confirm or correct:

  - **PE2 (BC1 oracle circularity) appears CLOSED.** Your `49e937b` carries an explicit
    **OWNER RULING 2026-07-26**: the fixture payload is "OUR OWN ARTWORK, compressed by a THIRD-PARTY
    encoder", with the reasoning that "the independence D7's oracle needs comes from the **encoder**
    being outside our control, not from the **artwork** being someone else's", plus a requirement that
    the encoder be "named and pinned in the fixture script, with its version recorded, so the oracle's
    independence is auditable". That answers PE2's circularity objection directly — but the escalation
    block still lists PE2 as blocking the build.
  - **PE1 (`repo_texture_root()`) appears PARTLY overtaken, and is still actionable.** The plan now says
    "**The `LUM_CoreTex.utx` 30 → 0 count is now INTEGRATION-tier**" — which *is* a disposition, though
    it is the one round 2 objected to (the plan elsewhere calls that criterion "the offline criterion for
    the bug that motivates the whole build — it must not be marked integration"). Either way the
    mechanical half is unresolved: **`repo_texture_root` still appears 10× in the plan and does NOT exist
    in `uedcli/tests/conftest.py`** (verified 2026-07-26), so a builder following S1 or S6 still calls a
    function that is not there.

  **Ask:** if both are closed, delete or rewrite the "Two items block the build and are escalated" block
  so `to-build.md` stops disagreeing with it; if PE1's integration-tier move is the accepted answer, say
  so there and purge the 10 dead `repo_texture_root` references. Also worth a line either way: that block
  is what a reader checks to decide whether this is buildable, and right now it says "blocked" while the
  commits below it say otherwise.

  *(Context from my side: `745d0fa` — which your S2c cites — added mesh skins as a third consumer of this
  decoder, after surfaces and `actor preview --faces textured`. The spec amendment that introduced it has
  itself not been through a spec round.)*
- `p2` `[debug]` **`level preview --native` fills polygons by triangle FAN, which bleeds outside a
  concave face.** `render.rs:196-206` triangulates each poly as `(v0, vk, vk+1)`; that is only valid
  for a convex polygon, and for a concave one it paints area outside the boundary.
  `architecture.md` records **0.1–0.6 % of faces in real exported maps are concave** (spike
  `concave-faces/`, live 2026-07-23), which is why `preview.py` already carries
  `_poly_is_convex_2d` rather than assuming convexity.
  **Scope caveat from the reviewer who found it:** `render.rs` rasterizes post-CSG **BSP node**
  polys, which the build produces convex, so the authored-face measurement reaches it only on the
  **mover** path (movers are not carved into the world model). Narrower than it first looks, but
  real. Surfaced while speccing `actor preview --faces`, whose scanline fill handles concave faces
  correctly — so the two renderers deliberately disagree here until this is fixed. *(2026-07-26.)*
- `p1` `[OWNER — decide]` **Asset-catalog spec: re-gate round 1 found NEW STRUCTURAL findings. Parked
  again. Recommend SPLITTING the spec rather than a third fix-and-regate.** 3 cold Opus reviewers
  2026-07-26 (second round of 3), ~65 findings, all three verdicts "not ready to build on" — after the
  ~45 findings of the first round had all been folded. Convergence was again high, and several of the new
  defects were **introduced by the previous round's own fixes** (`CLAUDE.md` "Review gates" predicts
  exactly this). Per the structural rule the work does NOT pass the gate and is not merged. **`CLAUDE.md`
  also says this pattern does not converge and another round would not land it**, so the recommendation
  below is to change the artifact's shape, not to fix again.

  **A. Structural — conflicts with the owner's own protected doc.** §3c hashes procedural textures over
  properties **resolved against the class defaults**. `direction/asset-catalog.md`'s *Rejected* list kills
  precisely that: "**Content-hashing everything** — a class fingerprint over default properties is
  brittle", reason given as "any game patch would orphan the curated description". A patch to `Fire.u`'s
  `FireTexture` defaults therefore re-keys every procedural shard, and §3b's protection (owner-approved
  migration only) does **not** engage because no uedcli code changed. The 2026-07-26 parameter-hash ruling
  and this Rejected bullet cannot both stand — the owner must reconcile them. Note also there is **no
  `[OWNER — confirm]` item** parked for the parameter hash at all, so it currently has no durable home
  and the spec contradicts the protected doc as written.

  **B. Structural — two sections are sized by measurements that do not hold on the composed search
  path.** Re-measured against the real configured path (`~/.uedcli/config.toml` → `.../DX/{System,
  Textures,Sounds,Music}`, 119 package stems):
  - **Sound.** §4a claims 10,826 Sound exports of which ~10,200 are `DeusExConAudio*` VO. Actual on the
    path: **747** Sound exports, **0** `DeusExConAudio*` — those packages exist only under `System.bak/`
    (18) and `SystemOk/` (18). The 10,826 figure reproduces only by walking non-path directories (a
    whole-tree walk gives 31,059). So the new per-substrate config key, `--include-vo`, and the
    excluded-count reporting are all bought to prevent a 10k-line dump **that does not occur**. Worse,
    the VO that IS on the path — `LUM_ConversationsAudioMission20` (109 exports) and `TNM` (84) — is
    **not matched** by a `DeusExConAudio*` pattern, so the project's own conversation audio would leak
    into `sound list` while the machinery reports "excluded: 0". §4a's "expected corpus ≈ 550" measures
    **747**. Plan S4's hot-path cost criterion and §8's central worked example both rest on the bad
    number.
  - **Procedural textures.** §3c's "208 + 42 + 14 + 8 + 50 + 4 = 326" reproduces only by walking
    `System.bak/`, `TNM2/`, `2027/`, `IWR/` and `Maps/`. On the composed path: **40** `FireTexture`,
    **8** `WetTexture`, **1** `WaveTexture`, **0** `IceTexture`, **0** `ScriptedTexture` = **49**. So the
    entire `ScriptedTexture` apparatus (its own `preview_state`, stderr reason, batch-vs-single exit-2
    rule, name-keyed identity, plan work) is sized by "50 of 326" of which **zero are reachable**.
  - Also: the unnamed sixth addend is **`TNMScriptedTexture`** — a *mod-defined* `ScriptedTexture`
    subclass, 4 exports. That proves both that §3c's per-class table must match **by descent, not exact
    class name**, and that out-of-table procedural classes already exist on this install. §3c gives no
    rule for one, so it falls through to a pixel hash over **zero pixels** and every such texture
    collapses to a single identity — the exact failure §3c refuses for `ScriptedTexture`.

  **C. Owner carve-out taken silently** (all three reviewers). §3b's "index-building writes the preview
  PNG it has in hand" overrides `direction/asset-catalog.md`'s "**`preview` … is the only producer** …
  no exploratory command can ever trigger a long render" and owner decision 7 — with no parked item.
  Measured cost of the first cold `texture list`: ~2,700 PNGs (~77-146 MB) written by a read-only
  exploratory verb. **This one is mine and I withdraw it** — the direction doc wins; the fix is simply
  not to write PNGs while indexing.

  **D. Still-standing escalation, unresolved across two rounds.** "No re-key path across a pixel edit":
  the project edits its own `LUM_CoreTex.utx`, so its own texture edits retire the identity and
  `classify prune --outdated` deletes descriptions that are still accurate. There is no verb and no
  `classify set --identity` to carry a classification forward. Escalated by name after round 1, folded
  nowhere.

  **E. Graded alpha is not covered by `masked`.** A BC2/BC3 texture with 8-bit *graded* alpha (10
  measured on this substrate; pervasive on UT, in scope per `direction/scope.md`) is one identity with its
  opaque twin, one opaque preview, one classification, and **no fact distinguishes them** —
  `bAlphaTexture` is currently left as "decide during the build". Identity is frozen, so this is cheap now
  and unfixable later.

  **RECOMMENDATION — split the spec.** All the churn is concentrated in the **texture** arm (frozen
  identity, procedural hashing, alpha, the preview/identity coupling) and in **audio** (whose corpus
  numbers must be re-measured on the composed path before any config surface is designed). The **class
  arm** is the part agents most lack, is nearly clean, and its remaining findings are ordinary fixes.
  Proposal: (1) split the class arm into its own spec and build it; (2) re-spec texture identity on its
  own, where the irreversible decisions get a dedicated gate; (3) re-measure the sound corpus on the
  composed path, then spec audio. `CLAUDE.md`: the answer to a non-converging gate is to give the work a
  fresh spec moment, not a third round. *(2026-07-26.)*
- `p1` `[OWNER — confirm]` **SIX further per-surface rulings made 2026-07-26, durably recorded here
  because they currently live only in the ephemeral spec.** Verbatim, awaiting a yes for
  `direction/conventions.md`:

  > **Texel density RESETS TO UNIT.** No `brush poly align` mode adopts a seed face's texel scale, so
  > `--fresh-frame` has one possible value and is deleted. Scoped by the two rulings below: it binds
  > **`run` alone**, because `wall`/`floor` take the projection's own `|proj|` density and `one-tile`
  > derives its density from the face.
  >
  > **Align modes are SUBCOMMANDS**, not a mutually-exclusive flag group: `brush poly align
  > wall|floor|run|one-tile`. The flags are disjoint per mode, so `-h` is accurate per mode and bad
  > combinations become argparse errors rather than runtime checks — the same shape as
  > `brush build <shape>`.
  >
  > **`wall` and `floor` are WORLD-SPACE aligned**, in orientation AND anchor: they adopt UnrealEd's
  > own `POLY TEXALIGN FLOOR`/`WALLX`/`WALLY` projection family (measured 2026-07-26), anchoring where
  > the surface plane crosses the projection axis rather than on any face. `floor` projects along Z;
  > `wall` along whichever of X/Y the face faces more. This makes alignment idempotent and independent
  > of which faces were selected. Its consequence is accepted: a face not square to its projection
  > axis is stretched, so density is `|proj|`, not 1.
  >
  > **`one-tile` is FIT TO THE POLY** — one tile of the texture spans the face, stretched
  > non-uniformly to fill, anchored at the face's minimum corner. Its density comes from the face, so
  > it is the one mode exempt from reset-to-unit. It takes the projection *directions*, normalised, so
  > a sign has a predictable up-vector.
  >
  > **`brush poly scale` is in scope** as the fourth canonical surface op — after reset-to-unit it is
  > the only general way to express a texel density.
  >
  > **`--fit-perimeter` fits whole TILES, not whole texels.** As shipped it rounds the total advance
  > to an integer texel, which on a 256-texel texture leaves the closing seam ~31 texels out; it must
  > round to a multiple of the texture's pixel size along the axis the advance lands in.

  Evidence: `spikes/2026-07-26-unrealed-texalign-semantics/`, `spikes/2026-07-26-poly-rotate-curved-track/`.
  Supersedes the two now-ruled `[OWNER — decide]` items below (orientation, anchor).

- `p1` `[OWNER — confirm]` **The per-surface verb split (`pan`/`rotate`/`align --run`).** Spec:
  `specs/2026-07-26-poly-surface-verbs.md` (revised after review round 1). Six rulings were made in
  session on 2026-07-26 and live only in that ephemeral spec until confirmed. Proposed addition to
  `direction/conventions.md` under "Verbs compose" (verbatim, awaiting a yes):

  > **A per-face verb prints per-face selectors.** The `brush poly` mutators (`set`, `pan`, `rotate`,
  > `align`) print the `BRUSH:idx` selectors they acted on, one per line — not the touched brush
  > names. A bare brush name means *all* of that brush's polys, so a per-face verb that printed one
  > would silently widen the set for the next verb in the pipe. Consequence, stated so it is not a
  > surprise: a poly verb chains into another poly verb, not into a whole-actor verb like
  > `brush scale`, which takes bare names.
  >
  > **Attributes and frames are different verbs.** `brush poly set` assigns stored per-face fields
  > (texture, flags). `pan`, `rotate` and `align` transform the texture FRAME. Pan is expressed in
  > integer texels and lives in the polygon `Pan`; a computed continuity offset lives in the float
  > `Origin`; the two never occupy the same field.

- `[resolved 2026-07-26]` **The `--run` seed had no source under "`--run` orders the chain itself".**
  Raised independently by all three round-1 spec reviewers. Resolved by the owner: the order faces are
  passed in has NO bearing on the result — a PRE-WALK derives the root too (the lower-poly-index end of
  an open run; the lowest index on a closed run), which is stronger than the reviewers' proposed
  "root = first input token". The pre-walk also detects branching. No `--seam` flag. Folded into
  `specs/2026-07-26-poly-surface-verbs.md` §2.3; nothing outstanding.

- `p2` `[debug]` **`level preview --native` checkerboards an unresolvable texture ref and warns —
  a `conventions.md`-Rejected warn-and-continue.** `preview_native._TextureTable` renders a
  checkerboard for any ref it cannot resolve and prints one stderr warning, then exits 0 with an
  image that looks like an answer. `direction/conventions.md` lists exactly that under **Rejected**
  ("a half-answer that looks like a full one is worse than a refusal; the note scrolls away").
  Surfaced while speccing `--faces textured`, which now **exits 2** on an unresolvable ref per that
  rule — so the two renderers are deliberately inconsistent until this one is brought in line.
  Changing an existing verb was out of scope for that spec; it is not out of scope forever.
  *(2026-07-26.)*
- `p1` `[OWNER — confirm]` **Does class curation get a general file-fact OVERRIDE field?**
  `direction/asset-catalog.md` says curation is "a description, plus **an override where the file fact is
  wrong**" — but its own *Rejected* list kills "a curated-vs-derived override model for `placeable`". The
  two cannot both hold, and the catalog spec's shard payload carries `tags`/`description`/`colors` with no
  general override, so as specced a wrong file-fact cannot be corrected at all. Raised independently by
  two of three gate reviewers 2026-07-26. Either the topic drops the override clause, or the spec gains a
  field — an implementer must not pick. (The §4b colours override is the one existing instance and stays
  either way.)
- `p3` `[chore]` **`class list --all` / `class show --all` are migration-error shims, which
  `conventions.md` forbids.** `cli.py:1418` and `:1443` define them as `argparse.SUPPRESS`'d flags whose
  only job is to `parser.error()` with a pointer to `--depth all` — the exact "a flag defined only to
  `parser.error(\"X was renamed to Y\")`" pattern the no-back-compat-cruft rule names. Pre-existing, not
  caused by the catalog work, but the catalog build is what next touches both verbs, so delete them then.
  Surfaced by a gate reviewer 2026-07-26 as adjacent-but-real. *(2026-07-26.)*
- `p1` `[OWNER — confirm]` **`conventions.md` needs a calibrated carve-out for the THIRD stdin
  convention.** Ruled 2026-07-26 ("it's fine") and written into the catalog spec's decision 8, but
  `direction/conventions.md` still says "Exactly TWO stdin conventions … never add a third", with a
  third listed under Rejected — so two protected docs contradict each other until this lands. Proposed
  addition (verbatim, awaiting a yes):

  > **Calibrated exception — `classify set -` reads JSONL.** The asset catalog's `classify set` accepts a
  > JSONL row set on stdin (`{ref, tags, description[, colors]}`), a THIRD `-` convention beside the
  > name list and the T3D snippet. It is approved because a classification write carries per-item
  > *fields*, which a bare name list cannot express, and because a per-ref process start (~0.3 s) would
  > make classifying a corpus turn-bound. The two-convention rule's actual requirement — that `-` means
  > exactly one thing *per verb* — still holds: within the catalog nouns `-` is a name list for
  > `show`/`preview`/`classify unset` and JSONL for `classify set`. No further convention is added
  > without the same explicit approval.

- `p2` `[OWNER — decide]` **`ScriptedTexture`'s identity is unresolved (50 of 326 procedural exports).**
  Falls out of the 2026-07-26 parameter-hash ruling (spec §3c): a procedural texture is keyed on the
  properties that make it distinct, but a `ScriptedTexture` is drawn by UnrealScript at runtime, so its
  appearance may not be a function of its stored properties at all. Its declared property set could be
  empty, which would collapse every `ScriptedTexture` in a package to ONE identity. Acceptable (they are
  canvases, arguably interchangeable) or does it need a different key? Flagged OPEN in the spec rather
  than picked silently. *(2026-07-26.)*
- `p1` `[OWNER — decide]` **Unified-asset-catalog spec: gate round 1 ran, found STRUCTURAL defects, work
  is PARKED.** 3 cold Opus reviewers, 2026-07-26, ~58 findings, all three verdicts "not ready to build
  on". Convergence was high (17+ findings hit independently by 2 or 3 reviewers), including all four
  defects in the same day's revision. Per `CLAUDE.md` "Review gates" a structural finding replaces the
  remaining round and does NOT pass the gate: the spec re-enters at round 1 after the rulings below.
  **Do not start the 13 slices.** Five decisions are the owner's:

  1. **Does texture identity cover the TRANSPARENCY MASK, and is the preview artifact addressed by the
     identity or its own digest?** (all 3 reviewers). §3b freezes identity as `sha256(w, h, RGB)`; §3a
     says the preview PNG is content-addressed by "the bare hex sha256 of its pixels" AND that "for
     textures the preview hash IS the identity — no second digest". Those cannot both hold, because the
     decode path already returns a mask (`utexture.TextureResolver.resolve_masked()` → `(w,h,rgb,mask)`)
     and the gated `specs/2026-07-25-native-texture-formats.md` §8-D pins the mask as derived from pixel
     data (P8 index-0, BC1 punch-through, BC2/BC3 block alpha; 10 stored BC3 textures measured). If the
     preview carries the mask, its digest ≠ identity and two textures with identical RGB + different
     masks **share one preview file** — an agent classifying a masked grille is handed the opaque twin's
     image, the misattribution decision 14 bans the contact sheet to prevent. If the preview drops the
     mask, every masked texture is shown OPAQUE — exactly the defect §4d was added to surface. Identity
     is frozen and is every shard's path, so this is not revisitable after shards exist.
  2. **Are procedural textures name-keyed?** (2 of 3; one called it structural). §4a deliberately widens
     enumeration to `Engine.Texture` descendants, and the sibling spec measured that EVERY
     `FireTexture`/`WetTexture`/`WaveTexture`/`IceTexture`/`ScriptedTexture` stores mips with
     `DataCount == 0` — 208+42+14+8+50+4 across the DX tree. No pixels ⇒ no pixel-hash key ⇒ §3a's
     "cannot be classified". So water and fire are enumerable, referenceable and **permanently
     unclassifiable**; `texture list --unclassified` never empties and `classify status` never reaches
     done. **`direction/asset-catalog.md` may already answer this**: "Identity: content hash where
     content exists, **name where it does not**" — a procedural texture has no content, so the owner's
     own rule arguably prescribes the name fallback the spec omits.
  3. **Is `classify set -`'s JSONL an approved THIRD stdin convention?** (all 3). `conventions.md` says
     "Exactly TWO stdin conventions … never add a third"; `direction/asset-catalog.md` blesses
     "`classify set -` reads JSONL". Two owner-protected docs conflict, and inside one noun `-` means a
     name list for `show`/`preview` and JSONL for `classify set`. Needs a carve-out in `conventions.md`
     or the feature dropped.
  4. **How are editor-icon sprites detected?** §6 marks them via an "icon **group**" pattern set, but
     measured against tracked `uned/UED22/Engine.u`: 28 of its 32 texture exports are **groupless** —
     `S_Weapon`, `S_Camera`, `S_ZoneInfo`, `S_Ambient`, … — and the only groups present are fonts;
     `Engine.ZoneInfo`'s `Texture` default is the 2-part `Texture'Engine.S_ZoneInfo'`. A group pattern
     matches NOTHING, so every sprite class would report `preview_state: ok` and `prewarm` would count
     hundreds of lightbulb glyphs as covered — inverting the honest-reporting §6 exists to guarantee.
     The only signal that exists is the `S_` NAME prefix, which `conventions.md` rejects for class
     questions and §0 forbids as inference. Needs a ruling or an explicit config of icon **refs**.
  5. **RULED 2026-07-26 — `asset-catalog/` approved.** `direction/projects-and-config.md` updated to
     state it (`Confirmed:` trailer). Note `config.project_catalog_dir()` still returns
     `texture-catalog`: that direction↔code gap is expected and is plan S1's job, NOT to be "fixed"
     early — LUM's existing `texture-catalog/` resolves under today's default, and decision 13 deletes
     the legacy catalog as part of the build.

  **Rulings 1-5 are all in as of 2026-07-26** (see the spec's §3b "ONLY PIXELS ARE HASHED", §3c,
  §6 thumbnails, decision 8, and this item). **What still blocks the gate is the remaining cluster
  below plus the ~45 non-structural findings.**

  Also escalated because it is authored-work-destroying and half design: **`classify set` has no defined
  behaviour over an existing shard** (replace / merge / refuse), against `direction/safety.md` "a
  destination that already exists is never written over silently"; **pixel-hash dedup defeats §3b's own
  conflict-free-merge premise** (two agents classifying two differently-NAMED refs with identical pixels
  write the SAME shard, second silently overwriting the first, while the write-once `ref` still names the
  first); and **no re-key path exists across a pixel edit**, so `classify prune --outdated` deletes
  descriptions that are still accurate — on a project that edits its own `LUM_CoreTex.utx`.

  The remaining ~45 findings need no ruling and are the agent's to fix once the above land. *(2026-07-26.)*
- `p1` `[OWNER — confirm]` **`level doctor`'s scope boundary — proposed `direction/trunk-and-editor.md`
  addition.** Ruled 2026-07-26 and already written into `docs/usage.md`, `architecture.md` and
  `cli.py`'s `help=`; needs a durable home in the owner's own tree. That topic already says the
  "is this trunk well-formed?" lint *"folds into `level doctor`"*, which is where the bound belongs.
  Proposed text (verbatim, awaiting a yes):

  > **`level doctor` is bounded by INTENT-INDEPENDENCE.** It reports only defects that are wrong
  > *regardless of what the author intended*: the math and geometry that breaks or burdens the BSP,
  > zoning of the same kind, and objectively-wrong footguns — an `Event` matching no `Tag` fires into
  > the void, a light buried in solid geometry lights nothing. It does **not** judge gameplay or style.
  > **Passage/occlusion checking is rejected, not deferred:** doctor can measure the free gap between
  > two brushes but cannot tell a deliberately sealed wall from an accidentally blocked doorway,
  > because the two are identical geometry and differ only in intent. Whether a space is comfortable,
  > whether a decoration is well seated, whether the level is detailed or good — all need eyes on
  > renders, from a human or an independent reviewing agent. A clean `doctor` report is not a quality
  > report, and no better heuristic changes that.

- `p2` `[implement]` **Two IN-SCOPE `doctor` checks are not implemented.** Both fall inside the
  intent-independence bound ruled 2026-07-26, and both were named by the owner as things doctor should
  catch:
  (a) **a light buried inside solid geometry** — it lights nothing; the DiveBar polish pass found
  **five of 40 lights** strictly inside solid brushes (two inside their own door mover, one in a
  structural column, two in a floor dais), whose visible symptom was pure-black doors and an unlit
  cellar, and point-in-brush-bbox over `Engine.Light` found all five in seconds
  (`spikes/levelbuild-friction/agent-reports.md`);
  (b) **an `Event` matching no actor's `Tag`** — this already EXISTS as `eventgraph.py`'s
  `dangling_event` (`eventgraph.py:223`, *"fires into the void"*) but is surfaced only by
  `event graph`, so a `doctor` run misses it. Decide whether doctor absorbs the eventgraph lint or
  calls it; `doctor.CATEGORIES` is currently `degenerate,watertight,convex,planar,solidity,csg_order,
  scale` with no reference-integrity category at all. *(2026-07-26.)*
- `p1` `[spec]` **`class list`/`--subclass-of` enumerates classes from packages with NO loadable v69
  stub, and two package views disagree.** Deliberately left out of the 2026-07-26 unified-asset-catalog
  spec revision (owner's call) — recorded here because it is real and the spec now says so in §14.
  The friction log calls it *"the worst-shaped defect I hit"*
  (`spikes/levelbuild-friction/agent-reports.md`, two independent entries):
  - `class list --flat --subclass-of DeusEx.DeusExDecoration` lists `Endemia.Ashtray`,
    `Endemia.GlassBottle`, `Endemia.WoodStool1`, `TNM.NapalmCanister` … interleaved with usable
    `DeusEx.*` classes, **unmarked**. Every `actor build | actor add` of one printed `added 1 actor(s)`
    and exited 0. The level then failed EVERY materialize with `level references v68 code package(s)
    with no v69 stub: Endemia`, i.e. the trunk was poisoned and the only clue was the package name in
    an error twenty minutes downstream.
  - The failure has an **opposite, worse shape under stderr suppression**: a previous session's helper
    redirected stderr, so ~15 props were a silent no-op — the bar shipped with no stools and no
    bottles and nobody noticed until a render.
  - **REFUTED, with the check recorded:** the log's "two views of one catalog disagree about whether
    `Endemia` exists" is **not** a defect. Measured 2026-07-26 in the LUM project: bare
    `class list --flat` returns **42** classes, because it is the documented depth-1 view of *the direct
    children of `Engine.Actor`* (`classindex.list_classes` docstring, `classindex.py:245-261`) — those
    42 happen to span 4 packages, so `cut -d. -f1 | sort -u` prints `DeusEx DXOgg Engine TNM`.
    `--depth all` returns **1,345** classes across **12** packages including **65** `Endemia.*`, and
    `--subclass-of DeusEx.DeusExDecoration` returns **52** `Endemia.*`. Same function, different depth,
    all as documented. The log's agent read a depth-1 category listing as a corpus listing.
  - **The real residue is a HINT, not a bug** (`p3` `[chore]`): bare `class list --flat` prints 42 bare
    class names with no count, header, or "these are categories — drill in with `--subclass-of`" note,
    so it is indistinguishable from a complete listing — which is precisely the misreading that
    produced the false conclusion above, in an agent that then acted on it.
  The log's suggested fixes, in its own order of value: (1) reject the class at `actor build` with the
  message materialize already produces; (2) mark or omit unstubbed packages in `class list`; (3) a
  `level doctor` check for "trunk references a package with no v69 stub", catchable offline in a second.
  The spec mentions stub/v68/v69 **zero times**. *(2026-07-26.)*
- `p1` `[OWNER — confirm]` **Texture GROUP is a first-class fact — proposed `direction/asset-catalog.md`
  addition.** Decided 2026-07-26 and already written into
  `specs/2026-07-25-unified-asset-catalog.md` §4c, but absent from the direction topic, so the
  decision has no durable home yet. Proposed text, to be appended to the **Identity: content hash
  where content exists, name where it does not** section (verbatim, awaiting a yes):

  > **A texture's GROUP is a stored fact, not just a ref component.** UE1 subdivides a package with an
  > optional Group, so a texture is addressed `Package.Name` or fully `Package.Group.Name`. Ref
  > assignment emits the 2-part form unless there is an intra-package name collision, which means the
  > group vanishes from the output for most textures — including `CoreTexMetal.LadrBrwnMetal`, whose
  > group is the reserved `Ladder`. In Deus Ex the group is what decides whether a surface is
  > climbable, so the catalog must be able to answer "which textures are ladders" directly: the group
  > is stored as a per-texture fact, printed by `show`, and filterable with `--group` on
  > `list`/`search`. It is a fact read from the package, never a classification, so it is not
  > LLM-overridable — and it is **not** part identity, since identical pixels in two groups are
  > deliberately one classifiable thing.

- `p1` `[OWNER — confirm]` **Texture `masked` is a stored fact — proposed `direction/asset-catalog.md`
  addition.** Decided 2026-07-26, written into `specs/2026-07-25-unified-asset-catalog.md` §4d and
  `unrealed/quirks.md`, but not yet in the direction topic. Proposed text (verbatim, awaiting a yes):

  > **`masked` is a texture fact, read from the package.** `Masked` is a property of the *texture
  > object*, set by the `Masked` checkbox when the texture is imported into UnrealEd; UE1 then ORs a
  > texture's own flags into every surface it is applied to. So a masked texture punches its
  > palette-index-0 pixels into see-through holes on any surface, with no surface polyflag set — which
  > makes it invisible to any audit of surface flags, and a hole into unbuilt space wherever it lands
  > on a solid face. The catalog therefore stores `masked` as a per-texture fact **read from the
  > export's stored flag, never inferred** from the palette or from derived colours: inference is
  > forbidden by the governing principle, and a texture may carry an index-0 colour without being
  > imported masked. Filterable with `--masked`; not part of identity.

- `p2` `[OWNER — confirm]` **Should the pixel-hash identity be called FROZEN in `direction/`?** The
  topic already records texture identity as the exact pixel hash (`sha256` over w, h, raw RGB), which
  is correct and needs no change. What it does *not* say is that the function is **frozen**: every
  tracked shard's path IS that digest, so any change to what the decoder emits silently re-keys every
  shard at once — all classifications read back "unclassified" and become prunable. That is the one
  irreversibility in the design that can destroy authored work, and it currently lives only in
  `specs/…-unified-asset-catalog.md` §3b and the plan. Proposed one-line addition to the same section:

  > The identity function is **frozen** — `(w, h, RGB)` in that order, pinned by a committed golden.
  > Changing what the decoder emits re-keys every shard and orphans every classification, so it moves
  > only by an explicit migration that rewrites them. Adding a new *fact* about an asset is always
  > safe; changing the *decoder* never is.

- `p1` `[chore]` **The unified-asset-catalog spec revision is UNREVIEWED — a `spec` round is owed.**
  `specs/2026-07-25-unified-asset-catalog.md` was four-rounds-gated on 2026-07-25, then revised
  2026-07-26 with §4c (group as a queryable fact), a rewritten §3b (frozen pixel-hash identity), an
  extended §3a row shape and two new §12 coverage bullets. `CLAUDE.md` "Review gates" puts the spec
  moment at the widest row precisely because a spec defect gets built on top of, and this one has 13
  planned slices stacked on it. `plans/2026-07-25-unified-asset-catalog-plan.md` carries a STALE
  banner and must be re-cut after the spec round passes — the group fact adds work to the
  texture-adapter slice that the plan does not sequence. *(2026-07-26.)*
- `p1` `[chore]` **The `uedctl`→`uedcli` rename shipped UNGATED — it never had its build review.**
  The whole-repo rename (777 files, 5383±5383 lines, all three case variants, plus 12 doc filenames
  and the `uedctl/`→`uedcli/`, `uedctl-native/`→`uedcli-native/`, `bin/uedctl`→`bin/uedcli`,
  `2026-06-27-decontainerize-uedctl/` path moves) was committed on the owner's explicit instruction
  to "commit and worry about reviews later", so the `build` round CLAUDE.md "Review gates" requires
  was deliberately skipped, not passed. `bin/test` was green (3345 passed, 16 skipped, 64 deselected,
  1 xfailed, + 58 cargo goldens) and `git grep -i uedctl` is empty, but no cold reviewer ever read
  the diff. What a reviewer would have been asked to check, and what therefore remains unverified:
  a substring that merely *contained* `uedctl` but denoted something external (docker image/tag
  names, registry names, anything crossing a repo or machine boundary) and now points at nothing;
  word-boundary damage; cross-doc links into the 12 renamed filenames; and whether the diff is
  purely mechanical. Run a `build` round over `git show <rename-commit>` when convenient.
  *(2026-07-26.)*
- `p1` `[chore]` **The texture-format evidence has NO durable home and will die with an ephemeral
  spec.** `spikes/2026-07-25-native-texture-formats/` contains only `pkgfixture_proto.py` and no
  write-up. The measured facts — the three dumped `ETextureFormat` enums and where they disagree,
  the 18,176-export sweep, the 8,327 ambiguous chains, the 11 stored `Format` properties,
  `CompMips` as the true trailing-bytes cause — live **only** in
  `specs/2026-07-25-native-texture-formats.md`, which is ephemeral and gets deleted when the work
  lands. Nothing under `unrealed/` mentions `TEXF`/`ETextureFormat`/`CompMips`/`DXT1`. Land them in
  `unrealed/package-format.md` (or a new `unrealed/texture-format.md`) BEFORE that spec is deleted.
  `rules/spikes.md`: pin the finding, or it rots. *(Surfaced by the packages + asset-catalog
  drafters, 2026-07-26.)*
- `p2` `[debug]` **`architecture.md` contradicts `direction/conventions.md` on half-answers.**
  `architecture.md` says `ClassIndex` skips a single unparseable `.u` "with a stderr note (never
  aborts)" — the exact warn-and-continue shape `conventions.md` "No silent half-answers, and no
  fallbacks" forbids. Either the doc is stale or the code needs a ruling; `inbox.md:2939` already
  notes the fix is not mechanical. Decide which side moves. *(packages drafter, 2026-07-26.)*
- `p2` `[chore]` **`architecture.md`'s Substrate section carries a deferred note whose symbols are
  deleted.** It still ends with "*Deferred follow-up: the stub-build + texture sync mounts are
  sourced from `substrate_code_dirs`/`install_system_root`, NOT yet from the composed config*" —
  un-deferred 2026-07-14 17:40, and both symbols are gone from `uedcli/`. *(containers drafter.)*
- `p2` `[spec]` **`$UEDCLI_LEVEL` / `--tree` / the dropped `level select` have no direction home.**
  Decided 2026-07-20 21:30 and BUILT (`level_select.py`, `cli.py`'s `_tree_flag`, no `select`
  parser), but absent from every `direction/` topic — the trunk-and-editor and projects-and-config
  drafters each judged it the other's. Half is level targeting (`trunk-and-editor.md`), half is
  ambient-resolution precedence mirroring `$UEDCLI_PROJECT` (`projects-and-config.md`). Needs a
  home before it is lost. *(Both drafters, 2026-07-26.)*
- `p2` `[chore]` **`rationale/` topics are unwritten for material the drafters surfaced.** Agent-owned
  engineering decisions with no home yet: the schema-cache mechanism (stat tuple over content hash,
  per-package primitives over compositions, marshal over JSON, the frozen-golden version guard);
  the intersect `BUILDER_PAD`/seed-subtract findings; the actor-name resolution implementation
  (case-fold the dict key, per-callsite try/except); the `root_outside` CSG detail. `rationale/`
  currently holds only `cli.md`, `emit.md`, `README.md`, `MIGRATION.md`. *(Multiple drafters,
  2026-07-26.)*

- **[OWNER — review] p1 DOCS RESTRUCTURE IS COMPLETE — one issue, everything that needs your eye.**
  Thirteen `direction/<topic>.md` docs + `rationale/` now replace `direction.md` and the frozen
  `decisions.md`. Resident context **1,063 → 686 lines**. Spec
  `specs/2026-07-25-docs-restructure.md`, plan `plans/2026-07-26-docs-restructure-plan.md`,
  migration record `rationale/MIGRATION.md`.

  **1. The thirteen topic docs.** Every decision in them was confirmed in session, but the prose
  was written from subagent drafts afterwards — the *wording that landed* has not been read back by
  you. `scope` · `terminology` · `organization` · `conventions` · `trunk-and-editor` ·
  `materialize` · `safety` · `process` · `packages` · `containers` · `generators` ·
  `projects-and-config` · `asset-catalog`.

  **2. `asset-catalog.md` was written despite being HELD, and deliberately says nothing about the
  two open arbitration items.** They are still `[decide]` below and decide whether ~46% of the
  texture corpus decodes. The doc states the governing principle (the tool does not infer), the
  colour exception, and the settled BC2/BC3 limit — and is silent on the mechanism, so confirming
  it does not ratify them.

  **3. `rationale/MIGRATION.md`'s 227-row entry index is a KEYWORD GUESS, not a disposition** —
  **80 rows came back `?`**. Only the rows above the index, claimed by a topic's own sweep, are
  authoritative. The table says so in its own header.

  **4. NEITHER OLD FILE WAS DELETED, and that is deliberate.** `decisions.md` still holds the
  *bodies* of ~200 entries whose substance no topic doc has absorbed; deleting it on a keyword
  guess would destroy reasoning that only git would remember. `direction.md` is now thirteen
  one-line pointers and is safe to delete whenever you say. Deletion needs your sign-off on what,
  if anything, is dropped — that was the plan's design and it still holds.

  **5. ~95 tracked files cite `decisions.md` by date.** Correct today (the file exists, frozen);
  they become dangling the moment it goes. `test_no_citation_of_a_deleted_doc` makes that failure
  loud rather than silent, so deletion cannot sneak past it.

  **6. Three direction/code deltas** where confirmed direction now leads the tool (detail in
  `rationale/MIGRATION.md`): label verbs reject `--tree stash|prefab` though your ruling says
  accept; `stash apply`/`prefab apply` mint no batch label though the new rule says they must;
  `actor folder list`/`actor label list` do not exist.

  **7. Your name is swept from `CLAUDE.md`, `direction/`, `rationale/`, `rules/` and
  `dev/docs/README.md`** — replaced with "the owner", pronouns neutral, parking tag `[OWNER —
  confirm]`, trailer `Confirmed:`. It survives in ~20 files outside that scope (frozen
  `decisions.md`, ephemeral specs/plans, board files, `architecture.md`, root `README.md`) and in
  two FILENAMES (`dev/docs/andrzej.md`, `dev/docs/2026-06-20-open-questions-for-andrzej.md`) —
  untouched because the first reads "My own todolist, don't touch". Four commits carry the
  pre-rename `Andrzej-confirmed:` trailer; history is never rewritten, so audit both spellings.

- needs a design → **`to-spec.md`** (tag `[spec]`)
- needs an investigation first → **`to-spike.md`** (tag `[spike]`)
- has a spec, needs sequencing → **`to-plan.md`** (tag `[plan]`)
- ready to do, no spec/plan needed (a chore, a trivial fix, or a reviewed plan) → **`to-build.md`**

This is also where anything the AI wants to **flag for Andrzej** lands (a provisional call, an
assumption, a risk, a deviation, or a question only he can answer) and where **his own open
questions** live — there is no separate "flagged"/"to-resolve" lane; it's all just capture here,
triaged forward when it's ready.

Keep entries terse here — a one-liner is fine; detail gets added when it's triaged forward. A `pN`
priority is optional until triage. When you triage an item, **move** its line out to the target
queue (don't copy — one home per item).

- **[spec] p2 `level doctor` should flag an actor that is EMBEDDED IN world geometry.** A
  world-colliding actor whose collision volume sinks into solid space is a real level-design bug —
  the engine shoves it out, drops it through the floor, or leaves it blocking movement — and
  nothing currently catches it. **Rule Andrzej gave: report when the overlap exceeds 2 uu OR 10% of
  the actor's own size** (either, not both — so a small decoration is judged proportionally and a
  large one absolutely). Scope is actors that actually collide with the world; a non-colliding
  decoration or a light may sit inside a wall legitimately.
  - **Open for the spec, do not guess:** which dimension "10% of its size" measures against
    (`CollisionRadius`, `CollisionHeight`, or the smaller of the two — they differ a lot for a tall
    thin pawn); whether the collision volume is taken as the engine's cylinder or the mesh bbox;
    and whether a resting-on-a-floor contact of a fraction of a uu needs an explicit tolerance so
    every placed decoration does not report.
  - **Depends on solid-space classification**, which is why this is `[spec]` and not `[chore]`:
    deciding "is this point inside world solid" needs the native CSG core, and `level doctor` is
    otherwise pure per-actor/T3D compute. Worth settling whether the coarse core is accurate
    enough here, or whether this check has to wait on the `bspBrushCSG` port — and what the verb
    does when no core/package path is resolvable (exit 2 naming what is missing, per the
    `is_mover` precedent, rather than silently skipping the check).
  (Andrzej, 2026-07-26.)
- **[ANDRZEJ — decide] p1 Docs restructure — spec gate round 1 returned a STRUCTURAL finding; work
  is PARKED.** Spec: `specs/2026-07-25-docs-restructure.md` (3 cold Opus, 2026-07-25). 2 of 3
  reviewers independently: deleting `direction.md` abolishes the **"want" lane** with no
  replacement — after it, nothing answers "what are we building toward" (`architecture.md` may not,
  by house rule; the board is one-line queue items; `decisions.md` is a per-choice ledger, not a
  synthesis). Reviewers' counter-proposal: **drop the `@` import, keep the doc** — takes the whole
  ~7k always-on cost off the table without deleting a lane, a 44-file retarget, or an editorial
  rewrite. Per `CLAUDE.md` "Review gates" the work is parked, not merged, until Andrzej rules;
  it then re-enters at round 1.
- **[ANDRZEJ — decide] p1 Docs restructure: shard axis for `decisions.md`.** All 3 reviewers:
  entries are 46 in 2026-06 / 181 in 2026-07, so a monthly shard leaves `2026-07.md` at ~7,030
  lines — 78% of the original, against a D4 rationale that rejected one-file *because* it is ~9k
  lines. Options: topic/subsystem axis (loses order-preservation, which C1's verification depends
  on), fixed entry-count, prune-first-then-remeasure, or keep monthly and drop the size rationale.
- **[ANDRZEJ — decide] p1 Docs restructure: Part A may be a net context LOSS.** Reviewers A+C: the
  two biggest sections the spec moves (`review-gates` ~216, `documentation` ~96) are exactly the
  ones "After every change" fires on *every* change, so most sessions re-read them as uncached
  tool output; and R4 replaces the 382-line `direction.md` with a pointer to `architecture.md`
  (2,157 lines / 189 KB, ~6.5x). Rare-trigger sections only (worktrees/spikes/background/board/
  tests = 193 lines) may be the honest scope.
- `p1` `[chore]` **Docs restructure: spec's measured facts were wrong — corrected.** `direction.md`
  citers 10 → **45** (incl. 5 `.py`); `decisions.md` citers 120 → **171** (45 `.py`, 3 `.sh`,
  `pyproject.toml`); ledger entries 229 → **227** (`## Format` + a template heading inside a fenced
  code block). The spec's C1 verification used the same naive `^## ` matcher that produced the bad
  count, so a splitter built to it would split inside the fence and self-certify green. Any redo
  must anchor on `^## \d{4}-\d{2}-\d{2}`, be fence-aware, and assert the format block survives.
- `p1` `[chore]` **Docs restructure: link-check scope must be repo-wide, not `dev/docs`+`docs`.**
  ~49 citations of `decisions.md` and 5 of `direction.md` live in `uedcli/*.py`, `bin/_venv.sh`,
  `pyproject.toml`; `CLAUDE.md` "New UnrealEd findings … back-reference them from code comments"
  makes these load-bearing. Also: the dominant citation form is *prose* (``CLAUDE.md` "Review
  gates"``), which a link checker passes — needs a string-based check too. And `bin/test` must run,
  so the batch is a **build** row, not docs-only.
- `p2` `[chore]` **Docs restructure: `decisions.md` holds 39 refs to `direction.md`** — deleting it
  strands them, and editing them violates the never-reword rule asserted in `CLAUDE.md`,
  `decisions.md`'s preamble and `dev/docs/README.md`. Needs an explicit carve-out (mechanical
  repath declared not "rewording") or a superseding entry declaring them historical + a documented
  link-check exemption for the ledger.
- `p2` `[chore]` **Docs restructure: sequencing defects.** Ledger entries D1–D5 were scheduled
  *last*, i.e. after the step that deletes a doc — if interrupted, the only record of why is an
  ephemeral spec; they must land first. Step 6 also writes to `decisions.md`, which C1 has by then
  replaced. Part A was expected to land a code-cli-conventions rules file citing `direction.md` before Part B
  deletes it. And per `CLAUDE.md`, specced pipeline work needs a **plan round** — the spec went
  spec-gate → build-gates with no plan doc.
- `p2` `[chore]` **Docs restructure: `rules/` must be added to the NOT-trivial list, and router
  lines must never be `@` imports.** After Part A ~550 of `CLAUDE.md`'s lines live in
  `dev/docs/rules/*.md`, which is not on the NOT-trivial list — a one-line edit there would be
  gateable as trivial, an observable weakening. Separately, one `@dev/docs/rules/…` row silently
  negates the entire saving while looking correct; gate on `grep -n '@dev/docs/' CLAUDE.md` empty.
- `p2` `[chore]` **Docs restructure: `direction.md` "asset catalog" content must NOT go to
  `to-spec.md`.** It is spec'd + planned + reviewed and sits on `to-build.md:48-52`; routing it
  back would walk a reviewed item backwards, violating "an item lives in exactly ONE queue".
  Re-verify every board destination against the board's real state.
- `p2` `[debug]` **`CLAUDE.md`'s "The repo this tool lives in" is factually wrong in this
  checkout** — it says uedcli lives at `Tools/uedcli/` inside `dx_lum` with `_scratch/` "two levels
  up"; the git toplevel is `/home/neob91/Documents/Dev/uedcli`, `_scratch/` is at that root, and
  there is no `Tools/`. Pre-existing, and the section stays permanently resident, so the error sits
  in the most privileged position available. Scheduled for the docs-restructure plan's Task 9.
  (`Tools/uplayctl/CLAUDE.md`, which mirrors these rules, is in a *different* repo — this
  restructure silently desynchronises it.)
  **RESOLVED 2026-07-26 (`ab0ad33`), Andrzej-decided:** the two sibling claims in this item are now
  true rather than fixed-by-deletion — `.claude/worktrees/` was added to `.gitignore` (precisely,
  not a blanket `.claude/`, so `settings.json` stays tracked), and `.claude/settings.json` was
  created with `worktree.baseRef: "head"` so `EnterWorktree` branches from the current branch like
  the manual procedure does. Reasoning belongs in `direction/process.md` when Task 4 lands it.
- `p2` `[chore]` **Docs restructure: concurrency.** A live worktree (`brush-profile-generators`)
  holds the pre-restructure tree; git cannot auto-merge an append into a file that has become a
  directory. Land only when no worktree is in flight, or state the manual reconciliation.
- `p3` `[chore]` **`dev/docs/README.md`'s doc table is already incomplete** — omits `andrzej.md`,
  `prefabs.md`, `dev-runtime.md`, `deusex-assets-setup.md`, `engine-internals/`, `reviews/`,
  `board/someday.md`, `board/HANDOFF-native-full-parity.md`. Worth one pass when `rules/` is added.
- `p3` `[chore]` **`board/inbox.md` (2,602 lines) and `board/done.md` (1,125) are themselves
  unpruned** — out of scope for the docs restructure, noted there.
- **[debug] p2 `brush vertex move` reaches the user as a bare Python traceback.**
  `brush vertex move <name> --at 64,64,64 --to 1e30,64,64` prints a full traceback ending
  `ValueError: no brush vertex at (…)` from `uedcli/vertex.py:81`. `dispatch`'s top-level handler
  chain catches `_SelectionExit`, `_ProjectError`, `LevelSelectionError`, `ConfigError`,
  `CoordinateError`, `GeometryError`, and the editor errors — but not a plain `ValueError`, so this
  one escapes. Violates `CLAUDE.md` "never let a Python exception reach the CLI user". Pre-existing
  and untouched by the profile-generator work; found while probing the neighbouring write-path
  guard. Fix by raising a named error at the vertex lookup, with a regression test.
  (Round-2 build review, 2026-07-26.)
- **[debug] p3 A positive-but-degenerate `--angle` builds a NON-MANIFOLD revolve at exit 0.**
  `brush build revolve --angle 1 --segments 1 --point 64,0 --point 192,0 --point 192,128
  --point 64,128` exits 0 with only the off-grid advisory, and `level doctor` then reports
  `edge … is shared by 4 faces (non-manifold)`. Confirmed IDENTICAL on `master`, so the profile
  generators did not introduce it — a 1-uu sweep collapses the near and far rings to within
  `WELD`. Same family as the degenerate-dimension item below, but that one names only
  `--depth`/`--height`, so this instance would otherwise go uncaptured. The fix likely belongs
  with it: a minimum representable sweep, named per flag. (Round-2 build review, 2026-07-26.)
- **[debug] p3 A degenerate-but-positive dimension exits 2 without naming the flag or the
  value.** `brush build extrude --depth 1e-9 --point 0,0 --point 96,0 --point 96,32` and
  `brush build cube --width 256 --breadth 64 --height 0.0001` both print `invalid brush geometry:
  builder: face has < 3 distinct vertices` — true, but it names neither the offending flag nor
  what the user typed, so there is nothing to act on. The positive-dimension guard
  (`dispatch._POSITIVE_BUILD_DIMS`) passes them because they ARE > 0; the face only collapses
  later, when `_dedup_ring` welds vertices that land within `WELD` of each other. Fix at the
  shared guard (a minimum representable extent, named per flag), not per verb — it affects every
  shape. **Re-filed 2026-07-26:** this was the second half of the coordinate `[debug]` item, and
  it was deleted along with the half that WAS fixed (the `decimal.InvalidOperation` traceback,
  now `model.CoordinateError`, guarded in `emit`). Caught by the round-2 build review; the deletion was the error the
  board exists to prevent, so it is logged here rather than only corrected in place.
- **[ANDRZEJ — decide] p3 Should the >64-face POLY-BUDGET advisory cover every `brush build`
  shape, not just `extrude`/`revolve`?** Shipped 2026-07-25 with the profile generators, gated on
  those two shapes (`dispatch._SWEPT_SHAPES`). The OFF-GRID advisory's gate is forced — an ungated
  one turns `test_generators.py`'s "a solid 8-gon cylinder says nothing on stderr" red, and the
  spec deliberately leaves `cylinder`/`cone` alone — but the poly-budget gate is a judgement call I
  made rather than a spec requirement. Ungated it would also fire on e.g. `brush build staircase
  --steps 16` (66 faces), which is arguably a true and useful warning. Deliberately NOT decided in
  the build: it changes an existing verb's observable output.

- **[verify live] p3 Cap merge-back after `bspMergeCoplanars`.** Materialize an L-profile
  `brush build extrude` and count cap SURFACES in the built map. Prediction (an inference from the
  `TryToMerge` decode, never observed): the build pass fuses tiles wherever each pairwise merge's
  two INPUTS have vertex counts summing to ≤16 — so a 2-piece cap fuses back to one surface and a
  3+-piece cap may fuse only partially. A by-product is whether `Engine.dll`'s `RemoveColinears`
  carries a convexity reject our Rust port omits. Spec §6.1 / §11 of the (now landed) profile
  generators; nothing depends on the answer, it is a documentation-truth item.

- **[verify live] p3 Does a FULL-TURN revolve (a genus-1 torus brush) build correctly?**
  `brush build revolve --angle 65536` emits a single brush with a hole through it. Nothing in
  `kb/csg-bsp.md`, `quirks.md` or the spikes evidences UE1 `bspBrushCSG` behaviour on a genus-1
  brush — the staircase precedent covers only a simply-connected stepped hull. Materialize one and
  check the built map for holes; the fallback if it builds badly is two 180° revolves (two
  brushes), which costs an actor and nothing else. Spec §4.7 / §11.

- **[implement] p3 The two profile generators have NO editor-blessed parity case.** All six
  parametric shapes are pinned against real-editor captures by `tests/builder_parity_cases.py`;
  `extrude`/`revolve` ship with SELF-blessed goldens (`fixtures/builder_extrude.t3d`,
  `builder_revolve.t3d`), which pin drift, not correctness. Adding a parity case needs the
  `integration`-gated capture run against a live editor. Note the two families already dropped from
  the live capture suite (`OFFLINE_ONLY`: staircase, spiral) were dropped because the DEINTERSECTION
  readout invents vertices on non-convex / non-axis-aligned geometry — a swept profile is likely to
  hit the same wall, so this may end up offline-only too.

- **[ANDRZEJ — decide] p2 Where does builder input validation belong: the CLI or the builders
  library?** Item #10.4 put the positive-dimension guard in `dispatch._POSITIVE_BUILD_DIMS` /
  `_check_positive_build_dims` (CLI layer) because the spec asked for "one exit-2 message shape
  naming the offending FLAG", and only the CLI knows flag spellings. Consequence a round-1 reviewer
  measured: the *library* is still unguarded — `builders.cube(-32.0, 64, 64)` and
  `builders.staircase(4, -32.0, 16, 64)` both return happy inside-out brushes, silently. Meanwhile
  the SIBLING constraints of the same family (`steps >= 1`, `sides >= 3`,
  `0 < degrees_per_step < 180`, `inner_radius > 0`) all live in `builders.py` and raise
  `GeometryError`. So one class of builder input is validated at the CLI and a neighbouring class at
  the library, and the table has to mirror argparse `dest` names into `dispatch.py` to bridge them.
  Non-CLI callers at risk: the native materialize path, `stash`/`prefab` code if it ever grows a
  builder route, and #12's `extrude`/`revolve` helpers. Options: (a) keep as is and accept the split;
  (b) duplicate the check in `builders.py` as a `GeometryError` so both doors are guarded, accepting
  two messages for one condition; (c) move it wholly into `builders.py` and lose the flag-named
  message the spec asked for. **This was not decided by the spec and is not the AI's call.**
- **[ANDRZEJ — decide] p2 Item #10.3 renamed the annotation SELECTION internals but deliberately kept
  "label" for the DRAWING machinery — the spec asked for more.** `LabelSpec`/`parse_label_spec`/
  `DEFAULT_LABELS` became `AnnotationSpec`/`parse_annotation_spec`/`DEFAULT_ANNOTATIONS`, but
  `_LabelItem`, `_PlacedLabel`, `_place_labels`, `_label_size`, `_LABEL_WEIGHTS`, `poly_labels` keep
  "label", on the reasoning that a label there means one concrete text box laid out on the canvas —
  annotations are decided, labels are placed. The `to-build.md` §10.3 spec listed the drawing
  machinery's prose too and justified the item with "'label' now means two unrelated things in one
  codebase"; under the split a cold reader still meets "label" in `_place_labels` meaning something
  unrelated to `--label`, and the codebase carries four senses in total (preview drawn text, the
  actor dimension, Docker container labels in `preview_game.py`, the legend). Recorded in
  `decisions.md` 2026-07-25 18:40 UTC. **Confirm the split or ask for the full rename.**
- **[chore] p3 `test_zoom_does_not_highlight` does not test its own claim.**
  `uedcli/tests/test_actor_preview.py` — the comment says "a zoom target is NOT bolded/highlighted",
  but the assertion (`_CSG_PALETTE["subtract"][0] in _colors(...)`) only proves the brush drew in its
  normal CSG hue, which holds with or without highlighting. Pre-existing; #10.1 only swapped its
  pixel reader from PPM-header parsing to a Pillow decode. A real test would compare against a
  `--highlight`ed render and assert the vivid/bold run is ABSENT.
- **[chore] p3 One #10 commit (`6c3df18bd`) leaves the tree red.** It landed the `--png` deletion in
  `cli.py`/`dispatch.py`/`preview.py` without the test updates, which came in the next commit
  (`631617888`), so `bin/test` fails at that commit and `git bisect` across the range is broken. It
  was split that way only because a stream watchdog fired mid-task and the in-flight work had to be
  committed immediately to avoid losing it. Not repaired because that would mean rewriting published
  history, which is forbidden; the branch is squash-merged, so the red intermediate does not reach
  `uedcli-impl`. Recorded so the "each commit lands green" rule is not silently eroded.
- **[chore] p3 Trunk-save lost-update detection aborts at whole-save granularity (known tradeoff).**
  The `TrunkLevelSource.save` compare-and-abort (spec `specs/2026-07-25-trunk-write-safety.md`, D3)
  aborts the ENTIRE save if any one actor in `changed ∪ deleted` was touched concurrently — so a large
  batched pipeline (`actor find … | actor prop set -` over hundreds of actors) loses its whole save
  when a single target raced, and a persistent concurrent writer could livelock the retry. This is the
  deliberate abort-not-merge semantics (Andrzej 2026-07-25) and is recoverable (uedcli is stateless per
  invocation; the re-run reloads fresh and recomputes), so it is not a correctness bug — logged as a
  known coarse-granularity tradeoff, not surfaced as a surprise. A finer-grained "write the
  non-conflicting subset, report the conflicts" mode is the possible future refinement. (From the D3
  spec review, 2026-07-25.)

- **[chore] p3 `actor order --after/--before REF` can write a stale-computed rank when REF is
  concurrently re-ranked — a stale-READ ordering anomaly, out of the same-actor lost-update scope.**
  `compute_reorder_ranks` derives the moved actor M's new rank from the load-snapshot positions of REF
  and its neighbor. If another process re-ranks REF and commits first, M's save has `changed = {M}` (REF
  ∉ changed), so the trunk-write-safety D3 conflict check never inspects REF — M is written relative to
  REF's now-stale position and may sort to the wrong side of REF or collide. This is NOT a lost update
  (REF's write survives; only M's ordering is stale) and is **pre-existing** to delta-writes — D3 neither
  introduces nor worsens it; collisions stay harmless via the (order_value, name) tiebreak, `level
  doctor`'s duplicate-order check flags them, and re-running `actor order` heals it. Logged so D3's
  "airtight/100%" framing isn't mistaken for a global ordering-consistency guarantee (it is scoped to
  same-actor lost updates over `changed ∪ deleted`). (From the D3 spec review, 2026-07-25.)

- **[spec] p1 ANDRZEJ — the two `CLAUDE.md` files now give contradictory review-gate rules, and the
  new uedcli policy block has no ledger entry.** Three reviewers in one round independently flagged
  this; escalating rather than editing your own convention files. (a) **Direct contradiction, both
  auto-loaded:** `Tools/uedcli/CLAUDE.md` opens "**EVERY change gets reviewed — there is no
  trivial-change exemption**" with a 2/3/4 reviewer ladder, while the repo-root `CLAUDE.md` still
  says "For any **non-trivial** change … fan out **two** … (A trivial change — a typo, a one-line doc
  tweak — doesn't need the gate; use judgement.)" and is not scoped to exclude uedcli. An agent
  working in `Tools/uedcli` reads both and gets opposite instructions on the exemption AND on the
  headcount. Suggest the repo file say a per-tool file may impose a stricter gate. (b) **Dangling
  citation:** the tool file cites "in one 2026-07-25 round the two reviewers overlapped on only two
  of eight findings … — see `decisions.md`, 2026-07-25", but no `decisions.md` entry records that
  round or that statistic; the rounds are described in `board/done.md`. Repoint it. (c) **No decision
  entry exists for the gate policy at all** — the headcount ladder, context-vs-priming, the
  observability test, batching, and the feature-branch/squash-merge rule all landed only in a
  convention file, against that file's own rule that choices + rejected alternatives go in the
  append-only ledger. (2026-07-25, round-4 cold reviews.)

- **[chore] p3 `MAP SAVE` doc-accuracy remnants from the round-4 review — five small corrections,
  all in dev docs, none affecting behaviour.** Logged rather than fixed under the two-round gate
  ceiling. (a) `unrealed/commands.md` and `spikes/2026-07-25-map-save-mechanism/README.md` say the
  `SavePackage` literals sit at "**consecutive** offsets"; they don't — 14 other phase literals
  (`Untag`, `TagExports`, `CheckExportCompat`, `TagImports`, `ExportNames`, `SaveSummary`,
  `BuildNameMap`, `SortNames`, `SaveNames`, `BuildImportMap`, `SortImports`, `BuildExports`,
  `SortExports`, `SetLinkerMappings`) sit between `UObject::SavePackage` and `SaveExports`, and four
  more between `Save.tmp` and `Moving '%s' to '%s'`. Say "ascending offset order" and quote the full
  run — the intervening names (esp. `SaveSummary` early vs `RewriteSummary` last) are STRONGER
  evidence for the inferred sequence than what was published. (b) Both docs call the summary "the
  36-byte header"; the engine's summary is **64 bytes** (measured `nameoff=64` on `00_Intro.dx`,
  `00_Training.dx`, `00_TrainingCombat.dx` — bytes 36-63 hold the GUID + generation records). 36 is
  uedcli's READ WINDOW, not what `RewriteSummary` patches. (c) `measure_header_window.py` bare-asserts
  every package passes; it should collect outliers instead, since legitimate zero-count packages exist
  (`uned/UED22/WinDrv.u`, `Window.u`) and a search path containing one would die with an unexplained
  `AssertionError`. (d) That harness needs the retail install AND the tool dir as cwd (run from the
  repo root it dies with a confusing `ImportError` because the repo's `uedcli/` maps dir shadows the
  package); document both and fail with a named error. (e) `architecture.md` says
  "`qualify.export_and_qualify` … never called either" — that function no longer exists (removed in
  `607dc430f`); say it was deleted with the store. (2026-07-25, round-4 cold reviews.)

- **[chore] p3 Two round-4 pinning gaps in the `core.dll` engine-facts regression.**
  `test_engine_facts.py` asserts only that 2 imports are present and 7 are absent, while
  `spikes/2026-07-25-map-save-mechanism/README.md` states all 8 file-API imports as fact — and the
  README's Q1 offset table (7 byte-exact offsets) is unpinned, so a relink rots it silently. Assert
  the full file-API import set and the offsets, or stop stating them as exact. (2026-07-25, round-4
  cold review.)

- **[chore] p3 `decisions.md`'s 12:40 UTC "Mechanism correction" reads as current for 13 lines
  before being withdrawn.** Its bold lead-in still asserts "so the move is a read/write COPY … the
  reachable truncation is a half-finished COPY", and only the 14:05 UTC note below retracts it. A
  reader skimming headings re-adopts exactly the over-read the batch exists to retract. Append
  "(WITHDRAWN — see below)" to the lead-in. Append-only ledger, so annotate, don't reword.
  (2026-07-25, round-4 cold review.)

- **[chore] p3 `docs/usage.md` now under-states which verbs fail on an off-path actor class.** The
  per-actor paragraph says "the verbs listed above exit 2 naming that class", listing only the
  mover-aware verbs — but `apply.run_materialize` resolves every actor's class defaults before the
  editor starts and raises `SchemaError` → clean exit 2 naming the class, so `level materialize`
  fails the same way for a different reason (schema/defaults, not mover-ness). One sentence.
  (2026-07-25, round-4 cold review.)

- **[chore] p3 Two tests in `test_engine_facts.py` don't test what they claim (pre-existing).**
  `test_collision_box_is_twice_the_half_height` is `radius, half_height = 22.0, 40.0` then
  `assert 2 * half_height == 80.0` — a tautology over its own literals that imports nothing from
  uedcli and can never fail. `test_the_sheer_axis_enum_matches_the_real_core_package` docstrings "It
  must match `Core.u`'s real `ESheerAxis` ordering" but never opens a package, though the real names
  are in the committed `uned/UED22/core.u`. Both predate this work; surfaced by a round-4 reviewer
  reading the file the new regression was added to. (2026-07-25.)

- **[chore] p3 Stale `canonicalize_mover_blob` references in two more ephemeral docs.**
  `specs/2026-07-18-unify-t3d-trees.md` (5 places) and `plans/2026-07-18-build-unify-t3d-trees.md:53`
  still describe the deleted helper as shipped API ("**uedcli/movers.py** — gains a public
  `canonicalize_mover_blob`"). Its sibling `specs/2026-06-27-uedcli-native-dx-read-design.md` got a
  STALE banner in the same batch; these were missed. Ephemeral docs, so lowest priority — but the
  deleted name now appears nowhere else. (2026-07-25, round-4 cold reviews.)

- **[chore] p2 FLAG for the texture workstream: two corpus claims in its spec/plan are measured over
  UNTRACKED files, so its "exact count" criteria cannot pass on a clean clone.** Not my change —
  surfaced by a round-4 reviewer over the same commit range. (a) `<repo>/Textures` is labelled
  "git-tracked, 6 packages / 418 Texture exports"; `git ls-files Textures/` returns **4** packages
  (`France.utx`, `LUM_CharacterTex.utx`, `LUM_CoreTex.utx`, `LUM_InfoPortraits.utx`) totalling **384**
  exports — `CoreTexSky.utx` and `CoreTexWater.utx` are untracked working-tree files. (b) The UED22
  figure ("34 packages / 1,998 exports") only reproduces with a RECURSIVE scan; non-recursive gives
  32 / 1,934, and the extra two are `DoNotPlaceInventorySpots/Engine.u` + `PlaceInventorySpots/`
  `Engine.u`, whose 32 textures each duplicate the top-level `Engine.u`'s. Re-measure over
  `git ls-files`, or commit the two `.utx` and say so, before S1 starts. (2026-07-25.)

- **[chore] p3 FLAG: `to-build.md` and `inbox.md` both own the `xfer` timeout work, and one item
  schedules a function for deletion that another schedules for repair.** Not my change.
  `to-build.md` says the inbox chore covers "only `driver.py`'s 8 calls + `xfer.remove`" and claims
  `cp_in`/`cp_out` for itself, while the inbox entry (widened by the round-3 review) already covers
  all three `xfer` subprocesses — `board/README.md` says one home per item. Separately `to-build.md`
  lists `xfer.cp_in` among zero-caller dead code to DELETE while also scheduling it for a timeout
  bound; whichever builder runs first invalidates the other. Also two `to-build.md` links point at
  specs that are untracked (`2026-07-25-trunk-write-safety.md`,
  `2026-07-25-decimal-map-coordinates.md`). (2026-07-25, round-4 cold reviews.)

- **[chore] p3 Every docker subprocess in `driver.py`/`xfer.py` EXCEPT the `map_save` probes is
  still an unbounded wait — 8 `docker exec`s across 6 driver methods, plus all THREE in `xfer.py`.** `map_save`'s file probes go through
  `_container_probe`, which bounds each `docker exec` with `PROBE_TIMEOUT` and turns a
  `TimeoutExpired` into a `DriverError`. Nothing else does: `_wine_ctl`, `dexec_bash`,
  `set_clipboard`, `log_size`, `read_log_since`, `dismiss_blocking_dialog` (three calls), and
  `xfer.remove`'s `docker exec rm -rf` **plus `xfer.cp_in`/`cp_out`'s `docker cp`** all call
  `subprocess.run` with no `timeout=`, so a hung dockerd parks the caller forever (`CLAUDE.md`
  "never an open-ended wait"). **Seven of those calls also pass `check=True`** (`log_size`,
  `read_log_since`, all three in `dismiss_blocking_dialog`, and both `xfer` `docker cp`s), so a
  docker failure reaches the user as a raw `CalledProcessError` traceback instead of a named
  `DriverError` — a second rule broken ("never let a Python exception reach the CLI user"). The
  `docker cp` pair matters most in practice: `level materialize` funnels every map in and out through
  them. Not folded into the `map_save` fix because `_wine_ctl exec` drives genuinely long editor verbs
  (`MAP REBUILD` can run minutes) and needs its own bound chosen rather than copied — and note
  `map_save`'s own `MAP SAVE` line goes out through `_wine_ctl`, so its bounded poll loop is preceded
  by one unbounded call. (2026-07-25, while fixing the `map_save` verification; counts corrected
  twice by the build reviews. Deliberately no line numbers — method names are stable, line numbers
  rot within the commit that adds them.)

- **[chore] p3 `map_save` has no INTEGRATION test — the new accept rule has never run against a real
  editor.** `test_driver.py` drives it against a fake container and a fake clock (thorough: every
  branch is mutation-checked), and `test_real_packages_pass_the_completeness_check` feeds real `.u`/
  `.dx` headers to the validator offline. What is unpinned is the round trip: that a live `MAP SAVE`
  into the `dx-lum-uned` container is ACCEPTED by the four-signal rule, in the wall-clock the editor
  really takes. It also newly depends on `stat -c '%s %.9Y'` and `od -An -v -tu1` existing in that
  image (verified by hand 2026-07-25 — GNU coreutils 9.1 — but nothing re-checks it after an image
  rebuild). `test_driver_integration.py` covers only `map_export`/`exec`; add an
  `@pytest.mark.integration` save round-trip there. (2026-07-25, cold review of the `map_save`
  change.)

- **[spike] p3 WHERE does `MAP SAVE` create its `Save.tmp`, and can it be left behind or collide?**
  📖 `core.dll` strings, 2026-07-25 (`unrealed/commands.md` "`MAP SAVE` writes `Save.tmp`") show the
  editor serializes into a **fixed-name** `Save.tmp` and then moves it onto the target — but the
  string is a bare filename, so its DIRECTORY (beside the destination? the editor's cwd?) is inferred,
  not extracted, and everything below depends on it. Cheap to settle live: drive a `MAP SAVE` of a big
  map and `ls`/`inotifywait` the container's `/work` and `/opt/UED22` while it runs. If the temp does
  land beside the destination: `xfer.remove` only reclaims the uuid-named work file, so a wedge
  mid-save leaves a stray `Save.tmp` for the container's life (harmless while the container is
  ephemeral, but it is state nobody owns), and — more importantly — two saves into one directory in
  one container would fight over the single temp. Nothing does that today (one save per invocation),
  but the warm-editor path makes it thinkable. The same probe would also settle whether the move is a
  rename or a copy (watch the destination's size/inode), which is the open question behind
  `map_save`'s structural check — and, in the same trace, whether the destination is ever opened
  WITHOUT truncation. That last one is a real hole in the check: a size-preserving in-place rewrite
  would hold `size` constant for the whole write, so the stability signal is satisfied throughout and
  the header check compares the NEW header against the OLD, larger size — i.e. a mid-write file could
  be accepted. Unreachable for both production callers (fresh uuid paths, nothing pre-exists) but
  live for any fixed-path caller. (2026-07-25, cold reviews of the `map_save` change; evidence so far
  in `spikes/2026-07-25-map-save-mechanism/`.)

- **[chore] p3 Re-measure the native-CSG mover exclusion now that the gate is schema-aware.**
  `architecture.md` "World-CSG brush selection" quotes HK/UNATCO leaf-blob + zone counts measured
  2026-07-19 WITH the old `*Mover`-suffix test, so the `DeusEx.BreakableGlass` brushes (4 on HK)
  were still being carved into the world then. The numbers are now labelled as pre-change; re-run
  `harness/build_native_hkmarket.py` + `shatter_probe.py` (both index-aware now) to refresh them —
  it matters for a workstream whose bar is byte-identity with UnrealEd. (2026-07-25, cold review.)

- **[chore] p3 `level doctor`'s watertight check now covers MORE mover subclasses — including the
  known glass false positive.** `docs/leveldesign/general/recipes/glass.md` already documents that
  `check_watertight` false-flags welded mover glass; with mover-ness now schema-aware,
  `DeusEx.BreakableGlass`/`BreakableWall` brushes are newly IN scope for that check (the name-suffix
  gate skipped them). Either narrow the check for movers or downgrade the finding — the existing
  glass-recipe note now applies to strictly more actors. (2026-07-25, cold review of #9.4.)

- **[chore] p3 Two brush-identity checks are still NAME tests, next to the hierarchy rule that
  replaced one.** `doctor._is_closed_solid_brush` decides world-brush-ness with
  `cls == "Brush"`, and `preview_native.is_builder_brush` keys on the bare string too, so a
  `MyPkg.MyBrush` subclass of `Engine.Brush` is silently outside both. Same failure shape as the
  mover suffix guess that 2026-07-25 10:18 UTC removed; the fix is the same `ClassIndex` walk, but
  `is_builder_brush` in particular is load-bearing for the transient red builder brush and must not
  become resolver-dependent lightly. (2026-07-25, cold review of #9.4.)

- **[spec] p3 A fourth confidence marker for AUTHOR-ATTESTED UnrealEd facts?** `CLAUDE.md` defines
  three: ✅ uedcli-used / live-verified, 🔬 live-probed, 📖 extracted from the binary string table.
  Andrzej's own hands-on knowledge of the editor is none of them literally, yet it is stronger than
  📖 — e.g. "every 2D-shape-editor operation yields ONE builder brush" (`kb/geometry-builders.md` §4,
  `decisions.md` 2026-07-25 03:05 UTC), currently filed ✅ with the attestation spelled out inline so
  no reader assumes an automated verification exists. If such facts become common, add a marker (👤?)
  and a line to `CLAUDE.md`; if they stay rare, the inline-provenance convention is enough. (Surfaced
  2026-07-25.)

- **[spec] p3 Should the GENERATOR family validate geometry, not just class/texture refs?** Today
  `brush build` (every shape) and `brush intersect`/`deintersect` validate only class + texture
  existence; `geometry.validate_brush` runs when geometry ENTERS THE TRUNK (`actor add`,
  `dispatch.py:1995`) and on `clip`/`replace`/`vertex move`/`bake`. So a generator's output that never
  reaches `actor add` — `brush build … > shape.t3d`, or piped into `brush intersect` — is never
  geometry-checked. Uniform today, and `decisions.md` 2026-07-25 10:20 UTC deliberately kept it that
  way rather than let the two new profile verbs become a two-verb exception. If early validation IS
  wanted, do it family-wide: one call in the shared `brush build` tail plus the intersect tail. Weigh
  the gain (an error at the step that owns the input) against the cost (a behaviour change to four
  existing verbs, and mostly a duplicate of a check one pipeline stage later). (Surfaced 2026-07-25.)

<!-- Surfaced by the profile-generator spec's cold-review gate (2026-07-25). -->
- **[debug] p2 `brush build cylinder/cone --sides` has NO upper bound — >16 emits an invalid cap
  face.** An `FPoly` holds at most 16 vertices (`FPoly::VERTEX_THRESHOLD`; `kb/csg-bsp.md` §5.2), and
  `kb/geometry-builders.md` §1 records the cap as invalid above 16 — but `builders.cylinder`/`cone`
  accept any `sides >= 3` (`builders.py:204`, `:227`), so `brush build cylinder --sides 24` silently
  emits a 24-vertex cap. Exactly the defect the new `extrude`/`revolve` cap tiling exists to prevent,
  but in existing code. Fix: reject above 16, or tile the cap the way
  `specs/2026-07-25-brush-profile-generators.md` §6 does. (Cold review, 2026-07-25.)
- **[spec] p3 `brush build revolve`: allow a profile TOUCHING the revolve axis (solids of
  revolution).** v1 requires every profile vertex strictly off-axis (`u > 0`), because a vertex ON the
  axis degenerates its swept quads to zero width — they need collapsing to triangles. That restriction
  rules out spheres/cones of revolution, the natural use for a full-turn revolve.
  (`specs/2026-07-25-brush-profile-generators.md` §4.7; cold review, 2026-07-25.)
- **[spec] p3 `brush build revolve` should NOT merge its faces — leave them separate so textures can
  be aligned per face.** (Owner request, 2026-07-26.) What merges today, and it is not one thing:
  - **The CAPS are fused, deliberately.** A non-convex or >16-vertex profile is ear-clipped and then
    merged back across shared diagonals for as long as each piece stays convex and fits the 16-vertex
    `FPoly` bound (Hertel–Mehlhorn, `profile.convex_pieces`). So a cap that is conceptually many
    facets arrives as a few large ones, and there is no face to align a texture onto separately. The
    fusion exists on purpose — its own docstring: *"merging matters, because every extra face is BSP
    nodes and rendering cost"* — so removing it is a **trade** (more faces, more nodes, more render
    cost) and not a pure win. That is why this is `[spec]` and not `[chore]`.
  - **The SIDES are already unmerged model-side** — `builders.revolve` emits `n × s` separate quads,
    one per (profile edge, segment). But every segment of profile edge `k` carries the SAME
    `ItemName=Side<k>`, so `--item Side0` selects the whole swept strip and there is no item-level
    handle on a single facet. Individual facets ARE addressable as `BRUSH:idx` selectors from
    `brush poly find`, so this may be a selector-ergonomics gap rather than a geometry one.
  - **The ENGINE merges coplanar surfaces at `MAP REBUILD`** (`bspMergeCoplanars`, within
    `THRESH_NORMALS_ARE_SAME = 2e-5` — `unrealed/quirks.md` "More build thresholds"). Anything the
    generator keeps separate can still be fused in the built map, so a model-side-only fix may not
    reach the surfaces the level designer actually aligns against.

  **Do not guess which of the three was meant — settle it at triage.** Then the real design questions
  are: is unmerged the DEFAULT or a flag (`--no-merge-caps`, or a general "one face per facet" mode);
  does it apply to `extrude` and the other cap-tiling builders too (same `convex_pieces` seam, so
  they would diverge otherwise); and what happens to the node-count budget on a full-turn revolve,
  where `inbox.md`'s own poly-budget note already flags a 16-segment revolve of an 8-point profile as
  128 swept faces plus caps.

  **MEASURED 2026-07-26 — the goal is a curved TRAIN TRACK whose textures run properly around the
  bend, and on that evidence the merge framing above is mostly a red herring.** Ran
  `brush build revolve --point 64,0 --point 96,0 --point 96,32 --point 64,32 --angle 16384
  --segments 4` and read the emitted T3D:
  - **`Link=` is NOT the mechanism and is not ours.** uedcli emits **zero** `Link=` lines (0 across
    18 polys), `model.Polygon` has no `link` field so ingest drops it, and `normalize.py` says
    outright *"The emitter drops Link."* `unrealed/t3d.md`'s polygon reference: *"computed BSP surface
    link; never authored, **ignored on import**."* A real editor export of a 6-poly cube in `_scratch`
    carries `Link=0,1,2,3,4,5` — one per poly, all distinct. So a `Link=N` seen on a revolve came back
    from the editor and is a per-poly index, not evidence of merging; editing it separates nothing.
  - **The CURVING faces are already separate AND correctly parameterised.** `Side1` (outer) has **4
    distinct normals** — four distinct planes, so `bspMergeCoplanars` cannot touch them — and each
    facet carries its own plane-derived axes: `TextureU=(0,1,0)` along the revolve axis, `TextureV`
    rotating with the facet (`-0.195,0,0.981` → `-0.556,0,0.831` → `-0.831,0,0.556` →
    `-0.981,0,0.195`), unit length (scale 1 texel/uu). These are individually alignable today.
  - **The FLAT faces are one surface by geometry, not by choice.** `Side0` has exactly **one**
    distinct normal across all 4 facets — a flat annular fan. The engine fuses those at `MAP REBUILD`
    however the T3D is written, because a flat annulus is flat. Nothing model-side reaches it.
  - **THE ACTUAL DEFECT: `Pan lines: 0`.** No facet carries any pan offset, so every facet's texture
    starts at the same phase and the pattern **restarts at each segment boundary** — a seam every
    22.5° at `--segments 4`. For track, sleepers jump and bunch at every facet edge. This is
    independent of merging entirely, and it is what makes a curved sweep unusable for a repeating
    run.

  **So the feature actually wanted is an arc-length-continuous parameterisation along the sweep** —
  each successive facet's `Pan` (or `Origin`) advanced by the arc length consumed so far, so the
  pattern flows around the bend as one run. Model-side, no editor, consistent with generators already
  owning texture vectors. **The one design question that changes the implementation, ASKED AND NOT
  ANSWERED (owner deferred it 2026-07-26 — do not guess):** arc length is radius-dependent (the inner
  strip sweeps `64·Δθ` per segment, the outer `96·Δθ`), so what drives the run?
  (a) **per-strip arc length** — texels stay square on every face, but inner and outer rails drift out
  of phase around a long bend; (b) **one reference radius for the whole brush** (centreline, or a
  `--texture-radius` flag) — sleepers stay in lockstep across the track width, which is what real
  track looks like, at the cost of slight stretch outer / squeeze inner; (c) **per-facet fit** —
  predictable, seam-aligned, but the pattern restarts each segment, so wrong for track.
  Secondary, cheap, and independent: **all cap faces share ONE `Item=Cap` label** (measured: a
  concave 6-point profile yields 28 polys = 24 sides + 4 cap tiles, all labelled `Cap`), so the two
  ends cannot even be selected apart, while sides get per-edge `Side0..SideN`. Per-cap labels would
  cost nothing.

<!-- Surfaced by the blind-build idiom test (5 cold agents built real-DX shapes using only the CLI +
     user docs, no source, 2026-07-25). All 5 shapes built correctly; these are the CLI papercuts they hit. -->
- **[debug] p1 Rapid `actor duplicate`+`rotate` in a loop SILENTLY drops trunk writes.** A tight
  back-to-back `duplicate`→`rotate` loop (building a ring of copies) produced **0 persisted actors** —
  each `duplicate` returned an empty name to stdout and wrote nothing to the trunk; the identical
  command run singly worked immediately after. Reads as a trunk delta-write race / non-atomic batch
  mutation under fast successive writes. A retry + per-step count check worked around it. Silent
  data-loss on a normal scripted loop is serious — repro: loop `dup=$(actor duplicate X --by 0,0,0
  | tail -1); actor rotate "$dup" --by 0,8192,0 --pivot 0,0,0` ~7× fast. (Blind-build test, 2026-07-25.)
- **[spec] p2 No first-class "flip CSG op" affordance (add↔subtract).** The add/subtract-**twin** idiom
  (build a solid, carve its identical void — the *dominant* real-DX workflow) requires
  `actor prop set <dup> CsgOper=CSG_Subtract`, with the enum spelling reverse-engineered from generator
  T3D. Add `actor duplicate --csg add|subtract` (flip on copy) or a `brush csg set add|subtract` verb so
  the workflow is discoverable, not folklore. (Blind-build test, 2026-07-25.)
- **[spec] p2 `actor find <NAME>` (bare positional) is rejected — must use `--name GLOB`.** The positional
  slot is reserved solely for the `-` stdin token, so the natural `actor find Foo` errors ("find takes
  no positional name; use --name"). Three independent hits (2 build agents + Andrzej). Consider accepting
  a positional name-glob when the token isn't `-` (mirrors `actor show <glob>`), keeping `-` as the
  universe pipe. (Blind-build test + Andrzej, 2026-07-25.)
- **[chore] p3 `brush clip` prints nothing on success.** A successful clip emits only the "editing level"
  banner — no confirmation — so a blind builder can't tell it did anything without re-inspecting. Print
  e.g. `clipped <name>: 6→7 faces`. (Blind-build test, 2026-07-25.)
- **[debug] p2 `DistanceFromPlayer`/`LastRenderTime` look like the same engine-runtime family as the
  mover `Saved*` fields, but are NOT in `normalize.COMPUTED_PROPS`.** Measured over the git-tracked
  editor exports: `DistanceFromPlayer` on 27 898 of 47 524 actors (11 546 distinct values),
  `LastRenderTime` 9 038 times — both plainly per-frame engine state (how far the actor was from the
  player / when it was last drawn), on every actor class, not just movers. They do NOT currently
  break the post-verify, because an offline UCC `batchexport` of a freshly built map does not emit
  them (nothing has rendered yet) — but a trunk INGESTED from one of those exports carries them as
  if they were authored content, and they would then ride into the built map. Decide whether they
  join `COMPUTED_PROPS`; get evidence first (which write path emits them) rather than adding on
  faith — the standing rule that kept `SavedTrigger` out. (Surfaced by a cold review of the mover
  `Saved*` fix, 2026-07-25.)
- **[chore] p2 `level preview --game`'s INTERNAL materialize runs the H3 post-verify, with no way to
  skip it.** A preview `.dx` is throwaway, so verifying it buys nothing and any post-verify mismatch
  blocks previewing the level at all — the failure mode that made the mover `Saved*` bug (fixed
  2026-07-25) block previews as well as builds. `level preview --game` does not expose
  `--no-verify`; today's workaround is the two-step `level materialize --no-verify --out foo.dx`
  then `level preview --game --map foo.dx`. Preview's internal build should skip the verify (or
  expose the flag). (Split out of the mover `Saved*` item when that was fixed, 2026-07-25.)
- **[debug] p2 `level doctor` reports a MOVER built via `brush intersect` as non-manifold / not
  watertight — FALSE POSITIVE.** A glass-door mover (solid frame + subtracted opening + flush
  **semisolid** translucent pane, welded with `brush intersect`) trips 16–32 `watertight … shared by 3
  faces (non-manifold)` errors, because the semisolid pane's side faces intentionally COINCIDE with the
  subtracted reveal walls (that non-merging is the whole point — see
  `leveldesign/general/recipes/glass.md`). But (a) a **mover never goes through world BSP**, so the
  manifold/CSG-hole requirement simply doesn't apply to it, and (b) an intentional coincident-semisolid
  interior is a valid UE1 construction. The door renders correctly in `level preview --game` regardless.
  Doctor's watertight check should **skip mover brushes** (and/or brushes with intentional coincident
  semisolid faces), or downgrade to info. (Surfaced building the DeusExMover glass door, live-verified
  2026-07-25.)
- **[spec] p3 `brush build extrude --taper S` — scale the FAR cap (the frustum/loft remnant).**
  RE-SCOPED 2026-07-25 now that `brush build extrude` has landed, which is what the rest of the old
  "`cube --taper` / wedge builder" item asked for: wedges, voussoirs and tapered blocks come
  straight from a **trapezoid profile**, because that taper lives IN the profile plane, and the
  `arch-voussoir.md` recipe shows it. The genuine remnant is taper **along the sweep axis** — a
  frustum/loft where the far cap is a scaled copy of the near one (UED's *Extrude to
  Point*/*Extrude to Bevel*), which neither `extrude`, nor `brush clip`, nor `brush build cone`
  (apex-only, no `CapHeight` truncation) can produce. One flag on `extrude`, scaling the far cap
  about profile `(0,0)`; note it makes the side quads non-planar unless the scaling is uniform, so
  the spec must say what happens to a non-uniform case. (Blind-build test, 2026-07-25; re-scoped
  2026-07-25 when extrude landed.)

- **[debug] p2 A partial `Location` still WRITES back zero-filled (the compare half is fixed).**
  The typed compare (2026-07-25 02:15 UTC) reads an omitted axis as the class default via the
  `Actor.location_text` side-channel, so an `Engine.Camera` export `Location=(X=100,Y=200)`
  (default `(X=-500,Y=-300,Z=300)`) now COMPARES as Z=300. What is left is the WRITE half: the
  numeric triple `parse_t3d` fills is still `(100,200,0)`, so `actor add` of that raw editor T3D
  stores `Z=0.000000` in the trunk — the actor really does move 300 uu. Fixing it needs a
  class-defaults resolver at the INGEST verb (which has project context, unlike `parse_t3d`, which
  is deliberately schema-free — it is also the trunk/stash/prefab/generator-snippet reader).
  `Engine.Camera` is the only one of 1346 actor classes that defaults `Location` non-zero, so that
  is the whole blast radius. Second, narrower remnant of the same side-channel: a mutation that
  lands EXACTLY on the zero-filled triple (`actor move --to 100,200,0` on such an actor) still
  parses back equal, so the omitted axis keeps reading as the class default — that one can only
  ever cause a spurious ABORT, never a false pass. (2026-07-25 00:36 UTC; compare half fixed and
  item re-scoped 2026-07-25 02:15 UTC.)

- **[debug] p2 Four write paths still omit a property against a hardcoded zero/constant.** The
  2026-07-25 00:36 UTC contraction work established "no write path omits a property to mean zero"
  (an omitted property re-imports as the CLASS DEFAULT) and fixed it in `dispatch`/`normalize`/
  `transform`. These four were left, all measured harmless against the CURRENT DX class set but all
  the same shape: `movers.set_key_pos`/`set_key_rot` drop an all-zero `KeyPos(i)`/`KeyRot(i)`;
  `movers._set_numkeys` drops `NumKeys` when it equals a hardcoded **2**; `movers.canonicalize_mover`
  deletes `Rotation` when the base pose folds to identity — **and that one runs on the map-INGEST
  path, into the durable trunk**; `native/materialize.py:456-461` skips a zero `Location` (the
  `Engine.Camera` bug verbatim, unwired from the CLI today). Not fixed with the rest because
  rewriting mover keyframe emission churns every mover trunk on disk for a case no `Engine.Mover`
  subclass currently reaches (verified: none defaults `NumKeys`/`KeyPos`/`KeyRot`, and the only
  class defaulting `Rotation` is not a mover). Surfaced by both cold reviews. (2026-07-25 00:36 UTC.)

- **[chore] p3 Two warm-editor spike harnesses compare editor exports with `canonical_level_hash`.**
  `dev/docs/spikes/2026-07-18-warm-editor-materialize/harness/warm_editor_canoncmp.py:52` and
  `warm_editor_probe.py:194` hash two editor exports against each other. Since 2026-07-25 00:36 UTC
  that hash is pure/schema-free (no LevelInfo-name rewrite, no float32 quantization, no dropped poly
  `Normal`), so those harnesses would now report round-trip noise as a real difference. They are
  committed evidence for the warm-editor acceptance criterion, so they should move to
  `normalize.compare_view` (which needs a `ClassDefaults`, hence a resolver — and since
  2026-07-25 02:15 UTC returns typed `ActorValues`, not text) before being re-run.
  (2026-07-25 00:36 UTC, cold review.)

- **[debug] p3 bspcsg core: `first_add_seed` treats ANY leading `CSG_Add` as the convex world
  SHELL.** *(No longer blocks the CSG merge verbs — `brush deintersect` prepends a distant
  seed-subtract so the shortcut cannot fire, and all 17 goldens match the editor. Still open
  for `level materialize` and any other caller whose first brush is a non-shell Add, hence
  demoted to p3 rather than dropped.)* When the first brush filtered into a node-less world is an Add, the core skips
  classification and SEEDS its faces as world root nodes stored REVERSED (`bspcsg.rs`, the §92 §32
  convex seed). That is right for the one case every real level opens with — the first Add IS the
  world box — and wrong for an Add that is a small solid sitting inside what a later subtract turns
  into void: the seeded faces survive as splitters. **Verified divergent against the live editor**
  2026-07-25, case `h_leading_additive_deintersect` (`brush deintersect` over `[Add pillar,
  Subtract room]`): UnrealEd classifies normally, the later subtract cuts the pillar's faces away,
  and it returns the plain 6-poly room void; native returns 22 polys — the void with the pillar
  punched out. The code comment already states the assumption ("a NON-convex first Add would need a
  real recursive `bsp_build`"); this is the first measured case where it bites. NOT fixable in the
  verbs: `deintersect` cannot prepend scaffolding to move the seed off the user's first brush,
  because any synthetic brush INSIDE the builder hull contributes faces that Phase 2 collects as
  caps (a leading no-op wrap-ADD was measured to turn the doorway plug into the whole padded box) —
  the working fix was a subtract placed OUTSIDE the hull. Golden `h_leading_additive_deintersect`
  is committed and PASSING. (Found building intersect/deintersect, 2026-07-25.)
- **[implement] p2 bspcsg core: apply scaled brushes (port the coarse core's `MainScale`/`PostScale`
  math into `build_geometry_bspcsg`).** The default incremental core `build_geometry_bspcsg`
  (`bspcsg.rs:2064`) **rejects** any non-identity-scale brush ("scaled brushes are not yet supported"),
  while the older coarse `build_geometry` DOES apply scale (`_build_brush_input`, built 2026-07-19,
  `done.md`). So the bspcsg core — the default for materialize AND the base for the new
  `brush intersect`/`deintersect` — cannot build any map or set containing a scaled brush. **Deferred
  from the intersect/deintersect feature** (`specs/2026-07-24-intersect-deintersect-native-brushset.md`
  §6) with this as the tracking item, per Andrzej ("if we defer scale, we need a prioritized board
  item"). Cross-cutting: also gates bspcsg materialize of real (scaled) DX maps. Scope: apply the linear
  part `L = PostScale·R·MainScale` to the brush polys where the coarse core already does, drop the
  `bspcsg.rs:2064` reject, add a scaled-vs-explicit differential test (mirror `test_native_scale.py`).
  (Andrzej, 2026-07-24.)
- **[spec] p2 `brush identify` — classify a real brush's shape + reverse-map it to a generator (2026-07-24).**
  Two coupled capabilities surfaced by the corpus brush-idiom study (`specs/2026-07-24-corpus-brush-idioms.md`
  §7 gaps 2+3): (a) given a brush's polys/verts, **name its shape** against the generator vocabulary
  (`cube`/`cylinder`/`cone`/`sheet`/`staircase`/`spiral`/2D-extrude) or tag it *freeform*; (b) emit the
  **`brush build <shape> --params…` invocation that reproduces it** (or report non-generatable freeform).
  No verb today — `brush poly list`/`vertex list` give raw geometry, not a shape identity. Bias toward
  reporting *freeform* when params don't reproduce within tolerance (a too-eager classifier hides the
  overbuilding the study exists to catch). The study's harness prototypes this; promoting it to a verb
  (`brush identify [--as-generator]`) is the gap. Enables the reverse-mapping deliverable AND is generally
  useful (remix/dedup/lint real brushwork). (Andrzej-adjacent, flagged 2026-07-24.)
- **[debug] p2 `actor preview` with NO target set silently no-ops (exit 0, renders nothing) — should ERROR.**
  `actor preview --focus X` (or any flags) with **no positional names and no `-`** hits
  `_resolve_target_names(args.names)` → empty `raw` → `return 0` (`dispatch.py:3651-3654`) — a preview
  command that produces no image and says nothing, exit 0. Violates direction.md "No silent
  half-answers" (a command that can't satisfy the request must fail cleanly, exit 2, naming the problem).
  Should error e.g. `actor preview: no actors to render — pass names or - (a piped set)`. **Keep the
  DELIBERATE empty-`-`-stdin no-op distinct:** `actor find … | actor preview -` with empty stdin is a
  clean exit-0 no-op (the composable-pipe convention) and must stay — only the *no-set-at-all* case
  (no names, no `-`) should error. Cost me ~20 min of "exit 0 but no file" debugging. (Andrzej, 2026-07-25.)
- **[debug] p3 `parse_coord`/`parse_pan` accept `nan`/`inf`/`snan` (same class as the fixed `parse_bbox`).**
  `decimal.Decimal("nan"|"snan"|"inf")` construct fine, so they slip past the `except InvalidOperation`
  guard in `cli.parse_coord` (and likely `parse_pan`): `--at nan,0,0` yields a NaN triple that misbehaves
  downstream, `--at inf,0,0` a silent infinity. `parse_bbox` got a `.is_finite()` check (2026-07-24 review
  of `--within-bbox`); apply the same guard to `parse_coord`/`parse_pan` and add non-finite cases to their
  parse tests. (Flagged by the `--within-bbox` cold review, 2026-07-24.)
- **[chore] p3 `brush stats` — per-map poly/vertex complexity histogram (2026-07-24).** Minor: aggregate
  per-brush poly/vertex counts across a level (the complexity-budget number for the corpus study,
  `specs/2026-07-24-corpus-brush-idioms.md` §7 gap 5). Scriptable today from `brush poly list` + `model.py`;
  a dedicated verb is a nice-to-have, not a blocker. Consider folding into `brush identify` output.
- **[spec] p2 `find` RELATIONAL predicates — the deferred third "conditionals" family (2026-07-24).**
  Cross-actor reference filters, beyond what `--prop Base=X` incidentally catches: e.g. `--references
  <actor>` (actors whose object-prop refs point AT the target), mover/trigger pairing by `Tag`/`Event`,
  actors sharing a `Group`. Substrate-specific semantics (which fields are refs; DeusEx vs stock
  Unreal), the most complex of the three families — Andrzej deferred it while the property + spatial
  specs (`specs/2026-07-24-find-prop-predicates.md`, `specs/2026-07-24-find-spatial.md`) go first. Adds
  ATOMS to the composable-`find` boolean model, orthogonal to it. Spec when the first two land.
- **[spec] p1 Composable `actor find` — a stdin name-set input for FULL boolean queries (2026-07-24).**
  Today `find`'s repeated filter = OR within a dimension, different filters = AND across them; there is
  **no same-dimension AND** (`--label X --label Y` is X OR Y, not "both") and **no NOT**. Rather than a
  `--where` expression DSL (a whole grammar + a second filter syntax competing with the `--label`/
  `--folder`/`--class` flags + poor pipe-composition), make `find` a CONSUMER of a name-set as well as a
  PRODUCER: **`actor find <filters> -` restricts the search to the piped-in actors** (intersection),
  with **`--exclude`** subtracting instead. Boolean algebra then falls out of pipes, exactly like the
  mutating verbs' `-` convention: **AND** `find --label X | find --label Y -`; **AND across dimensions**
  `find --folder castle.** | find --exact-class Light - | find --label hero -`; **OR** repeated flag or
  `{ find --label X; find --label Y; } | sort -u`; **NOT** `find --label Y | find --label X --exclude -`
  (X ∖ Y). One capability → full boolean, no DSL, no per-dimension `--all-labels` flags. Keep repeated
  `--label` as OR (consistency with `--folder`/`--group`/`--exact-class`); AND comes from chaining.
  **Orthogonal to the actor-labels spec** — a general `find` feature benefiting every dimension; do NOT
  bloat the label spec with it. Rejected alternatives: `--where` DSL (overkill, second syntax);
  per-dimension `--all-labels` (narrow, no NOT); explicit `actor intersect`/`diff` verbs (clunky
  two-input, need process substitution — subsumed by the stdin restrict). Raised while speccing
  actor-labels (`find --label` OR-within); Andrzej flagged high-prio.
- **[spec] p1 `actor find --exclude` must NOT require actors on stdin (refinement of the composable-`find`
  item above, 2026-07-24).** `--exclude` used WITHOUT a piped-in set should not error/no-op — it should
  simply SUBTRACT the actors that match the filters from the whole level and return everything else (the
  complement over all actors), i.e. `find <filters> --exclude` = `all-actors ∖ (matched-by-filters)`. With
  stdin it subtracts from the piped set (`piped ∖ matched`, per the item above); without stdin the implicit
  set is the whole level. This makes plain NOT a single command (`find --label hero --exclude` = every actor
  that is NOT `hero`) instead of forcing the two-stage `find <all> | find --label hero --exclude -` pipe.
  Fold into the composable-`find` spec — it's the same `-`/`--exclude` design, just fixing the default input
  set when stdin is absent. Andrzej flagged.
- **[spec] p2 Commands that accept actor names on STDIN (`-`) should ALSO accept them as positional args
  (2026-07-24).** Every consuming/mutating verb that reads its target set from stdin via `-` should equally
  take the same names directly on the command line, so `actor prop set Foo Bar Texture=…` works without a
  `printf 'Foo\nBar' | ... -` dance. Revisits the current CLI convention that `-` is the SOLE names source,
  mutually exclusive with CLI args (uedcli `CLAUDE.md`): positional names and `-` stay mutually exclusive
  per-call, but a verb must offer BOTH intake modes, not stdin-only. Audit which consuming verbs are
  currently stdin-only and add positional intake where missing. Andrzej flagged.
- **[spec] p2 Rename `brush build --mover-class` → `--brush-class`, and enforce the class descends from
  `Engine.Brush` (inclusive) (2026-07-24).** The flag currently names a Mover class (`brush build
  --mover-class <Package.Name>`, direction.md "Generator pattern"), but the general shape is "which brush
  actor class to emit" — a Mover subclass is just one case, and the value must be `Engine.Brush` itself or
  any descendant. Rename to `--brush-class` and VALIDATE at parse time via the class hierarchy
  (`ClassIndex.descends_from(cls, "Engine.Brush")`, inclusive — accept `Engine.Brush` and every subclass);
  reject a non-Brush class with a clear exit-2 error naming the offending value, never a traceback. Update
  `docs/usage.md` + `direction.md`'s generator-pattern note. Andrzej flagged.
- **[flag] p2 Proposal: collapse level/stash/prefab into ONE flat "tree" concept — rename the `level`
  concept → `tree`, a `Trees/{Maps,Stash,Prefabs}/<name>/` layout with an auto-created `Trees/.gitignore`
  ignoring `Stash/`, `UEDCLI_LEVEL`→`UEDCLI_TREE`, `--target`→`--target-tree` (Andrzej idea, 2026-07-22).
  MY EVAL: recommend AGAINST the wholesale rename/reorg — the valuable core already shipped and the
  residual is net-negative.** ALREADY DONE (so this is NOT greenfield): the three share ONE T3D-tree
  format (`t3dtree.py`, invariant 2026-07-18 23:01), and "tree" is ALREADY the umbrella — `--tree
  KIND/NAME` (KIND ∈ level|stash|prefab) *replaced* `--target` on 2026-07-20 21:30. So
  `--target`→`--target-tree` is moot: the flag is `--tree` now, and `--target-tree` would re-introduce
  the exact "target" word that was rejected then (source-vs-destination wart + `materialize --out`
  collision) plus redundancy (the value already names the kind). Objections to the residual:
  **(1) the KIND distinction is load-bearing, not incidental** — same *format*, genuinely different
  *kinds*: a **level** materializes to a playable `.dx`/`.unr` (git-tracked domain object), a **stash**
  is machine-local throwaway (captured/applied, no world), a **prefab** is a git-committed shareable
  library artifact (placed; `packages`+`meta.json` siblings). `level materialize`/`preview` are
  level-only *because a stash/prefab has no world to build*. A flat `tree create/materialize/apply`
  doesn't erase the kinds — only the word for them — so you'd trade named kinds (clear) for per-verb
  "not valid for this kind" errors (worse). **(2) "tree" is already taken:** terminology (2026-06-23)
  fixes **T3D tree** = the on-disk directory FORM shared by all three, and **level** = the playable
  domain object; renaming level→tree collapses the content/container distinction and makes "tree" mean
  both. **(3) moving stash into `Trees/Stash/` erodes the `.uedcli/` safety invariant** (direction.md:
  ALL machine-local throwaway — stash, flocks, staging temps, delivered preview maps — sits in ONE
  self-ignoring gitignored `.uedcli/`); it splits throwaway state across two homes and swaps a
  self-ignoring dir for a tracked dir + carve-out `.gitignore` (more fragile — a mis-edit commits
  scratch; the other `.uedcli/` tenants still can't move). **(4) the `Trees/{Maps,Prefabs}/` root
  re-forces the parallel tree that the project-layout decision (2026-07-17 20:58) explicitly rejected**
  — maps-dir/prefabs-dir are independently-configurable relative paths with defaults *so uedcli can
  point at a repo's EXISTING dirs* (LUM already has `Maps/`, `Prefabs/` at their own locations).
  **(5) `$UEDCLI_LEVEL` is deliberately a BARE level name** — the ambient default is "which LEVEL am I
  editing"; you never ambiently edit a stash/prefab (those are always explicit `--tree stash/x`), so
  `$UEDCLI_TREE` (implying `KIND/NAME`) is meaningless as an editing default. SALVAGEABLE: a single
  `Trees/` root with an auto-created `.gitignore` is a genuinely nice ergonomic *default* IF decoupled
  from forcing the layout AND from moving stash out of `.uedcli/` — but given (3)/(4) probably not worth
  the churn. DECIDE-OR-DROP: your call; record in `decisions.md` if you pursue any of it.
- **[debug] p3 Re-evaluate whether `_reject_nonlevel_target_for_folders` is STALE post-unify (2026-07-22).**
  Folder verbs reject a `--tree stash|prefab` target (`dispatch.py:1707,3011-3021`), a guard from before
  the unify-T3D-trees change gave stash/prefab real per-actor sidecar slots (folders now persist there —
  `stashlib.py:101-109`). The actor-labels spec proposes labels ARE allowed on `--tree stash|prefab` (the
  sidecar exists); if that's right, the folder guard is inconsistent and probably stale. Decide: drop the
  folder guard too, or keep both trunk-only. Ref: `specs/2026-07-22-actor-labels.md` §11.4.
- **[flag] p3 `actor preview` overlays are POINT-actor-only (built 2026-07-21).** `--show-collision`
  / `--show-light-range` / `--show-sound-range` resolve fields ONLY for point actors (`actor.brush is
  None`), so a colliding BRUSH mover (`bCollideActors=True`) draws no cylinder. Chosen to keep the
  "brush-only preview is schema-free / works with no game install" guarantee strict — resolving a
  brush's collision would force a schema load for a brush actor. The `actor-preview` spec §3 says
  "every previewed colliding actor"; this narrows it to point actors. Fine? If movers should show
  collision, we'd resolve schema for brush actors too when an overlay flag is set (breaking the
  schema-free-brush guarantee only under `--show-*`).
- **[flag] p2 `level preview --game` blocked on this box: TWO independent gaps found (2026-07-21).**
  Dogfooded the whole path — installed GOG Deus Ex (1.112fm) at `~/Games/DeusEx`, ran
  `dev/scripts/install-deusex-assets.sh` (clean), previewed. `--native` renders brushdemo fine.
  `--game` is blocked by:
  **(1) The `edit/` UCC toolchain is unprovisioned.** `preview_game.py` gates on
  `uedcli/game/inputs/edit/hUCC.exe`. The 9-file set is user-supplied/gitignored (uplayctl provenance)
  and is NOT anywhere on this box (`../uplayctl/game/inputs/edit` absent). `hUCC` = **Hanfling's** UCC
  (a community build matched to the DX **v68** engine), NOT "headless" — plain `UCC.exe` is already a
  headless CLI tool; `UnrealEd.exe` is the GUI binary that wedges open. **Can `uned/UED22/UCC.exe`
  substitute? Investigated in depth (harness `_scratch/ucctest/*.sh`; results `result*.log`) —
  PARTIAL:**
  - Run UED22's UCC **in its own dir with its own v469 DLLs**, it compiles the engine-only
    **`UedPreview.u` cleanly** (my first "it fails with `appChdirSystem`" test was mis-set-up — UED22's
    v469 `UCC.exe` against the game's v68 `Core.dll`; discount it. In its own env it works.)
  - It **CANNOT compile `UedPreviewDX.u`** (the DeusEx driver): `Unrecognized member 'ShowHud' in class
    'DeusExPlayer'`. Two-sided wall: (a) UED22's committed `DeusEx.u` is a mesh/structure stub —
    **method-stripped** (the `DeusExPlayer` type resolves, but its methods `ShowHud`/`inHand`/… are
    absent); (b) the **full v68 `DeusEx.u`** (which has those methods) can't load under UED22 because it
    references `Core.Object.Sprintf` 73× — a function DeusEx added to its **v68** `Core` (verified: 3
    hits in game `Core.u`, **0** in UED22 `core.u`).
  - **So UED22's UCC builds the base package but not the DX driver → Hanfling's `hUCC` (matched Core
    with `Sprintf`) is genuinely required for the driver half.**
  - **Candidate unblock WITHOUT `hUCC`:** teach the stubber to preserve function **declarations**
    (empty bodies) so `UedPreviewDX` can typecheck its call paths against a fuller `DeusEx` stub under
    UED22's UCC — it needs the signatures, not the `Sprintf`-dependent bodies. Open question whether the
    stubber can emit method decls without the bodies. (Alt: provision the Hanfling `edit/` set.)
  - **Precompile + COMMIT `UedPreview.u`/`UedPreviewDX.u`** still needs ONE working v68 UCC (`hUCC`, or
    the stubber fix above) to do that first compile — so it's a fix, not a bootstrap.
  - Harness scripts live in `_scratch/ucctest/` (gitignored → will be wiped); promote to
    `dev/docs/spikes/` + add an engine-fact regression (the `Sprintf` v68-Core divergence, the stub
    method-stripping) if this is pursued.
  **(2) DinD asset-path visibility.** This box runs Docker-in-Docker; the daemon sees the repo tree but
  NOT `~/Games` — a container mount of `~/Games/DeusEx` comes up EMPTY (verified: repo path → 93 files,
  home path → 0). So `~/.uedcli [games.deusex].paths` MUST point at the in-repo `dev/games/deusex/`
  (fixed 2026-07-21), not `~/Games`. `--native` didn't catch this (it's in-process/host-side). Worth
  deciding whether uedcli should detect/repoint or document this for the global-CLI model, since
  `~/Games`-style paths are the natural user choice and silently yield empty mounts under DinD.
- **[docs] p2 `deusex-assets-setup.md` "How it's wired" cites the RETIRED `packages.substrate_code_dirs`
  symbol + a stale host-side resolution mechanism.** Cold review (2026-07-21) found the "Host-side
  resolution" bullet asserts `packages.substrate_code_dirs` resolves manifests against
  `DeusExAssets/{Textures,Sounds,Music}`; that symbol is retired (`dispatch.py` calls it "the retired
  hardcoded `substrate_code_dirs`/`texture_catalog_root`", decisions.md 2026-07-14). Current path is
  `packages.editor_search_dirs` + `_remap_to_container` + `ensure_load` over the composed config search
  path (architecture.md ~1532). Pre-existing (not introduced by the dev/scripts move); needs the live
  symbols verified before rewriting the bullet. Same doc, "How it's wired" section.
- **[docs] p3 `uned/deusex-installer/` is framed as a managed setup home in `architecture.md` (~1496-1503)
  but the SOURCE-arg script never uses it.** Cold review (2026-07-21): `install-deusex-assets.sh` takes
  any `SOURCE` path and (for ACE) extracts into `dev/games/<game>/`; it never reads/writes
  `uned/deusex-installer/`. Main setup doc caveat already softened (2026-07-21); `architecture.md`'s
  "raw installer lives at uned/deusex-installer/" framing is the remaining vestige. Also re-check the
  "Verify it worked" expected package counts (System ~17 / Textures ~57 / Sounds ~2 / Music ~35)
  against a real install when one is available.
- **[flag] p3 Should `dev/docs/` move to `dev/docs/`? (raised 2026-07-21 when `install-deusex-assets.sh`
  moved to `dev/scripts/`.)** The script move created a top-level `dev/` tree, so now "dev-facing stuff"
  lives in two places: `dev/scripts/` (new) and `dev/docs/` (existing). Moving `dev/docs/` → `dev/docs/`
  would ostensibly consolidate everything dev-facing under one `dev/` root. **My recommendation: DON'T,
  UNLESS it's step 1 of a full product-vs-dev reorg** (see last point). Churn/`git blame` cost is NOT
  the objection (Andrzej doesn't mind it); the substantive reasons are: (1) **The consolidation is
  illusory.** Dev machinery is already scattered and stays scattered — `bin/` (`test`, `_venv.sh`),
  `uned/` (`bake_ued22.sh`, `wine_ctl.py`, `entrypoint.sh`), `tests/`, `uedcli-native/`. Moving
  `dev/docs/` adds a THIRD dev location (`dev/docs` + `dev/scripts` AND still `bin/`+`uned/`+`tests/`),
  it doesn't unify. (2) **`docs/` is already a clean audience-split doc root, one level down:** `usage.md`
  + `leveldesign/` (user) vs `dev/` (dev), with `docs/README.md` the authoritative router. Pulling `dev/`
  out relocates one arm of an existing clean split to a farther root and ORPHANS `docs/README.md` (it
  now routes across roots). (3) **The name misdescribes the content.** `dev/docs` = "the dev section of
  the docs" (accurate: the corpus is fundamentally documentation — architecture, decisions, unrealed
  knowledge, board, specs, plans); `dev/docs` = "the docs corner of dev" inverts what the thing is.
  (4) It isn't pure docs anyway — `dev/docs/spikes/` holds ~209 committed `.py` harness files; `dev/docs`
  honestly frames it as "dev knowledge base incl. evidence," `dev/docs` promises docs then hides scripts.
  **When it WOULD make sense:** as step 1 of a real top-level split — **product** (`uedcli/`,
  `uedcli-native/`, `bin/uedcli`) vs **development-of-product** (everything else: docs, spike harnesses,
  `bin/test`, the `uned/` build scripts, `tests/` all under `dev/**`). Then `dev/docs` is coherent and
  reason (3) weakens. So the decision is about SCOPE, not effort: one-off doc relocation (no) vs commit
  to pulling ALL dev machinery under `dev/` (yes — then do the whole reorg, don't half-move). Andrzej:
  keep/drop/expand-scope — your call.
- **[implement] p2 Native CSG core assumes CONVEX brushes — decompose or guard for non-convex builder
  output.** Surfaced by the one-actor `brush build` review gate (2026-07-21). `uedcli-native/src/
  csg.rs:60` `point_in_convex` classifies "inside" as behind EVERY face (the convex hull), and
  `csg.rs:61`'s comment "DX brush builders emit convex brushes, so this is exact" is now **falsified**
  — the single non-convex staircase brush mis-builds on `level preview --native` + native `level
  materialize` (concave notches fill solid). Confined: default UnrealEd materialize + `--game` preview
  are correct (see `decisions.md` 2026-07-21 12:22). Fix = decompose a non-convex brush into convex
  pieces on the native CSG path (or guard + warn). Joins the documented ~11% native solidity
  divergence (`architecture.md:1141`).
- **[spec] p2 Derive `actor prop`'s reject set from editor-editability, not a hard-coded list.**
  Today `propedit.HARD_REJECT` is a hand-maintained deny-list (`name`, `brush`, `keypos`, `keyrot`,
  `keynum`). Instead, block a prop when UnrealEd itself would not expose it as editable — the
  principled source of truth. The schema decode already carries the signal: `Prop.property_flags`
  (the `CPF_*` bits; the editor-edit flag is `0x1`) and `Prop.category` (`None` for a non-editable
  plain `var`, set for an editable `var(Category)`). **Reconcile the two axes at spec time:**
  editor-editability ≠ uedcli policy. Some editor-editable props are still uedcli-owned-elsewhere and
  must stay blocked (`keynum` is editable but we canonicalize it to 0; check whether `name` carries
  the edit flag), and `keypos`/`keyrot` are authored via `mover key` (verify they're non-editable so
  the gate blocks them for free). So the likely shape is "not editor-editable → block" PLUS a small
  explicit policy set for editable-but-uedcli-managed props. Consistent with the 2026-07-20 16:18
  decision that `NumKeys` (editor-editable) is settable. Ref: `propedit.HARD_REJECT`, `uprops.Prop`.
- **[implement] p2 Reimplement UnrealEd's `PATHS DEFINE` in uedcli.** Build the AI navigation network
  (reachspecs between `PathNode`/`NavigationPoint` actors) natively, the way the editor's `PATHS DEFINE`
  console command does, so pathnoding is drivable offline instead of only via the editor. Needs a spike
  to decode what `PATHS DEFINE` actually computes/emits (reachspec fields, connectivity/collision
  probing, which actor classes participate) before it can be specced.
- **[spike] p2 §92 STAGE 2 DONE (dome CAP), STAGE 3 = the dome's SLOPED facets.** Stage 2 decoded the
  `Brush755` dome divergence: the cause was NOT `SplitWithPlane`/`TryToMerge` but a MISSING per-brush
  pre-pass — the editor's **`bspValidateBrush`** (`Editor.dll 0x37290`) `iLink`-shares coplanar
  same-facing brush faces into ONE surf. Ported into `bspcsg.rs::bsp_brush_csg` (finalized-normal gate,
  exact-axis kept, temp-space remap): UNATCO N=105 `only-native` **28→20**, castle byte-identity
  UNCHANGED, N=104 clean; regression + two cold reviewers resolved. Decision `decisions.md` 2026-07-19
  08:58 UTC; §92 §11; spec `specs/2026-07-19-unatco-dome-csg-divergence.md` (LANDED). **Stage 3:** the
  20 residual `only-native` at N=105 are the dome's SLOPED (non-coplanar) facets — a class
  `bspValidateBrush` does not touch. Re-bisect `unatco_subset.py bisect 105 762` on `only-native` for
  the next first-divergence, decode + port + castle-gate. `only-native` grows 28→534 over N=105→762 —
  still a handful of classes / weeks of cycles.
- **[chore/flag] p2 §92 STAGE 0 done — parity BASIS corrected to bare `MAP REBUILD` (GOOD); a
  PROVISIONAL default change to confirm.** Built the `MAP REBUILD;BSP REBUILD GOOD OPTGEOM ZONES`
  golden (editor did NOT wedge — the two prior wedges were a false-idle artifact; fix = generous
  barrier `--quiet-reads 30`, now the required setting for BSP-REBUILD goldens at UNATCO scale).
  **Measured finding overturning the plan's hypothesis:** `BSP REBUILD GOOD` re-partitions to **7273
  nodes — MORE than OPTIMAL (6859)**, so it does NOT reproduce native's csgRebuild partition (§92 §2
  option (b) REJECTED). native's TRUE node basis is the **bare `MAP REBUILD` golden (6314)** →
  native **+111 nodes (+1.76%)**, +82 surfs, +146 vectors (surfs/vectors invariant to all 4 rebuild
  paths). **PROVISIONAL CALL I made (please confirm):** changed `build_ued_golden.py`'s
  `--rebuild-cmd` DEFAULT from `OPTIMAL OPTGEOM ZONES` to a bare `MAP REBUILD` (native's node/surf/
  vector basis) — the clean-leaf `GOOD OPTGEOM ZONES` variant is now opt-in. This means the two
  parity bases are SEPARATE (no single rebuild path gives both native's node partition AND a clean
  refs/leaf==1.0 leaf array); `bsp_health_check.py` still flags a bare golden's stale leaves (correct
  — means "don't use its LEAVES", not "its nodes are wrong"). If you'd rather the default stay a
  clean-leaf ZONES golden, say so.
- **[spike/chore] p2 UnrealEd-golden parity basis landed (spike §89) — TWO follow-ups.** The correct
  native-parity basis is now UnrealEd's OWN build of the SAME trunk, not the shipped `.dx`
  (`harness/build_ued_golden.py`; proven on UNATCO). Findings: (a) UnrealEd BUILDS our trunk headless
  fine, deterministically (~30 s), BUT `apply.run_materialize` cannot do it at scale — its editor
  driver `wine_ctl exec` is fire-and-forget (~0.3 s, no wait-for-completion), so `MAP SAVE`/`docker cp`
  race the still-running rebuild and fail "nothing written". The harness works around it with a CPU
  idle-barrier. **Should this barrier fold into production `run_materialize`/`driver`?** (I did NOT
  touch the concurrent-session file.) (b) vs the golden, native's geometry SOUP is near-exact
  (Points −0.07 %, Bounds +0.2 %, LeafHulls −0.6 %) but native **over-splits Leaves 3.6×** (2759 vs
  762) and over-produces Vectors/Verts ~+24 % — native builds a less-merged BSP than UnrealEd's `GOOD`
  batch rebuild of the identical brushes. That is the sharpest geometry target now; chase against the
  golden, not the shipped map. (Methodology validated: UnrealEd batch-rebuild vs the incrementally-
  authored shipped map differ +21.7 % nodes / −66 % leaves on the SAME 734 brushes — most of §84's
  native-vs-shipped gap was that, not native.) **[SUPERSEDED re: Leaves by §91 — the "over-splits
  Leaves 3.6×" was a CORRUPT GOLDEN, not a native defect; see the §91 item below. Vectors +24 %
  stands as a real residual; re-measure Verts once the golden is re-cached un-truncated.]**
- **[chore] p2 §91 — the "native over-produces Leaves 3.6×" gap is a CORRUPT batch golden, NOT a
  native defect (spike §91, decode-proven).** The batch golden's `Leaves` array is a truncated/partial
  MAP-SAVE capture: its own tree has **4454** empty terminal cells but only **762** leaf entries
  (refs/leaf 9.45 — impossible for a completed Pass A, which appends one leaf per cell). Native (2759,
  refs/leaf **1.00**) and the real shipped `03_NYC_UNATCOHQ.dx` (2266, **1.00**) are BOTH correctly
  1:1 — native's leaf policy matches UED22's disassembled Pass A (§70 §2). **No leaf fix is needed in
  native.** The defect is DETERMINISTIC, not a barrier-timing truncation: a generous-barrier rebuild
  (`--quiet-reads 30 --rebuild-min-seconds 90`, knobs added §91) gives a BYTE-IDENTICAL Model body
  (still 762 leaves), so a longer wait does not fix it. Two follow-ups: **(a)** root-cause why the
  headless `ed.rebuild()` path emits a non-1:1 `Leaves` array AND an under-built `Verts` pool (golden
  verts/node 12.11 vs shipped 15.90 — likely the same headless `MAP REBUILD` not running the full
  `TestVisibility` leaf-enum + Pass-D vert re-emit) — until fixed, the cached goldens' `Leaves`/`Verts`
  are un-gradeable, use the shipped map + native §70 invariants; **(b)** add a `distinct(iLeaf) ==
  len(Leaves)` (refs/leaf == 1.0) assertion to `bsp_health_check.py` so this golden is rejected at the
  door (it currently only range-checks `iLeaf`, which is why the invalid golden passed).
  **✅ BOTH DONE (§91 §9, 2026-07-19).** (a) Root cause: `MAP REBUILD` (== `BSP REBUILD GOOD`, NO
  `ZONES` keyword) runs csgRebuild+bspBuild but NOT the visibility/leaf pass — `AssignLeaves` is gated
  on the `ZONES` keyword of the SEPARATE `BSP REBUILD` parser (Editor.dll 0x65482, skipped via `je`
  when ZONES absent), so the on-disk `Leaves` stays the stale incremental-paste array (signature: 2750
  iLeaf slots on NON-terminal nodes). Decode-confirmed via UTF-16 exec tokens + vtable-slot 0x264.
  FIX = the two-step full rebuild `MAP REBUILD; BSP REBUILD OPTIMAL OPTGEOM ZONES` (BSP REBUILD alone
  gives an EMPTY model — no csgRebuild); now `build_ued_golden.py`'s `--rebuild-cmd` default. (b) The
  refs/leaf==1.0 assertion is in `bsp_health_check.py` (rejects the old cached goldens, exit non-zero).
  **Corrected UNATCO golden: Leaves 2934 (refs/leaf 1.00), Verts 98152, Zones 9 — vs native the "3.6×
  Leaves" is now −6 % (both 1:1), "+24 % Verts" is now −3.5 %, "+2 Zones" is now EQUAL (9=9).** The
  ONLY real residual is `Vectors +24 %` (shipped 596 ≈ golden 599, native 745). **ROOT-CAUSED
  2026-07-19 (§91 §10, decode-proven — OVERTURNS the earlier "extra node-plane normals / §80
  leak-repair flipped planes" guess):** the excess is **entirely texture axes** (vTextureU +105,
  vTextureV +50; surf normals IDENTICAL at 257/257/257) carried by native's **extra surfaces** from
  the less-merged CSG partition. Node planes are stored INLINE and never enter `Vectors`, so the
  leak-repair contributes ZERO vectors; matched surfaces agree exactly (no sign bug); and the editor
  itself keeps n/−n as separate vectors (golden 310 negation pairs) so "dedup n/−n" is wrong.
  **No localized `bsp_add_vector` fix exists — closing Vectors couples to the incremental-`bspBrushCSG`
  port** (§80 §5, the same work that closes node/surf topology). + the §70 §13.3 CSG-shatter zone
  residual on native's OWN builds. Castle golden stays 1:1 under the fix.
- **[spike/plan] p2 Real-level (UNATCO) CSG byte-parity — SCOPED + staged plan (spike §92, 2026-07-19).**
  Corrects the §91 §9.4 framing and splits the real-level residual into TWO clean pieces, with the
  incremental-`bspBrushCSG` port already DONE + byte-exact for the castle. **(1) The "native −6 % nodes /
  −1067 solid" vs the §91 golden is a PARITY-BASIS ARTIFACT, not a native defect** ✅: the §91 golden is
  `MAP REBUILD; **BSP REBUILD OPTIMAL** OPTGEOM ZONES`, and the `BSP REBUILD OPTIMAL` step re-partitions
  the whole BSP with OPTIMAL (stride 1) — which native does NOT model (native = `csgRebuild` = GOOD/12).
  Against the single-`MAP REBUILD` (GOOD) golden native is only **+111 nodes (+1.8 %, +163 solid / −90
  semi)** and the sign FLIPS. Proven from cached builds: both goldens carry identical 3616 surfs / 599
  vectors while nodes differ 6314 (GOOD) vs 6859 (OPTIMAL). **(2) The +82 surfs / +146 vectors residual
  is REAL and basis-independent** ✅ — the one genuine CSG-partition gap. By class: **+38 solid + +46
  semisolid**, BIDIRECTIONAL (174 only-native / 92 only-editor — NOT a pure under-merge, so forcing a
  merge regresses, §82 §10.6). Born in the incremental `FilterWorldThroughBrush`/`bspMergeCoplanars`
  phase (surf-count-invariant to OPTIMAL vs GOOD; not `SplitPolyList`/`bspOptGeom`). **Follow-ups:**
  (a) **Stage 0 = fix the basis** (highest-leverage, no `bspcsg.rs`): grade the node tree against a GOOD
  golden, resolve the Leaves-vs-node basis tension (a `MAP REBUILD; BSP REBUILD GOOD ZONES` golden build
  wedged twice this session — the editor crash-proneness; decode `Editor.dll 0x65220`'s GOOD Balance if
  needed). (b) **Stage 1 = editor-tree oracle on UNATCO subsets** (the §82 §10.7 gdb-`bspAddNode` method,
  bisected over ~730 solid+detail brushes) to pin the FIRST surf-set divergence, then decode+port each class
  (castle-byte-gated). **Honest effort: WEEKS of staged oracle-driven work, NOT a few merge-rule fixes**
  — the castle already implements every known merge rule byte-exactly, so the UNATCO residual is by
  construction the next-order divergences it doesn't exercise. Full plan + attribution:
  `sections/92-bspbrushcsg-reallevel-port-plan.md`; harness `surf_class_diff.py`,
  `reallevel_brush_profile.py`.
- **[flag] p1 §92 real-level surf over-production (+82/+146) was STALE — current native 3609 vs golden 3616 (−7 under); needs direction on the next parity target (2026-07-19 reconcile).** The "+82 surf / +146 vector
  over-production" premise driving §92 §12's staged gdb-grind is obsolete: (a) `unatco_subset.py` had a MOVER
  CONFOUND (28 DeusExMovers pushed through world CSG → +221 phantom surfs; fixed `cd56c1ae2`), which
  manufactured the "170 axis-aligned over-production in (213,396]" redirect; (b) the +82 figure itself was
  measured against STALE pre-current-core `.dx` (3698 surfs). A fresh mover-clean `build_native_unatco.py`
  gives **3609 surfs vs golden 3616 = −7 (slight UNDER-production)**, two native paths agreeing. So the "weeks
  of gdb-grind for coplanar over-production" plan is retired. Open questions for Andrzej: is the −7 a real hole
  or the subtract-into-void baseline; what is the real remaining byte residual (compiled parity is only 19.07%,
  mass in Nodes/Verts/LeafHulls — `_scratch/baseline-reconcile/`); the +146 VECTOR delta is NOT stale (all
  texture axes, 745 vs 599); the golden-node-basis question is now less critical. Docs reconciled: `PARITY-STATUS.md`, §92 §2/§3/§12 banners, `decisions.md` bspValidateBrush note.
- **[finding] p3 Castle re-baselined onto its OWN UED batch golden — the ~58 % headline STANDS (spike
  §90).** Applied §89's method to the castle (`harness/build_ued_golden.py` FULL+LIT — every castle
  actor is an engine class, no `DeusEx.u` stub / world-only / mover contamination; golden deterministic:
  two runs byte-identical modulo header GUID/timestamps). Three RAW diffs: native vs golden = **58.08 %**
  compiled (per-section aligned positional, `harness/persec_bytematch.py`), native vs shipped = **58.07 %**
  — SAME number, so re-basing does not move the castle headline. And golden vs shipped `Test_Castle.dx`
  = **99.89 %** positional / identical Model-body SIZE / byte-identical in EVERY section except Nodes/
  Surfs/Lights (pure object-ref renumbering) / identical BSP topology (nodes 1156, leaves 384, surfs
  485, verts 16163). **Verdict: `Test_Castle.dx` IS effectively a clean batch UED build** (unlike UNATCO
  it has NO incremental-authoring inflation — it was purpose-built by one `MAP REBUILD`), so the 58 %
  was always a fair golden. The native gap is real geometry/encoding drift (Surfs 21 %, Verts 27 %,
  Lights 1.6 %), not a golden artifact. **Lesson:** a shipped map's fairness as a golden depends on
  batch-vs-incremental build — verify per level with a golden-vs-shipped diff before trusting it.
- **[spike/implement] p1 The REMAINING UE1 texture layouts** (Unreal Gold `RGB32`/`RGB64`/`RGB24`/
  `RGBA8`; 227 `BGRA8_LM`/`R5G6B5`/`RGB8`/`BGRA8`, and `BC4`+). Created by
  `specs/2026-07-25-native-texture-formats.md` decision 4 (Andrzej, 2026-07-25). The measured layouts
  (P8, BC1, BC2, BC3, `CompMips`) are covered by that spec; these have **zero samples anywhere on this
  machine**, and slot numbers are NOT portable between engines (Unreal Gold slot 2 = `RGB64` at 8 B/px
  vs 227 slot 2 = `R5G6B5` at 2 B/px — decisions.md 2026-07-25 06:30). So this needs **sample
  acquisition first** (a UT/227 content set, or a purpose-built export), then per-layout verification,
  then implementation — implementing from the definitions alone would return a plausible WRONG image
  (swapped channels) rather than an error. Until it lands, those slots produce the named
  `unverified-format` error, so nothing is silent.

- **[debug] p1 Native real-level LOAD — blocker 2 remaining (blocker 1 FIXED 2026-07-19, §88).**
  A native build of any REAL level (UNATCO/Catacombs/HK) does NOT reach the "5.5-min CPU hang" — it
  used to **fast-fail** first on ~~blocker 1~~ (now fixed). **~~Blocker 1: every actor class imported
  under `Engine`~~ — FIXED 2026-07-19:** `pkgref.build_class_package_index` scans the composed `.u`
  set for each class's real defining package (threaded into `Resolver._package_of_class`), so
  `DeusExMover`→`DeusEx.DeusExMover` etc. (77 DeusEx + 13 Engine class imports on NativeUnatco, zero
  misclassed). Boot-confirmed: the `Can't find Class Engine.DeusExMover` abort is gone; the load now
  reaches blocker 2. Regression in `tests/test_native_materialize.py`. (Closing the 9 355 prop-skip
  warnings + restoring Sound/Music imports was scoped OUT — it surfaces a separate `MyLevel`
  local-object-ref import defect; see the two follow-up chores below.) **Blocker 2 (behind it, the
  original hang, HARDER): a single-thread CPU loop in the software-renderer path during load.** With
  imports corrected, the map clears linking then spins ~92 % CPU forever, frozen before "Bringing
  Level up for play". `winedbg` puts the spinning thread in `deusex`-mainloop → `extension` →
  `engine` render → `softdrv`/`core`/`windrv::BitBlt` (NOT the linker/GC). Reproduces WORLD-ONLY
  (no DeusEx actors); the BSP is structurally sound (no cyclic/bad indices) — so it's the software
  renderer looping on the over-split/over-zoned WORLD during the load-time frame draw (an
  `OccludeBsp`-class pathology; ties to the §84 +33 % over-split / §70 20-vs-7 over-zoning lanes) or
  possibly a world-texture-reference defect (124 vs 133 tex imports, some group-less). Next test
  (§88 §7): small-world-subset vs full (renderer-BSP) and single-base-texture rebuild (texture).
  Evidence + reproduce: `sections/88-native-load-hang.md` + `harness/{load_hang_probe.sh,
  build_native_unatco_variant.py,build_native_unatco_qualified.py,bsp_health_check.py}`. (Found +
  root-caused 2026-07-19; supersedes the "UNATCO load-hang" framing in the older board notes below —
  the hang is real but sits BEHIND blocker 1.)

- **[debug] p2 Native prop-schema lookup skips every prop on a BARE trunk class (9 355 warnings on
  UNATCO); closing it surfaces a `MyLevel` local-object-ref import defect (§88).** `default_schema_
  lookup` early-returns `{}` for any unqualified class (`"." not in fqcn`), and real-level trunks
  store bare classes (`AllianceTrigger`), so ALL typed props are dropped ("not in class schema
  (skipped)"). Qualifying the bare class for the schema lookup (via `pkgref.build_class_package_
  index`, already built for the import fix) closes the warnings — BUT then object-property values
  that reference sibling actors (`Region.Zone=LevelInfo'MyLevel.LevelInfo0'`, `Base=`, mover
  markers, AmbientSound refs) emit a bogus **`MyLevel` PACKAGE import**, and the game fails the load
  with `Can't find file for package 'MyLevel'`. Intra-level object refs must resolve to the target
  actor's LOCAL export ref, not a package import (cf. the `Brush=Model'MyLevel.<shape>'` drop
  `materialize._trunk_to_actorspecs` already does). Fix both together: qualify-for-schema AND
  resolve local object-property refs to export refs. (Tried + reverted 2026-07-19 — the class-import
  fix landed without it.)

- **[chore] p3 Native real-level build drops all `Sound`/`Music` object imports (§88).** Editor 03
  emits 17 Sound + 1 Music imports (AmbientSound/actor sound refs); native emits 0 — the actor-prop
  emit path skips Sound/Music object properties (same bare-class schema early-out as the prop-skip
  debug item above; resolving props restores these 18 imports). Non-fatal (not a load blocker) but a
  fidelity gap; fold into the actor-property emit work. (Found 2026-07-19.)

- **[implement] p2 Native build emits Movers with an EMPTY private Model — a mover door has no
  geometry.** `assemble` reserves every non-default brush actor's `{shape}Polys` with
  `write_upolys_body([])` (an empty private Model); a STATIC brush's geometry lives in the world
  BSP so that's fine, but now that Movers are (correctly) excluded from world CSG (2026-07-19),
  a mover's brush geometry is in NEITHER the world model NOR its private Model → a native-built
  mover is a geometry-less actor (no visible/collidable door). Surfaced by the mover-CSG-exclusion
  cold review. Fix = populate a Mover's OWN private Model (its animated brush polys + the mover's
  own BSP/bounds/hulls) at assembly, the way UnrealEd does — separate unbuilt native-mover work.
  Until then the native build renders movers as empty actors. See `architecture.md` "World-CSG
  brush selection" + `materialize._in_world_csg` docstring.

- **[chore] p3 Pin the native zone flood against the actual RUST (not just the Python oracle), and
  test multi-zone Connectivity.** The zone-flood BlockPortal fix (§70 §13) is validated editor-exact
  via the harness oracle, and the shipped Rust is confirmed to reproduce the oracle on the native
  UNATCO/Catacombs trees (45=44+1, 43=42+1) — but `tests/test_zone_flood.py` runs the Python oracle,
  not the Rust; the only Rust-path zone tests (castle build, water-portal) are on NON-discriminating
  topology. Add a `uedcli_native` FFI entry that runs `assign_leaves_and_zones` on an externally
  supplied Model so a test can feed a shipped map's tree through the REAL Rust flood and assert
  editor NumZones — or a synthetic map through the materialize path where the infinite-quad and
  real-poly rules differ. Also: Pass F `Connectivity` (the zone adjacency bitmask) is untested on any
  multi-zone map, and it iterates the `MIN_AREA`-filtered `portals` list while barriers are not
  area-filtered, so a barrier pair whose only portal face is sub-`MIN_AREA` would lose its
  connectivity edge (empirically clean: castle byte-identical; flagged, not observed). (Cold-review
  findings, 2026-07-19.)

- **[spike] p2 Native SURFACE SET diverges on heavy-overlapping SUBTRACT — Surfs +6.7 % on
  Paris-Catacombs.** §86 cross-check (2026-07-19): on `10_Paris_Catacombs.dx` native emits 6927
  Surfs vs editor 6491 (+436), where the castle was exact and UNATCO −0.2 %. Overlapping SUBTRACT
  brushes make native fragment/merge world surfaces differently from UnrealEd's `bspBrushCSG`
  (coplanar-merge / T-junction handling). New, heavy-subtract-specific; castle+UNATCO never surfaced
  it. Needs a heavy-subtract level kept in the parity loop. (Related, unchanged: over-zoning 33-vs-17
  and uniform BSP over-split +10…+17 %.)

- **[debug] p1 Native zone OVER-FRAGMENTATION — SPLIT into two causes; the flood bug is FIXED, a
  CSG-tree cause REMAINS (this is the real bottleneck).** Root-caused 2026-07-19 with an isolation
  oracle (`harness/zone_flood_oracle.py`) that runs native's Pass B/C flood on the EDITOR's OWN tree,
  and pinned §70 §13. **(1) FIXED — zone-portal OVER-MARKING (`zones.rs`, in-lane):** native flagged a
  face a zone boundary whenever the generating node's surf was `PF_Portal`, using the WORLD-sized
  infinite quad clipped to the whole cell — over-marking a small portal surface's entire cell face. On
  the Catacombs EDITOR tree this falsely zone-marked 1084 within-zone faces → 56 zones vs editor 17.
  The editor's `BlockPortal` (§3) stamps only the leaf-pairs the `PF_Portal` node's REAL polygon
  covers; ported as `collect_zone_barriers` (real-poly re-filter through the coplanar-chain HEAD's
  subtrees). Now editor-exact leaf-pair-wise on ALL FOUR editor trees (interior zones 3/6/4/16 =
  editor); castle byte-identical; regression `tests/test_zone_flood.py`. **(2) REMAINS — native's CSG
  tree is geometrically SHATTERED (`bspcsg.rs`/`passes.rs`, OUT of the zones lane):** the oracle's
  pure-adjacency `[D1]` (union EVERY portal, ignoring the zone flag) still finds **44** disconnected
  leaf-blobs on NativeUnatco and **25** on NativeCatacombs where the editor's own tree is 4/3 — whole
  rooms are portal-DISCONNECTED (14–18 leaves have ZERO portals), insensitive to `MIN_AREA`
  (1.0→0.001 gives 44→41). No flood change can merge leaves that share no face. So native UNATCO stays
  45 zones AFTER the fix, and the UNATCO load-hang suspicion rides on cause (2), NOT the flood.
  **ROOT-CAUSED 2026-07-19 — see §87 `87-cause2-shattered-tree.md`.** Cause (2) is Pass-1
  OVER-SOLIDIFICATION: a golden cross-tree PointRegion probe (`harness/shatter_probe.py`, validated
  `[A]=0` on the byte-identical castle) shows native fills as SOLID **74.5 %** of the editor's OPEN
  space on HK Market, 15.3 % UNATCO, 9.7 % Catacombs — and `[A]` is IDENTICAL pre- vs
  post-repartition (`UEDCLI_BSPCSG_NOREPART`), so the root is Pass-1 incremental `bsp_brush_csg`, NOT
  repartition/merge/find_best_split (all ruled out) and NOT `zones.rs` (proven byte-faithful). The
  mechanism is the `is_csg_filter` dead-node hack (`bspcsg.rs:437`, drops the engine's `NumVertices>0`
  clause): an FWTB-DEAD face buried solid-on-both-sides by overlapping ADDITIVE brushes wrongly keeps
  flipping `Outside`, so later additive fragments in genuine void are mis-classified `F_INSIDE`,
  dropped, and the void mis-labels solid. TRIGGER = overlapping-additive burial (castle has 23.2 %
  dead nodes but `[A]=0` — dead-node COUNT is not it; the malignant kind is additive-buried). The
  disconnection/entombment is the downstream consequence. **Next action:** the scoped fix in §87 §7 —
  tag FWTB-deleted faces buried solid/solid vs subtract-divider and make `is_csg_filter` transparent
  for the buried kind; re-verify castle byte-identity + N=4..8 soup; add a dense overlapping-additive
  level to the differential loop. Module: `bspcsg.rs` ONLY (MEDIUM effort; deeper order-faithful
  re-port is the LARGE fallback). Evidence: §87 + §70 §13; reproduce `harness/shatter_probe.py` +
  `harness/overlap_discriminator.py`. (Found 2026-07-18; split + flood-half fixed, cause-2 pinned
  2026-07-19.)
- **[debug] p2 Native BSP is uniformly OVER-SPLIT at UNATCO scale (~+9…+21 % nodes/verts/points/
  leaves).** Same cross-check (§84): Nodes +21.4 %, Vectors +16.6 %, LeafHulls +15.1 %, Leaves
  +13.6 %, Bounds +12.3 %, Verts +10.9 %, Points +9.1 % vs editor 03 — while **Surfs is
  essentially exact (3581 vs 3589, −0.2 %)**. So the world-surface SET generalizes cleanly; the
  BSP tree that carves it is less-optimal (more split) than the editor's. Negligible on the
  95-brush castle, compounds at real scale — a CSG/BSP-balancing gap castle-tuned byte-parity work
  can't see. (Found 2026-07-18.)
- **[debug] p1 Native surface SET HALVES on a DENSE level — `06_HongKong_WanChai_Market`: Surfs
  2664 native vs 5224 editor (−49 %), and the whole BSP UNDER-builds ~−50 %.** Second real-level
  cross-check (§85): build SUCCEEDS unlit (26 s, 110 MB, no crash, no geometry warning, no brush
  dropped) on 1330 brush-bearing actors / 8229 source polys. But the UNATCO pattern **inverts**:
  where UNATCO's surf set matched (−0.2 %) and its BSP *over-split* (+9…+21 %), HK's surf set
  **halves** and the BSP *under-builds* — Nodes −54 %, Verts −55 %, Points −51 %, Bounds −51 %,
  Leaves −63 %, LeafHulls −43 %, Vectors −22 %. Native's HK body (863 KB) is SMALLER than native's
  UNATCO body (1.05 MB) despite 1.8× the brushes — native is collapsing/absorbing the dense,
  overlapping additive coplanar surfaces the editor keeps distinct. So the BSP-count divergence has
  **level-dependent SIGN**, and the "surface set generalizes cleanly" claim from §84 is FALSE on a
  dense level. Root cause (not chased): incremental-`bspBrushCSG` over-merge on tightly-packed
  overlap; density (not add/subtract ratio — both levels are additive-dominant) is the trigger.
  Evidence: `spikes/2026-07-15-native-materialize/sections/85-hkmarket-parity.md`; reproduce via
  `harness/build_native_hkmarket.py`. (Found 2026-07-19.)
- **[debug] p1 Native OVER-ZONES now confirmed on a SECOND real level — HK Market 64 zones vs
  editor 5 (+1180 %).** §85 corroborates the UNATCO over-zoning (45 vs 7): the editor treats the
  whole market as near-single-zone (5, no ZoneInfo actor → all from portal surfaces) while native
  fragments to 64. Over-zoning is now a **standing, level-independent** native defect (seen on both
  cross-checked levels, unlike the BSP-count sign which flips), gameplay-affecting (zone
  render/sound/water). Fold into / raise the priority of the existing UNATCO over-zoning debug item
  above — same root defect, two witnesses. (Found 2026-07-19.)

- **[chore] p3 `zones.rs` `fix_ring` — two latent faithfulness caveats (§70 §12, cold-review 2026-07-18).**
  (a) `fix_ring` (and the existing `fpoly::fix` it mirrors) compares each vertex to its immediate
  ORIGINAL predecessor, not the last-KEPT vertex like UnrealEd's real `FPoly::Fix` — diverges only on
  a monotonic sub-0.002 drift chain `[A,A',A'']` (none on the calibration castle). (b) `fix_ring` is
  applied ONLY to Pass-D `Orphan` emissions; the real editor runs `Fix` on EVERY fragment before
  `bspAddNode`, so a future map with a coincident-vertex pair on a LIVE (`OriginalRing`/`Frag`) ring
  would keep it in native (wrong `iVertPool`/`NumVertices`) while the editor drops it. Byte-equivalent
  on `Test_Castle.dx` (no live ring has a within-0.002 dup); restricted to orphans to avoid touching
  the live ring-sum / `NumSharedSides` guards. Make `Fix` universal + last-kept-vertex-faithful if a
  future map shows live-ring drift.

- `p2` `[implement] native point-pool byte-ORDER (follow-up to pBase fix, §82 §10.18/§10.19, 2026-07-18)` —
  the surf/vector-ORDER half is **DONE** (§10.19): the editor KEEPS the incremental-CSG surf pool (95
  brushes → 95 contiguous actor runs) while native cleared+rebuilt it in repartition order (322 runs);
  a post-build canonical re-sort (`reorder_surfs_canonical`+`rebuild_vector_pool`, `bspcsg.rs`) landed
  Surfs order + node.iSurf byte-exact + Vectors ORDER 26/26 (residual Vectors bytes = 1–3 ULP normal
  FP, out of pool scope). What REMAINS is the POINT pool: (a) native carries **26 UNREFERENCED points**
  (the +26 overshoot — its `bsp_refresh` skips point compaction; the editor's drops them → count/length
  become byte-exact 2035/24422). Both landed in §10.20: `reorder_points_canonical` (`bspcsg.rs`) drops
  the 26 orphans (Points 2061→2035, section length byte-exact) and re-lays the survivors bases-first
  then rings (matching the editor's 484-base leading block) → whole-body positional match 29.6%→**43.6%**,
  leading 132-base block byte-EXACT. REMAINING (⚠️ deeper follow-on, NOT forced): the editor's exact
  intra-block sub-order (base #132+, ring order) is a `bspRefresh` reachability-DFS-compaction artifact
  of the PRE-compaction pool indices — not reconstructable from the final model (native's own incremental
  pool scored 1/2035; the clean bases-then-rings rule caps at the editor's own 384/2035). Plus an
  ~84-point sub-0.002 FP-value floor. To close it: reproduce the editor's incremental pre-compaction
  point pool + its bspRefresh point-compaction DFS order (out of the current pool-numbering scope).
- **[flag→Andrzej] §82 §10.16's Points diagnosis was WRONG and is now superseded by §10.18
  (2026-07-18).** §10.16 blamed the Points gap on "the repartition CLEAR" and proposed a risky no-clear
  repartition. Disproven: gating out the clear leaves `refd_points=1681` unchanged; the real cause was
  the DROPPED authored `FPoly::Base` (surf pBase defaulted to `verts[0]`), fixed cheaply by plumbing
  T3D `Origin`. No no-clear repartition is needed. (Doc note only — §10.16's VERT diagnosis
  = `zones.rs` Pass-D ring re-emit still stands.)
- **[flag→Andrzej] Board-hygiene 2026-07-18: pruned stale session-store / editor-screenshot items —
  do any capabilities want re-framing for the git-native world?** Removed from the board because their
  entire design premise (the deleted event-sourced session store `session.py`/`replay.py`/`merge.py`/
  `reconcile.py`/`integrity.py`, or the deleted editor-screenshot preview renderer `preview_render.py`)
  no longer exists (decisions.md 2026-07-05 14:58 git-branches-replace-sessions; 2026-07-16 12:13
  two-backend preview). Deleted items: `session stop` removal (verb already gone); `level preview` =
  one-shot editor screenshot (now two-tier `--game`/`--native`); Scale support spec (SHIPPED
  2026-07-18); `session verify --deep` (command-log replay of the deleted store); `merge --sessions
  A B → C` (now a plain `git merge` of two feature branches); field-level 3-way non-geometry merge (was
  `reconcile.py`/`plan_apply` — per-actor `.t3d` now merge natively via git); derive-`packages`-set
  (there is no stored package manifest anymore — `direction.md`). The genuinely-dead ones are simply
  gone; the two whose *capability* might still be wanted in git terms are flagged here: (a) combining
  two in-flight work units before merge, and (b) smart per-property merge when git's line-merge is too
  coarse for non-geometry props. Keep/drop your call.
- **GROUND-TRUTH byte-parity state PINNED 2026-07-18 (corrective — `sections/82b-ground-truth-byte-diff.md`,
  harness `ground_truth_bytediff.py` + `ground_truth_triage.py`).** Raw on-disk parity of the level
  `UModel` body is **0.005 % (12 / 249,287 B)** — only `NumZones` + trailing are byte-identical. **Prior
  "byte-exact" reports were NORMALIZED-oracle results, NOT on-disk bytes.** The geometry *identity* is
  already close (node plane SET 1156/1156, Vectors set 26/26, Surf texture+PolyFlags multisets, build-time
  node_flags `{0:1145,5:11}` all match); the bytes diverge on **serialization ORDER, the light bake, and
  the render/collision aux arrays**. Triaged REAL must-fix (by leverage): (1) ~~node~~/point/vert emit ORDER +
  weld — **node emit ORDER DONE 2026-07-18 (§82 §10.17): RAW positional plane match `172/1156 → 1156/1156`,
  first divergence NONE — the tree was already isomorphic, a tail-relabel of the Pass-D fragments fixed the
  linearization.** Remaining sub-item is the point/vert pool (2035/1684, verts 16163/10407) — the §82
  §10.13-10.16 vert-pool port below; (2) lighting bake — LightMap 484/480, LightBits 49513/48015, Lights
  11392/3928 (§20; FP-determinism hazard §41); (3) Zone numbering swap + Vectors order (tiny bytes, big
  iZone/vNormal cascade); ~~(4) LeafHulls 3866/4028; (5) Bounds 484/0~~ **(4)+(5) DONE 2026-07-18:
  faithful `FilterBound` port (`passes.rs::bsp_build_bounds`) emits both — Bounds 484/484 & LeafHulls
  3866/3866 (array lengths byte-EXACT; all 308 hull plane-ref sets byte-identical; residual is
  ≤0.005-unit FBox float drift inherited from the not-yet-parity Point pool (pBase), see §82c);
  live-verified NativeCastle renders clean (no OccludeBsp crash)**; (6) trivia: ~~prefix
  FBox.IsValid byte (native 1 vs editor 0 — 1-byte fix)~~ **DONE**, NumSharedSides 2739/2728, field_0x54 Polys ref.
  Triaged **"and similar" EXCLUDABLE** (session/view, same category as GUID/timestamps): prefix name-index,
  NodeFlags `0x08`/`0x10` occlusion bits (masking both makes editor build-flags == native exactly), raw
  object-ref index VALUES (export/import renumbering). **@Andrzej:** the two big independent blocks are the
  emit-order port (in flight) and the light bake; everything else is derived or trivia.
- **[flag→Andrzej] Surfs section = the two object-ref fields; PINNED as session artifact + oracle question
  raised (2026-07-18, `sections/83-surf-ref-order-session-artifact.md`, harness `surf_ref_order_analysis.py`).**
  Re-investigated the Surfs residual (a follow-up asked whether native's actor **export order** is a
  deterministic lever for per-surf `iActor`). Finding: the raw Surfs section is **21.2 %**; the mismatched
  bytes are **two object-table-INDEX fields** — `iActor` (export index, 0 %) + `texture_ref` (import index,
  0 %) — **plus a real ~114 B `pBase` tail** (87 %, owned by the still-open point-pool port, not this layer).
  The other 7 surf fields are byte-exact. Both refs resolve to the **right name** 485/485, and the trunk
  **carries the names** (95/96 brush names shared with the golden) — so it is purely an index-**ORDER**
  problem, not a missing-identity one. Against the golden the order is NOT trunk order, NOT `Actors[]` order,
  NOT FName-hash and NOT lexicographic (clustering rules those out; it does NOT by itself prove "session"
  — clustering also fits a name-grouped/paste rule). Reachability (full offset sweep; an earlier narrow sweep
  under-reported this): deterministic-from-trunk brush order caps at **~40 %**; the editor's own brush ORDER,
  compacted, reaches **92.1 %**; editor-EXACT indices 93.3 %, +texture 98.7 %. So the lever is the brush
  **ORDER**, worth ~+19 pts deterministically and ~+71 at the editor's order. I did **NOT** land an assembly
  reorder — it's premature (see oracle below) and touches ref-bearing sections whose editor bytes are
  themselves session-ordered. **TWO decisions for you:** (a) **Oracle (gating)** — the golden used everywhere
  is the *hand-authored* `Test_Castle.dx`; `direction.md`'s bar is "UnrealEd's build of the **same trunk**".
  A clean editor `MAP IMPORT` of our trunk might number exports in deterministic T3D/trunk order, which would
  make the ~40 % deterministic ceiling the WRONG number (true reachable could approach 92 %). Want a `[spike]`
  to `level materialize` the castle trunk through the editor and re-run `surf_ref_order_analysis.py` against
  *that*? (b) If (a) says trunk order matters, want the assembly reorder (all actors first, then subobjects —
  the editor's block structure) landed then? Currently NOT done, pending your call.
- **[spike] p2 Native point/vert-pool byte-parity: port the Pass-D orphan-ring re-emit (`zones.rs`) +
  a no-clear repartition (`bspcsg.rs`).** The final geometry-body byte item (`points 2035 / verts 16163
  / nss 2739`). **RE-SCOPED 2026-07-18 (`sections/82` §10.16) — the prior "CSG over-production /
  z=0 graze" framing was FACTUALLY WRONG, proven by a live oracle sweep** (`editor-tree-oracle/
  repart_pool_oracle.py`, `repart_stage_oracle.py`). Native does NOT over-produce: the editor's CSG-phase
  pool (**4939 pts / 17120 verts**, `bspRepartition` entry) is *bigger* than native's, nodes/surfs match
  exactly (2316/524). The editor's `bspBuild` then COMPACTS to **4405 verts / 2088 pts** (`EmptyModel(0,0)`
  keeps Points/Vectors/Surfs, `SplitPolyList` appends+dedups, `bspRefresh NoRemapSurfs=1` keeps referenced
  + all 524 surf bases). Live ring sums are IDENTICAL (Σnv=4521 both). The two real gaps are pure orphan
  bookkeeping:
  - **Verts (native 4521 vs editor 10518 — dominant) = `TestVisibility`/Pass-D ring RE-EMISSION.
    ~~Fix is in `zones.rs`~~ DONE 2026-07-18 (`sections/70` §11).** Ported the per-landing orphan
    re-emit in `zones.rs`: **Verts 10407→16183** (editor 16163, +20 residual), **NumSharedSides
    2707→2739 byte-identical**, all guards intact (1156/1156 planes, soup
    853/853). **+20 residual half-closed 2026-07-18 (`42-bspoptgeom-decode.md §9`):** +2 of it was a
    `bspOptGeom` pass-1 over-weld (missing live-table dup-guard update, fixed in `bspoptgeom.rs`) →
    welds 977→975, **Verts 16183→16172**, NumSharedSides still 2739. **Remaining +9 = Pass-D orphan
    slots** (native pool 10527 vs editor 10518 at `bspOptGeom` ENTRY) whose stale-pre-`bspRefresh`
    `iVertex` bytes are still not editor-faithful — see next item.
- **[implement] p2 Pass-D orphan `iVertex` stale-index parity** — the last Verts-section byte
  residual. **The +9 orphan-slot COUNT half is DONE 2026-07-18 (`sections/70` §12): Verts 16172→16163
  = editor.** The +9 was three spurious `[A,B,B]` orphan triangles native's `clip_poly` emitted that
  the editor's `FPoly::Fix` drops — fixed by `zones.rs` `fix_ring` on Pass-D orphan rings. **What
  REMAINS (RE'd infeasible in-lane, deferred):** the surviving orphan verts' `iVertex` still carry
  native's snapped indices, not the editor's stale pre-compaction ones. Those stale indices run up to
  **2642** (measured on `Test_Castle.dx`) — a transient CSG point numbering that peaked above 2643
  during Pass-D and was compacted away. Reproducing it needs native to reconstruct the editor's whole
  point-pool construction history, which conflicts with `bspcsg.rs`'s pool CLEAR at repartition
  (§10.16) + `reorder_points_canonical`'s final renumber (§10.20) — both load-bearing for the
  Points-section byte-parity guard, both outside the `zones.rs`/`passes.rs` lane. So a `passes.rs
  bspRefresh` point-renumber sim cannot be byte-faithful without perturbing the Points guard.
  Evidence: `sections/70 §12`, `42 §9`.
  - **Points (native 1684 vs editor ~2088) = the repartition CLEAR.** Native clears Points + compacts
    Surfs 524→485 at repartition; the editor keeps them. **Fix is in `bspcsg.rs`** (no-clear repartition +
    deferred surf compaction into `bspOptGeom`) but entangled with `surf.pBase`/`vert.iVertex` pool indices
    → high tree-regression risk; needs care to preserve the byte-exact tree.
  - **DONE this pass:** `UModel::Bound` prune type binary-verified — it is an **`FSphere`** (`BuildBound`
    = `Engine.dll 0x16fcf0`, not `0x100cee8c`; `FilterWorldThroughBrush 0x33250` arg5 = `&Bound.Sphere`,
    `DoFront=d>=−R / DoBack=d<=R`). Native's box prune (tighter) was replaced with the sphere in
    `bspcsg.rs` — output byte-invariant (uncleared verts now EXACTLY 17120 = editor). `bspoptgeom.rs`
    correct/frozen; `bspAddPoint` FIRST-vs-NEAREST is a red herring for pool SIZE.
- **[implement] p3 Annotated class catalog — FOLDED into the unified asset catalog spec
  (2026-07-25).** Curated per-class knowledge NOT in the `.u` is now the catalog's class arm
  (`specs/2026-07-25-unified-asset-catalog.md` §6), and Andrzej's decision 10 SHRANK it: the
  superclass already says what a class is for and stock-map placement says what is commonly placed,
  so there is no curated role/category taxonomy — curation is a description plus overrides where the
  derived answer is wrong. Tracked on `to-plan.md` with the rest of the catalog; this entry stays
  only to record that the "annotated catalog" idea resolved into a much smaller thing.
- **[note] p2 Backward-compat: class-discovery ingest/generator validation changes exit status of
  previously-green no-config runs.** Once the class-discovery spec builds, `actor build` / `brush
  build --texture` / `actor add` run WITHOUT a games config (or against a class/texture whose package
  isn't on the composed path) will **exit 2** where they silently passed. Intended (no-fallback, same
  honest cost `actor prop` pays) and Andrzej-chosen (generators-AND-boundaries), but it IS a visible
  behavior change — flagged so it's a deliberate break, not a surprise. Also: the generators
  (`actor build`/`brush build`) stop being stateless context-free producers (they now resolve a
  project to validate the class) — a documented contract change to `direction.md`'s "Generator
  pattern: stateless T3D producers".

### Native-castle "black no-sky regions" are LIGHTING, not sky/backdrop/zones (2026-07-17)

> **CORRECTED + RESOLVED 2026-07-18.** This 2026-07-17 "it's lighting" premise was **wrong** — it was
> disproven by §19 of `sections/20-lighting-bake.md` (native vs editor render-DARK counts are 54 vs
> 54, lightmaps value-for-value equal; the black is present, lit geometry the game does not DRAW) and
> then FIXED in `zones.rs` (`sections/70-zones-portalization.md §9` + `20-lighting-bake.md §20`): node
> Pass D was a subtree-descent guess mis-zoning ~450 walls `(0,0)`, and native wrongly wrote
> `FBspSurf.iZone` (editor leaves it 0). After the fix the three interior poses hit editor parity
> (s76 32.1 %→3.8 %, s34/s07 →0.0 %). Residual: **s69 (water pool) ~20 %** is the pre-existing
> water-portal/pool-pit gap (separate item), NOT lighting. Collision unchanged (`phys=1`).

Investigated the reported defect: `NativeCastle.dx` renders large BLACK areas in-game where
`Test_Castle.dx` (editor) shows lit surfaces (poses s57 `at:400,400,20;rot:25,225`, s69
`at:0,455,10;rot:-15,90`, s76 `at:0,0,120;rot:-89,0`; A/B pairs `_scratch/shots/ab80/pairs/`).
The task hypothesised a **sky/backdrop / zone-portalization coverage gap**. **That premise is not
borne out — the geometry, zones, SkyZone, and FakeBackdrop are all correct and complete.** The
black is **unlit geometry** (a lightmap-bake defect, `light.rs` — owned by the concurrent lighting
line). Evidence (all offline, repro scripts under the scratchpad / `_scratch/shots/nat_flat/`):

- **Geometry is complete.** The native software rasterizer (`preview_native`, same CSG core + same
  built `Model`, **no lighting, no zone cull**) renders s69 and s76 with **full coverage** — the
  entire ground plane (s69) and the whole room floor+walls+crate (s76), zero holes. The in-game
  black areas have geometry there.
- **Zones are membership-correct.** Native's interior/water/sky partition matches the editor
  (renumbered): interior zone conn `0x6` ↔ water conn `0x6`, sky **isolated** conn `0x8` — identical
  to `Test_Castle`. Native sky zone sits cleanly ABOVE the castle (z≥420, skybox at z2488–3512); **no
  interior surface is wrongly assigned to the isolated sky/solid zone**, so nothing is zone-culled.
  Part of one convex room renders lit while part is black in-game ⇒ not a per-zone cull.
- **FakeBackdrop identical.** Exactly 1 FakeBackdrop surf (#4, flags `0x00400080`) in BOTH maps;
  native DOES render the starfield where the backdrop is in view. Backdrop pipeline is fine.
- **Lightmaps present.** native 433/438 surfs lit, editor 484/485 — the black is wrong per-surface
  bake VALUES, not missing lightmaps or structure.
- Native has 438 surfs vs editor 485 (over-consolidated coplanar fragments from the un-ported
  `bspOptGeom` trim, documented in `build.rs::find_best_split`) — but this is **coverage-equivalent**
  (rasterizer proves it) and does NOT cause black. No fix made: nothing in the sky/zone/geometry
  scope (`zones.rs`/`materialize.py`/`assemble.py`) is wrong. **Redirect to the lighting line.**

### Level-authoring capability audit — "can an agent build DX-quality levels?" (2026-07-17)

Captured from three cold subagent stress-tests (build a DX-authentic room / a zoned two-room + door
mover / a detailed+decorated space) driving ONLY the offline CLI, plus my own repros. Theme: the
**authoring** surface is broad and mostly ergonomic, but the **feedback loop lies or is blind** on the
things that matter most (doorways, zones, lighting, decoration, stairs), and an agent **can't discover
the substrate's class vocabulary** or **validate a texture/class ref at author time**.

- **[debug] p1 Native preview mis-renders overlapping subtractive DOORWAYS, and `doctor` says "no
  issues".** A doorway = a second subtract overlapping the room (or connecting two rooms). In
  `--native` it renders as a wedge/partial opening with **magenta on the CSG-generated cut faces**
  (missing-texture sentinel — those new faces inherit no texture even when `brush poly list` shows the
  authored faces textured). Reproduced minimally (two rooms straddling x=0 + a through-wall subtract →
  imperfect wedge opening, untextured=gray). So the DEFAULT feedback loop is unreliable for the single
  most fundamental connective operation, with **zero warning**. Unknown whether it's a preview-only
  artifact or a real build defect — disambiguating needs the `--game`/materialize tier the offline
  loop can't reach. Root cause lives in the native CSG core / `preview_native` (owned by the
  native-materialize line — COORDINATE, don't touch those files). Repro: `_scratch/doorprobe/`.
  (Agent A + my repro.)
- **[implement] p2 `@actor` aiming doesn't resolve in the DEFAULT `--native` preview.** `level preview
  --native "look:@Room"` (and `at:@Room`) → `actor not found`; `@refs` resolve only in `--game --map`.
  So the fast offline loop can't aim at your own geometry by name — raw coords only, made worse by the
  suffix item above. Native should resolve `@refs` host-side against the trunk (thought `actor_aim_point`
  did — live it did not; verify + fix). (My probe.)
- **[docs] p2 Craft docs are UnrealEd-GUI-framed with NO uedcli-verb walkthrough, no DX scale
  numbers, no class catalog.** `leveldesign/*.md` teach the GUI mental model (red builder brush,
  Order→To First, F8 rebuild) but nothing maps that craft onto the actual verbs; there are no DX
  human-scale proportions (room height, doorway W×H, camera eye height — both agents guessed from
  general UE1 memory); no catalog of real DX **door/mover** classes (only `DeusEx.ElevatorMover` /
  `Engine.Mover` are ever cited, neither a plain door) or **decoration** classes; and the end-to-end
  **portal authoring recipe** (which flags, incl. actor-level solidity) is written nowhere. To *teach*
  an agent, add a task-oriented "build a room → cut a door → zone it, command by command" guide + a
  scale/class quick-reference. (A + B + me.)
- **[note] p3 `--native` is flat-shaded gray with no lights/meshes/lighting; movers need close-ups.**
  By design (documented), but the consequence for authoring: lighting mood, every decoration/fixture,
  and mover open/close STATE are all authored BLIND offline — a closed-door mover is nearly
  indistinguishable from the wall at distance. Native is a geometry/proportion tool only; verifying
  lighting + decoration needs the `--game` tier. Worth stating plainly in the "how to build" guide so
  an agent shoots movers/lights close-up and defers lighting judgment to `--game`. (A + B.)
- **[debug] p2 `doctor` `fallthrough` warns on EVERY upward-facing semisolid poly — trains you to
  ignore the category.** A detailed space emitted 17 `fallthrough` warns, all benign (ceiling beams at
  Z=220 nobody can walk on), because the check flags any up-facing semisolid regardless of
  reachability. Noise this dense hides a real fall-through. Needs a reachability/height gate so the
  warning means something. (Agent C.)
- **[spike] p2 N=33 soup divergence = a merge-blocking clip on a DEAD merlon-east node; a cumulative
  incremental-tree-ORDER divergence, NOT any local rule — BLOCKED on an editor-tree oracle.** Traced to
  full mechanism + instruction level 2026-07-17 (`sections/82 §10.6`, supersedes §10.5's read). The
  `x=112` "box" is `Merlon_y4jykf`'s east face (brush 10/N=11); `TowerNE`'s west face is `x=111.958`
  (brush 31/N=32); `RoofNE` is N=33. The roof underside splits at WallBack-north `y=160` into an upper
  band (→ reaches `TowerNE` west, clips `111.958` ✓) and a lower band (`y∈[128,160]`) that descends
  WallBack-**top** into the merlon east-face `iFront` staircase and SPLITs at **`node[80]` (`x=112`,
  `nv=0` — DEAD, deleted by TowerNE's FWTB)**. `node[80]`'s live coplanar sibling `node[255]`
  (`x=111.958`, the TowerNE-west fragment, absorbed there at N=32 because `0.042 < 0.25`) is on its
  `iPlane` chain, which `SP_Split` does NOT consult — so the lower band keeps `x=112`. The two same-plane
  bands then fail `TryToMerge` (`y=160` corner `111.958` vs `112`, `0.042 > 0.002` box); the editor
  produces BOTH at `111.958` and merges to one 5-vert face. **Three decisive negatives (§10.6):**
  (1) disasm of `FilterEdPoly 0x32bf0` proves the engine has **no dead-node (`nv==0`) skip** — it splits
  at every node's surf plane, so the editor clips `111.958` only because `node[80]` is off its roof-B
  path (tree structure, not a rule); (2) the `0.25` threshold is **non-separable** — a `very_precise`
  probe fixes the roof but symmetrically un-merges the mirror sliver on the tower SW diagonal
  (`-0.707,-0.707,0,-178.2`), same `0.042` gap; (3) **only the SOUP matters** (final tree is rebuilt
  from it) — editor `golden32/33` final trees carry the same `x=112`/`x=111.958` plane multiset (`2/2`)
  as native, the sole difference is this one roof soup face. The temp-brush-`LAME/0/0` and coplanar-seed
  hypotheses were prior disproven. **The whole `only-editor` family (`-248/-280/-295.7/BRoof`) is this
  shape.** Ordered `node_diff` prefix stays `0/1156`. **The editor's INCREMENTAL tree is not dumpable
  (only its soup-rebuilt final tree is), so pinning the earlier order rule that diverges is blocked; the
  next lever is an editor-tree oracle (e.g. an `MAP REBUILD` with node-add logging), NOT another blind
  local tweak.** Do NOT force the merge/clip — forcing regressed twice.
- **[RESOLVED → next divergence below] p2 §10.8's node-4 coplanar-chain-head/dead-node root cause is
  DECODED + FIXED; the soup is now byte-exact.** The mechanism (`sections/82 §10.9`): `NodeCleanup`
  (`0x34020`) is notify-only — the relink is **`bspCleanup` (`0x36160` → `CleanupNodes 0x32100`), run
  at the TAIL of `bspBrushCSG` PER-BRUSH** (`0x35de1`, unconditional for Add/Subtract), so each brush
  filters through the prior brush's CLEANED tree. `CleanupNodes` splices dead (`nv==0`) nodes:
  promote the `iPlane` successor, inheriting front/back children SWAPPED iff it faces opposite
  (`Normal·Normal < 0`, `FPlane::operator|`, threshold 0.0) — this IS the §10.8 `(+1,0,0)`-dead-vs-
  `(−1,0,0)`-alive orientation flip. Also `bspBuildFPolys`→`MakeEdPolys` (`0x33bb0`) is a **tree-walk**
  (self,front,back,plane), not an index scan, so the repartition-input soup ORDER is tree-structural.
  Ported to `bspcsg.rs` (`bsp_cleanup`/`cleanup_nodes` per-brush; `bsp_build_fpolys`→`make_ed_polys`).
  **Verified:** node 4 now identical (`tree_struct_diff.py 33` residual diffs are unreachable dead
  nodes only); merlon splitter region node-for-node identical; **`soup_cmp.py` 0/0 byte-exact** (was
  24/17); `compare_trees.py 32` identical; `bin/test` 1363 green. Decode harness: `dll_disasm.py`/
  `dll_exports.py`/`dll_vtable.py`/`cleanup_proto.py` in `harness/editor-tree-oracle/`.
- **[flag→Andrzej + spike] p2 NEXT DIVERGENCE — the REPARTITION over-splits from a soup-ORDER gap
  (`FindBestSplit`), not the incremental soup.** With the soup multiset now exact, `node_diff.py` is
  still **0/1156**: native's final tree is **1251 nodes vs editor 1156** (plane multiset 1058 shared /
  193 only-native / 98 only-editor — native OVER-splits). The divergence is entirely in
  `bspBuild`/`SplitPolyList`/`FindBestSplit`, which consumes the exact soup in a still-different ORDER
  → picks different partition planes. The order gap traces to ~37 residual incremental
  fragment-CREATION-order swaps (the `119`/`120`-type coplanar surf-28 pair; and the `#184`
  `compare_trees` swap, now a raw-leaf-add artifact the per-brush cleanup reconciles in the final
  structure but not in creation order) — §10.8's distinct "byte-identity tree-order" residue.
  **Caveat for whoever picks this up:** the golden `Model.Polys` is the POST-`SplitPolyList` array
  (reordered in place), NOT a valid oracle for the `SplitPolyList` INPUT order. Build an editor oracle
  that dumps `Model->Polys` at the `bspBuild` entry (right after `bspMergeCoplanars` inside
  `bspRepartition 0x49fc0`) to compare the true input order, then decide: last incremental emit-order
  swaps, or a `FindBestSplit` stride/tie residue. `sections/82 §10.9`.
- **[flag→Andrzej] p3 Kept the byte-verified temp-brush `LAME/0/0` even though it doesn't fix N=33.**
  `build_brush_temp_bsp` now builds with `Opt=LAME, Balance=0, PortalBias=0` (the value the binary
  actually pushes — `findbestsplit-params-decode.md §4`), replacing the historical `OPTIMAL/50/70`.
  It is **exactly soup-neutral** (full-castle `onlyN=21/onlyE=15`, nodes `1171`, surfs `485` — same
  as before; verified by flipping the config). I kept it because it matches the binary and the repo
  rule says code should reflect verified engine facts; the task had said "revert if the hypothesis is
  wrong." If you'd rather this session touch no functional param, revert the three `bspcsg.rs` hunks
  (`TEMP_BALANCE`/`TEMP_PORTAL_BIAS` → `50/70`, `Opt::Lame` → the old stride-1) — it changes no output.
- **[debug/perf] p1 Default `build_geometry` (point-in-solid oracle) is IMPRACTICAL at UNATCO
  scale.** The full 762-brush `01/03_NYC_UNATCOHQ` trunk takes **>45 min** in the default
  `build::build_geometry_from_brushes` (each fragment classification replays `point_in_solid`
  against every accumulated `WorldBrush` ⇒ ~O(brushes²·fragments)) — it never finished under a
  45-min timeout even running alone. The OPT-IN `build_geometry_bspcsg` (BSP-growing core) builds
  the SAME 762 brushes in **38 s** (nodes 6822 / surfs 3644 / points 9579 / leaves 2861) and the
  full unlit materialize (assemble + self-check + write, 1.0 MB `.dx`) in **44 s**. So the byte-
  identity `bspcsg` core is ALSO the only viable FUNCTIONAL path for real levels — the default
  oracle path scales fine for the 95-brush castle but not a real DX map. Decision needed: route
  `run_materialize_native`/`_build_level_model` (and `preview_native`) through `build_geometry_bspcsg`
  once it's trusted, OR optimize the oracle (spatial index over `WorldBrush`). (Found 2026-07-17
  driving the UNATCO native build.)
- **[debug] p1 Native materialize `LIGHT APPLY` bake (`bake_lighting`, Rust) is far too slow /
  resource-heavy for a full DX level.** An unbounded LIT build of the UNATCO trunk was SIGTERM'd
  (systemd-oom, exit 143) at ~7 min; unlit builds are the only ones that complete. The N-4 per-lumel
  BSP ray test over all surfaces × all participating lights needs a perf pass (or a coarser/optional
  bake) before lit native maps of DX-scale content are feasible. Unlit maps render fine. (Found
  2026-07-17.)
- **[debug] p1 Native map built by `bspcsg` does not become PLAYABLE in-game (pawn never possesses
  / `--game` travel never completes) even though the shipped map travels fine in the same warm
  container.** Confirmed 2026-07-17: `--game --map <our.dx>` never possesses a pawn on the UNATCO
  map (travel deadline expires → REBOOT_BUDGET retries burn the whole timeout), while
  `03_NYC_UNATCOHQ.dx` travels + shoots 5 frames in the SAME warm container — so it's OUR build, not
  the harness. A direct link probe (drive the warm container: `TravelToLevel <our-stem>` then poll
  `GetCurrentLevelName`/`Ping`) shows the link goes **completely dead** after the travel — no reply
  for 120s — so the engine **crashes or hangs at LOAD time** on our `.dx`, which is DISTINCT from
  (and earlier than) the runtime "pawn falls through the floor" collision-fall (that would still
  LOAD + possess, then sink). So it is NOT confirmed to be only the collision-hull leak
  (MEMORY: native-castle-blocker-is-collision; architecture.md "leaf-bounding repair"/
  `bound_leaked_solid_leaves`); it needs a **game-log capture on load** to pin the cause — a bad
  export/ref/BSP the always-on OFFLINE self-check doesn't catch, a missing package, or the hull leak
  surfacing as a load-time AV. Next step: `--keep-alive` a container, travel to our map, read
  `DeusEx.log`. **BUT the GEOMETRY is correct and renders**: the OFFLINE native rasterizer (`level preview
  --native`, routed through `build_geometry_bspcsg`) renders the UNATCO trunk recognizably — the
  spawn corridor (tiled walls + red herringbone floor + "U.N.A.T.C.O. Personnel ONLY" sign), Manderley's
  wood-paneled office (both framed diplomas + desk), the security room — matching the editor golden's
  BSP geometry (shots in `_scratch/shots/unatco-native-offline` vs `unatco-editor`). Missing in the
  draft tier: mesh/decoration actors (terminals, chairs), lighting, sky projection. So: **the rotation
  fix + bspcsg build produce correct renderable geometry; the in-game LOAD failure is the single
  biggest blocker to a WALKABLE native UNATCO** (diagnose via DeusEx.log; likely `bound_leaked_solid_leaves`
  / hull emission at DX scale, or an export/ref the offline self-check misses). (`--native` had to
  no-op its scale-reject gate, like materialize, to accept the ~90 PostScale'd brushes — same
  scale-drop gap.)

- **[chore] p3 Warm `--game` remnants (deferred from the 2026-07-17 build).** Not built, low-impact:
  (1) **additive re-farm on reuse** + dangling-symlink sweep — currently a project-overlay change
  trips the fingerprint and reboots (correct but heavier than an in-place re-farm), and a NEW base
  map appearing mid-session isn't picked up until a reboot; (2) the **boot-time assertion** that
  `/resources/preview` never enters `Paths`/`r*` (today it's structurally true — leading `p`, farm
  globs only `r*` — so the assertion is belt-and-suspenders). *(The `--map` same-content-different-
  extension clash was FIXED in the review gate — `copied_map` now carries the ext into the stem.)*
  See `specs/2026-07-17-game-preview-warm-container.md`.
- **[implement?] p3 `--game` preview ≤1s (from ~2.2s warm).** Andrzej wants a same-map 1-shot warm
  preview in ≤1s; the one-exec drive got it to ~2.2s but the dev CLI can't go sub-1s. Levers:
  (1) the eventual **Nuitka release binary** removes ~0.56s Python interpreter+import startup;
  (2) **fold the reuse `docker inspect` INTO the `exec`** (batch self-checks a baked fingerprint env
  vs a passed arg; boot on failure) → −~0.3s; (3) **tune the settle** (`UED_SETTLE_S`, now 0.2s) — live
  spike the minimum before frames go stale (biggest lever for BATCHES: 0.2s×N). Even fully optimized
  the dev CLI is ~1.5-1.8s; sub-1s needs the release binary. Deferred by Andrzej ("ship ~2.2s").
- **[debug?] p3 Warm `--game`: idle self-death verified only via a backdated marker, not a real
  10-min wall-clock idle.** The watchdog loop + kill path are confirmed (backdate `/work/.last_use`
  700s → self-terminates in ≤60s), but a true unattended 10-min idle wasn't timed. Low risk (the
  mtime math is trivial); flag only if a container is ever seen lingering.

- **[implement] Incremental `bspBrushCSG` core (`build_geometry_bspcsg`,
  `uedcli-native/src/bspcsg.rs`) — §8.1 split-and-re-add + §8.2 Subtract-reverse LANDED; residual now
  at REPARTITION, not the filter.** p1. Default `build_geometry` untouched, full suite green (1242
  passed / 1 skipped / 2 xfailed; 30 cargo tests). What changed this increment (decode
  `sections/82-bspbrushcsg-port-decode.md §8`): (1) `filter_world_through_brush` replaced the old
  clip-to-largest-fragment hack with the engine's SPLIT-AND-RE-ADD — the world face is filtered down
  the brush's convex temp BSP (`build_brush_temp_bsp`), every bit31 outside cut-fragment is re-added
  as a NODE_Plane node sharing the original surf, interior fragments delete the original; grazes roll
  back; (2) §8.2 Subtract fix — dropped the LOOP-1 reverse, `leaf_func` now adds only on
  {F_INSIDE,F_COPLANAR_INSIDE} and REVERSES at store time (descent keeps the outward normal); (3) the
  repartition now rebuilds Points/Vectors (drops CSG-phase orphan points). Counts vs editor
  (`harness/bspcsg_diff.py`, step 64): **nodes 1263 (ed 1156), surfs 437 (ed 485), points 1901 (ed
  2035 — was 2509, now near-parity), verts 4945 (ed 16163), num_shared_sides 0 (ed 2739), bounds 0
  (ed 484)**. The CSG SOUP is correctly fattened (pre-repartition verts 4914→**46058**, mechanism
  verified: 1704 genuine cuts + 7696 correct rollbacks on the castle). Solidity vs oracle **98.43%
  (step-64 on-grid)** — a DROP from the old clip's 99.35%. Investigation: ALL disagreements are
  within 8u of a brush boundary face (zero interior/far leaks); they are grid-sensitive (offset grid
  +13.37 → only 26 real >2u leaks vs 791 on-grid). BUT the editor's own golden model scores
  **99.97%/100%** on the same harness, so the leaks are REAL, not a boundary-density artifact — the
  residual is in the **MERGE/REPARTITION stage** (`bspMergeCoplanars`/`TryToMerge` §7c not
  instruction-exact + `bspBuild`/`SplitPolyList` re-partition of the finer soup leaks at shared
  boundaries; the pre-repart soup is 96.9%, repartition heals to 98.43% but not to the editor's 100%)
  and the missing `bspOptGeom` (which gates the vert count to 16163 and is out of scope). **§8.3
  coplanar IsCsg Outside-seed: RESOLVED & LANDED 2026-07-17.** The earlier blind attempt (measured
  98.43→98.36, reverted) was wrong because the §7b pseudocode mis-assigned the FCoplanarInfo fields.
  Full instruction-level disasm of `FilterEdPoly 0x32d91` + `FilterLeaf 0x33130` (see
  `re-raw-zones/bspbrushcsg-filter-decode.md §7b`, now corrected) + a LIVE N=2 castle differential
  (`subset_diff.py`) pinned it: `+0x20 FrontLeafOutside` is the OTHER-side descent seed (not a leaf
  result), `+0x24 BackNodeOutside` is the classify `frontOutside`; each side gets the ordinary
  SP_Front/SP_Back CSG adjust (`Out||csg` / `Out&&!csg`). Fix in `bspcsg.rs` (both `filter_*` and
  `wtb_filter_*`): N=2 native 15→14 nodes = editor (surplus `(0,0,-1,0)` face now `FACING_IN`→dropped);
  full-castle shared-plane multiset 867→971, node count 1028→1158 (editor 1156), solidity 98.96→98.99%.
- **[spike] Native full-castle node-for-node prefix still 0 after the §8.3 fix — next divergence is the
  REPARTITION ROOT + under-fragmentation.** p2. Post-fix the ordered prefix is still 0: `node[0]`
  repartition root is native `(-1,0,0,-72)` vs editor `(-1,0,0,48)` (parallel, different offset) because
  the pre-repartition soup still differs — dominated by (a) the split-and-re-add UNDER-fragmenting
  (verts 4560 vs ed 16163, num_shared_sides 1152 vs 2739; only-in-editor planes are repeated
  axis-aligned floor/wall planes e.g. `(0,0,1,0)×25`), and (b) missing zone/visibility (`i_zone (1,1)`
  vs `(0,2)`, `node_flags 0` vs `8`). Needs the §6/§8.1 fragmentation pinned + zones/TestVisibility +
  `bspOptGeom` (out of scope) before the ordered prefix can move off 0.

- **[debug] Native castle collision floor sits 12u too low (pawn rests z=35 vs editor z=47) — root
  cause RE'd 2026-07-16 to the BSP-tree IsCsg-propagation, NOT the bounds pass.** p1. The
  editor-vs-native gap reproduces exactly offline (`line_check.py` box sweep at (0,-250): editor
  floor-contact z=0 on node 1152, native z=-12 on node 885 = the water-sheet plane node 15). The
  z=0 stone-floor node plane EXISTS in the native tree (node 19) and `point_in_solid_world`/iLeaf
  correctly call z=-2 solid — but the game's box LineCheck gates hull-testing on the IsCsg
  `Outside` propagation (`if Outside: return` BEFORE the `iCollisionBound` read, per
  `re-raw-zones/linecheck-oracle.md`), and that propagation produces NO solid terminal covering
  z=0 at (0,-250) — an unbounded-splitter mis-flood (a far wall's plane, e.g. node 863 y=-380,
  classifies the column empty and the room's own bounding faces never re-subdivide the cell). This
  is the SAME mis-flood build.rs:519-561 already documents and patches for iLeaf; the patch is
  impossible for collision because the game reads propagation live, not a stored field. So
  `bsp_build_bounds`/`cull_parallel_planes` are faithful mirrors of the broken tree — the fix must
  make the native BSP build (build_bsp_opt / csg.rs) produce a solid terminal cell for the stone
  floor like the editor's node 1152 (i.e. propagation must match point_in_solid). Stopped short of
  editing csg.rs per the task guardrail (it just passed render/zone parity gates) — needs
  Andrzej's call on scope. Full trace in session transcript 2026-07-16.

- **[debug] Native-preview post-build review findings (two cold reviewers, 2026-07-16) — gate
  OPEN, fixes deferred on Andrzej's "switch to --game first" hold.** p2. The confirmed real ones:
  (1) HIGH `preview_native.add_poly` crashes with AttributeError on the out-of-range-owner GREY
  path (`poly.flags` read before the None check) — the guard the join promises; its test
  exercises only `_node_polys`, false coverage; (2) HIGH `--size` above 16384 (or ≥2^32) leaks a
  raw `BuildError`/`OverflowError` traceback (`render_frame` call not wrapped; no upper bound in
  dispatch); (3) MED `img.save` unwrapped — disk-full / out-dir removed / `shot-01.png` squatted
  by a directory → raw OSError; (4) MED negative `PolyFlags` in a trunk → PyO3 OverflowError
  (materialize masks with `& 0xFFFFFFFF`, preview dropped the mask); (5) MED `utexture` resolver
  can raise IndexError/MemoryError on hostile mip counts/sizes (cap dims, wrap `mip0_to_rgb`);
  (6) MED `--fov`/orbit-`elev` unvalidated (fov 0/nan → NaN garbage frames exit 0; |elev|>90
  silently aims away); (7) LOW u32 overflow in `lib.rs` texture length check (do it in u64);
  (8) LOW scale-gate regex fails OPEN on exponent-notation scales; (9) LOW one-axis-missing
  texture axes discard BOTH authored axes; (10) LOW shading uses |N·L| where spec §5 said
  max(0,N·L) — doc the deviation; (11) LOW `query.py` missing blank lines after the
  `overview_brush` deletion; architecture.md says "never an IndexError" (false until (1)) and
  cites the golden at `tests/fixtures/…` (actual: `uedcli/tests/fixtures/…`); (12) test gaps:
  BuildError-wrap test can pass vacuously, no mover-scale-rejection test, no over-limit --size
  test. Full reports in the session transcript 2026-07-16; fix before calling the native tier
  done.

- **[implement] `packages.ensure_load` cannot detect a FAILED `OBJ LOAD` — a missing transitive
  content dep (e.g. `UNATCO.utx` → `CoreTexDetail`) silently renders every ref unbound
  (DefaultTexture bubbles).** p3. Hit live 2026-07-16 (anchor capture, minimal package dir). The
  console `OBJ LOAD` is fire-and-forget; consider a post-load `Editor.log` scrape for
  `Failed to load`/`Can't find file` and a named error, or a host-side `dxpkg.transitive_closure`
  pre-check over the resolved load set.

- **[implement] Native preview perf: an 8-shot castle batch is ~11.5 s vs the ≤10 s soft target,
  and 8.0 s of it is `build_geometry` (the CSG carve) — the rasterizer is 0.35 s/frame.** p3.
  Preview needs neither collision hulls nor lighting; a build flag skipping `bsp_build_bounds`
  (and any other materialize-only pass) for preview builds is the lever — COORDINATE with the
  native-materialize line (it owns `build.rs`/`passes.rs`; measured in
  `spikes/2026-07-16-native-preview-anchor/perf.md`).

- **[debug] Native preview: black speckles on tower-roof CONES at some angles (castle
  acceptance, `spikes/2026-07-16-native-preview-anchor/perf.md`)** — looks like coplanar-fragment
  z-fighting (the N-2 un-merged coplanar residuals) between abutting cone facets. p3,
  draft-acceptable; revisit after `bspMergeCoplanars` lands (the b-case residual).

- **[plan] `level preview --lit` — the scoped fast-follow (native-preview spec §8, decision
  2026-07-16 12:13): consume the N-4 `bake_lighting` arrays in `render_frame` (raw dot-product
  lumel frame, NOT the panned texel frame — spec §8 pins the math).** p3. v1 shipped flat-shaded
  2026-07-16; `render_frame`'s FFI grows optional lightmap arrays.

- **[debug] Native collision-hull latent edges (flagged by post-build review, 2026-07-16).** p3. All
  LOW / not-yet-reproduced, native build is live-verified playable. (a) `model_write.rs`/`umodel.py`
  hardcode the serialized trailing `RootOutside` INT to `0` instead of deriving from
  `model.root_outside`; the hull descent seeds from `model.root_outside` (false today), so they only
  *coincidentally* agree — an additive/`root_outside=true` build would seed one way and serialize the
  other. Wire the flag from `model.root_outside` (keep the Rust↔Python gate-5 byte pin). (b)
  `passes::bsp_build_bounds` keeps only the FIRST hull when a node has two solid terminal children
  (only possible for a non-CSG node embedded in solid — shouldn't occur for carved rooms); add an
  assert/guard if one ever appears. (c) Pin the 64-plane cap boundary (63/64/65) once a map can
  produce it — culling keeps the castle at max 10 planes/hull (editor max 10), so it's currently
  unreachable; the cap now `eprintln!`s + truncates (keeps the hull) instead of silently dropping.
  (d) Consider non-parallel redundant-plane culling for exact editor parity (editor mean 5.6
  planes/hull; ours 7.9 after parallel-dedup) — harmless (extra planes only tighten the convex cell),
  purely a size/parity nicety.

- **[build] NATIVE BUILD IS NOW PLAYABLE (2026-07-16) — playability blocker was COLLISION HULLS, NOT
  zones (handoff assumption corrected).** p1. ✅ **`NativeCastle` live: `phys=1`, pawn rests at
  `(0,-250,47)`, level STAYS, `uplayctl shot` renders the castle first-person**
  (`_scratch/shots/native_castle_playable.png`). Root cause was NOT zone portalization: the pawn fell
  through the floor because the native build shipped no collision hulls. `UModel::LineCheck` forks on
  Extent — every pawn/actor sweep (`Extent!=0`) is `FBoxLineCheckInfo::BoxLineCheck` (game `0xf42f0`),
  whose ONLY hit clips the swept box against `LeafHulls[iCollisionBound]`; `iColl=-1` = non-solid, no
  node-plane fallback. Fixed by porting `bspBuildBounds` (`uedcli-native/src/passes.rs::bsp_build_bounds`
  → `LeafHulls` + `iCollisionBound`); `Bounds`/`iRenderBound` stay empty/`-1` (render, separate).
  Offline oracle: `harness/line_check.py` (box sweep HITs at `floor+extent`). Decision:
  `decisions.md` 2026-07-16 15:20 UTC; full decode `re-raw-zones/linecheck-oracle.md`. Supersedes
  section 60's "bounds optional" (true only for a zero-extent line trace).
  **REMAINING for full byte-parity (NOT playability — deferred):** real multi-zone `TestVisibility`
  portalization (leaves/zones/`FZoneProperties`/`ZoneInfo` refs — fully RE'd this session, passes A–G in
  `sections/70-zones-portalization.md` + `re-raw-zones/`), the side pool (`bspOptGeom`
  `NumSharedSides`/`iSide`), render bounds, and editor `NF_` node flags. These fix per-room
  gravity/water/sound/`ZoneInfo` + byte parity; the map is walkable without them (single interior zone).
  `_multizone_warning` still fires for multi-room maps. `zones.rs` is still a stub. (Revert the scratch
  `DeusExLevelInfo` injection if any remains — Test_Castle has none, not the fix.) Handoff doc
  `HANDOFF-native-full-parity.md` is now superseded by this entry + `decisions.md`.
- **[chore] Lit-render first-person VISUAL is intro/menu-blocked for custom maps.** p2. The lighting
  crash is FIXED (below), and a `uplayctl session start --map NativeLit` confirms `link up on NativeLit`
  with 0 singularities + a possessed player — but DeusEx composites its **intro/menu overlay** over the
  render, and there's no menu path to true first-person for a *custom* map (only an in-game console
  `open` gives it), so `uplayctl shot` / an X grab shows the intro logo, not the lit room (the world
  renders clean BEHIND it). To screenshot a native map first-person, drive: boot → skip intro → New
  Game/Training (real first-person) → in-game console `open <map>` → shot (cf. `game/dxplay.sh enter`).
  Nice-to-have for visual verification; the render itself is proven by metrics.
- **[build] HANDOFF — N-4 LIGHTMAP BAKE + lit-render crash: BOTH DONE (RESOLVED 2026-07-16).** p1.
  ✅ **Lit maps now render clean** — root cause was `FBspSurf` on-disk **field order**: `iLightMap` and
  `iActor` were serial-swapped (we wrote `iActor` in slot 7, `iLightMap` last; real maps DXOnly/DX/Entry
  do the reverse). The game read `iLightMap` from our `iActor` value (`7`, a brush ref) → out-of-range
  `Model.LightMap[7]` (only 6 records) → garbage `iLightActors` → bad `Model.Lights[]` pointer → the
  `c0000005` AV in `AddLight` (`Render.dll 0x10b08b4a`, 254/254 exceptions). Fixed in `umodel._enc_surf`/
  `_parse_surf` + Rust `model_write.rs::put_surf` (swap `i_light_map`/`i_actor` to the verified order);
  156 tests pass; `+seh` re-measure of NativeLit = **0 AVs** (was 254). The earlier "FP singularity"
  (§13) was a RED HERRING — see spike section 20 §14 for the full correction. The N-4 bake itself was
  byte-correct all along. ✅ **DONE (2026-07-16):** `run_materialize_native` now defaults
  `no_light=False` (lit); the **real castle** (161 actors → 418 lit surfs, 90 brushes, real LUM
  textures) boots to `READY map=NativeCastle`, **0 texture errors, 0 singularities** — the fix
  generalizes. Fixing the castle also required TWO asset-wiring fixes (spike §15): texture imports now
  carry the GROUP (`LUM_CoreTex.Concrete.concrete_02`) and `ClassPackage=Engine` (both were wrong;
  `native/pkgref.py` + `run_materialize_native(pkg_dirs=…)`), and `game-entrypoint.sh` now wires a
  project OVERLAY (`/overlay` = `DX/LUM`) so custom `LUM_*` packages resolve. ⚠️ The original "needs a
  fuller Model" and "FP singularity" framings below are SUPERSEDED (kept for history).
  **N-4 is built + tested + committed:**
  `uedcli-native/src/light.rs` (the `LIGHT APPLY` bake, rayon) + `linecheck.rs` (the `UModel::
  LineCheck` BSP shadow ray) are real now; FFI `bake_lighting(built, lights)`; Python orchestration
  collects participating lights, bakes, and `assemble._patch_light_refs` rewrites the `Lights` array
  light-indices → export refs. Output is **byte-format-correct vs real maps** (decoded `NativeLit.dx`
  beside `00_Intro.dx`: same unit basis, `FLightMapIndex` shape, `N×⌈U/8⌉×V` bit sizing, light-ref +
  NULL runs). The map **loads + the pawn stands**. Regression tests + the gate-5 dual-serializer
  cross-check pass; whole offline suite green (1159). **BLOCKER (fully characterized live, spike
  `sections/20-lighting-bake.md` §11):** the DeusEx **software renderer** faults per-frame on ANY
  lightmapped surface — `Render.dll FLightManager::SetupForSurf → SetupNormalSurface`, logged as
  "Anomalous singularity in URender::DrawWorld" (headless game survives; screenshots black). Isolated:
  `NativeUnlit` (no lightmaps) renders CLEAN; `NativeDark` (all-DARK records, no bits/lights) CRASHES;
  real `DXOnly` (also dark records) renders CLEAN. The difference is **Model completeness** — real maps
  have `num_shared_sides>0` + real vert `iSide` + real node **Bounds** (`iColl/iRend>=0`); our native
  build ships the MINIMAL Model (empty Bounds, `iSide=-1`, `num_shared_sides=0`). The UNLIT path
  tolerates it (why `NativeCSG` renders), the LIT path does not. **So `run_materialize_native` now
  defaults `no_light=True`** (renderable unlit build); the bake is opt-in `no_light=False`. **NEXT
  SLICE (own item below):** decode `Render.dll` `SetupNormalSurface`/`SetupForSurf` (base
  `0x10b00000`; `SetupNormalSurface` guard str @ VA `0x10b2a350`, code @ `0x10b07136`) to pin whether
  node **Bounds** (`bspBuildBounds` proper + serialize the `c0`/`cc` arrays our writer drops) or the
  **`bspOptGeom` side pool** (or both) is the requirement, then port the minimum. Repro maps at
  `DX/Maps/Native{Lit,Dark,Unlit}.dx` (scratch `_scratch/build_litcsg.py`).
  **Collision-fix (commit aa243e38e) review-gate findings — ✅ ALL RESOLVED 2026-07-15:**
  (1) `50-…md` §1.2 + the §4.3 table rows now annotate the front/back inversion + NF_IsNew as "benign
  for RENDER but ARE the COLLISION bug, see §60"; (2) `60-…md` §4/§7 now record the live result
  (`phys=Walking`, `z=-134` stable) instead of framing it as an open gate; (3) `60-…md` §5 iZone disasm
  corrected to the BYTE read `mov al,[eax+esi+0x34]` (stride 1, node base via `shl eax,6`), re-verified
  against the live `System/Engine.dll`; (4) multi-room single-zone is now GUARDED — `materialize.
  _multizone_warning` emits a warning (>1 Subtract / PF_Portal / ZoneInfo) instead of silently shipping
  wrong per-room zones (test `test_multizone_warning_fires_for_multi_room_and_is_quiet_for_single`).
  **Infra:** drive the game with `bin/uplayctl session start --map <MAP>` (NOT raw `docker run`); it
  needs the `dx-lum-uned` base image — do NOT `docker image prune -a` (it deletes that base; rebuild
  via `Tools/uedcli/uned` docker-compose, cache-fast). Disk is at ~96% — `docker system prune -f`
  periodically (NOT `-a`).
- **[spike] LIT-RENDER crash is LIT-ONLY and a LIGHTMAP-EMISSION bug — NOT Model completeness (side
  pool / Bounds RULED OUT).** p1. **Premise corrected 2026-07-16 (spike section 20 §12).** The earlier
  framing ("needs node Bounds and/or the `bspOptGeom` side pool") is **WRONG**: a full `Render.dll`
  disasm of the lit path proved it dereferences NEITHER `iSide`/`NumSharedSides` NOR node Bounds — so do
  NOT port them for lighting (the `c0`/`cc` writer arrays are irrelevant here too). And a live re-test
  shows the crash is **LIT-ONLY**: `NativeDark` (all-dark records, `iLightActors=-1`) now renders CLEAN
  (0 singularities, player possessed) — the old "NativeDark crashes" was stale (pre-collision-fix). Only
  LIT records (`iLightActors>=0`) crash `SetupNormalSurface`, so the fault is in the light-application
  path (light loop `0x10b070c6` → `AddLight 0x10b08b30`, bit-plane ptr `LightBits+DataOffset+i*bytesPerLight`).
  Our lightmap arrays are otherwise well-formed (grid matches `DXOnly` exactly; runs NULL-terminated;
  offsets in-bounds; basis non-degenerate). **CORRECTED ROOT (live binary-patch capture, 2026-07-16 —
  see spike `sections/20-lighting-bake.md` §13; this SUPERSEDES the earlier "bad `Model.Lights` pointer /
  AV at `AddLight`" conclusion):** captured the runtime value live and it is **NOT** the `Model.Lights`
  pointer — `Model.Lights.Data[iLightActors] = 0x07c9ce80`, a **valid MAPPED `AActor*`**. And **neutering
  `AddLight`'s `[ebx+0x1e0]` read (binary-patched to store-and-return) does NOT stop the crash**: NativeLit
  still logs `Anomalous singularity ... SetupNormalSurface → FLightManager::SetupForSurf`. So the fault is
  a **runtime FP singularity in `SetupForSurf`** — `Render.dll 0x10b07696 fdiv st(1)` divides by
  `|V|²`, `V=(0,0,0)` for one lumel ⇒ divide-by-zero. `V = M·g` (per-surface `FCoords` matrix `M`
  `[ebp-0xe4]`, built from the surf lightmap basis + `Pan`/`UScale`/`VScale` + lumel grid). **Tested & ruled
  out this session:** light position/symmetry (off-centre `(137,89,96)` light still crashes, 239
  singularities); `Model.Lights`/`LightBits`/serialization/geometry (all byte-exact, §12). **THE OPEN STEP:
  find which emitted per-surface lightmap input makes `M` degenerate for our surfaces but not for a real
  lit map's — (i) capture `M`/`g` live at `0x10b07453` with the same store-to-scratch patch (9 floats →
  `0x10b5c800..`, read back), OR (ii) field-diff our `iLA>=0` `FLightMapIndex`+surf basis vs `Entry.dx`'s 3
  genuine lit records (`iLA` 22/27/32 — `DXOnly` is all-dark, NOT a valid control). Harness committed:
  `harness/{game_capture_patch.py,game_capture2_travel.py,boot_watch_singularities.sh}`; capture/RE recipe
  in `engine-internals/gotchas.md` §4 (INT3 is DEAD for `__except`-guarded faults; store-to-scratch works).
  `game-entrypoint.sh` now RELAUNCHES until the link binds (beat the boot-deadlock). Fix is bake/emission
  side, NEVER a BSP port. `run_materialize_native` stays `no_light=True` until it lands.
  **FLAG for Andrzej:** this render crash has consumed ~2 context windows; the bake is byte-correct and
  maps LOAD fine, but the FP-singularity fix needs deeper live RE. Decide: keep drilling (capture `M`
  live / diff vs `Entry`), or ship lighting-bake-correct + render-off (`no_light=True`) and defer the
  render fix as a known engine-render quirk? (My lean: one more capture pass at `M`/`g` — it's now a
  narrow, well-instrumented target — then reassess.)
- **[plan] Native BSP leaf/solidity assignment — player FALLS THROUGH THE FLOOR (no collision).**
  p1. Surfaced 2026-07-15 once the render-crash was fixed and `NativeCSG.dx` (single-subtract room)
  finally ran: the game renders the room with ZERO render errors, but `GetPlayerPosition` shows the
  pawn at `z=-2,000,000+` and `phys=2` (PHYS_Falling) — it drops straight through the floor.
  **ROOT CAUSE RE'd (spike `sections/60-leaf-solidity-collision.md`, 2026-07-15): NOT iLeaf.** The
  game's `UModel::LineCheck`/`PointCheck` never read `iLeaf`; they decide solidity from
  `FBspNode::IsCsg()` (`Engine.dll 0xf68b0`: blocks iff `NumVertices>0 && (NodeFlags &
  (NF_NotCsg|NF_IsNew))==0`) and descend by re-deriving each node's side (`iChild[1]`=FRONT/positive).
  Two real bugs, both fixable in one `finalize_leaves_and_bbox` pass: (1) every node ships
  `NodeFlags=0x20` (`NF_IsNew`) → `IsCsg`=false → NO node blocks (DXOnly ships `0x00`); (2) our build
  stores the FRONT child in `i_front`(+0x20=`iChild[0]`) but the engine reads FRONT from `iChild[1]`
  (+0x24) → topology INVERTED → interior segment hits a leaf at node 0, floor plane unreachable.
  Fix (spec in §6 of the spike): exchange `i_front↔i_back`, clear `NF_IsNew`, set `iLeaf` front=empty
  /back=solid, `iZone=(0,1)`. Applied to parsed `NativeCSG.dx` it reproduces `DXOnly`'s node/flag/leaf
  /zone table exactly and makes every region resolve correctly in an engine-descent sim. `iLeaf` still
  gets fixed but for `PointRegion`/zone correctness, not the fall. A collision hull (`LeafHulls`) is
  NOT needed (`iCollisionBound=-1` skips the hull test, `0xf1bff`). **✅ RESOLVED + LIVE-VERIFIED
  2026-07-15:** §6 fix landed in `build.rs::finalize_leaves_and_bbox`; the live game now reports
  `phys=PHYS_Walking`, `speed=0`, `z=-134` STABLE (was `phys=Falling`, `z=-2,000,000+`) — the pawn
  stands on the floor, render still clean. Pinned by `test_finalize_collision_topology_matches_dxonly`.
  Remaining: multi-room leaf/zone (deferred `TestVisibility`), and wall/ceiling collision not
  separately exercised (same BSP mechanism as the verified floor). Repro: regen `NativeCSG.dx`
  (scratch `regen.py`), boot `dx-lum-game` with `DX_MAP=NativeCSG`,
  `docker exec -i <cn> python3 /work/client.py GetPlayerPosition`.
- **[debug] Native Model ships `bbox=(0,0,0)` — the Python parser drops the prefix bbox.** p3.
  Found 2026-07-15 (pre-existing, not lighting). `_build_level_model` does Rust-build → Rust-serialize
  → `umodel.parse_model_body` → assemble → `umodel.write_model_body`; the parser starts at
  `pos=_PREFIX` and never captures the 42-byte UPrimitive prefix (FBox bbox + FSphere), so the parsed
  Model defaults `bbox_min/max=(0,0,0)` and the final written map's Model bbox is zeroed (confirmed:
  `NativeCSG.dx` prefix bbox = all zeros). Tolerated live (both lit + unlit native maps render / walk
  with it — the engine recomputes/uses node bounds), but it IS a lost field. Fix: have
  `parse_model_body` capture the prefix bbox (+ FSphere) and retain it, so the round-trip preserves it.
  Low priority (harmless so far). The Rust serializer itself writes the correct bbox — it's only lost
  on the Python re-parse round-trip.
- **[flag for Andrzej][implement] N-4 light participation + radius are a HEURISTIC (no CDO read).**
  p3. `materialize._participating_lights` decides a light contributes to the bake by `LightType !=
  LT_None` from the trunk props, falling back (when `LightType` is absent) to "carries a light prop
  or is a `*Light` class"; missing `LightRadius` defaults to **64** (world radius `(64+1)*25=1625`).
  The CORRECT source for both is the class **default object (CDO)** in the game `.u` — the type-only
  schema (`uprops`) carries prop *types*, not default *values*. Fine for lights with explicit props
  (the common case + the test maps), but a light relying on class-default `LightType`/`LightRadius`
  is guessed. Fix when a CDO-default reader exists (also wanted for the materialize default-value
  omission gap). Non-blocking while lit render is gated anyway (see the N-4 handoff).
- **[spike] RESOLVED (loads + renders clean) — native from-scratch `.dx` game-load.** p1. The ULevel
  no longer fails to instantiate and the renderer no longer crashes: `NativeCSG.dx` (real Rust CSG)
  loads in the live game, possesses the player, and renders with 0 `OccludeBsp`/singularity/Critical.
  Two fix clusters landed: (a) six from-scratch serialization/structure bugs for load
  (export `RF_Load` flags; ULevel `TimeSeconds` 4-byte width; drop bogus `MyLevel` self-import;
  name-table `RF_Load` flags 0x70010; valid 2-zone Model `NumZones`; every actor carries
  `Level→LevelInfo` for the `Actors(0)==Level` assert); (b) the `FBspNode` field cross-wiring
  (`iRenderBound=0` into an empty Bounds array crashed `URender::OccludeBsp` on a NULL FBox) —
  fixed + documented in spike `50-model-ondisk-layout-and-render.md` (commit 51e47618b). Remaining
  playability gap tracked separately above (collision/leaf-solidity) and lighting is N-4 (view is
  black = unlit build). Original failure detail retained below for history.
- **[spike] (historical detail for the above) native from-scratch `.dx` did NOT game-load: engine could not instantiate the
  ULevel (`Failed to find object 'Level None.MyLevel'`).** p1. **First-ever game-load test of a
  natively-synthesized map (N-3 gate / M0 gate — never actually run before) FAILS.** Both a full
  N-3 multi-brush map (subtract room + add pillar + light + PlayerStart + DeusExLevelInfo, real
  CoreTexMetal texture import) AND the **minimal M0 carved-box map** fail *identically*, so the
  blocker is in the CORE from-scratch package assembly (M0 skeleton: `native/pkg_write` +
  `assemble` + `level_write` + `actor_write` + `umodel`), NOT in the N-3 typed-props / import
  synthesis (those are correct + tested) and NOT geometry quality. What we KNOW (headless DeusEx via
  `uplayctl session start --map <name>`, map symlinked into the game root from `DX/Maps/`): port
  **7777 comes up + the game possesses on the DX.dx boot map**; the travel `open <map>` runs
  (`Log: Browse:` + `Log: LoadMap:` + `Log: Loading: Package <map>` — the package DOES load), then
  `Warning: Failed to load 'Level None.MyLevel': Failed to find object 'Level None.MyLevel'` and the
  engine gracefully reverts to DX.dx (NO crash, NO other error line). So the package parses far
  enough to load, but the engine's linker never registers the `MyLevel` ULevel export — most likely
  `CreateExport`/`Preload` of the ULevel (or an actor) body silently fails so `FindObject<ULevel>`
  returns null. The header + name/import/export TABLES are byte-structurally identical to a real map
  (ver 68, licensee 0, pkgflags 0x1; Level export name=MyLevel, outer 0, flags 0x70001, cls→Engine.Level;
  LevelInfo0 exp[0] identical), and the file passes the always-on offline self-check + re-parse +
  the independent `bspspike` parser — so this is a body-serialization detail the ROUND-TRIP parsers
  don't catch but the ENGINE's real deserializer rejects (exactly §5/§7's "from-scratch synthesized
  values are the first real test" risk). Next: get a verbose per-object error — load the map in the
  **editor** (`dx-lum-uned` MAP LOAD logs the failing object/property) or read UE1 `ULevel::Serialize`
  / `AActor::Serialize` and diff my ULevel-trailing-block / StateFrame / property-tag bytes against a
  real map's level export byte-for-byte. Repro: `_scratch/native_e2e.py` (writes a map);
  `native.materialize.build_carved_box_package()` (the M0 map). This gates the whole native-materialize
  line — nothing ships until a native `.dx` actually loads.
- **[spike] `bspOptGeom` redundant-node removal (`Editor.dll 0x36870`) — decode to instruction
  level.** p2. Blocks the FINAL Tier-S surf-set parity for corpus case **b** (off-grid wedge) and
  contributes to **f** (portal). Context: the native CSG/BSP core (N-1) + N-2 cleanup passes
  (`bspMergeCoplanars` surface reassembly, `bspRefresh`, `bspBuildBounds`) now reproduce case b's
  node COUNT (19) and surf COUNT (11) EXACTLY, but 5 surfs' per-surf VERTEX SETS still differ. Root
  cause: `find_best_split` uses a **split-minimizing deviation** (see `uedcli-native/src/build.rs`)
  instead of the byte-verified MAP REBUILD `Balance=50` heuristic, because `Balance=50` over-splits
  (case c goes 12→24 nodes) and the editor only recovers via `bspOptGeom`'s redundant-node removal,
  which §7.2/§10 of `spikes/2026-07-15-native-materialize/sections/10-bsp-csg-build.md` describe
  **structurally but NOT instruction-by-instruction**. Need: disassemble `0x36870` (the node-dedup
  / "which split nodes are redundant" predicate) so the port can run the true `Balance=50` tree +
  trim and reproduce the editor's exact split distribution (e.g. b's far +X wall split at y=-87.5
  by a wedge plane the split-minimizing heuristic never makes). Simple adjacency-based trims were
  ruled out (they would wrongly drop b's far-wall split, which no surf is adjacent to). Differential
  harness ready: `uedcli/native/csg_golden.py` + `tests/test_csg_native_differential.py` (b/f are
  strict xfail).
- **[spike] Portal CSG: cospatial discard of a NotSolid-forced portal's side faces + multi-zone
  `TestVisibility` (`0xaa940`).** p2. Blocks corpus case **f** (portal). Two sub-unknowns: (1) the
  portal box's 4 side faces sit coplanar with the room walls; the editor DROPS them but native's
  `AddFunc` keeps them as `F_COSPATIAL_FACING_IN` (§4.3 says keep-unless-semisolid, and a
  Portal is forced NotSolid not Semisolid) — so either the decoded keep-set is incomplete for the
  portal-forced-NotSolid path, or a later pass drops them; needs a live differential to pin which.
  (2) `TestVisibility`'s multi-zone flood (`0xaa940` → `sub_aa370`'s ~8 passes) is only
  output-format decoded (§8), so f's 2-zone split across the `PF_Portal` face is not reproducible;
  native emits single-zone (§8.3). f additionally needs the `bspOptGeom` item above (walls split at
  z=±4). See the b/f xfail notes in `tests/test_csg_native_differential.py`.
- **[spec→plan / FLAG-FOR-ANDRZEJ] Native `level materialize` — full offline `.dx` build WITHOUT
  UnrealEd is fully reverse-engineered + specced.** p1. Done autonomously overnight (2026-07-15).
  The three hard unknowns are now closed: **CSG/BSP** (both D2 gaps — leaf-filter + node emission —
  byte-decoded, 33/33 checks), **lighting** (the decisive find: `LIGHT APPLY` stores **1-bit
  visibility masks, not intensities/colours** — collapses the "2nd long pole" to a per-lumel BSP
  ray test; format double-proven), and the **ULevel body / actor bodies / GUID mint / reachspecs /
  package assembly** (ULevel round-trips **100/100** byte-exact; GUID/gen **100/100**). Spec:
  `specs/2026-07-15-native-materialize-design.md`; evidence: `spikes/2026-07-15-native-materialize/`
  (3 sections + reproducible harness). **Two cold reviewers ran; findings folded** (Tier-K LineCheck
  battery reinstated, lighting shadow-correctness gate added, import resolver + `Actors[0]/[1]`
  synthesis owned, zones scoped honestly, Scale/UPolys assigned). **NEEDS ANDRZEJ SIGN-OFF** before
  the port: it PROPOSES decisions that revise the "lighting/paths = defer to optional editor
  final-bake" disposition (`spikes/2026-06-27-decontainerize-uedcli/05-lighting-and-paths.md`) — see
  spec §9. Until sign-off these are proposals, NOT in `decisions.md`. The port itself is a scoped
  multi-slice build (N-1..N-5, spec §7), not overnight work.
- **[DECISION-MADE / build-lang] Native materialize: editor DITCHED entirely (no `--native`/`--verify`),
  and hot loops go in RUST.** p1. Andrzej directed (2026-07-14): `level materialize` IS the native build,
  no flags, no fallback editor path; correctness = an always-on OFFLINE self-consistency check; the
  editor survives only as a dev-time golden-capture oracle. Perf was measured early (harness
  `.../harness/perf_probe.py`+`bench.py`): pure CPython misses the ≤2min/≤20s target — UNATCO-HQ ~71s,
  **UNATCO-Island ~7.6min** — so the two hot loops (CSG classify/split + BSP LineCheck) go in Rust with
  Python orchestration + the proven serializers. **Glue DECIDED: PyO3/maturin extension `uedcli-native`**
  (in-process; FFI boundary = the `UModel` body as bulk `bytes`; ship=Nuitka, venv=dev-only; sidecar
  rejected). Adds a Rust toolchain to dev. Spec §3/§4/§6/§8/§9 updated. **Reviewed (2 architecture
  reviewers, findings folded):** mandatory §6 **gate 5** (Rust↔Python serializer cross-check — anti-drift);
  FFI mechanics (`Result`→`BuildError`, panic-catch, `Python::allow_threads` for interruptibility);
  staged API (geometry/bake/paths, paths returns separately); rayon determinism invariant; **M0**
  glue+game-load proof before N-1; `_venv.sh`/`bin/test` need real Rust-build integration (optional/
  skippable, source-hash-gated). **Two flagged open items now RESOLVED by spikes 40/41
  (`spikes/2026-07-15-native-materialize/40-nuitka-pyo3.md`, `41-fp-model-x87-vs-sse.md`):** (1) **Nuitka
  + PyO3 PROVEN** — trivial `abi3-py312` module bundles + loads under both `--standalone` and `--onefile`
  (auto-detected, like Pillow); gotchas measured (needs `patchelf`; glibc floor 2.34; Linux/x86_64 only —
  cross-platform matrix separate; `level preview`/stub-build still need Docker). (2) **FP model = SSE,
  NOT x87** — the UED22 DLLs are 2022 MSVC `/arch:SSE2` rebuilds (zero x87/`fldcw`/FMA), so **bit-exact
  parity IS reachable with native Rust `f32`**; remaining work is deterministic op-ORDER fidelity
  (replicate `PlaneDot`'s reduction, forbid FMA). **Still open:** there is NO CI — gates are a
  local-runner responsibility until one exists. **Build STARTED** (M0 + Python glue + Rust core) in a
  worktree; port not sign-off-complete.
- **[FLAG-FOR-ANDRZEJ] Native-materialize residuals that need ONE differential editor run each** (the
  only things static disassembly couldn't close; all non-blocking, enumerated in the spec §5/§7): the
  Add/Intersect/Deintersect CSG filter-func keep-sets (byte-decoded now, confirm live); the lightmap
  lumel→world **inverse-basis** (validate one baked surface before trusting shadows — a correctness
  residual, not cosmetic); the NavigationPoint 16-int static-array property-tag encoding; `R_DOOR`/
  `R_PLAYERONLY` reachflag values (5/7 confirmed); full multi-zone `TestVisibility` portalization
  (first cut = single-zone). None block N-1..N-3.
- **[chore] Fix `bspspike/umodel_parser.py` `FBspSurf` mislabel:** field at mem `+0x18` is `iLightMap`
  (parser calls it `i_actor`); `+0x24` is the brush `Actor`. Verified via `GetLightMapIndex`
  (`Engine 0x1127c0`). Fold in at native-materialize N-4. p3.
- **[implement] AUTO-stub referenced packages in `level materialize` (capability, not safety).** p2.
  Since the uniform-mount cutover (decisions.md 2026-07-14 19:21) the editor mounts the whole composed
  set, so v68 `.u` are on its Paths (shadowed by `/stubs` for STUBBED packages). The SAFETY hole is
  already closed: `ensure_load`'s `unloadable_v68_packages` gate refuses an unstubbed v68 code package
  with a clean error before any `OBJ LOAD` (no more wedge). What's LEFT is the capability — so a level
  referencing a DeusEx class actually BUILDS: `run_materialize`/`render_shots` should
  `stub_missing_packages(search_dirs=…)` the referenced v68-only packages before the editor load (the
  pattern `qualify.export_and_qualify` uses), instead of erroring. Needs a working stub build (env
  currently blocked by absent `Effects.u`).

- **[flag for Andrzej][debug] Materialize post-verify fails when the trunk carries a prop equal to
  its CLASS DEFAULT.** p2. The editor OMITS default-valued props on export, so a trunk that stores
  an explicit default fails H3 post-verify. Confirmed across MULTIPLE props on the 161-actor castle
  (2026-07-14): `LightPhase=0` is dropped (Light default 0) AND `LightPeriod=32` is dropped (Light
  default 32) — while NON-default values of the SAME props are preserved (`LightPhase=130`,
  `LightPeriod=24` survive the round-trip). So it is genuinely default-VALUE omission, not a
  computed/volatile field (do NOT add these to `COMPUTED_PROPS` — that would wrongly strip a
  non-default authored value too). Surfaced AFTER the qualify/LevelInfo/float32/Normal fixes landed
  (those are DONE and make the castle round-trip faithful up to this point — see `decisions.md`
  2026-07-14). This is the last known materialize round-trip gap. A correct general fix needs
  class-default awareness — decide the approach: (a) a baked per-class default table, or (b) read a
  freshly-spawned actor's defaults from the editor during materialize (it is already running), then
  strip trunk props equal to the default on BOTH sides before hashing. NOT done here: it needs your
  call on approach, and guessing "looks default" (e.g. any `=0`) risks erasing meaningful explicit
  values. Also: the castle build helper should stop emitting default-valued Light props in the
  first place. **Update 2026-07-18:** the missing class-default-VALUE capability is being built by
  the `actor prop` subcommands work (spec `specs/2026-07-18-actor-prop-subcommands.md` §5 — offline
  binary defaults decode, a third route beating both (a) and (b)); Andrzej decided (decisions.md
  2026-07-18 10:02 §11) this verify fix stays a SEPARATE item that consumes that capability once it
  lands.

- **[flag for Andrzej] `brush build --name` was a HARD rename to `--base-name` — no back-compat
  alias.** p3. Done 2026-07-12 per your rename directive. A cold reviewer flagged that this is a hard
  break on an LLM-facing surface: any existing prompt/example using `brush build --name` now fails
  with argparse "unrecognized arguments". Deliberately NOT aliased (you chose the clean break to push
  the correct spelling into prompts). If LLM-prompt breakage bites, a hidden alias is ~1 line:
  `add_argument("--name", dest="base_name", help=argparse.SUPPRESS)`. Decide keep-broken vs alias.

- **[flag for Andrzej] `--target` v1 — one LOW edge left (two others FIXED in post-build review).**
  p3. Of the three edges the `--target` build reviewers surfaced (2026-07-12): (a) corrupt-box
  traceback and (b) emptied-stash "not found" were **FIXED** in the post-build multi-reviewer pass —
  `StashLevelSource`/`PrefabLevelSource` `load` now catch a corrupt box → clean exit 2 (plus the
  pre-existing `stash show`/lifecycle corrupt-`meta.json` traceback, guarded in the same pass), and
  the stash existence oracle moved to a `meta.json`-keyed `FileStashRegister.exists()` so an emptied
  stash stays targetable; all with regression tests. **Remaining (c):** `--target prefab/<name>`
  requires a resolvable project (`_resolve_project` runs for all three kinds) even though the prefab
  library root is repo-relative, not project-scoped — a minor over-constraint matching the spec's
  "all three live under the project". Cheap to relax if it bites; left as-is.

- `[spec]` **Nuitka standalone-release build for uedcli.** p2. The dev loop now runs uedcli in a
  Python-3.12 Docker image (`bin/uedcli` + `docker/Dockerfile` + `bin/_dev-run.sh`; see
  `dev/docs/dev-runtime.md`). The intended *release* is a Nuitka-compiled single binary (interpreter
  + Pillow baked in, no host deps). Open: how the editor-driving verbs' Docker dependency is handled
  in a standalone binary (the binary still needs a docker CLI + daemon to spin editor containers).
  (Deferred per Andrzej, 2026-07-11.)

- `[implement]` **Editor-driving verbs under the dev wrapper leave root-owned files.** p2. The dev
  container runs `--user host-uid`, but the sibling editor containers it spawns (`editor.py`'s
  `docker compose run`) run as **root** with no `--user`, so files they write into mounted host paths
  (`~/.uedcli/cache/stubs`, editor scratch) become root-owned and can then block the host user / the
  `--user` dev container from rewriting them. (This already bit us: a pre-existing root-owned
  `~/.uedcli/cache/stubs` from an earlier editor/stub run — `sudo chown -R "$USER":"$USER" ~/.uedcli`
  clears it.) Fix: run editor containers as the host user, or make the caches tolerate mixed
  ownership. Also: only the repo + `~/.uedcli` are identity-mounted — per-game base-asset `paths`
  outside the repo (`[games.*]`) will need identity mounts once materialize wires them. Full editor-
  verb validation under the wrapper (path translation, socket perms) is still unrun.
  (Flagged 2026-07-11 during dev-wrapper build; from cold-review findings.)

- `[chore]` **Confirm or downgrade the ✅ confidence markers on two salvaged engine facts.** In
  `unrealed/quirks.md` I marked the builder-brush-identification predicate and the multi-actor
  group-rotate ground truth **✅** (uedcli-used / live-verified) although their source spikes are 🔬
  live-probes — downgrade both to 🔬 if you want strict source-spike confidence. (AI flag, 2026-07-11.)

- `[chore]` **Relocate or delete the orphaned `dev/docs/spikes/bspspike/` harness.** Bare
  `bsp_csg.py`/`bsp_editorlog.py`, no markdown sibling, and nothing links it (every reference points at
  `_scratch/bspspike/`). Tied to the parked offline-BSP work — move it under a
  `2026-06-24-offline-bsp-engine-*` slug, or delete if `_scratch/` holds the authoritative copy (git
  keeps history). (AI flag, 2026-07-11.)

- `p2` `[implement]` **Rebuild the mover/stash/surface LIVE round-trip integration tests on
  `run_materialize`.** Slice 6 deleted `test_mover_integration.py`/`test_stash_integration.py`/
  `test_surface_integration.py` (they were bound to the deleted `SessionStore`+`run_apply`). The
  materialize round-trip is covered by `test_materialize_verb.py`, but the substrate-specific live
  assertions those held have no equivalent — e.g. a mover's `KeyPos(1)`/`KeyPos(2)`/`KeyRot`/no-`CsgOper`
  surviving a real editor cycle. Re-author on `run_materialize` + a trunk `Level` (start with the mover
  one — highest-value). Substrate-gated (`-m integration`), so it can't be verified on a box without the
  `dx-lum-uned` container. Surfaced by slice 6 (2026-07-07).

- **Namespace the stub cache by substrate** (`.uedcli/cache/stubs/` → e.g. `.../stubs/deusex/`, or
  key it by substrate id). Stubs are inherently substrate-specific (the v68→v69 DeusEx conversion);
  separating them per-substrate aligns with the generic-UE1 direction (per-substrate, no DeusEx
  baked into shared paths) and avoids cross-substrate name clashes if a second substrate is ever
  added. Touch points: `config.stub_cache_root`, `packages._stub_cache_dir` /
  `substrate_search_dirs`, the `/stubs` bind-mount, cache-key/migration. Surfaced 2026-06-26 (Andrzej).
  Small but has a substrate-identity design angle — triage to `to-spec`/`to-build` accordingly.

- **De-containerize uedcli (drop Docker/wine/`.exe`) — roadmap specced, awaiting Andrzej's scope
  decision.** `p2` Spike series `../spikes/2026-06-27-decontainerize-uedcli/` (texture/mesh/package-
  write/qualify/lighting/stub-elimination) + roadmap `../specs/2026-06-27-uedcli-decontainerization-roadmap-design.md`.
  PROVEN native: texture decode (pixel-exact vs UCC), package-container write (byte-exact), qualification.
  CONFIRMED: stubs exist for mesh-format + Engine/Core divergence (not v68/v69); native write deletes the
  whole stub pipeline. The dominant work is the offline BSP engine (D2) + completing/​inverting the `Model`
  serial format. **Geometry premise CONFIRMED game-side (🔬 2026-06-28, `decisions.md` 2026-06-28):** the
  game never re-runs CSG and uses the pre-built BSP for render AND collision (0-node world → spawn crash;
  68-node → spawns + walks); v69 `.dx` loads in v68 game. So Q0 is now a pure effort/strategy fork, not a
  feasibility unknown. **Next gate (cheap, high-value, runnable now): hand-build a minimal native `Model`
  → native `.dx` → load in `dx-game` → does the player spawn?** — every game-pass so far used the editor's
  `EDIT PASTE`; a natively-synthesized `Model` has never been game-loaded. **Still blocked on Andrzej's Q0
  scope decision** (promote D2 to required vs editor-`MAP REBUILD`-only-geometry intermediate) — a scope
  call only he can make. Once decided: Phase A (native texture sync / qualify / `.dx`-read,
  container-free, low-risk) and Phase B (native package writer + `FPropertyTag`/`ULevel` body) triage to `to-plan`.

- **De-containerization follow-on spec items** (surfaced by the 2026-06-27 spike series;
  all gated on Andrzej's scope decision Q0 in the roadmap spec). Each is its own future
  `[spec]`/`[spike]`:
  - `[spec]` p2 — **Native package WRITER module** (`package_writer.py`): from-scratch
    serializer from the proven primitives (`package_rw` encoders + `prop_writer` + StateFrame),
    incl. offset back-patch, GUID/generation + version policy, `ULevel` body, and patching
    internal absolute offsets (FMipmap/lazy-array/Model) when a body is relocated. (Phase B.)
  - `[spec]` p2 — **Native `texture sync`** wired to `utexture` decode (drop the UCC/PCX/
    container seam). (Phase A; lowest-risk immediate win.)
  - `[chore]` p3 — **Fold `umodel_serialize.detect_prefix` back into `umodel_parser.py`** so
    the READ parser handles the 57-byte UPrimitive-prefix variant (243 models; one,
    `00_TrainingCombat.dx Model413`, has real geometry the fixed-42 assumption mis-reads).
    The serializer already auto-detects; the parser doesn't. Mind its callers
    (`native_render.py` etc.). Surfaced by `spikes/2026-06-28-umodel-serialize-byte-exact.md`.
  - `[spike]` p2 — **Native `Model` GAME-load gate** (the cheap D2 de-risk, now unblocked):
    hand-author a minimal carved-room `Model`'s arrays, emit natively via `umodel_serialize`
    + the package writer, load in `dx-game`, confirm player spawns. Serialization is proven
    byte-exact (`decisions.md` 2026-06-28); this tests a *natively-emitted* (vs editor-built)
    Model end-to-end. Gates Q0's D2 commitment.
  - `[spec]` p2 — **Native qualification** in `qualify.py` (import-table read + manifest
    name→package index w/ load-order collision policy), replacing OBJ DEPENDENCIES/OBJ LIST.
  - ~~`[spike]` p3 — **Native mesh DECODER**~~ — **DONE 2026-07-25**
    (`spikes/2026-07-25-native-mesh-decode/`): full `UMesh`/`ULodMesh` body decodes byte-exact on
    902 meshes (466 retail v68 + 436 UED22 v69), vertex stride self-detects, textured render
    proven. `umodel.exe` is no longer needed for a mesh READ — it survives only inside the stub
    pipeline. Remaining: productise the harness into `uedcli/` (rides the asset-catalog build).
  - `[spike]` p3 — **Native textured preview** — **superseded: specced as `level preview --native`
    (Andrzej 2026-07-16)**; see `specs/2026-07-16-native-preview-design.md` + the `to-plan.md` entry.
  - `[spec]` p3 — **Native lighting baker** (2nd long pole): per-lumel raytrace producing the
    `FLightMesh` + lumel bytes (~1.7MB/small map); downstream of D2. Plus native pathnode
    reachspec build (moderate).
  - `[spike]` p3 — **Native sound/music decode** (`.uax`/`.umx`): DeusEx `.uax` has NO RIFF
    (raw PCM or other encoding — storage TBD); off the de-containerization path (external
    refs), for a future sound catalog.

- `[flag for Andrzej]` **Two different UIs for "read a T3D from file-or-stdin".** p3. `actor add`
  takes a **positional** arg (`-` = stdin, else a path), while `stash capture` takes **flags**
  `--from-t3d PATH` / `--from-stdin`. So `actor add` can't use `--from-t3d` and `stash capture`
  can't take a positional `-`. The error handling is now unified (`_read_t3d_input`), but the surface
  is split. Defensible (stash capture's default source is the selected level, so it needs explicit
  override flags), but worth deciding whether to also accept `stash capture -` for symmetry.
  (Surfaced by a cold reviewer during the exception-safety hardening, 2026-07-12.)

<!-- ═══════════════════════════════════════════════════════════════════════════════
     DOGFOODING FINDINGS (2026-07-12) — surfaced building, previewing, and expanding
     a castle end-to-end (brush build → actor add → doctor → level preview → texture →
     materialize → concentric-bailey expansion). Grouped by subsystem; deduplicated;
     CRITICAL/HIGH severity called out inline. See decisions.md 2026-07-12 (preview).
     ═══════════════════════════════════════════════════════════════════════════════ -->

### Brush building & placement
Castles are walls-with-teeth-in-rings; every one of these is about placing repetitive
axis-related geometry without hand-doing the arithmetic.

### level preview (snapshot renderer)
The posing rewrite landed (POS@ROT → auto-frame; decision 2026-07-12); these are the residual gaps.

- `[chore]` **Exterior hero shots need an open/skybox level, not a sealed room.** p3. Every camera is
  inside the enclosing `World` subtract → no exterior bird's-eye. That's level geometry, not a preview
  limit — fold into the castle content (open/tighten the room) if exterior shots are wanted.

### level materialize
**RESOLVED — live-confirmed 2026-07-19.** The whole cascade is fixed: `qualify` off-by-one FIXED (regression-tested), semisolid-MAP-SAVE proven NOT-a-bug (5/5 spike), and the two texture-package CRITICALs (H3 re-export; symlink-outside-repo drop) LIVE-CONFIRMED fixed — a real materialize of the 161-actor castle trunk referencing three external packages (`LUM_CoreTex`, `CoreTexWater`, `CoreTexSky`) built clean (448858-byte `.dx`, exit 0 ⇒ H3 verify passed, zero "Can't find file", all three packages present in the import table). The only survivor is the defensive-warning residual below.

<!-- ── boot-flake retry follow-ups (from the 2026-07-19 review gate on the bounded-retry change) ── -->

- `[flag for Andrzej] p3` **Should the editor readiness-retry also recover wineprefix corruption?** The
  bounded `ensure_editor` retry (landed 2026-07-19) reaps only the *container* and re-mounts the same
  per-id `uned-wp-<id>` wineprefix volume each re-spin — so it recovers transient container/X-display
  startup races but NOT a corrupt/half-initialized wineprefix. Wiping the volume (`docker volume rm`)
  between attempts would cover that too, at ~0.5 GB wine re-init per retry. Deliberately deferred; your
  call whether the retry should escalate to a volume wipe on a later attempt.

- `[chore] p3` **`native/csg_golden.py:362` calls `ensure_editor(editor_id)` with no `state_dir`** (now a
  required kw-only arg → `TypeError`), and its `try/finally stop_editor` starts after the call, leaking
  the wineprefix volume on an `EditorNotReadyError` give-up. Harness-only (native golden-capture spike),
  pre-existing — clean up when next touching that harness.

### actor & build verbs

- `[debug]` **HIGH: `actor delete`/`actor find` glob missed a `LevelInfo`-class actor.** p2. `actor
  find --class LevelInfo` + `--name 'LevelInfo*'` fed to `actor delete` did NOT remove it → a later
  `actor build Engine.LevelInfo` produced two → materialize precondition trip "found 2". Check
  `actor find`'s `--class`/`--name` handling for `Engine.LevelInfo`-class actors.

### texture workflow

- `[implement]` **LOW: `project show` reports "0 package(s)" while the path actually resolves.** p3.
  Printed "0 packages" in-container (dangling DeusExAssets symlink — see the materialize texture bug)
  while a host check saw 56, with nothing tying them together → chased a non-issue. Count should
  reflect the resolved/composed set, and warn (not silently show 0) on a dangling in-container glob.

<!-- ── castle moat/expansion round (2026-07-12): more dogfooding ── -->

- **Water cluster — RESOLVED / triaged 2026-07-19 (live-verified).** WaterZone authoring needs NO
  bespoke scaffold verb: `actor build Engine.ZoneInfo --prop bWaterZone=True | actor add -` (or the
  placeable `DeusEx.WaterZone` class) round-trips the props into the trunk, schema-validated. The two
  reported doctor false-positives: watertight-on-portal-sheet is ALREADY FIXED (2026-07-18;
  `_brush_polyflags` OR's per-poly flags — verified zero findings on a real portal sheet); the
  fallthrough-on-nonsolid warn has been REMOVED (the `doctor` `fallthrough` check was deleted) and
  `brush build sheet --flag <name>` was added — both landed 2026-07-19. (Deferred follow-up: the same
  `--flag` build-time passthrough on the OTHER `brush build` generators — cube/cylinder/… emit
  multi-face solids where a per-face flag differs semantically from a single-face sheet, so it wants
  its own decision.) The water-authoring recipe (water = a translucent NONSOLID zone-portal SHEET over a `bWaterZone`
    ZoneInfo; portals must be non-solid, not semisolid) folds into the level-design docs + AI-skills
    item below. (Content gap, not a tool gap: LUM_CoreTex ships no dedicated water texture — but the
    base `CoreTexWater` package is now reachable, see the base-texture RESOLVED note above.)

- (reinforcement) The **moat ring** was 8 hand-placed brushes (4 subtract trenches + 4 water) plus
  manual arithmetic to clear the bailey towers' ±388 reach — again the **wall-run/ring/perimeter
  generator** + **`actor bbox`** gaps already logged. Rings/moats/walls are the dominant castle
  primitive; a ring generator would collapse most of a build.

<!-- ── moat water / DeusEx-package wiring (2026-07-12): dogfooding + a concrete cost of a logged CRITICAL ── -->

- **RESOLVED (live-confirmed 2026-07-19) — the DeusEx base texture library is now fully reachable.** The
  old root cause (the dev container mounting only `$REPO_ROOT=LUM`, so the parent `DX/` was unmounted and
  `DX/Textures` globbed to zero) is gone: uedcli runs HOST-NATIVE since 2026-07-14, and config `paths`
  are bare dirs. `[games.deusex].paths` already lists `.../DX/Textures`; `project show` resolves 264
  packages (54 base `.utx` tagged `[base]`), and a base-only package (`Airfield.utx`, 108 textures) syncs
  and decodes clean. No mount, no stopgap-copy needed. (Was: `[flag for Andrzej]` p1.)

<!-- ── diagonal expansion (2026-07-12): grid-aligned diagonal walls via vertex-shear ── -->

<!-- ── composition + grouping ideas (2026-07-12, Andrzej) ── -->

- `[spec]` **Name-taking verbs accept actor names from STDIN (`-`).** p2. `actor find` already prints
  matching names one-per-line for piping, but the mutate/query verbs take names only as CLI args, so
  the pipe doesn't close: you copy-paste or `$(...)`-substitute. Let `actor set -` / `actor prop -` /
  `actor delete -` / `actor rotate -` / `brush poly set -` etc. read the newline-separated name list
  from stdin, so `actor find --group castle.tower | actor prop - --set Texture=…` composes end-to-end
  (mirrors `actor add -`'s stdin convention). Andrzej, 2026-07-12.

<!-- ── uplayctl in-game screenshot dogfood: PlayerStart-in-solid (2026-07-12, Andrzej) ── -->

<!-- ── castle detail-pass dogfood: semisolid materialize bug (2026-07-13, Andrzej) ── -->

- `[spec]` **`level preview` auto-frame gives awkward interior compositions; no "hero" exterior shot.** p2.
  The overview (`all`) frames the enclosing room subtract from INSIDE at wall height → you get a
  looking-across-a-dark-floor view, never an aerial/exterior of the structure. For screenshotting a
  build there's no way to pose an outside-looking-in hero shot (rotation-posing was already dropped —
  see the earlier preview-rotation inbox item). A `preview` vantage that pulls back outside the level
  bounds (or frames a set of brushes from their collective outside) would make build screenshots
  actually sell the geometry. Andrzej, 2026-07-13.

- `[chore]` **Lighting lesson: `LE_NonIncidence` fill lights over-brighten baked in-game lighting.** p3.
  In `level preview --mode lit` the castle looked moody (good contrast); in-game the same lights
  washed the walls near-fullbright. Cause: I used many `LE_NonIncidence` fill lights (ignore surface
  normals → brighten everything) layered with the existing 28 lights. Lesson for the substrate notes:
  preview-lit ≠ in-game baked lighting; use FAR fewer/dimmer fills, rely on motivated torch pools +
  deliberate dark gaps. Worth a line in a lighting doc. Andrzej, 2026-07-13.

- `[chore]` **Asset-wiring Part A: base-game config dir typos are silently skipped (diagnosability
  cost).** p3. `config.resolve_dirs` skips a NON-existent dir even under `require_absolute=True` (the
  games config) — the intended offline-safety behavior (decisions.md 2026-07-14 03:30: model verbs
  must run without the base game installed). Cost: a typo in `~/.uedcli/config.toml`'s game `paths`
  degrades to a generic downstream error (empty schema code-path → `SchemaError`; incomplete load
  set → materialize "missing package"), never "configured dir X does not exist". Both cold reviewers
  flagged it (2026-07-14). Consider an OPT-IN existence check / `uedcli doctor`-style config lint for
  the games config, where existence is not offline-optional. Not a bug — a UX follow-up.

- `[flag for Andrzej][debug] Asset-wiring Part A: `actor prop`'s new config-error path has no
  regression test, and `_class_schema` still isn't project-threaded (Part B).** p2. `dispatch._class_schema`
  now resolves the project from cwd/env + loads the games config, so a present-but-broken config
  (malformed TOML / ambiguous project / game named by the project but absent from the games config)
  raises `config.ConfigError` mid-`actor prop` → caught by `dispatch()` → exit 2 (verified clean, no
  traceback). But: (a) no offline test exercises it (the tests monkeypatch `_class_schema` as a
  seam), which the tool's "cover each no-traceback path with a regression test" rule wants; and (b)
  the invocation's `--project` flag is NOT threaded into schema resolution (it re-resolves from
  cwd/env, keeping the 1-arg seam), so a `--project` override can't reach the schema path. Part B:
  thread the resolved project down from the `actor prop` handler and add the regression test. Marked
  in code with `# TODO(asset-wiring Part B)` (dispatch.py `_class_schema`).

- **[flag for Andrzej][implement] Native materialize: M0 landed; wire apply.run_materialize as the
  SOLE path only after N-1 CSG parity.** p1. The native glue (`uedcli/native/`) + Rust crate
  (`uedcli-native/`) are in: a trivial carved-room `.dx` assembles, passes the always-on offline
  self-check, and re-parses with both parsers; §6 gate 5 (Rust `model_write` == Python oracle) passes;
  `fpoly.rs` is the N-1 start. **Deviation from spec §3/§4 ("editor DITCHED, native is the ONLY
  path"):** `apply.run_materialize` still drives the editor. Flipping it now would make `level
  materialize` non-functional for real (multi-brush) levels — the Rust CSG core (csg/build/passes/
  zones/linecheck/light/paths) is N-1..N-5 and unbuilt — and would break the editor-mock materialize
  tests. I did NOT rip out the working editor path with a non-functional replacement; the cutover is
  gated on: (1) N-1 CSG reaching Tier-S parity (§6 gate 3), (2) N-3 full trunk-actor typed-property
  serialization (`_trunk_to_actorspecs` currently carries class + Location only), (3) migrating
  `test_apply`/`test_materialize*` off the editor mock. Confirm this sequencing is what you want.
- **[implement] Native materialize remaining slices (N-1..N-5).** p1. **N-1 CSG core LANDED
  (2026-07-15):** `fpoly` (Finalize/Reverse/Transform/SplitWithPlane) + `csg` (bspBrushCSG two-pass
  leaf-filter, FilterEdPoly/FilterLeaf cospatial routing, all 4 CsgOper funcs) + `build`
  (bspAddNode/FindBestSplit/SplitPolyList/bspBuild, pooling, surf-sharing) are ported and wired into
  `lib.rs build_geometry` (flat-buffer brush API). Validated by an **editor-golden differential** —
  the harness (`native/csg_golden.py` + frozen `tests/fixtures/csg_golden/*.json`, captured on a
  live ephemeral editor) plus `tests/test_csg_native_differential.py` (offline). **Tier-S surf-set
  parity reached on cases a (single subtract), c (add-in-subtract), d (abutting-subtracts — the known
  prior-port 11-vs-10 ANNIHILATION bug, PROVEN fixed via the exact-0.0 cospatial facing route), e
  (semisolid detail).** cargo: 13 tests; pytest: 6 pass + 2 xfail. **RESIDUALS (see below).** Still
  to build: N-2 zones/cleanup, N-3 `pkgref`+typed props+game-load smoke, N-4 `linecheck`+`light`,
  N-5 `paths`. FP-model + Nuitka bundling already de-risked (spikes 40/41).
- **[implement] N-1 residual: `bspMergeCoplanars` (§7.1) coplanar-face union.** p2. The off-grid
  wedge golden (case b) fails Tier-S: native emits ~2× surfs (un-merged coplanar fragments where a
  brush clips a wall into pieces the editor merges). `build.rs merge_coplanars` is currently a NO-OP
  (identity) — it happens to match a/c/d/e (disjoint or seam-split faces stay separate), but case b
  needs the real edge-adjacent coplanar polygon union + a `RemoveColinears` re-pass. Also the
  split-minimizing `FindBestSplit` variant (documented in `build.rs`) substitutes for the later
  merge/opt passes; a faithful merge would let `FindBestSplit` revert to the exact engine score.
  Tracked by xfail `test_case_b_offgrid_wedge_residual`.
- **[implement] N-1→N-2 residual: portalization/zones (`TestVisibility` §8).** p2. The portal golden
  (case f) fails Tier-S: native is single-zone (1 leaf, no zone split), the editor makes 4 zones / 3
  leaves / 16 nodes from the portal brush. The portal NotSolid force (§5) IS applied; the missing
  piece is the zone flood (`sub_aa370`'s ~8 passes — output-format decoded, algorithm not). This is
  the same N-2 single-zone→multi-zone slice. Tracked by xfail `test_case_f_portal_residual`. Leaf
  COUNT parity for multi-region carves (golden c=6 leaves) is the same slice (native emits 1).
- **[spike] M0 native `.dx` game-load smoke — what's needed (not done this run).** p2. The M0 box
  (`materialize.build_carved_box_package`, written by the test to `_scratch/m0_box.dx`) passes the
  offline self-check + both parsers, but was NOT loaded in-game (the running containers are dev
  shells/dind, not a booted headless DeusEx on :7777). To close: (1) drop the `.dx` in the game's
  `Maps` search path; (2) boot headless DeusEx (uplayctl-style) and `open m0_box.dx`; (3) assert boot
  to :7777 with no load error, the player spawns at `PlayerStart0`, and a `Screenshot` renders
  non-black. Caveats the M0 box will expose first: surfs are UNTEXTURED (`texture_ref=0` → renders
  black even if it loads — add a texture import via `pkgref` before judging render), and the actor
  set carries class + Location only (N-3 typed-prop serialization). This is the §6 gate-4 game-load
  smoke, first real test of from-scratch synthesized values.

<!-- ── AI brainstorm (2026-07-16, "uedcli:creative" session) — un-triaged idea capture;
     checked against every board queue for duplicates before writing. Grouped by theme. ── -->

### Brainstorm — small composable wins

- `[debug]` **Native materialize silently IGNORES `PostScale` and `SheerRate`** (only `MainScale` is
  read — `materialize.py::_build_brush_input`; the Rust scale check never sees them), so a brush
  carrying either mis-builds with no error — exactly the "silently mis-builds" class
  `FPoly::Transform`'s scale rejection exists to prevent. p2. Surfaced by the native-preview spec
  review (2026-07-16); the preview spec checks all three fields itself (§4.2) and does not inherit
  the hole. Fix materialize's brush-input gate to match.

- [spike] p2 **Native BSP exact-topology parity → byte-identical `.dx`. NOW SPECCED:**
  `specs/bspbrushcsg-port.md` (2026-07-17) sequences the port foundation-first with a byte-diff gate
  per phase (topology → FVert/point pool order → surfs → render Bounds+LeafHulls → lightmaps →
  package wrapper), deletes the synthetic leaf-bounding scaffold, and settles the FP-determinism
  question (provisionally ACHIEVABLE — decoded routines are SSE-scalar, not x87 — gated on a Phase-0
  per-site characterization). **Blocked on:** (1) the two review-gate subagents, (2) Andrzej's calls
  on spec Q1-Q5 (byte-identity scope incl. package GUID; canonicalization fallback if a site is
  x87/rsqrt; effort ceiling; oracle-regen authority; trunk brush-flag round-trip). **Phase 0 is a
  BLOCKING decode+FP spike** (instruction-level `bspBrushCSG`/`FilterFPoly`/`bspBuildFPolys`/
  `bspMergeCoplanars`/`bspOptGeom`, FP x87-vs-SSE per hot site, editor-determinism diff). Context:
  castle nodes 909 vs **1156**, FVerts 3604 vs **16163**, surfs 438 vs 485, Bounds 0 vs 484. Once
  reviewed + Andrzej's calls land, move to `to-plan.md`. N-3+.
  **UPDATE 2026-07-17: Phase 0 DONE — verdict GO** (`81-phase0-feasibility.md` +
  `re-raw-zones/fp-classification-sites.md`, decision 2026-07-17 18:00). FP is SSE-scalar (the DLLs
  are a 2022 MSVC/SSE2 rebuild — MD5-identical to the golden-building container, NOT 1999/x87), input
  identity holds (castle = pure translation), normal provenance = PRESERVE, pool order/`NumSharedSides`
  reproducible. The FP crux is resolved FAVORABLY; remaining blockers are the review gates + Andrzej's
  Q1–Q5, and the port-prerequisite decodes (`FilterFPoly` leaf funcs + bevel planes, `bspBuildFPolys`,
  `bspMergeCoplanars`, `FindBestSplit` score op-order) — these gate the port, not the GO verdict.

- [spike] p3 **Rotated-brush input identity (byte-identity precondition for UNATCO-class content).**
  The castle is all identity-transform brushes so native `v+Location` is bit-trivial, but the editor's
  `Actor::BuildCoords` FRotator→matrix uses the `GMath` sine LOOKUP TABLE (`FGlobalMath`), NOT libm
  `sinf` — so reproducing rotated-brush world verts bit-exactly needs that table ported.
  **UPDATE 2026-07-17: FUNCTIONAL rotation is now ENABLED** (no longer rejected).
  `materialize.py::_build_brush_input` builds the rotation matrix via `rotation.actor_matrix` →
  `euler_to_matrix_uu`, which ALREADY reads the ported `GMath` sine table (`rotation.gmath_sin/cos`,
  indexed `(field>>2)&16383`) — the same table+convention `preview_native` uses and that
  `spike 2026-06-19-frotator-convention` verified against the editor to ~1e-5uu. So the "port the
  table" premise is already satisfied by `rotation.py`; verified on a controlled −90° Yaw box
  (`+X(256,0,0)→(0,−256,0)`) and pure/combined Yaw/Pitch/Roll boxes matching `rotation.world_vertices`
  exactly. The full 762-brush UNATCO trunk (283 rotated brushes) materializes clean. What remains for
  BYTE-identity is only whether `euler_to_matrix_uu` reproduces `BuildCoords` bit-for-bit (matrix
  ELEMENT order / rounding), folded into the `bspcsg` byte-identity port — not a functional blocker.

- [chore] p3 **Two Phase-0 corroborations** (cheap, non-blocking): (a) xref `FVector::Normalize`
  (core `0x24940`, the one x87 `fdivrp` reciprocal near geometry) against the CSG-build call graph to
  confirm no build-path caller reaches it (CalcNormal uses the SSE `NormalizeSlow`, so surf normals
  are safe); (b) run the editor materialize on the castle trunk **twice** and byte-diff masking the
  16-byte GUID (offset 36) — empirical editor-determinism corroboration (static argument already PASS).

- [debug] p3 native CSG residual: ~0.24% of dense-grid cells read native-SOLID where the editor is
  EMPTY (thin shells along octagonal-tower/diagonal-wall slant planes). Root cause is the un-ported
  `bspOptGeom`/Balance=50 BSP-quality trim + `zones::assign_leaves` `outside` propagation marking
  some cells solid; the point-in-solid leaf correction (build.rs) only clears spurious EMPTY leaves,
  not spurious solid. Centroid divergence is already 0 and grid agreement 99.76% (was ~89%). Would
  need either the bspOptGeom trim or a full point-in-solid leaf re-assignment (touches zones.rs).

- [implement] p2 native CSG build sub-minute scaling: the behavior-preserving pass (2026-07-17,
  `architecture.md` "Native CSG build performance") cut the build ~2–3.7× (N=150 15.5→7.1s
  byte-identical; AABB fast-path + parallel `FindBestSplit`), but the per-brush classify-BSP rebuild
  is still O(M²)×N ≈ O(N³) — the dominant cost, so full 762-brush UNATCO is still single-digit
  minutes, not the <1 min ideal. Three faster ideas were REJECTED for changing output / not being
  provably byte-identical (see architecture.md): (a) **lean classify trees** (skip the transient
  tree's per-node vertex pool) — ~15%, byte-identical on the WHOLE acceptance corpus (castle +
  UNATCO-150/300) but only *empirically*; the `model.points`-dedup coupling means a surf `p_base`
  could shift ≤0.002uu. Recoverable if we either accept empirical verification + add sheared-brush
  differential fixtures, or decouple the classify-tree split base from the shared points pool.
  (b) **brush-local classify tree** (drop world faces whose plane clears the brush AABB) — ~100×
  (full-762 → seconds) but changed node/vert counts (coplanar double-routing + whole-face/`discarded`
  emission depend on the full tree). (c) **point_in_solid AABB cull** — only ~2% and not exact for
  sheared/acute brushes (axis pad vs face-normal tolerance). The real sub-minute path is an
  ALGORITHMIC change: incremental CSG (update the classify tree instead of rebuilding), a PROVABLE
  form of the local-tree restriction, or `rayon::join` on the `SplitPolyList` recursion (exact but
  only ~2× more). ANDRZEJ: is empirical byte-identity (a) acceptable to reclaim the ~15%? Harness:
  `spikes/2026-07-15-native-materialize/harness/csg_perf.py` (`time` + `hash` byte-identity gate).

- [debug] p1 **LAST geometry-body byte gap = `bspcsg.rs` point-pool / CSG-transient accounting (detector
  is now FIXED) — 2026-07-18.** The `bspoptgeom.rs` detector had a REAL byte-parity bug: it read the
  `0x3276a` `??TFVector` call as a plain edge divide and transcribed the ring scan as an *along-edge*
  projection `E·(P-Pcur)/|E|`, so it rejected every deep-interior T-junction and welded ~22. That call
  is `FVector::operator^` = the CROSS product — the real test projects onto `E×N` (edge × plane normal)
  = the **perpendicular** distance from the edge line. Re-decoded & fixed (`tjunction_edge`, decode
  §6b): castle now welds **1012**, matching **959/975** of the editor's inserter-oracle welds
  (permutation-invariant on (node-plane, welded-P)); golden stays a fixpoint; `bin/test` green (1429).
  **What's LEFT (this item):** native **1797 points / 10418 verts / NumSharedSides 2728 / Σnv 5533** vs
  editor **2035 / 16163 / 2739 / 5496**. The live ring geometry MATCHES (1549/1555 distinct live coords
  identical, 6 sub-0.05uu FP aliases, +37 over-weld). The whole residual is point-pool bookkeeping:
  native's repartition **clears + rebuilds** the Points pool from the live soup (→1797, missing 485
  editor orphan-CSG coords, +247 spurious z=−12/−80 coords that drive the +37 over-weld), while the
  editor does NOT clear (keeps ~2091 pre-opt incl. transient orphans, merges 56 → 2035). Native's raw
  *uncleared* CSG pool is ~6627 (3× editor) — `bspBrushCSG` leaks transient points from rolled-back
  grazes, so neither clear (1797) nor no-clear (6627) matches 2091. **Fix = stop `bspcsg.rs`'s
  incremental-CSG transient-point leak so the non-clearing repartition pool lands at 2091 pre-opt /
  2035 post-opt, WITHOUT perturbing the byte-exact node/surf/vector tree** (every `surf.pBase`/
  `vert.iVertex` is a pool index — high entanglement, hence deferred rather than forced). Do NOT loosen
  the detector to force counts — it is validated correct. (decode §6a/§6b.)

- [debug] p1 **bspcsg first-divergence is now the §8.3 cospatial-facing-in surplus face — NEEDS A LIVE
  DIFFERENTIAL TRACE, do not guess.** The FindBestSplit param fix LANDED 2026-07-17 (Balance 50→12,
  PortalBias 70→0, Opt=GOOD stride `max(NumPolys/10,1)` on the repartition path only; temp-brush kept on
  its invariant OPTIMAL/50/70) + `bspOptGeom` wired after `bspRefresh`. Over-fragmentation is FIXED:
  full-castle nodes 1263→**1028** (editor 1156), surfs 454, points 1579, `NumSharedSides` 0→940. But the
  node-for-node matching prefix is STILL 0 — node[0] (the repartition ROOT splitter) differs. The N=2
  subset differential (`harness/subset_diff.py diff 2`) isolates the cause cleanly: **shared planes 14,
  only-native 1, only-editor 0** — native carries all 14 editor node-planes PLUS exactly ONE surplus
  face (WallBack's floor-coplanar bottom face `(0,0,-1,0)`), and that extra face flips FindBestSplit's
  root choice. The param fix itself is CORRECT (it reproduces the editor node-for-node on the editor's
  OWN 14-face soup — `harness/validate_params.py`). The surplus face is the §8.3 `F_COSPATIAL_FACING_IN`
  classification: native mis-classifies it as FACING_OUT (filter 5, added) where the editor gets
  FACING_IN (filter 4, dropped). This is the §8.3 coplanar Outside-seed nuance — **already tried and
  REVERTED once (no improvement), and the §7b coplanar-goto branch is genuinely ambiguous from static
  disasm; decode doc §8.3 says "do not re-apply blind; trace first."** So: STOP for RE — a node-for-node
  repartition/coplanar differential trace against the live editor to pin which `Outside` the back-subtree
  descent seeds when the coplanar node IsCsg. (spec §"Secondary residuals" #1.)
- [implement] p2 bspcsg `bsp_build_fpolys` walks the node ARRAY; the engine's `MakeEdPolys` (0x33bb0)
  walks the TREE recursively (front/back/iPlane DFS). This reorders the repartition soup, and since
  `FindBestSplit` ties break by order it can shift deeper splits. NOT the current first-divergence
  (the cospatial surplus face above blocks first — it changes soup CONTENT, not just order, so a
  walk-order port cannot fix N=2 while that face survives). Port `MakeEdPolys` as a tree DFS ONLY after
  the cospatial residual lands and node-for-node parity is still short. (spec §"Secondary residuals" #2.)

- [debug] p1 **N=33 `RoofNE` soup divergence — SUPERSEDED, see the `[spike] p2` N=33 entry above.**
  The §10.4 "clips against TowerNE's **diagonal** face" diagnosis was WRONG: traced to instruction
  level 2026-07-17 (`sections/82 §10.6`), the spurious `x=112.0` is the **axis-aligned** `Merlon_y4jykf`
  east face on a **DEAD** node (`node[80]`, `nv=0`), and the split-selection is faithful — the real
  divergence is a cumulative incremental-tree-ORDER one, blocked on an editor-tree oracle. No local fix.

- [implement] p3 native lighting backface cull assumes SINGLE-SIDED surfaces (`light.rs::light_in_front`,
  §20 §17). A `PF_TwoSided` surface renders its one lightmap from BOTH faces, so the editor may
  legitimately list a back-side light on it; the strict `(light-base)·normal > 0` cull would drop it,
  darkening that surface vs the editor. `Test_Castle` has no such case (0/3497 back pairs), so it's a
  latent generic-UE1 gap, not a castle regression. Needs an oracle map WITH a lit two-sided surface to
  see what `shadowIlluminateBsp` actually does before adding a `PF_TwoSided`-bypass — do NOT guess.

- [spec] p2 **Native OMITS the per-LEAF permeating light lists — the dominant raw-byte gap in
  `Model.Lights` (e4): native 3928 vs editor 11392 entries.** Pinned 2026-07-18 (spike §20 §21;
  harness `lights_run_diff.py`). `Model.Lights` has TWO regions: region 1 `[0,7455)` = per-leaf
  permeating runs indexed by `FLeaf.iPermeating` (366/384 leaves; monotonic in leaf order;
  `iVolumetric` all −1 here), region 2 `[7455,11392)` = the per-surface shadow runs native already
  bakes. Native emits ONLY region 2, and `zones.rs` stubs every leaf `iPermeating=0` (points at a
  surface run — wrong garbage for dynamic-actor lighting). Reproducing region 1 needs a port of
  UnrealEd's per-leaf volumetric light-permeation gather (convex leaf volume × radius × BSP shadow),
  INCLUDING the editor's exact within-run light ORDER (gather-discovery order, non-ascending, e.g.
  leaf0=`[2,1,3,6,7,11,12]`). Union-of-bounding-surfaces was REFUTED (Jaccard 0.42). Belongs in
  `light.rs` (a lighting bake), runs after zones, sets `leaves[i].i_permeating` + prepends region-1
  runs to `model.lights`. NOTE: even done, the section stays raw-byte NON-identical until export
  renumbering (wrapper) + BSP surf/leaf ORDER (bspBrushCSG byte-identity) parity land — so this
  closes CONTENT/COUNT, not positional bytes. Lighting is never hashed/never blocks load, so p2.

- [flag→Andrzej] 2026-07-18: raw-byte identity of the three light sections (LightMap a8 / LightBits
  b4 / Lights e4) is **gated on two upstream items, not the bake**: (1) object-ref renumbering of the
  export table (wrapper-level, `wrapper_diff.py`), and (2) BSP surf/leaf enumeration ORDER (native
  bspcsg orders them differently than the editor — the bspBrushCSG byte-identity item). `light.rs`
  can only make the sections structurally complete + content-correct; positional byte-identity is
  those two items' job. Flagging so the byte-identity roadmap sequences them before "lighting bytes".

- [debug] p1 **Residual native render-black (s76/s69/s07 left) is ZONE/SKY PORTALIZATION, not
  lighting/solidity — corrects the occlusion-fix handoff premise.** After shipping the bspcsg-core
  switch (decisions 2026-07-17 21:10), the coordinator framed the leftover black as "bspcsg's ~0.03%
  wrongly-solid cells over-occluding light LOS." Four measurements on shipped `NativeCastle.dx` vs
  editor `Test_Castle.dx` DISPROVE that: (1) point-in-solid sweep through the dark nooks is
  char-for-char IDENTICAL to the editor — no wrongly-solid cell exists; (2) the +4 bias origin is not
  in solid for the dark surfs; (3) with the CORRECT dark test (walk the light run for set bits — an
  empty run is `iLightActors→0`-terminator, NOT `==-1`; testing `==-1` manufactures false regressions)
  native has 59 dark vs editor 55, and only ONE clean native-dark-but-editor-lit surface (surf#278, a
  wall — a hard bake edge case); (4) the biggest dark surfaces (skybox #461–466, towers #369–421) are
  dark in BOTH maps, and s76 black pixels raycast onto surfaces that HAVE lightmaps. Conclusion: the
  black is a render/zone difference (NativeCastle's incomplete zone/sky portalization — the handoff
  commit says so), fixed by the zones/portalization work item, NOT by any bspcsg solidity change. Do
  NOT chase a bspcsg over-occlusion fix for this — there is nothing wrongly-solid to fix (evidence in
  spike §20 §18 "CORRECTED diagnosis"). Open sub-item: surf#278's single-surface dark-vs-editor-lit is
  a real but tiny bake edge case (origin clear, all LOS blocked) — low priority, needs the two-sided /
  lumel-position angle, not solidity.

- [debug] p1 **CONFIRMED DEFINITIVE (2026-07-17): residual black = game BSP render-traversal skips
  present, baked-LIT surfaces; not lighting, not solidity, not normals.** Geometry-matched value-level
  lightmap diff (NOT array-index — the two 485-surf Models order surfs differently) + exact-game-camera
  raycast settle it. (A) native vs editor render-dark = 54 vs 54; of 459 geometry-matched twins, exactly
  ONE native-dark-editor-lit regression (surf#278). (B) Raycast of the 4 task poses into native geometry:
  100 % lit surfaces in view, **0 % baked-dark, 0 % void** — yet the game renders s76 32 %/s34 14 %/s69
  18 %/s07 16 % black. So under every black pixel there IS a present, lit native surface the ENGINE
  doesn't draw. Structural diff pins it: native `node.i_zone (0,0)×450` + node_flags ~all-0 vs editor's
  rich `NF_*` (8/13/16/24) + `(0,2)×1058`; interior zone renumbered. The task's "zones ruled out" was
  the Visibility MASK (all 0xff, never computed even on real maps — §70 §0), NOT the node-level
  portalization, which IS the mechanism. Fix = the zone/leaf/node-flags **portalization** port
  (`zones.rs`/`passes.rs`/`build.rs`/`model_write.rs` — the concurrent WIP), NOT `light.rs` and NOT the
  bspcsg surf-normal. Evidence + harness: spike §20 §19, `harness/blackcause_*.py`. **`light.rs` needs no
  change for the residual black.**

<!-- ── layout-reorg review round 1 (2026-07-18) ── -->

- `[flag for Andrzej]` **Untracked test level `uedcli/maps/foobar/` + the machine-local
  `current-level` pointer aim at it.** p3. A round-1 build reviewer flagged it as live-check
  leftovers, but it PREDATES the build (it appears in this session's opening git status), so it was
  not deleted on the never-discard rule — it may be another session's scratch. If it's yours/dead:
  delete `uedcli/maps/foobar/` and re-run `level select` (the stale pointer errors cleanly once the
  dir goes). Review round 1, 2026-07-18.

<!-- ── layout-reorg review round 3 (2026-07-18) ── -->

- `p2` `[note] RESOLVED` **The residual 29 tail nodes — `zones.rs` `TestVisibility` Pass D
  fragment-splits — are now PORTED; native node count 1156 = editor, plane multiset (fp-tolerant)
  1156/0/0.** DONE 2026-07-18 (`sections/70` §9 rewritten + `sections/82` §10.11 follow-up).
  `zones.rs` Pass D now faithfully ports `AssignAllZones` (`0xa7400`): each node's polygon is
  re-filtered through the chain head's back-then-front subtrees, and a face whose landings disagree
  per side is split into one fragment node per surviving zone (moat/water outer walls `w=±500/±410`
  fan out — surf 354→10 nodes, 355→10, 349/350→8). Replaces the never-split centroid sampler. Bonus:
  the filter-based Pass D also drops the old `(0,0)×2` solid-solid nodes to `×0` (exact editor
  match) and the whole iZone distribution now matches the editor under the zone-number permutation
  (native 1↔editor 2). `test_case_f_portal_full_compare` un-xfailed (now full parity).
- `p2` `[implement]` **Geometry-body pool byte-parity is gated on `SplitPolyList` ring-vertex
  DISTRIBUTION, not `bspOptGeom`/pool-dedup.** Live oracle (2026-07-18, `42-bspoptgeom-decode.md`
  §6a) proved: native's soup is byte-identical to the editor's (853 polys / 3315 verts), but
  `bspBuild`/`SplitPolyList` turns it into ~4400 ring-verts (avg 3.8/node) where the editor makes
  **10518** (avg 9.1/node). Same 1156 node planes + same point pool (all 975 editor T-junction welds
  land on points+planes native already has), but native distributes vertices into rings differently —
  606 of the editor's 975 welded T-corners are ALREADY in native's rings, so native's (correct)
  `bspOptGeom` detector fires only 22 vs the editor's 975. Editor's on-disk **16163** verts = ~5000
  live + ~11000 ORPHANS from 975 insert-and-orphan welds; native's **4543** = ~4300 live + ~240 (22
  welds). To close verts→16163 / points→2035 / NumSharedSides→2739, `SplitPolyList` (`bspcsg.rs`
  `split_poly_list`/`find_best_split_exact`/`bsp_add_node`) must reproduce the editor's exact per-node
  ring content so the same 975 cracks exist. This is a repartition-fidelity task, NOT a
  `bspoptgeom.rs` one — the detector + pass 2 + append/orphan layout are validated correct. Do NOT
  loosen the detector to force inserts (over-welds, diverges from golden). Oracles committed under
  `dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/bspopt_*_oracle.py`.
- `p2` `[implement]` **`Vectors` pool (native 44 vs editor 26): thread authored `TextureU/TextureV`.**
  Oracle: editor has 26 vectors already at `bspOptGeom` entry; native's 18 extras are face-local
  `default_texture_axes` bases (`bspcsg::alloc_surf`) that no `bspAddVector` threshold can merge. The
  trunk brush polys DO carry authored `TextureU/TextureV` (world/45°-aligned → dedup into the
  26-normal pool), but `materialize._build_brush_input` never parses/threads them. Fix spans
  `materialize.py` → Rust `BrushInput`/`FPoly` → `alloc_surf` (build.rs/csg.rs/lib.rs), OUTSIDE the
  `bspoptgeom.rs`/`bspcsg.rs` dedup scope. Details `42-bspoptgeom-decode.md` §8.
- `p3` `[note] RESOLVED` **`node_flags=8` is `NF_PolyOccluded`, a render-only occlusion bit — NOT a
  build derivation gap; native correctly omits it.** DLL-confirmed 2026-07-18 (`sections/82` §10.11 +
  §70 §9): `render.dll` sets `0x08` at `0x10019c26` and `0x10 NF_BoxOccluded` at
  `0x100193db`/`0x10019526` (software-rasterizer occlusion walk, gated on the current camera's span);
  `Editor.dll` — which holds the entire deterministic build (`csgRebuild`/`bspBrushCSG`/`bspRepartition`/
  `bspRefresh`/`TestVisibility`) — sets NEITHER. The 598 saved `0x08` nodes are the editor's last
  viewport-render leftover (camera-dependent, non-deterministic across saves). Confirmed-excluded, not
  faked. Nothing to implement.

- `p2` `[debug]` — **native materialize: corrupt/locked `.utx` silently dropped from the texture-group
  index** (`native/pkgref.py:117`, silent-swallow audit 2026-07-18). `build_texture_group_index` does
  `except Exception: continue` per `.utx`; a corrupt / truncated / unsupported-version / momentarily-
  LOCKED package is skipped with NO note, so every texture that lived in it emits only a 2-part
  `Package.Name` import (Group missing) → Deus Ex raises "Can't find Texture in file" at map load = a
  broken map, zero signal. Fix: a stderr skip-note (mirroring the `dxpkg` closure discipline).
- `p2` `[debug]` — **native materialize: a transient schema-resolve failure silently strips ALL of a
  class's props** (`native/materialize.py:260`, silent-swallow audit 2026-07-18). `except Exception:
  cache[fqcn] = {}` is far broader than "class has no schema" — an absent package, an `OSError` on a
  `.u`, or a resolver bug all collapse to `{}`, so the caller treats every prop as untyped and DROPS
  them; the level materializes SILENTLY incomplete instead of failing loudly. Fix: narrow to
  `except SchemaError` (or surface the real error) so a real fault ≠ "no schema".
- `p2` `[process/flag]` — **build #2 feature was split across sessions/commits by the concurrent
  commit-sweep.** The `actor bbox`/`--json`/`--rotate` *dispatch.py* handlers landed in commit
  `fa08513a4` (message "schema cache: surface unwritable-cache write failure…") — a DIFFERENT
  session's sweep picked up my uncommitted dispatch.py hunks under an unrelated subject — while the
  matching *cli.py* parser wiring stayed uncommitted, so HEAD briefly carried DEAD dispatch handlers
  with no CLI entry point. The coherent feature (cli+dispatch+tests+docs) was finally committed whole
  in `7e823a708`. Flagging the sweep behaviour: it can bisect a single feature across commits/authors
  and mislabel it. (Andrzej: no action needed on the code — just awareness of the orchestration.)
- `p3` `[decide] follow-up from build #2 (actor find --json)` — **`actor find --json` emits a JSON
  ARRAY OF NAME STRINGS**, mirroring the one-per-line default (the items ARE names). If a richer
  per-actor object form (name+class+folder+group) is wanted for scripting, that's a small follow-up —
  not built, pending your call.
- `p3` `[decide] follow-up from build #2 (--rotate vs --prop Rotation=)` — on `actor build`, passing
  BOTH `--rotate P,Y,R` and `--prop Rotation=…` silently resolves to the `--rotate` value (documented
  as shorthand for the same field). Left permissive; say if you'd prefer a conflict error.
- `p3` `[decide] follow-ups from build #4 (event graph, item 10)` — three things I decided and want
  your eyes on (all recorded in decisions.md 2026-07-18 20:54 UTC):
  1. **Unset `Tag` treated as NOT a matchable receiver.** UE1 defaults an unset Tag to the class
     name at runtime; I only wire an edge on an EXPLICIT non-empty Tag (a class-name-default Tag
     never receives). Assumption per the task; flagging it in case you want the class-name-default
     honoured for a specific pattern.
  2. **Exit 0 even with lint findings** (`event graph` is a wiring PRODUCER; lint is advisory to
     stderr / in `--json`). No `--strict` non-zero-exit mode yet — say if you want one for CI.
  3. **Scope limits:** the edge model reads the single `Event` prop only — multi-event ARRAY props
     (Dispatcher `OutEvents(n)`, Counter, etc.) fire events that currently produce NO edges. And
     the unreachable-mover lint is conservative: it flags a mover with an explicit unused Tag and no
     self-moving `InitialState`, but does NOT flag a tagless mover (bump/loop trigger mechanisms
     aren't reliably knowable offline). Both are candidate follow-ups if you want deeper coverage.
- `p2` `[process/flag]` — **build #4 cli.py+dispatch.py hunks were again swept into a concurrent
  agent's commit.** My `event`-group parser + `_event_graph` handler landed inside commit
  `cd364b6ac` (subject "class show --all: expand the whole super chain…") — a different session's
  stage-by-path picked up my uncommitted cli.py/dispatch.py edits. Same orchestration hazard already
  noted for build #2: the coherent feature (module+tests+docs, committed separately by me) is bisected
  across commits/authors. No code action needed — awareness only.
- `p2` `[decide] follow-ups from build #5 (poly align, item 11)` — DEFERRED pieces + interpretations
  from `polyalign.py` (design: decisions.md 2026-07-18 21:40 UTC). Flagging for your eyes:
  1. **`--wall` vs `--floor` distinction I chose:** the two flags are mathematically identical
     (adopt-seed is axis-agnostic; `_tex_basis` handles both fresh cases), so I gave each a concrete
     ORIENTATION GUARD — `--wall` requires the coplanar set to be vertical (normal ≈ ±X/±Y),
     `--floor` horizontal (normal ≈ ±Z). This makes the two flags catch mistakes (aligning a floor
     with `--wall`) instead of being redundant. Say if you'd rather they behave identically (one flag
     with an alias), or want the guard relaxed for near-vertical/near-horizontal slants.
  2. **`--fit-perimeter` offline meaning:** with no texture loaded, "integer number of texture
     repeats" isn't computable (needs the pixel width). I implemented it as snapping the around-ring
     density so the TOTAL U texel count is the nearest integer — the sub-percent scale nudge the seam
     needs. A true pixel-tile-seamless meet (period = texture width) is a follow-up once the catalog
     can supply dimensions to the aligner.
  3. **Scaled textured brushes:** continuity math uses the rotation-only frame transform (matching
     `preview_native._world_uv_frame`), NOT `actor_linear` (which includes MainScale/PostScale). For
     a SCALED textured brush the written frame will be slightly off. Out of v1 scope (builders emit
     unscaled brushes); follow-up if scaled-brush texturing becomes a real need.
  4. **DEFERRED modes (v2, per the decision):** `--face` fit-one-texture-to-a-surface (single-poly,
     closer to `brush poly set`); turning (non-coplanar) wall runs (per-face accumulate-along-run,
     like `--ring` unrolled); sphere wrap (needs per-vertex UV the flat per-poly frame can't express);
     an explicit `--seam <brush:poly>` anchor (v1 seam = first face in input order).
  5. **`brush poly find` is single-brush** (`<brush>` positional, like `poly list`). A cross-brush
     coplanar/adjacency `find` (`--coplanar <seed>`) is the natural next producer — would let a wall
     run be discovered by geometry rather than by folder — but it's its own spec.


- `p2` `[debug]` **`level preview --native` renders NO revolve brush at all — absent, not mis-drawn.**
  Measured 2026-07-26 (`dev/docs/spikes/2026-07-26-poly-rotate-curved-track/` finding 6). A
  `brush build revolve` never appears in a `--native` render. Ruled out: framing (re-measured on a
  clean level holding only a subtracted room and one 128-uu-tall arc); off-grid vertices
  (`brush build cylinder --sides 8` is off-grid and renders fine); non-convexity
  (`revolve --segments 1` is a convex 6-plane hexahedron and is ALSO absent). So this is **not** the
  documented "native assumes convex solids" caveat `docs/usage.md` attaches to `staircase`/`extrude`
  — that predicts a *mis-drawn* brush, and this is total absence for a convex one. `--game` renders
  the same brush correctly, so the geometry is sound. **Cause not identified**; winding/normal
  orientation on the swept faces is the leading suspect (an inside-out add contributes nothing to
  CSG) but was not tested. Impact: the fast offline preview is unusable for any revolved geometry,
  which is most curved detail, forcing the ~1-min `--game` path.

- `p3` `[implement]` **A brush that contributes NOTHING to the CSG result should be reported.** Hit
  live 2026-07-26 while building the curved-track spike fixture: replacing a room with a taller one
  put the new subtract AFTER the track bed in CSG order, so it carved the track away. The level then
  rendered solid black with no error, no warning, and nothing to indicate which brush had vanished or
  why — `actor order Room --first` fixed it, but only after the cause was guessed. CSG is behaving
  exactly as specified (order = precedence); the gap is diagnostic. `level doctor` already reports
  "a subtract that carves nothing" (`docs/usage.md`), so the symmetric case — an ADD wholly consumed
  by a later subtract — belongs beside it. Cheap to detect model-side and it turns a black screenshot
  into a named actor.

- `p2` `[spec]` **`brush poly scale` — the fourth canonical surface op, still missing.** Pan, rotate
  and align are specced (`specs/2026-07-26-poly-surface-verbs.md`); scale is deliberately NOT, because
  it interacts with how `align --run` derives texel density from the seed frame (by projection onto
  the run tangent/across directions), and speccing it blind would duplicate or contradict that. Needs
  its own spec once `--run` lands. (Supersedes the "fold in `texture scale`/`texture rotate`" clause on
  `to-spec.md`'s texture-alignment item — rotate is now specced under its real name, `brush poly
  rotate`; only scale remains.)

- `p3` `[implement]` **A non-quad face in an `align --run` set exits 2 — generalise it later if a
  builder ever emits one.** Decided in `specs/2026-07-26-poly-surface-verbs.md` §6 rather than
  deferred to the implementer. The quad assumption is load-bearing: a terminal face's free edge is
  found as the OPPOSITE edge of the quad (`entry = (exit + 2) % 4`), and an n-gon needs a different
  rule for "the far edge". No shipped builder currently produces a non-quad swept face, so the error
  is correct today; this item exists so the limitation is findable if one ever does.

- `p3` `[spec]` **Fitting a texture to an OPEN run — the sibling `--fit-perimeter` does not cover.**
  `specs/2026-07-26-poly-surface-verbs.md` restricts `--fit-perimeter` to CLOSED runs, because "fit an
  integer texel count so the loop closes" needs a loop. But "snap the density so a whole number of
  texels spans this wall run / this staircase stringer" is a legitimate and probably more common
  request, and it has no verb. It wants a different flag name (perimeter implies closure) and a
  decision about which end absorbs the residual. Raised by spec review round 2, which correctly
  pointed out the restriction was asserted rather than argued; recorded here rather than folded into
  that spec, whose gate had already run.

- `p1` `[OWNER — decide]` **`POLY TEXALIGN` is MEASURED; four things in
  `specs/2026-07-26-poly-surface-verbs.md` §4b now need your call.** The spike ran
  (`../spikes/2026-07-26-unrealed-texalign-semantics/`, live 2026-07-26; durable facts in
  `../unrealed/texalign.md`; six regressions in `test_engine_facts.py`). Headlines: the editor has
  **nine** mode tokens, not six — and **`ONETILE` and `WALLCOLUMN` do nothing at all** in UED22, so
  there is no fit-a-tile-to-a-face operation in the editor to port. Nothing in `TEXALIGN` ever changes
  texel density; the modes only choose an in-plane orientation and an anchor, at 1 texel/uu. The spec
  is NOT edited — the caller instructed explicitly, when commissioning the spike, that the spec was
  not to be touched and that the required changes were to be reported instead. **So note that §4b now
  states three things that are FLATLY DISPROVED and will mislead whoever builds from it**, quite
  apart from the four decisions: (a) "six modes against our two" — there are **nine**; (b) "we cannot
  currently say what any of them does" — all nine are now measured (`../unrealed/texalign.md`);
  (c) "**`ONETILE` has no counterpart at all** — fit exactly one tile to the face" — `ONETILE` is a
  **no-op** in UED22 and fits nothing. Those three are corrections of fact and do not need a ruling;
  only the four below do:
  1. **`align wall|floor` orientation.** The spec's `builders._tex_basis(n̂)` does not agree with the
     editor on any of the seven face directions measured (mirror / 180° / on a yawed wall a full
     90°), and `_tex_basis` lets V point UP on roughly half a room's walls where the editor always
     drives V down. **Match the editor (`WALLDIR` for wall, `FLOOR` for floor), or diverge on
     purpose?** Right now the spec reads as if `_tex_basis` were the editor's rule.
  2. **Anchor.** The editor pins `FLOOR`/`WALLX`/`WALLY` to a **world axis** — which is what makes
     separately-aligned faces across a level share one grid — while the spec pins to the **seed
     face's centroid**, making the result depend on which face was listed first and on how many
     invocations you split the plane across. A world-axis anchor would make `poly align --floor`
     idempotent and set-order-independent. **Change it?**
  3. **`one-tile` is a uedcli invention, not a port.** No objection from the spike; the spec should
     just stop implying an editor precedent.
  4. **Two modes worth adding, both absent from uedcli:** a `WALLPAN` equivalent (re-phase a wall's
     texture to world Z=0 without touching its axes) and the `WALLX`/`WALLY` projection pair (a
     stretched-but-continuous run across walls that are not quite parallel — the only thing the
     editor has for a TURNING run, which is what `align run` is reaching for).
  Also open, and deliberately not guessed at: **what `CLAMP` is FOR** (measured to be `DEFAULT` with
  `PanV = VSize−1`; the rendering consequence was not observed), and whether `ONETILE`/`WALLCOLUMN`
  are implemented in non-UED22 UnrealEd builds (not checked — out of scope, we ship UED22).
---

## From the 2026-07-18 unattended build chain (Andrzej, triage these)

- **RESOLVED (triaged + built 2026-07-19) — CLI consistency & clarity audit** (`../reviews/2026-07-19-cli-consistency-audit.md`, 8 findings, all accepted): **H1** poly-set stdin, **M1** mutator summaries→stderr, **M2** `--json` ×3, **M3** `--prop` on `brush build` (re-scoped to movers — CSG brushes were already fully covered by dedicated flags), **L2** clip/folder-get polish, **L3** unify `--catalog-dir` help (flag KEPT — load-bearing for project-less texture verbs) — all BUILT + committed 2026-07-19. **H2** (`actor move` over a SET) routed to `to-spec` (`--by`-only when moving >1 actor, per Andrzej).

- `p2 [spec-done→plan]` **`config.toml paths` as a TOML list** (Andrzej-requested 2026-07-19). Accept
  `paths` as a TOML array alongside today's colon-separated string, on both `~/.uedcli/config.toml`
  `[games.*].paths` and project `uedcli.toml`. Reviewed spec:
  `../specs/2026-07-19-config-paths-list.md`. **Awaiting your call on the sub-choices** (all
  recommended in the spec): accept-both-forms (not list-only); apply to both loaders; leave
  `catalog`/`prefabs`/`maps` as single strings; headline benefit is a colon-containing POSIX dir
  (Windows drive letters do NOT work on the Linux host — corrected in review). On confirmation this
  goes to `to-build.md` and the durable choice gets a `decisions.md` entry.

- `p3 [implement]` **Allow the folder-EDITING verbs on `--target stash|prefab`** — the unify-T3D-trees
  build (2026-07-19) made stash/prefab boxes persist a per-member `folder` sidecar (full trunk parity),
  and `StashLevelSource`/`PrefabLevelSource` load/save now preserve it. But the folder-editing surfaces
  (`actor folder set/unset/get`, `actor add --folder`, `actor find --folder/--no-folder`) still reject a
  stash/prefab target via `_reject_nonlevel_target_for_folders` (deliberate scope line, NOT a storage
  limitation now). Lifting it would let a captured subtree be re-organized in place. Needs its own small
  design (does `find --folder` over a box make sense? all-or-nothing writes?) before building. Same note
  applies to the CSG-order editing verbs (`actor order`) vs `_reject_nonlevel_target_for_order` — the
  boxes carry `order_value` sidecars now, just not exposed to the ordering verbs.
- `p3 [chore]` **Delete the ephemeral spec `specs/2026-07-18-unify-t3d-trees.md` + plan
  `plans/2026-07-18-build-unify-t3d-trees.md`** — the unify-T3D-trees work landed (2026-07-19); the
  durable outcome is folded into `architecture.md`/`usage.md` and `decisions.md`. Kept for now as a
  cross-check; prune once reviewed.

- **[spike→spec] p2 SPEC REVIEW ROUND 1 (2026-07-26) — the warm-editor spec DID NOT PASS the gate.**
  Three cold Opus reviewers over `specs/2026-07-18-warm-editor-materialize.md`; ~50 findings, heavy
  independent convergence. **The premise survived** — all three agree a one-shot commandlet
  structurally satisfies `commands.md`'s "fresh editor, exactly one level loaded" precondition that
  warm reuse cannot meet. **The mechanisms did not.** The spec is PARKED, not merged; per CLAUDE.md
  "Review gates" it re-enters at round 1 after re-design. Findings, grouped, all actionable:

  **A. The verify container cannot work as specified (all 3 reviewers).**
  1. `store_export.export_dx_t3d` is three `docker exec`s into a RUNNING container; §5.1 specifies a
     `docker run --rm` whose command exits by itself. You cannot exec into an exited container. §6's
     "simply handed the one-shot container" and §5.1 are mutually exclusive — and detaching to fix it
     reinstates exactly the leak shape the spec exists to remove.
  2. The image `ENTRYPOINT` is `tini -- bash /opt/uned/entrypoint.sh`, which ignores its args and
     gates the editor on `${LAUNCH_UED:-1}`. `LAUNCH_UED=0` lives in `docker-compose.yml` and in
     `stub.ephemeral_build_container`'s explicit `-e`, neither of which reaches a plain `docker run`.
     So the specced verify container boots Xvfb + fluxbox + x11vnc + `unrealed.exe`, waits for a
     window, THEN runs UCC — a full GUI stack, not a ~3 s one-shot. Needs `--entrypoint` + explicit
     `-e LAUNCH_UED=0`, and the timing claim is unestablished until measured.
  3. **`/stubs` is silently lost.** It is a compose volume, not part of `resource_mounts`, and the
     crafted ini puts it FIRST on `[Core.System] Paths` (the whole v69-shadowing scheme). A plain
     `docker run` has no `/stubs`, so any level using a stubbed class → the class never loads →
     `qualify_level_classes` raises → **exit 2 on a correct build, deterministically, for every
     stub-using project**. SP-F.2 only catches it if its fixture happens to use a stub.
  4. **stdout contamination.** `OBJ LIST CLASS=Class` emits a line for the class literally named
     `Engine.Polys`, which `parse_obj_dependencies` opens as a brush block. That is why
     `qualify._blocks_only` exists — its docstring records the live failure (3 blocks for a 1-brush
     level). §5.1's script runs both dumps into ONE undelimited stream, re-creating it; §3's "parsers
     reused verbatim" omits `_segment_since_header`/`_blocks_only` from both the kept and deleted
     lists. Also unknown whether `_blocks_only`'s `\nLog: Objects:` marker even appears in commandlet
     stdout, whose format differs. Fix direction: a delimiter line between dumps, or two separate
     invocations; either way the segmentation must survive.

  **B. The foundation is unevidenced.** Neither committed harness in `spikes/headless-materialize/`
  contains `OBJ DEPENDENCIES`, `OBJ LOAD` or `OBJ LIST` — zero hits. The findings write-up asserts
  the verb works headless and lands on stdout, but nothing reproducible backs it, and
  `rules/spikes.md` calls that the state a finding rots in. Nor was it observed after a `MAP LOAD` of
  an existing `.dx` (the spike ran it, if at all, after an in-memory build). Decision 6 rests on it.

  **C. The idle watchdog can kill live builds — and decision 8 puts it on the DEFAULT path.**
  §4.5's premise "every host-side `Driver` exec routes through `wine_ctl`" is false; `driver.py`'s
  own docstring enumerates the exceptions. `map_save` types through `wine_ctl` once, then polls up to
  **`timeout=600.0`** via `docker exec sh -c`, touching no marker — and the proposed `UED_IDLE_S` is
  **600**. The bounds are equal, and `levelbuild-friction` §3 records a real production `MAP SAVE
  never produced a finished file (after 600s)`. Because decision 8 also puts the watchdog on the
  ephemeral boot, the regression lands on the default path plus `stash intersect/deintersect`,
  `native/csg_golden.py` and `tests/editor_oracle.py`. Fix: refresh the marker from the probe loop,
  and make the deadline strictly greater than the longest bounded editor wait. SP-F.7 tests only the
  true-positive direction; nothing tests that a slow healthy build survives.

  **D. A killed build leaves a BUSY warm editor, and nothing detects it.** The health probe is
  `alive` + `window=<digits>`; it cannot see "still executing the previous invocation's `MAP
  REBUILD`". A SIGTERMed materialize (the spec's own §1(c) example) leaves the container up by
  design; the next acquire passes the probe and types into a busy editor with fire-and-forget input —
  which is the exact class `quirks.md` blames for the SP-E blocker. So the ~50 % failure can return
  through a door decision 6 does not close, and decision 5 turns it into a hard exit 2. Needs a
  busy/generation detector (e.g. a drive-start/end marker), not just a liveness probe.

  **E. The warm path is LESS resilient than today.** §4.3 caps warm boot at ONE reboot; `ensure_editor`
  retries readiness **3** times and its docstring calls startup death "the single most frequent
  interruption in the build→preview loop". The justification ("a second failure predicts the ephemeral
  would fail too") has no evidence and is undercut by the warm reboot minting a fresh wineprefix each
  time. And the ephemeral fallback — kept for mere lock contention — is not used for the one case
  where it is known-good recovery.

  **F. Two more direction conflicts, unparked** (the §4.3 teardown one WAS parked correctly).
  (i) §5.2/§5.3's read-write host `/work` staging bind mount contradicts `direction/containers.md`:
  *"Mutable exchange — ONE container-local `/work` dir … crossed only by `docker cp` … so nothing it
  holds can leak into the tree"*, plus its rejected "bind-mounting arbitrary host roots". Candidate
  resolution WITHIN the ruling: read-only input mount (a `.dx` is an asset to the verify) + T3D out
  over stdout. Needs the owner's confirmation that this reading is right. (ii) §4.1 puts the warm
  flock and crafted-ini temp in `~/.uedcli/`, while `direction/projects-and-config.md` inventories
  the per-user home as config + `cache/{textures,stubs,schema}` only and assigns flocks/staging temps
  to the in-repo `.uedcli/`. `preview_game` already does the former, so code precedes spec here.

  **G. The spike's acceptance criterion is both unreachable and insufficient.**
  - Unreachable: two known pre-existing post-verify FALSE POSITIVES will fail warm builds for
    unrelated reasons — `levelbuild-friction` §1 (engine-stamped `Base` missing from
    `normalize.COMPUTED_PROPS`; "the single most costly defect of the run. Deterministic, not flaky")
    and `headless-materialize` §11 (a `basement` GEOMETRY line-shift). SP-F.5 would report a design
    failure that is actually one of these. **The second of the two is FIXED (2026-07-26)** — it was
    not a false positive but a real emit defect: uedcli wrote `Pan U=0 V=0`, which the editor never
    writes back, so the two brush texts differed. `emit_polygon` no longer writes a zero pan
    (`rationale/emit.md`, `unrealed/t3d.md` "A poly sub-field has NO class default"). Only the
    `levelbuild-friction` §1 `Base` blocker remains against this criterion.
  - Insufficient: a **runt/unlit** map is not a "failure" by a 0/N pass-rate criterion. `friction`
    §1b documents a `--no-verify` build writing 23,126 bytes instead of 191,332 and printing success,
    and the H3 compare **structurally cannot** catch it because lighting is regenerable build output
    the compare ignores by direction. SP-E left a ready-made oracle (`warm_editor_canoncmp.py`) and
    nominated exactly this as pinnable; SP-F uses neither it nor a size/lightmap check.
  - N=8 at 0 failures has weak power: a residual 10 % rate still passes ~43 % of the time. State what
    confidence N buys.

  **H. Leak mechanics — the fix under-fixes, over-reaches and races.** (i) The watchdog *stops* a
  container; it never `docker rm`s it, and ephemeral names are fresh uuid7s so nothing re-takes the
  name — the RAM leak is fixed, the exited-container/COW-layer leak is not, and §1(c)'s "2
  never-started" containers can never self-reap (they ran no entrypoint). (ii) The `uned-wp-*` glob
  also matches `uned-wp-stub-*` from `stub.ephemeral_build_container`, and volumes are daemon-global
  while the ephemeral half carries no uid. (iii) "No attached container" is NOT race-free: compose
  creates the named volume before the container references it, so a sweep in that window removes a
  booting editor's prefix — and the ephemeral path is deliberately lock-free, so there is nothing to
  serialise against. (iv) The sweep runs only on the warm acquire path, i.e. never under the
  contention that produces the leaks. (v) The verify container's own crafted ini is never unlinked —
  one leaked temp per materialize, in a spec whose purpose is fixing leaks.

  **I. Fail-closed assertion checks the wrong property.** §4.5 asserts the watchdog by checking the
  env var made it in — but the named failure mode is a STALE IMAGE whose baked entrypoint has no
  watchdog code, which accepts `-e UED_IDLE_S` and ignores it. Must observe the effect (the
  entrypoint's own log line, as `game-entrypoint.sh` prints, or `/work/.last_use` existing). §8 pins
  the same wrong property.

  **J. Factual/citation defects.** (i) Today's verify runs **three** poll loops, not two —
  `qualify_live_level` calls `dump_obj_dependencies` AND `_read_loaded_classes`, then
  `verify_dx_matches` calls `_read_loaded_classes` again; two 90 s-ceiling class reads is also a far
  more plausible home for the derived ~42 s. (ii) The crafted ini is NOT "a pure function of the
  mounts" — `paths_ini_lines` host-scans each dir for present extensions, and the host pre-bake
  `uned/UED22/unrealtournament.ini` is covered by no fingerprint component. (iii) `preview_game`
  does not have the shape §6 says it factors: `acquire_warm_container` contains no flock (docstring:
  "Caller MUST hold the flock") and no reboot retry; `_acquire_lock` is **bounded blocking**
  (`WARM_LOCK_TIMEOUT_S`, raises) not nonblocking, and `REBOOT_BUDGET=3` is consumed in the render
  loops. (iv) `Commandlet batchexport not found` is in `commands.md`, not `quirks.md`. (v) §10 lists
  `Save.tmp`'s location as UNPINNED although the spec's own headline spike answered it 🔬 ("in the
  destination's own directory … two concurrent saves into one directory would therefore collide") —
  which is live for conflict F(i). (vi) §1(c)'s host numbers (8 containers / 9 volumes / ~5.5 GB) are
  my own session's census and appear nowhere committed; `friction` §2 reports a different count over
  a different window. (vii) "never purge" strengthens the cited spike's "does NOT **immediately**
  purge". (viii) §1's table violates CLAUDE.md's table-alignment rule.

  **K. Unaccounted memory doubling.** Every materialize now holds an editor container AND a verify
  container running the full editor engine (worse with A2's GUI stack). `parallel-editors.md`:
  ~0.5 GB each, concurrency is memory-bound, unbounded fan-out OOMs a small box — and §1(c)'s own
  incident was RAM+swap exhaustion on a 4-core/7.7 GB box. Neither §4.6 nor §10 mentions it.

  **L. Smaller, still real.** Fingerprint thrash when two projects alternate on one per-user warm
  container (every acquire mismatches → reboot + teardown + 0.5 GB resident for 10 min; not on the
  watch-list). `UED_IDLE_S`/lock keyed on `$UEDCLI_HOME` but the container name on `uid`, so two
  sessions with different `UEDCLI_HOME` share one container with different locks. No "container
  vanished mid-acquire" outcome in the gate §4.2 calls complete (should reboot, not exit 2). The
  `pinned` branch is unreachable in v1 yet specified and tested. `--keep-build` mechanism must change
  under §5.3's reorder (staging file already on host; `cp_out` source may be released) and nobody
  unlinks staging on the verify-failure path → one stranded `.dx` per failed verify. `qualify_live_level`
  becomes broken-not-dead if its two callees are deleted; `_FLUSH_FILLER_CMD`, `_COMPLETE_RE`,
  `Driver.obj_dependencies/log_size/read_log_since` all lose their last caller. No docs items
  anywhere: `docs/usage.md:12` ("no persistent session") is falsified for a USER-FACING doc,
  `architecture.md` still describes the verify in the same ephemeral container, `commands.md` has no
  `Editor.ExecCommandlet` entry, and the new stderr mode line is observable output. No `rationale/`
  landing named for the many implementation choices.

- **[chore] p2 `qualify.export_and_qualify` no longer exists but six files still cite it.** It is
  referenced as a live precedent by `apply.py`, `driver.py`, `stub.py`, `packages.py`,
  `tests/test_packages.py`, `tests/test_driver.py`, and by docs including `decisions.md` and two
  spikes — and, load-bearingly, by `quirks.md`'s "Consequence for warm materialize" line and SP-E's
  fix-candidate-1 rationale ("it already boots its own ephemeral editor precisely because a reused
  editor is untrustworthy"). Anything reasoning from that precedent is reasoning from a function that
  was deleted. Found during the 2026-07-26 spec review.

- **[chore] p3 The `headless-materialize` and `levelbuild-friction` spikes are UNCOMMITTED.** Both are
  untracked; the warm-editor spec's decision 6, its whole §5, its leak measurements and its scope
  limits all cite them, and `rules/spikes.md` requires harnesses committed under
  `dev/docs/spikes/<slug>/`. Until they land, a `git clean` destroys the evidence base. (Owned by
  whichever session ran them.)

- **[OWNER — confirm] p2 The H3 post-verify never runs against the build editor.** Decided
  2026-07-26 (owner chose "verify in a one-shot commandlet container" over an idle barrier and over a
  separate GUI verify editor). Folded into `specs/2026-07-18-warm-editor-materialize.md` decision 6;
  **`direction/materialize.md` is NOT edited until this is confirmed.** Proposed wording, verbatim,
  for `direction/materialize.md` § "The post-build verify":

  > **The verify never runs against the editor that did the build.** It runs in its own one-shot
  > headless container, which starts an editor engine with no GUI or display, executes a short
  > script of console verbs, prints its output and exits by itself in a few seconds. Two reasons,
  > and the second is the durable one. A reused build editor intermittently loses the *next* build's
  > `MAP SAVE` after a verify has run against it — around half of reused builds — so a warm editor
  > and an in-editor verify cannot coexist. And the qualification dump the verify depends on is
  > documented as requiring a *fresh* editor with exactly one level loaded, because loading a level
  > never purges the previous one's objects; a reused editor structurally cannot offer that, and a
  > one-shot container offers it by construction. The verify also stops depending on scraping a
  > block-buffered log file, which is what its two poll-until-settled loops existed to defeat.

  *(Rejected, for the same section: an editor-quiesce/CPU-idle barrier — it only works if the cause
  is a transient race, which the spike explicitly did not discriminate; a separate cold GUI verify
  editor — robust, but its boot costs about as much as warm reuse saves; making `--no-verify` the
  warm default — trading build correctness for speed on the one path whose job is detecting
  wrongness.)*

  **This decision also touches `direction/containers.md`, in two places.** (i) Its opening sentence
  enumerates the container kinds and assigns "materialize, qualify" to the editor container;
  qualification moves out to a fourth kind — a **one-shot headless commandlet container**, which
  starts an engine with no GUI or display, runs a short script and exits by itself. (ii) Its
  lifecycle bullet reads *"a warm-mode drive **or verify** failure tears it down before releasing the
  lock"* — written when the verify ran against the warm editor. **Proposed replacement, verbatim:**

  > **An untrusted container is never left warm**: a warm-mode *drive* failure tears it down before
  > releasing the lock, and the invocation fails with a hint rather than silently retrying. A
  > *verify* failure does not — the verify runs in its own container and so implicates the build, not
  > the editor, and discarding a healthy warm editor there would penalise exactly the moment the
  > operator is about to rebuild.

  **Until you rule on (ii), the build follows the CURRENT direction text and tears down on a verify
  failure too** (`specs/2026-07-18-warm-editor-materialize.md` §4.3 says so explicitly). This is the
  one place the spec knowingly proposes against a direction doc.

- **[OWNER — confirm] p2 Warm editor now; the native and commandlet BUILD backends are later,
  separate work.** Decided 2026-07-26 ("just build a warm container for now"), taken against
  `spikes/headless-materialize/findings.md`, which ranks `level materialize --native` first overall
  and calls the GUI editor a dead end. Recorded so the ranking is not silently re-litigated, and so
  the warm work is understood as a bridge rather than a foundation. Proposed wording, verbatim, as a
  closing note to `direction/materialize.md` § "The editor container":

  > The warm editor is a **bridge, not a destination.** The editor-free native build already
  > produces a complete map — geometry, lighting, movers, actor names and paths — in a fraction of
  > the time and with no Wine, container or display at all; what it still lacks is byte-parity with
  > UnrealEd on large maps. When that lands as a materialize backend, the warm editor becomes the
  > `--editor` fallback it was always going to be. Nothing should be built on top of the warm
  > container that would be expensive to retire with it.

  *(Rejected: re-scoping the warm-editor work to `materialize --native` now — a bigger, different
  change with an open byte-parity front; promoting the headless commandlet to a build backend — it
  cannot produce a lit map, and nine workarounds for that failed.)*

- **[OWNER — confirm] p2 EVERY editor container self-terminates when idle, not just the warm one.**
  `direction/containers.md` currently promises idle self-death only for the warm containers. That is
  where the container leak lives: teardown exists solely in a host-side `finally`, and SIGTERM (which
  is what `timeout … bin/uedcli level materialize` sends) kills Python without running it — so a
  killed or wedged ephemeral build strands a running editor and its ~0.5 GB wineprefix volume,
  permanently. Measured on this host 2026-07-26: 8 stranded containers over ~4 hours and 9 orphan
  volumes ≈ 5.5 GB. No host-side handler can fix it (SIGKILL), so the container has to be able to
  reap itself. Proposed addition, verbatim, to `direction/containers.md` § "Per-command ephemeral is
  the concurrency story":

  > **Every editor container self-terminates when idle — ephemeral ones included.** Teardown by the
  > invocation that started it is the fast path, not the guarantee: a killed uedcli process runs no
  > cleanup at all, and an editor that outlives its parent would otherwise hold its memory and its
  > disk forever. The container's own idle timer is what makes "ephemeral" true rather than merely
  > intended. Because a container cannot remove its own volume, the volume is reclaimed by a sweep of
  > unattached volumes on the next acquire — keyed on having no container attached, never on age,
  > since a legitimate build can outlive any threshold.

  Folded into `specs/2026-07-18-warm-editor-materialize.md` decision 8 + §4.5. *(Rejected: host-side
  signal handlers as the mechanism — they cannot cover SIGKILL; an age-based sweep as the primary
  mechanism — two legitimate multi-minute builds were in flight among the 8 stranded containers
  observed, and an age threshold would have killed them.)*

- **RESOLVED 2026-07-26 — was: [flag→Andrzej / spike→spec] p2 Warm-editor materialize spike (SP-E)
  RAN 2026-07-19 and FOUND A BLOCKER.** The design decision is made (the two `[OWNER — confirm]`
  items above); the spec is revised; the follow-up spike is `to-spike.md` SP-F. Kept below for its
  evidence until SP-F lands, then delete. Original entry: Spike
  `spikes/2026-07-18-warm-editor-materialize/results.md` (2-reviewer cold-gated; harnesses committed).
  **Editor reuse itself works** (a warm editor builds the castle correctly, and a genuinely-reused
  *successful* build is `canonical_level_hash`-identical to a fresh build), **but the H3 post-verify —
  which today runs AGAINST the warm editor — breaks it: ~50% of reused builds fail** because the
  verify leaves the editor in a state where a later build's `MAP SAVE` silently writes no file
  (`no_verify` reuse is 0/4-clean; isolating only the UCC export does NOT fix it → the disruptor is
  the in-editor qualify dump / editor-mid-verify racing the next fire-and-forget drive; §89 class).
  So `specs/2026-07-18-warm-editor-materialize.md` §4.4's "H3 verify against the same live editor"
  (D-Q3) must change. **DECISION FOR YOU (spec §8 SP-E RESULTS has the detail):** which fix —
  (1) run the WHOLE H3 verify (export+qualify) against a SEPARATE throwaway editor (works regardless
  of cause; but a cold verify editor costs ~15 s ≈ the entire ~16 s warm saving, so it'd need
  warm-pooling); or (2) a robust editor CPU-idle barrier after verify (cheap, keeps the saving — but
  only works if the cause is a transient race, which is NOT yet discriminated from durable state; gate
  it behind a quick discriminator first). Then SP-E must be **re-run to confirm 0/N** before building.
  Also surfaced: **SP-E.2 saw a possible REAL cross-level stale-pool residue** (a CASTLE `Bounce_`
  actor leaked into an anchor build's verify) — inconclusive (flaky-editor run), re-test after the
  fix; and **SP-E.7 (colliding names) not reached** (needs the fix + a fixture). The spec + `quirks.md`
  are folded; the build is NOT green-lit as specced. **The warm-editor spec is otherwise ready — this
  is the one gate.**

- `p3` `[chore] usability-nit leftover: --prefab-dir position` — `prefab` takes `--prefab-dir` on the
  PARENT parser (documented `prefab [--prefab-dir DIR] <sub>`, usage.md:550), so it must come BEFORE the
  subverb; `stash promote` takes it on the subcommand (`stash promote ID --prefab-dir X`, after). The
  usability probe wants these consistent. **DECISION NEEDED** (each has a cost): (a) ADD `--prefab-dir`
  to each prefab subcommand too so the after-subverb form ALSO works (additive, keeps the documented
  form — but the flag then lives in two places); (b) MOVE it to the subcommands only (consistent, but
  breaks the documented `prefab --prefab-dir X list` form + its docs); or (c) just document the
  difference. Deferred from the 2026-07-19 nits batch (the other nits landed) pending this call.

- `p3` `[debug] usability-nit leftover: single-name verb given multiple names dumps top-level usage` —
  e.g. `actor move A B` (move takes ONE name) → argparse reports "unrecognized arguments: B" with the
  TOP-LEVEL usage, not `actor move`'s. Wanted: a scoped error naming the offending extra + the verb.
  This is an argparse wart (unrecognized-args surface at the root parser after subparser parse); a clean
  fix needs either a per-subparser `parse_known_args` wrapper or intercepting `error()`. Not a small
  mechanical change — deferred from the 2026-07-19 nits batch for a deliberate approach.

- `p3` `[debug] usability-nit leftover: upstream pipe errors flow downstream as data` — when an upstream
  verb in a `|` pipe fails and emits something to stdout (e.g. argparse usage), a downstream `- ` consumer
  reads it as a name (`unknown brush 'usage'`). Our verbs send errors to stderr (so a clean pipe is
  fine), so this bites mainly on argparse-usage-to-stdout or a partial producer. A robust
  detect/annotate is fuzzy (heuristically recognizing "this stdin line is an error, not a name"). Needs
  design — deferred from the 2026-07-19 nits batch. (Related: the scoped-error item above would reduce
  the argparse-usage case.)


- `p3` `[chore] two tool-hygiene finds from the leveldesign docs re-review` — (a) `uedcli-native/src/
  bspcsg.rs:44` and `:1172` carry stale `NumPolys/10` comments that contradict the code two lines below
  (the stride is `NumPolys/20` for GOOD — the `*0x66666667 >> 35` idiom); fix the comments. (b) running
  `uedcli` outside a project prints stray debug lines to the terminal (`plaintext False`, `swingperiod
  True`, …) — looks like leaked debug output in schema/catalog loading; track down and remove.


- `p3` `[chore] spiral column/tread seam is polygonal-vs-chord` — the central column is a
  `SPIRAL_COLUMN_SIDES`-gon (16) prism, so its facets don't align to each wedge tread's STRAIGHT inner
  chord over `degrees_per_step` (a straight chord vs a run of column facets). Tiny cosmetic seam
  gaps/overlaps are possible where a tread meets the column. Harmless under additive CSG (the union
  still fills solid); would matter only if someone wants a pixel-tight seam. Deferred from the spiral
  redo fix batch.


- `p3` `[implement] true-occlusion label filter` — the `--labels` grammar's `poly:vis` ships meaning
  **front-facing** (the cheap backface cull). A stricter "don't label a face whose centroid is hidden
  behind other geometry" filter is a possible future refinement — either tightening `vis` or a new
  filter name — needing a real painter/z-buffer occlusion pass over the projected faces in the stdlib
  rasterizer. Optional, low priority; noted from spec `specs/2026-07-22-labels-granularity.md` (A4).


- `p3` `[implement] preview label tint — palette-cycle collision at 11+ actors` — the hybrid
  per-actor label tints (`preview._TINT_PALETTE`, 10 hues) cycle when a scene has >10 drawn actors, so
  the 11th actor shares actor #1's tint. Brush swatches (square) vs point markers (diamond) still
  differ by glyph, so a brush/point collision is legible, but two BRUSHES sharing a tint is not. Only
  bites very dense scenes; the legend + `--focus` mitigate. Options if it matters: grow the palette,
  or perturb luminance on the second cycle. Noted from the 2026-07-22 hybrid-tint build.


- `p3` `[implement] preview dense-default center still busy` — with the hybrid tint+legend, a scene of
  ~8 overlapping brushes at `--size 460` still crowds the center: adjacent small poly-index labels'
  tints take effort to separate at that size. `--focus <brush>` is the intended remedy (spotlights one
  brush, dims the rest — scored ~4.7 vs ~4.0 for the all-at-once view). A future non-focus improvement
  could be a larger default label font in dense regions, or auto-`--focus` hints. Noted from the
  2026-07-22 hybrid-tint cold-reader loop.

- `p3` `[chore] byte-golden refactor guard for `_scene_geometry`/`_framing`` — the projection+framing
  block extracted out of `render_brushes_pgm` (during the `--split` build, which has since been replaced
  by `--breakdown`) is verified behavior-preserving only by the existing count/color/position tests;
  there is **no byte-exact golden** of a fixed render guarding a future edit to those helpers (both
  `_scene_geometry`/`_framing` survive `--breakdown`). A single committed golden PPM (e.g.
  `brush_subtract.t3d` at a fixed size/view) would be the true guard. Flagged by the 2026-07-22
  build-review gate (nit N1).

- `p3` `[chore] done.md HYBRID entry went stale after the on-face port` — the "HYBRID per-brush label
  tint + legend + `--focus`" `done.md` entry still describes the leader/arrow/box poly-label path and the
  `_pale` label-box wash + black digits, all removed when on-face labeling became the sole renderer
  (commit `9dfb1ee44`) and `_pale` was dropped (`8a557f1a1`). The durable docs were reconciled; only this
  historical `done.md` tail entry is stale. Rewrite or drop it. Noted during the `--split` build.

- `p3` `[decide] decal anti-overlap: does the 20% overlap tolerance apply to point-actor MARKERS too, or
  only decal-vs-decal?` — Andrzej said "allow up to 20% overlap between decals". The build applies the
  `_DECAL_OVERLAP_TOLERANCE` uniformly to ALL obstacles in the resolver's set, which includes point-actor
  marker footprints (they share the `occupied` obstacle list). So a number may currently sit up to 20%
  over a marker. Provisional reading; confirm or split the tolerance (0 for markers, 20% for decals).
  Recorded in `decisions.md` 2026-07-23 15:22 UTC + spec amendments. Flagged by the build-review gate.

_(removed 2026-07-24: this `[debug]` rotation post-verify item was a duplicate — the fix landed as
the `Rotation` compare-time fold, `decisions.md` 2026-07-25, was generalized to every property by
the class-default contraction of 2026-07-25 00:36 UTC, and now falls out of the TYPED compare of
2026-07-25 02:15 UTC. Both halves of the original note are now wrong and are corrected here: the
equivalence does NOT live in `normalize_actor`, and the trunk does NOT store the editor's
zero-omitted spelling — the trunk stays faithful and the resolution to class defaults happens on the
throwaway compare view. My repro predated the fix.)_

<!-- ── small-fixes batch build (to-build.md #9, 2026-07-25) ── -->

- `p2` `[flag] to-build #9.5's premise was FALSE — I did NOT mark the two tests skipped, and here is
  what I did instead.` The item (and `decisions.md` 2026-07-24 21:58 UTC item 5) says
  `test_native_materialize.py`'s `test_box_sweep_lands_on_native_floor` and
  `test_point_below_floor_is_solid_after_hulls` die importing the spike harness, so mark them
  SKIPPED. **They do not die — both PASS at HEAD** (verified on a clean `bin/test`: 2389 passed, 1
  skipped, 0 failed, before I touched anything). The harness moved into the spikes tree
  (`fafe58e2f`/`322d696f1`) and `line_check.py` self-inserts the sibling 2026-06-27 harness dir on
  `sys.path`, so `utexture_decode` imports fine here. Marking two GREEN tests skipped would have
  deleted live coverage of the "pawn falls through the floor" bug, so I did **not** do it. What I
  built instead (commit `291c8f6e4`): `_load_line_check()` converts a HARNESS-side `ImportError`
  into a `pytest.skip` whose reason names the spike env, while an `ImportError` from `uedcli` itself
  still propagates (a regression in the code under test must stay red). Net effect: green here,
  a clean skip (never an ERROR) on a checkout where the harness's hardcoded absolute paths don't
  resolve. **Confirm this reading, or tell me to hard-skip the two tests as originally written.**
  Related latent fragility, un-fixed: `line_check.py` hardcodes
  `ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")` — it only imports at all
  on this machine's checkout path.

- `p2` `[debug] The SAME silent half-answer that 9.1 deleted from` `class show` `still lives in`
  `ClassIndex.ancestry`. `classindex.py:~168` catches a `SchemaError` from the super walk, prints a
  "super chain of X truncated" note to stderr and returns the TRUNCATED chain — never raises. After
  the 9.1 fix `class show` is safe only because its property walk errors out first; every OTHER
  consumer of that chain still gets a silently wrong answer when an ancestor package is missing:
  `descends_from` → `is_placeable` → `class list`/`--subclass-of` (a class simply stops being an
  `Engine.Actor` descendant and vanishes from the listing), `_distance_below`, and bare-name ingest
  qualification. Same decision applies (`direction.md` "No silent half-answers", 2026-07-24 21:58) —
  but the fix is NOT mechanical: `class list` deliberately tolerates one unparseable `.u` without
  aborting the whole listing, so the call is where to draw the line between "skip a broken package"
  and "refuse to answer". Surfaced by the #9 build-review gate (2026-07-25).

- `p3` `[chore] Bad cache-cap values behave two different ways.` `uedcli cache gc --max-bytes -1`
  exits 2 naming the flag (new, 2026-07-25), while `UEDCLI_SCHEMA_CACHE_MAX_BYTES=-1` is silently
  ignored and falls back to the built-in default (`schema_cache._env_int`, deliberate: "a bad
  override must never raise"). Defensible as-is — a typo'd env var must not break every command,
  whereas a typo'd flag is a direct instruction — but if the divergence bothers you, the env path
  could at least warn once on stderr. Surfaced by the #9 build-review gate (2026-07-25).

- `p1` `[decide]` **Three design calls the native-texture-formats review round made on Andrzej's
  behalf — please confirm or overrule.** All three are recorded in
  `specs/2026-07-25-native-texture-formats.md` + its plan, and each is cheaply reversible (one
  branch in the detection function plus its test), but none of them was his call and none is in
  `decisions.md` yet. The build's S7 is supposed to append them; flagging here so they are not
  silently inherited.
  1. **A four-slot `{Format code → layout}` map exists after all:** `{0: P8, 3: BC1, 6: BC2,
     7: BC3}`, everything else "recognised but unsampled". His steer was "make it work WITHOUT
     USING ANY SUCH TABLE"; the map is scoped so decoding never *requires* it (data-decisive chains
     decode with it unconsulted; an unknown code over an ambiguous chain is a named error, not a
     guess) and it is justified by all three dumped `ETextureFormat` enums agreeing on those four
     slots. But it IS an assumption about slot semantics, and it is the only one.
  2. ~~**A `Format` code that was never stored is treated as WEAKER than one that was.**~~
     **RESOLVED 2026-07-25 by Andrzej — nothing to confirm here any more.** He deleted both the
     `format-disagreement` case and the stored-vs-defaulted axis outright: a code breaks ties and
     vetoes a layout we cannot decode, but never contradicts the data, so a stored 0 and an absent 0
     now behave identically. Recorded in `decisions.md` 2026-07-25 17:45 UTC ("Texture layout
     arbitration is a tiebreak-and-veto"). Item 1 below survives him and is *strengthened*: the
     four-slot map is now also what vetoes (227 slot 8 = `TEXF_BC4` fits `bc8` identically to BC1),
     so it is load-bearing in a second way.
  3. **Detection and decodability are reported separately**: a chain that fits `linear4` uniquely
     *detects* successfully (`layout_source: data`) and then *fails to decode* with
     `unverified-format` naming the detected layout — rather than either decoding a guess or
     reporting "unknown".

- `p1` `[decide]` **One word in the texture-arbitration decision decides whether ~46 % of every
  texture corpus decodes — please confirm the reading I recorded.** Andrzej's AD1 (2026-07-25) says
  *"data fits several → a **stored** `Format` code breaks the tie; data fits several and no stored
  code → named error (never guess)"*. Read strictly — "stored" = the property is physically present
  in the export's tagged-property list — that second clause would turn **8,324** ambiguous chains
  into errors, because a `Format` property is stored on only **11 of 18,176** texture exports across
  the four corpora here. Concretely that is **1,137 of `uned/UED22`'s 1,998** textures, **1,362 of
  Deus Ex `System`+`Textures`'s 5,018**, and **5,826 of Unreal Gold's 10,742** — all of them ordinary
  P8 textures that decode correctly today and would stop, and the native preview would checkerboard a
  quarter of Deus Ex. **What I recorded instead:** an absent property is *not* an absent code — by
  UE1's serialization rule (a property is written only when it differs from the class default, and
  `Engine.Texture` declares no `Format`) an absent property IS the byte 0, which is `TEXF_P8` in all
  three enums measured, so it breaks ties exactly as a written 0 would. Under that reading the only
  files that stop decoding are the ones AD2 names (a code-less BC2/BC3), which matches AD2's framing
  of *the* limit. The strict reading is a one-line change in the detection function plus its tests if
  you meant it. `decisions.md` 2026-07-25 17:45 UTC records both the reading and this flag; spec §0b
  / plan §0d are written to the recorded reading. *(Measured 2026-07-25 by sweeping all four
  corpora.)*

- `p3` `[chore]` **`<repo>/Textures/` is only partly git-tracked, and that keeps biting the test
  design.** `git ls-files Textures/` lists four packages (`France.utx`, `LUM_CharacterTex.utx`,
  `LUM_CoreTex.utx`, `LUM_InfoPortraits.utx` — 384 `Texture` exports); `CoreTexSky.utx` (1.7 MB) and
  `CoreTexWater.utx` (172 KB) sit beside them **untracked** (34 more exports). Two drafts of the
  native-texture-formats plan wrote "6 packages / 418 exports" into *offline* test expectations,
  which would fail on a fresh checkout and drift here. Fixed in that plan with a count-stability rule
  (exact counts only over `uned/UED22` + fixtures + the single tracked `LUM_CoreTex.utx`), but the
  underlying question is yours: **should those two packages be committed, gitignored, or moved?** A
  content directory that is half-tracked and live is a permanent trap for any corpus test.
  *(A copy of `CoreTexWater.utx` is already committed as a test fixture under
  `Tools/uedcli/uedcli/tests/fixtures/`, so at least that one is duplicated content.)*

- **[chore] p2 — Review-gate round-2 findings left standing (logged, not fixed).** The 2026-07-25
  gate-loosening batch's round 2 raised 14 findings; most were fixed in that batch, these were not.
  Logged under the post-round-2 rule (fixed / logged / escalated / refuted), so they are deferred
  legitimately rather than dropped:
  1. **The trivial-tier backstop cannot fire as written.** `CLAUDE.md` says "if the Haiku pass shows
     the change was not trivial after all, it is re-gated from scratch" — but nothing requires the
     reviewer prompt to state the triviality claim or ask the reviewer to challenge it, so a
     reviewer given an ordinary "review this diff" prompt never volunteers a tier verdict. Fix: make
     the trivial-tier prompt quote the claim and demand an explicit trivial/not-trivial answer.
  2. **Asymmetric loophole guard.** The plan round is explicitly nailed shut ("not writing a plan is
     NOT a way to skip this round") but the **spec** round has no counterpart, and the plan round is
     bound to "specced pipeline work" — so an agent that writes no spec skips both rounds and only
     faces the build round. Fix: mirror the guard onto moment 1.
  3. **Five forward-looking docs still instruct the OLD gate** (the 2026-07-25 sweep missed them;
     each restates a reviewer count instead of citing `CLAUDE.md`, which the gate now forbids):
     `dev/docs/plans/2026-07-22-labels-granularity-plan.md:22-23`,
     `dev/docs/board/to-plan.md:75`,
     `dev/docs/specs/2026-07-19-leveldesign-docs-skills.md:319`,
     `Tools/uplayctl/docs/dev/plans/2026-07-12-…-place-ids-plan.md:249-250`,
     `Tools/uplayctl/docs/dev/specs/2026-07-02-navigation-exits-followpath-rooms-design.md:246-247`.
  4. **Contradiction to reconcile:** `specs/2026-07-19-leveldesign-docs-skills.md:3` says its spec
     gate is "pending" while `board/to-plan.md:69` calls the same spec "cold-review-gated +
     revised". One is wrong, and either way it costs or skips a whole spec round.
  5. **Both 2026-07-25 ledger entries were reworded in place after being pushed** (the plan-round
     trigger, the round-2 condition, the trivial definition and the uplayctl `Refs` note all
     changed), and only the "~15–25 %" arithmetic correction is disclosed in the text. Both ledgers'
     headers say an active decision is "never reworded, only superseded". Fix: either append a
     disclosure note to both entries, or add a header carve-out permitting in-place correction while
     an entry is still inside its own review gate. **Andrzej's call which.**

- **[spec] p1 ANDRZEJ — the older gate-contradiction item above is now STALE.** The `[spec] p1
  ANDRZEJ` entry that quotes `Tools/uedcli/CLAUDE.md`'s "there is no trivial-change exemption" and a
  "2/3/4 reviewer ladder", and the repo-root `CLAUDE.md`'s competing "two reviewers", describes text
  that no longer exists: the ladder was replaced 2026-07-25 17:20 UTC and the **repo-root
  `CLAUDE.md` was deleted entirely** the same day (its live rules folded into
  `Tools/uedcli/CLAUDE.md`, mirrored in uplayctl's). Its parts (b) dangling citation and (c) no
  ledger entry are also both resolved. Left for you to delete or re-scope rather than edited by the
  session that obsoleted it.

- **[chore] p2 Agent-session slowness on this machine is HARDWARE-bound — measured 2026-07-25.**
  Diagnosis run at Andrzej's request ("code review and coding tasks are extremely slow"). The box is
  an **Intel i5-2400, 4 cores, no SMT**; 7.7 GiB RAM with **167 MiB free** and **1.9 of 2.0 GiB swap
  consumed**; **five concurrent `claude` processes** at 1.9 GB RSS combined (two of them idle for 9 h
  and 1 h 49 m). Subagent concurrency is therefore `min(16, cores - 2)` = **2**. The gate headcount
  was cut to match (decision 2026-07-25 18:42 UTC); the rest is unaddressed and needs Andrzej's call
  because it is machine/repo-shape work, not tool work:
  1. **Idle sessions hold RAM and reviewer slots** — closing the two long-idle ones frees ~860 MB and
     two-thirds of the concurrency. No code change; a habit.
  2. **Root-level `rg` costs 3.6 s per search, vs 0.16 s excluding the binary-heavy dirs** (22×).
     Cause: ~500 MB of **tracked** blobs in the search path — `Temp/downtown_export*.t3d` (24 MB
     each), **three copies** of the 25 MB UED22 packages (`Tools/uedcli/uned/UED22/`, `Extra/UED22/`,
     `Extra/UED22_COPY/`), `Maps/20_Downtown.dx` (18 MB), `Textures/*.utx`. `.gitignore` cannot help
     (they are tracked). Fix: a repo `.ignore` (ripgrep-only, does not affect git or the build).
     Separately: is `Extra/UED22_COPY/` needed at all? Three tracked copies of the same 60 MB look
     accidental and they are a large part of the 3.2 GiB pack. **Deleting tracked files is Andrzej's
     call.**
  3. **698 MB of session transcripts** for this project alone (43 sessions, largest single file
     82 MB), plus 134 MB of `~/.claude/file-history`. Pruning speeds session resume but discards
     history — **Andrzej picks what to keep.**
  4. **2 GiB of swap for 7.7 GiB of RAM with five agents is undersized** — more RAM / zram / fewer
     concurrent sessions. Machine change, outside the repo.

- **[chore] p2 Tell the LLM level-designer to CHECK UEDCLI'S EXIT CODE — a failed operation is
  easy to miss.** Raised by Andrzej 2026-07-26 after the three-level agent build run
  (evidence: `dev/docs/spikes/levelbuild-friction/`). Agents repeatedly carried on after an
  operation had failed, because they read the *output* rather than the *status*. Concretely
  observed in that run:
  - `substrate stub Endemia` fails with `Exiting due to error` and **exit 2** — correct
    signalling — but the actionable cause (`Can't find Function in file 'Function
    DeusEx.DeusExDecoration.BeginPlay'`) is separated from the terminal line by blank lines and an
    out-of-order `stubbing Endemia…` progress line, so eyeballing the tail suggests "it printed
    something, probably fine".
  - The orchestrating session **itself misread a shell pipeline's exit status as uedcli's** and
    briefly reported a non-existent "exits 0 on failure" defect. `cmd | grep | tail` reports the
    LAST stage's status — `PIPESTATUS[0]`/`set -o pipefail` is needed, and every `2>&1 | tail`
    idiom in the docs' own examples is exposed to this.
  - Agents habitually pipe uedcli through `| tail -N`, which is exactly the idiom that discards
    both the status and the earlier lines carrying the cause.
  Where it belongs: `docs/usage.md` (a short "check the exit status, and how not to lose it
  through a pipe" note) and the level-design guides that show piped invocations.
  **Caveat that must be stated in the same note, or it teaches false confidence:** exit 0 is
  NOT sufficient. In the same run `level materialize --no-verify` exited 0, printed
  `materialized <path>`, and wrote a 23,126-byte runt with no light bake (correct build:
  191,332 bytes) — see friction §1b. So the guidance is "a non-zero status always means it
  failed; a zero status does not always mean it worked — check the artifact too."

- `p2` `[debug]` **The unwired native materialize path drops a non-zero polygon `Pan`.** Found while
  fixing the zero-`Pan` emit bug (2026-07-26, `rationale/emit.md`), NOT fixed there — it is a
  different defect on a different path and the fix under way was the compare/emit spelling, not the
  native builder. `native/materialize.py` (~line 716) flattens each poly's `vertices`, `normal`,
  `origin`, `texture_u`, `texture_v` for the Rust CSG core and **never passes `poly.pan`**;
  `uedcli-native/src/fpoly.rs`'s `FPoly` has no pan field at all, so nothing downstream could
  consume it. A face with an authored `Pan U=16 V=8` would therefore build with its texture
  unpanned. **The module is NOT dead code** — `brushcsg.merge` imports `_build_brush_input` and
  calls it per brush (imported at `uedcli/brushcsg.py:212`, called at 215-216), reached from
  `dispatch.py:1257` for
  `brush intersect`/`deintersect`. What keeps that harmless is a SECOND mechanism, not the path being
  cold: `brushcsg.py:229` re-attaches `pan` onto each result face from the SOURCE poly it was cut
  from, so the pan lost on the way into the CSG core is put back on the way out. A refactor that
  dropped that re-attach would silently unpan every intersect/deintersect result. What IS unreachable
  is the whole-map `.dx` writer in that module: `level materialize` has no `--native` flag (`--help`,
  checked 2026-07-26), and `unrealed/t3d.md` lists `native/materialize.py` as not-yet-wired.
  `architecture.md`'s `preview --native` paragraph independently records "Pan doesn't survive the
  build", which is the same gap seen from the preview side (preview works around it by computing UV
  from the AUTHORED poly rather than the built surf).
  What to do: decide whether the Rust `FPoly` carries pan (the editor bakes it into the surf's base
  point) or whether the Python side folds pan into `origin` before handing geometry over — then pin
  it with a differential test against the editor-built `.dx`, since a silently unpanned surface is
  exactly the kind of wrongness a post-verify on a native build would have to catch itself.

- **[finding] The rotate/scale default pivot has three open points the spec cannot durably hold.**
  `dev/docs/specs/2026-07-26-rotate-pivot-grid-aligned-center.md` §7 is the only home for these, and
  specs are ephemeral — so they land here.
  1. **Scope was never owner-confirmed.** The own-Location pivot is live on BOTH `actor rotate --by`
     and `brush scale --by` because they share `rotation.best_grid_pivot`. Splitting them would be
     the larger change, so sharing was kept — but it was an agent call, not a ruling.
  2. **Residual displacement is unmeasured.** The pivot is a member's Location, not the selection
     centre, so a group still swings by that member's offset from the centre — zero for a lone
     actor, roughly half the inter-member spacing otherwise. No target was set for it.
  3. **The long-lever off-grid residue is real and pre-existing.** Beyond ~11,438 uu from the pivot
     (`CLEAN_EPS / 8.742278e-08`) the GMath rotator dust exceeds the emitter's snap band, so a
     rotated `Location` lands genuinely off-grid: two actors 24,000 uu apart rotated 90° about their
     midpoint stored `X=11999.998951`. Orthogonal to the pivot choice. The obvious fix — an exact
     integer matrix for 90°-multiple deltas — would diverge from what UnrealEd computes for the same
     operation, against the byte-identity goal, so it needs a spike rather than a patch.
