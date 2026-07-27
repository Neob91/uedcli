+++
priority = "p2"
kind = "debug"
summary = "`brush vertex move` reaches the user as a bare Python traceback"
+++

# `brush vertex move` reaches the user as a bare Python traceback

`brush vertex move <name> --at 64,64,64 --to 1e30,64,64` prints a full traceback ending
`ValueError: no brush vertex at (…)` from `uedcli/vertex.py:81`. `dispatch`'s top-level handler
chain catches `_SelectionExit`, `_ProjectError`, `LevelSelectionError`, `ConfigError`,
`CoordinateError`, `GeometryError`, and the editor errors — but not a plain `ValueError`, so this
one escapes. Violates `CLAUDE.md` "never let a Python exception reach the CLI user". Pre-existing
and untouched by the profile-generator work; found while probing the neighbouring write-path
guard. Fix by raising a named error at the vertex lookup, with a regression test.
(Round-2 build review, 2026-07-26.)
