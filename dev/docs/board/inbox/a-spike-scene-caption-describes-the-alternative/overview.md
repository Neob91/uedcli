+++
priority = "p3"
kind = "chore"
summary = "A spike scene caption describes the alternative the spec REJECTED"
+++

# A spike scene caption describes the alternative the spec REJECTED

In
`spikes/2026-07-26-poly-rotate-curved-track/uv_preview.py`, `frame_one_tile`'s docstring and the
`onetile-ortho` scene text both say the corrected form is *"keep V for the up-vector, set
`U = V × N`"* — but the code does **Gram-Schmidt** (`u_dir = unit(sub(u_dir, mul(v_dir, dot(u_dir,
v_dir))))`), and `specs/2026-07-26-poly-surface-verbs.md` §2.6 lists `U = V × N` under **Rejected**
(it picks its own sign and mirrors the image on half the face directions). The rendered evidence is
correct; only the caption is wrong. Two-line fix, but it is a durable evidence harness, so a future
reader would take the caption as the ruling. Found while closing the spec's round-2 findings;
out of scope for that pass because it edits a different artifact. *(2026-07-26.)*
