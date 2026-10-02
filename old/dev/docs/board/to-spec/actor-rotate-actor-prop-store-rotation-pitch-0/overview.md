+++
priority = "p2"
kind = "debug"
summary = "`actor rotate`/`actor prop` store `Rotation=(Pitch=0,Yaw=8192,Roll=0)` with explicit ZERO fields — the editor re-exports `(Yaw=8192)` (zero fields omitted), so the trunk fails H3 post-verify on its next materialize"
+++

# `actor rotate`/`actor prop` store `Rotation=(Pitch=0,Yaw=8192,Roll=0)` with explicit ZERO fields — the editor re-exports `(Yaw=8192)` (zero fields omitted), so the trunk fails H3 post-verify on its next materialize

p2. Hit live 2026-07-16 building the native-preview anchor
fixture (worked around with `actor prop --set "Rotation=(Yaw=8192)"`). Fix: emit/normalize
FRotator props with zero fields omitted (`rotation.emit_frotator` already does this — the write
path that stores the composed Rotation doesn't use it), or canonicalize in `normalize`.
