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
