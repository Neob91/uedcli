+++
priority = "p1"
kind = "implement"
summary = "Solid and textured brush faces in actor preview; builds SECOND, after the texture decoder."
depends-on = ["native-texture-decode"]
spikes = ["dev/docs/spikes/levelbuild-friction/"]
+++

# `actor preview --faces {wire,flat,textured}`

Plan: [`../../../plans/2026-07-27-actor-preview-faces-plan.md`](../../../plans/2026-07-27-actor-preview-faces-plan.md).
Spec: [`../../../specs/2026-07-26-actor-preview-textured-faces.md`](../../../specs/2026-07-26-actor-preview-textured-faces.md).

**Read the PLAN first; it and the spec are self-contained.** The plan carries the slicing, the file
map, the Done-whens and the two mechanisms that are cheap to re-break; the spec carries the owner's
decisions with their rejected alternatives.

**Why it matters.** `actor preview` is a wireframe schematic today. **Every** texture-frame defect
in `../../../spikes/levelbuild-friction/agent-reports.md` — mirrored lettering, the half-shifted sheet,
the wrapped door trim, a cut-out texture on a solid face — was invisible in it and cost a full
materialize + render cycle to find. `flat` also makes a subtracted room show its interior instead
of the outside of a box.

**BUILD ORDER — this builds SECOND.** Slice `S4` consumes the mip-pyramid accessor and the
`bMasked` flag that board item `native-texture-decode`'s slice `S2b` delivers. Owner decision 2.11 orders
the whole feature after that item; the plan implements that as ruled. *(Only S4 has a technical
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
