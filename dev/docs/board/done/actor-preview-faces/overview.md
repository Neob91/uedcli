+++
priority = "p1"
kind = "implement"
summary = "Solid and textured brush faces in actor preview; builds SECOND, after the texture decoder."
depends-on = ["native-texture-decode"]
spikes = ["dev/docs/spikes/levelbuild-friction/"]
+++

# `actor preview --faces {wire,flat,textured}`

Plan: board item `actor-preview-faces-plan-cites-dev-docs`.
Spec: board item `four-actor-preview-faces-rulings-need-a-durable`.

**Read the PLAN first; it and the spec are self-contained.** The plan carries the slicing, the file
map, the Done-whens and the two mechanisms that are cheap to re-break; the spec carries the owner's
decisions with their rejected alternatives.

**Why it matters.** `actor preview` is a wireframe schematic today. **Every** texture-frame defect
in `../../../spikes/levelbuild-friction/agent-reports.md` — mirrored lettering, the half-shifted sheet,
the wrapped door trim, a cut-out texture on a solid face — was invisible in it and cost a full
materialize + render cycle to find. `flat` also makes a subtracted room show its interior instead
of the outside of a box.

**Prerequisite LANDED (2026-07-27):** board item `native-texture-decode` is done, so nothing here is
blocked any more. Slice `S4` consumes two things it shipped, both on the decoder's typed result:
**`DecodedTexture.mips`** — every mip level as `(w, h, rgb, mask)`, a lazy property rather than the
`resolve_mips()` accessor an earlier draft named — and **`DecodedTexture.b_masked`**, read as the
export's tag if present, else the resolved class default, and `None` when the search path carries no
code package to resolve one from. Owner decision 2.11 ordered the whole feature after that item, and
it was built that way. *(Only S4 has a technical
dependency — S1–S3 touch no texture code. That observation is parked on the inbox as the owner's
call, not the builder's.)*

**Five slices:** `S1` `texframe.py` extraction (pure refactor) → `S2` the seam + `--faces` +
`flat` complete → `S3` `--focus` over filled modes → `S4` `textured` → `S5` docs, rationale, board,
spec deletion.

**Gate status:** spec gate passed (multiple rounds, no structural finding in any); plan gate passed
(2 rounds, both rounds' findings resolved and each fix verified by grep rather than declared).

**Two things a builder must not get wrong**, both found by review rather than by writing: the
mirror predicate needs a `None` guard, because `rotation.actor_linear` returns `None` for identity;
and `getattr(args, "brush_colors", "csg")` does **not** fire for an existing-but-`None` attribute,
so `default=None` needs an explicit `or "csg"` at each of three call sites — and no picture test
can catch its absence, which is why the plan asserts it at the seam.
