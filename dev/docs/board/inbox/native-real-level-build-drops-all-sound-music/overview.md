+++
priority = "p3"
kind = "chore"
summary = "Native real-level build drops all `Sound`/`Music` object imports (§88)"
+++

# Native real-level build drops all `Sound`/`Music` object imports (§88)

Editor 03
emits 17 Sound + 1 Music imports (AmbientSound/actor sound refs); native emits 0 — the actor-prop
emit path skips Sound/Music object properties (same bare-class schema early-out as the prop-skip
debug item above; resolving props restores these 18 imports). Non-fatal (not a load blocker) but a
fidelity gap; fold into the actor-property emit work. (Found 2026-07-19.)
