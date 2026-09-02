+++
priority = "p1"
kind = "implement"
summary = "Solid and textured brush faces in actor preview; builds SECOND, after the texture decoder."
depends-on = ["native-texture-decode"]
spikes = ["dev/docs/spikes/levelbuild-friction/"]
+++

# `actor preview --faces {wire,flat,textured}`

Done. `--faces {wire,flat,textured}` — wire outlines, flat solid fills with physical occlusion, and
textured (each face painted with its real decoded texture through its authored UV frame). Shipped
across S1–S4; S5 docs folded (`rationale/preview.md`, `architecture.md`; usage.md in the S4 commit).
The `--faces` product rulings' durable `direction/` home stays parked in board item
`four-actor-preview-faces-rulings-need-a-durable`. Still owed, content-blocked: a real fill-cost
measurement on a game corpus.
