# To spike

Open questions that need a **spike** (`dev/docs/spikes/`) — a live or offline investigation — to
resolve before the dependent work can proceed. Findings fold back into the relevant spec. See
[`README.md`](README.md). Tag: `[spike]`.

---

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

- **[spike] p1 Probe the TEXTURE-side `Masked` property.** BLOCKS the build of
  `specs/2026-07-26-actor-preview-textured-faces.md` (§11); the spec is otherwise complete and
  re-gate-ready. `unrealed/quirks.md` (🔬 2026-07-26) establishes that **`Masked` is a property of
  the TEXTURE, set at import, and a texture's flags are OR'ed into every surface it is applied to** —
  alongside the per-poly `PF_Masked = 0x2` (`query.PF_NAMES`). So a face masks iff its poly carries
  `0x2` **OR** its texture was imported masked; index 0 on any other face is an ordinary colour, not
  a hole. quirks.md says that texture-side property is *"not yet probed to the stored property
  name/offset on the export; do that before relying on the exact spelling"* — so uedcli cannot read
  it today.
  **Question:** what is the stored property name/offset on a `Texture` export that records
  import-time masking, and how is it decoded by `utexture`? Deliverable is a
  `utexture.texture_is_imported_masked(ref)` predicate + the fact landed in `quirks.md` with
  evidence, per `rules/spikes.md` (pin it with a committed regression test or it rots).
  **Why the poly flag alone is NOT an acceptable interim:** it silently misses a masked-at-import
  texture painted on an unflagged solid face — `CoreTexMetal.ladder_a` on a container wall — which
  **two of the three levels** in `spikes/levelbuild-friction/agent-reports.md` hit independently, and
  which decodes to `flags: none`. Shipping poly-only gating would make `--faces textured` agree with
  the broken `grep Masked` audit that caused the original confusion.
  **Falsifier / acceptance:** on this repo's fixtures, the predicate must return False for
  `CoreTexWater.dirtywater` (reserved magenta at index 0, 0 texels using it) and must correctly
  classify a known masked texture; and `LUM_InfoPortraits.ArthurCallaway` (index 0 = real black,
  2.2 % of texels) must NOT be treated as masked. Harness lands in
  `spikes/2026-07-26-texture-masked-property/`.
