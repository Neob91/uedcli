+++
priority = "p2"
kind = "investigate"
summary = "Joystick touch-detection is static/unreliable; owner wants Q/E replaced with a modifier+W/S/LMB vertical scheme -- needs a conflict-free modifier"
+++

# Joystick visibility detection + Q/E replacement

DONE (touch-detection half only, 2026-09-20): the static `touchCapability.ts` capability check
(false-positived on Steam Deck and hybrid touchscreen+mouse laptops) is replaced by `inputMode.ts`'s
event-driven detection -- hidden until a real touch `pointerdown` fires, then hidden again on a real
keyboard press or mouse click (`pen` is a deliberate no-op, owner ruling 2026-09-20 -- a stylus
implies nothing about keyboard availability). Persisted via `localStorage`, mirroring
`useCollapsiblePanel.ts`'s convention.

The Q/E-modifier-replacement half was UNRELATED (a keyboard-binding question, not a detection one)
and is split out to its own item: `q-e-vertical-move-modifier-needs-ued22-re`.
