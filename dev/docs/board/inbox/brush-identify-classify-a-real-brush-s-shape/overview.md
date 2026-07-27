+++
priority = "p2"
kind = "unknown"
summary = "`brush identify` — classify a real brush's shape + reverse-map it to a generator (2026-07-24)"
+++

# `brush identify` — classify a real brush's shape + reverse-map it to a generator (2026-07-24)

Two coupled capabilities surfaced by the corpus brush-idiom study (`specs/2026-07-24-corpus-brush-idioms.md`
§7 gaps 2+3): (a) given a brush's polys/verts, **name its shape** against the generator vocabulary
(`cube`/`cylinder`/`cone`/`sheet`/`staircase`/`spiral`/2D-extrude) or tag it *freeform*; (b) emit the
**`brush build <shape> --params…` invocation that reproduces it** (or report non-generatable freeform).
No verb today — `brush poly list`/`vertex list` give raw geometry, not a shape identity. Bias toward
reporting *freeform* when params don't reproduce within tolerance (a too-eager classifier hides the
overbuilding the study exists to catch). The study's harness prototypes this; promoting it to a verb
(`brush identify [--as-generator]`) is the gap. Enables the reverse-mapping deliverable AND is generally
useful (remix/dedup/lint real brushwork). (Andrzej-adjacent, flagged 2026-07-24.)
