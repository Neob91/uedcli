# Split the asset-catalog spec, or fix and re-gate a third time?

## Context

The asset catalog is one engine that would list and describe four kinds of game asset — textures,
classes, sounds and music. Its spec has now failed **two** review rounds. The second round (3 cold
Opus reviewers, 2026-07-26) produced ~65 findings, all three verdicts "not ready to build on",
*after* the first round's ~45 findings had all been folded. Several of the new defects were
**introduced by the previous round's own fixes**.

`CLAUDE.md` says this pattern does not converge and another round would not land it. So the
recommendation is to change the artifact's shape rather than fix again. Below is what the round
actually found, because the recommendation only makes sense against it.

**A. Structural — conflicts with your own protected doc.** §3c hashes procedural textures over
properties **resolved against the class defaults**. `direction/asset-catalog.md`'s *Rejected* list
kills precisely that: "**Content-hashing everything** — a class fingerprint over default properties
is brittle", because "any game patch would orphan the curated description". A patch to `Fire.u`'s
`FireTexture` defaults therefore re-keys every procedural shard, and §3b's protection
(owner-approved migration only) does **not** engage because no uedcli code changed. The 2026-07-26
parameter-hash ruling and this Rejected bullet cannot both stand — you have to reconcile them.
There is also **no parked item** for the parameter hash at all, so it has no durable home and the
spec contradicts the protected doc as written.

**B. Structural — two sections are sized by measurements that do not hold on the composed search
path.** Re-measured against the real configured path (119 package stems):

- **Sound.** §4a claims 10,826 Sound exports of which ~10,200 are `DeusExConAudio*` VO. Actual on
  the path: **747** Sound exports, **0** `DeusExConAudio*` — those packages exist only under
  `System.bak/` (18) and `SystemOk/` (18). The 10,826 figure reproduces only by walking non-path
  directories (a whole-tree walk gives 31,059). So the new per-substrate config key, `--include-vo`,
  and the excluded-count reporting are all bought to prevent a 10k-line dump **that does not
  occur**. Worse, the VO that IS on the path — `LUM_ConversationsAudioMission20` (109 exports) and
  `TNM` (84) — is **not matched** by a `DeusExConAudio*` pattern, so the project's own conversation
  audio would leak into `sound list` while the machinery reports "excluded: 0". §4a's "expected
  corpus ≈ 550" measures **747**. Plan S4's hot-path cost criterion and §8's central worked example
  both rest on the bad number.
- **Procedural textures.** §3c's "208 + 42 + 14 + 8 + 50 + 4 = 326" reproduces only by walking
  `System.bak/`, `TNM2/`, `2027/`, `IWR/` and `Maps/`. On the composed path: **40** `FireTexture`,
  **8** `WetTexture`, **1** `WaveTexture`, **0** `IceTexture`, **0** `ScriptedTexture` = **49**. So
  the entire `ScriptedTexture` apparatus (its own `preview_state`, stderr reason, batch-vs-single
  exit-2 rule, name-keyed identity, plan work) is sized by "50 of 326" of which **zero are
  reachable**.
- Also: the unnamed sixth addend is **`TNMScriptedTexture`** — a *mod-defined* `ScriptedTexture`
  subclass, 4 exports. That proves both that §3c's per-class table must match **by descent, not
  exact class name**, and that out-of-table procedural classes already exist on this install. §3c
  gives no rule for one, so it falls through to a pixel hash over **zero pixels** and every such
  texture collapses to a single identity — the exact failure §3c refuses for `ScriptedTexture`.

**C. Owner carve-out taken silently** (all three reviewers). §3b's "index-building writes the
preview PNG it has in hand" overrides `direction/asset-catalog.md`'s "**`preview` … is the only
producer** … no exploratory command can ever trigger a long render" and owner decision 7 — with no
parked item. Measured cost of the first cold `texture list`: ~2,700 PNGs (~77-146 MB) written by a
read-only exploratory verb. **This one is the agent's and is withdrawn** — the direction doc wins;
the fix is simply not to write PNGs while indexing.

**D. Still-standing escalation, unresolved across two rounds.** "No re-key path across a pixel
edit": the project edits its own `LUM_CoreTex.utx`, so its own texture edits retire the identity and
`classify prune --outdated` deletes descriptions that are still accurate. There is no verb and no
`classify set --identity` to carry a classification forward. Escalated by name after round 1, folded
nowhere.

**E. Graded alpha is not covered by `masked`.** A BC2/BC3 texture with 8-bit *graded* alpha (10
measured on this substrate; pervasive on UT, in scope per `direction/scope.md`) is one identity with
its opaque twin, one opaque preview, one classification, and **no fact distinguishes them** —
`bAlphaTexture` is currently left as "decide during the build". Identity is frozen, so this is cheap
now and unfixable later.

## Options

- **Split the spec (the round's recommendation).** All the churn is concentrated in the **texture**
  arm (frozen identity, procedural hashing, alpha, the preview/identity coupling) and in **audio**
  (whose corpus numbers must be re-measured on the composed path before any config surface is
  designed). The **class arm** is the part agents most lack, is nearly clean, and its remaining
  findings are ordinary fixes. Concretely: (1) split the class arm into its own spec and build it;
  (2) re-spec texture identity on its own, where the irreversible decisions get a dedicated gate;
  (3) re-measure the sound corpus on the composed path, then spec audio. Consequence: the class arm
  ships soon; texture and audio are delayed but get the scrutiny their irreversible decisions need.
- **Fix and re-gate a third time.** Keeps one spec and one build. Consequence: `CLAUDE.md` predicts
  it will not converge, and the last round's fixes demonstrably introduced new defects.

## Recommendation

Split. `CLAUDE.md`'s own answer to a non-converging gate is to give the work a fresh spec moment,
not a third round.

## Answer

<!-- Empty = open. Write the decision here. -->
