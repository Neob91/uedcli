+++
priority = "p2"
kind = "implement"
summary = "class arm C2 remainder: --angles, multi-ref/stdin, preview cache pool"
+++

# class arm C2 remainder: --angles, multi-ref/stdin, preview cache pool

The C2 build task scoped `class preview` to a single-ref surface —
`class preview <ref> [--rotate P,Y,R] [--out FILE] [--size PX] [--json]` — and its report-back
checklist. That shipped (commits under `class arm C2:`). The spec's C2 (§7, §9) lists more that the
task did NOT ask for and this build deliberately did not do:

- **`--angles`** — the `front, back, left, right, top, bottom, iso` shot set (spec §4). Only `iso`
  (the single default shot) ships. Multi-angle is opt-in and per-angle-costed in the spec.
- **Multi-ref + stdin `-`** — the spec surface is `class preview <ref>… | -`; the built verb takes
  ONE `<ref>`. No `--skeleton` JSONL row form either (it pairs with the batch/stdin path).
- **Preview cache pool + `cache gc --previews`** (spec §2, §9) — content-addressed `previews/<hh>/…`,
  its own byte budget, recursive sweep that never evicts the current process's output. Not built; a
  preview re-renders every time. `class list --json`'s cached `preview: null|path` (spec §7) is C3
  enumeration territory and also not built here.

None of these block the shipped single-ref preview. Pick up when the arm continues; the rasterizer
(`uedcli/meshrender.py`) and the single-shot path are in place to build on.
