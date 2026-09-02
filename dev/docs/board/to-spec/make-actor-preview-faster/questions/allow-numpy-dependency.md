May `actor diagram` take a NumPy dependency to vectorize its hot loops?

## Context

uedcli is deliberately **Pillow-only** for third-party runtime deps (`bin/_venv.sh`,
`pyproject.toml` — "Pillow is the ONLY third-party runtime dependency"). The preview overview
flagged NumPy explicitly: "vectorize hot loops (NumPy is not a current dep — decide)".

Profiling shows the dominant cost (~85 % of a default render) is the pure-Python **on-face index
placement** (`_max_inscribed_box`/`_erode_convex`/`_clip_ge`), not per-pixel fill. That stage can be
sped up ~2–3× in plain stdlib with byte-identical output (spec option A), so NumPy is not required to
make the common case fast. NumPy would help most on large `--size` and filled (`flat`/`textured`)
renders, where per-pixel work dominates.

Options:
- **No NumPy** (recommended) — do the stdlib algorithmic speedups (A+B); keep the single-dep policy
  and the eventual Nuitka release-binary simplicity.
- **Allow NumPy** — bigger ceiling on fill/large-size, but a second heavy runtime dep for a viewer,
  affecting packaging.

Recommendation: **No** — get the win from the decal-layout optimization; revisit only if a
measured filled/large-size case on real content is still too slow.

## Answer

<!-- Empty = open. -->
