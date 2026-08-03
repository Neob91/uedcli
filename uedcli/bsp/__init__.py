"""Build-emergent BSP health checks that run after `level materialize`'s editor build.

`editorlog` parses the editor's `MAP REBUILD` warning counts (dropped faces, unlinked
T-points, infinitesimal nodes); `builtmodel` locates defects in the saved built `.dx`
(near-zero-area nodes = invisible walls; non-collidable floor surfs = fall-through);
`checks` wraps both as advisory, never-fatal steps for materialize.
"""
