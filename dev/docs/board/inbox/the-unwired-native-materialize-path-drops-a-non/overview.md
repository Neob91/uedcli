+++
priority = "p2"
kind = "debug"
summary = "The unwired native materialize path drops a non-zero polygon `Pan`"
+++

# The unwired native materialize path drops a non-zero polygon `Pan`

Found while
fixing the zero-`Pan` emit bug (2026-07-26, `rationale/emit.md`), NOT fixed there — it is a
different defect on a different path and the fix under way was the compare/emit spelling, not the
native builder. `native/materialize.py` (~line 716) flattens each poly's `vertices`, `normal`,
`origin`, `texture_u`, `texture_v` for the Rust CSG core and **never passes `poly.pan`**;
`uedcli-native/src/fpoly.rs`'s `FPoly` has no pan field at all, so nothing downstream could
consume it. A face with an authored `Pan U=16 V=8` would therefore build with its texture
unpanned. **The module is NOT dead code** — `brushcsg.merge` imports `_build_brush_input` and
calls it per brush (imported at `uedcli/brushcsg.py:212`, called at 215-216), reached from
`dispatch.py:1257` for
`brush intersect`/`deintersect`. What keeps that harmless is a SECOND mechanism, not the path being
cold: `brushcsg.py:229` re-attaches `pan` onto each result face from the SOURCE poly it was cut
from, so the pan lost on the way into the CSG core is put back on the way out. A refactor that
dropped that re-attach would silently unpan every intersect/deintersect result. What IS unreachable
is the whole-map `.dx` writer in that module: `level materialize` has no `--native` flag (`--help`,
checked 2026-07-26), and `unrealed/t3d.md` lists `native/materialize.py` as not-yet-wired.
`architecture.md`'s `preview --native` paragraph independently records "Pan doesn't survive the
build", which is the same gap seen from the preview side (preview works around it by computing UV
from the AUTHORED poly rather than the built surf).
What to do: decide whether the Rust `FPoly` carries pan (the editor bakes it into the surf's base
point) or whether the Python side folds pan into `origin` before handing geometry over — then pin
it with a differential test against the editor-built `.dx`, since a silently unpanned surface is
exactly the kind of wrongness a post-verify on a native build would have to catch itself.
