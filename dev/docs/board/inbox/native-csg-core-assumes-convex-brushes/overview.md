+++
priority = "p2"
kind = "implement"
summary = "Native CSG core assumes CONVEX brushes — decompose or guard for non-convex builder output"
+++

# Native CSG core assumes CONVEX brushes — decompose or guard for non-convex builder output

Surfaced by the one-actor `brush build` review gate (2026-07-21). `uedcli-native/src/
csg.rs:60` `point_in_convex` classifies "inside" as behind EVERY face (the convex hull), and
`csg.rs:61`'s comment "DX brush builders emit convex brushes, so this is exact" is now **falsified**
— the single non-convex staircase brush mis-builds on `level preview --native` + native `level
materialize` (concave notches fill solid). Confined: default UnrealEd materialize + `--game` preview
are correct (see `direction/generators.md` 2026-07-21 12:22). Fix = decompose a non-convex brush into convex
pieces on the native CSG path (or guard + warn). Joins the documented ~11% native solidity
divergence (`architecture.md:1141`).
