+++
priority = "p?"
kind = "owner-question"
summary = "gated on two upstream items, not the bake"
+++

# gated on two upstream items, not the bake

2026-07-18: raw-byte identity of the three light sections (LightMap a8 / LightBits
b4 / Lights e4) is **gated on two upstream items, not the bake**: (1) object-ref renumbering of the
export table (wrapper-level, `wrapper_diff.py`), and (2) BSP surf/leaf enumeration ORDER (native
bspcsg orders them differently than the editor — the bspBrushCSG byte-identity item). `light.rs`
can only make the sections structurally complete + content-correct; positional byte-identity is
those two items' job. Flagging so the byte-identity roadmap sequences them before "lighting bytes".
