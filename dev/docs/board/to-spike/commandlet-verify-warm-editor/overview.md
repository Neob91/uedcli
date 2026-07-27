+++
priority = "p2"
kind = "debug"
summary = "SP-F: verify via a one-shot commandlet container and re-test warm-editor reliability; blocks the warm-editor build."
spikes = ["dev/docs/spikes/headless-materialize/"]
+++

# SP-F — commandlet verify + warm-editor reliability re-test

BLOCKS the warm-editor
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
