+++
priority = "p2"
kind = "debug"
summary = "native materialize: corrupt/locked `.utx` silently dropped from the texture-group index"
+++

# native materialize: corrupt/locked `.utx` silently dropped from the texture-group index

— **native materialize: corrupt/locked `.utx` silently dropped from the texture-group
index** (`native/pkgref.py:117`, silent-swallow audit 2026-07-18). `build_texture_group_index` does
`except Exception: continue` per `.utx`; a corrupt / truncated / unsupported-version / momentarily-
LOCKED package is skipped with NO note, so every texture that lived in it emits only a 2-part
`Package.Name` import (Group missing) → Deus Ex raises "Can't find Texture in file" at map load = a
broken map, zero signal. Fix: a stderr skip-note (mirroring the `dxpkg` closure discipline).
