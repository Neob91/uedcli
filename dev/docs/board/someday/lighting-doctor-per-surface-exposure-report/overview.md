+++
priority = "p?"
kind = "unknown"
summary = "Lighting doctor: per-surface exposure report from the native bake"
+++

# Lighting doctor: per-surface exposure report from the native bake

Run the N-4 bake
offline and report numbers instead of vibes: surfaces with ZERO light contribution (pitch black),
surfaces where many lights stack (the `LE_NonIncidence` washout lesson, 2026-07-13), lights that
contribute to nothing (dead weight), per-room brightness histogram; optionally a top-down heatmap
image. Would have caught both castle lighting mistakes without booting the game. Gated on the N-4
lit-render fix only for *verifying* in-game — the bake itself already runs. (AI brainstorm 2026-07-16.)
