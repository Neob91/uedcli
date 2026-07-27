"""Native (editor-free) `.dx`/`.unr` materialize — the offline build path.

This package is the Python glue for the native `level materialize`: it reads the
git-tracked T3D trunk and writes a game-loadable UE1 package byte-by-byte, with the
BSP/CSG compute delegated to the Rust `uedcli_native` extension (when built) and the
proven byte-exact serializers kept here in Python.

Module map (see board item `native-level-materialize` §3):
  codec.py        - FCompactIndex + primitive read/write (shared)
  pkg_write.py    - UE1 package container: header/names/imports/exports/layout/GUID+gen
  umodel.py       - UModel body parse (self-check) + write-from-arrays (Python dev oracle)
  actor_write.py  - StateFrame + FPropertyTag property list + struct layouts + UPolys
  level_write.py  - ULevel body (Actors/URL/ModelRef/ReachSpecs/trailing)
  pkgref.py       - import/name resolver (class -> defining package, textures by ref)
  assemble.py     - object graph -> name/import synth -> package bytes; Actors[0/1] synth
  materialize.py  - run_materialize_native(): trunk -> build -> assemble -> self-check -> swap
"""
