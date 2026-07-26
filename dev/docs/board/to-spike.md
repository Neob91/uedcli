# To spike

Open questions that need a **spike** (`dev/docs/spikes/`) — a live or offline investigation — to
resolve before the dependent work can proceed. Findings fold back into the relevant spec. See
[`README.md`](README.md). Tag: `[spike]`.

---

- `p2` `[spike]` **Re-measure the SOUND corpus on the composed search path before the audio arm is
  specced.** Owner ruling 2026-07-26 ("spike first, then spec"). The old spec's scope rule was sized by
  numbers taken over directories the tool does not load: it claimed 10,826 Sound exports with ~10,200
  `DeusExConAudio*` VO; re-measured on the real configured path (119 package stems) it is **747 exports and
  ZERO `DeusExConAudio*`** — those packages exist only under `System.bak/` (18) and `SystemOk/` (18), and a
  whole-install walk gives 31,059, which is where 10,826 came from. The pattern also **misses the VO that is
  actually there** — `LUM_ConversationsAudioMission20` (109) and `TNM` (84) — so it would have leaked the
  project's own conversation audio into `sound list` while reporting "excluded: 0".
  **Measure, on the composed path only:** Sound exports per package; the Outer group structure (tracked
  `DeusExSounds.u` has 399 across 10 groups — `Weapons` 91, `Generic` 85, `Animal` 57, `Player` 56); how
  much is genuinely conversation VO and how it is identifiable; and whether `sound list` needs any default
  filter at all at that size. **Then** decide whether a per-substrate config key is warranted — do not
  design the rule first. Findings fold into
  `specs/2026-07-26-asset-catalog-audio-arm.md`. Two downstream claims also need re-basing on the result:
  the plan's hot-author-path cost criterion, and the engine spec's ObjectProperty-validation worked example.
  *(2026-07-26.)*

- **[spike] p2 SP-F — commandlet verify + warm-editor reliability re-test.** BLOCKS the warm-editor
  materialize build. Spec: `specs/2026-07-18-warm-editor-materialize.md` §9 (the seven questions, each
  with its falsifier). Context: SP-E (2026-07-19) proved reused builds fail ~50 % because the H3
  post-verify runs against the warm editor; the spec now moves the whole verify into a one-shot
  `UCC.exe Editor.ExecCommandlet` container (`spikes/headless-materialize/findings.md`: no GUI, no X,
  ~1.4–3.7 s, stdout + self-exit). SP-F confirms that substitution and re-tests reliability.
  **Acceptance for the reliability question is 0/N over ≥8 warm builds** — SP-E's lesson is that
  ~50 % is what "mostly works" looked like. Harnesses land in `spikes/2026-07-26-commandlet-verify/`.
  Two questions are prerequisites for the design at all: whether wine runs off the image's baked
  `/wineprefix` with no volume mount (§5.2), and whether the verify container's loaded-class set
  matches the live editor's (§5.5.2). SP-F.7 (SIGKILL a materialize, confirm the container
  self-reaps) is the leak regression.

- **[spike] p3 — does the GMath rotator residue on a long-lever rotate actually matter, and against
  which tolerance band?** A rotate orbits `Location` through UE1's GMath matrix, whose entries are not
  exactly 0/±1, so the stored `Location` picks up `|L−P| × deviation` of dust. Measured on the real
  levels and code (build/plan review, 2026-07-26): worst single-entry deviation over all 64 CARDINAL
  (pitch,yaw,roll) combos is **1.7484555314695172e-07** at `(49152,16384,16384)` — *twice* the
  lone-yaw figure, so dust reaches `emit.CLEAN_EPS` (0.001) at **5719 uu**, not 11438. Live case:
  two actors 24,000 uu apart rotated 90° about their midpoint store `X=11999.998951`. Silently.

  **What the spike must settle, because a plan built on guesses was refuted:**
  1. **Which band is the criterion at all.** `docs/leveldesign/general/geometry-and-bsp.md` calls
     "off-grid coordinates cause BSP holes" **a myth, explicitly false**, and names discrete tolerance
     bands instead — the tightest being the **~1e-4 uu vertex merge**. `CLEAN_EPS` is an *emitter
     cosmetic* band, not a geometric one. Judged against 1e-4 the threshold falls to ~572-1144 uu and
     would fire on ordinary content; judged against `CLEAN_EPS` it barely fires at all. Does a
     0.001-0.011 uu residue change a built `.dx` — vertex merge, coplanarity, node count? Build the
     same level with and without the residue and diff.
  2. **Is it detectable exactly rather than by threshold?** For a cardinal delta the exact matrix is
     all `{0,±1}`, so `exact = P + R_int·(L−P)` in `Decimal` is a free ORACLE: compare against
     `rotate_point`, report the real residue. It writes nothing, so it does NOT touch the
     byte-identity-with-UnrealEd constraint that rules out *substituting* the exact matrix. This
     removes the need for any threshold constant.
  3. **Scope.** `brush scale --by` has **no** dust — its orbit is pure `Decimal`
     (`dispatch.py`, `Loc' = P + S∘(Loc−P)`), verified exact at 31,000 uu. Only `rotate --by` is
     affected, and only for deltas that are 90° multiples: 8 of the 64 cardinal combos (every mix of
     0 and 49152) are already bit-exact, and a NON-cardinal delta is off-grid by nature at any lever
     arm (`--by 0,6000,0` at 100 uu already stores `83.906031`), which spec §7.4 accepts.
  4. **Reachability.** At 5719 uu, whole-level rotates of the real trunks hit 2 actors in
     ContainerYard and 2 in DiveBar (max lever 11392); at 11438, zero. So the band that matters is
     exactly the one a lone-yaw constant cannot see.

  Findings fold into `specs/2026-07-26-rotate-pivot-grid-aligned-center.md` §7.4. **Do not write the
  warning first** — a plan that assumed the lone-yaw constant, per-axis distance, and `brush scale`
  scope was refuted on all three (plan round, 2026-07-26). *(2026-07-26.)*
