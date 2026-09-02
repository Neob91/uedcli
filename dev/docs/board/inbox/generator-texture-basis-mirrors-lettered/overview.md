+++
priority = "p2"
kind = "debug"
summary = "Built-brush texture basis (v = cross(normal, u)) may mirror lettered textures vs UnrealEd; confirm against an oracle, then fix."
+++

# generator texture basis mirrors lettered textures — confirm vs UnrealEd and fix

Source: `dev/docs/spikes/levelbuild-friction/` finding §6b. Agents reported lettered/asymmetric textures
on generated brushes rendering **mirrored** (backwards signage).

Root cause candidate: `builders._tex_basis` emits the polygon's `TextureU`/`TextureV` with
`v = _cross(normal, u)` (`builders.py:147`). If that handedness disagrees with UnrealEd's own
BrushBuilder convention, every generated face is systematically mirrored.

`actor diagram` is confirmed **faithful** — it maps from the same emitted `TextureU`/`TextureV`
(`preview_native.py:16`; `preview.py:1917`), so it shows the same result the game builds. Fixing the
basis corrects preview and game together; no divergence to manage.

Task: confirm uedcli's basis against an UnrealEd oracle (a GUI-built brush's exported `TextureU`/`V`).
If mirrored, flip it. The generator goldens self-bless the current basis, so they get rewritten — that
is expected, not a regression.
