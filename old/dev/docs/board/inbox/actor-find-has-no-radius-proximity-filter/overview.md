+++
priority = "p2"
kind = "implement"
summary = "actor find has no radius/sphere proximity filter — only --within-bbox/--overlapping-bbox (axis-aligned box)"
+++

# actor find has no radius/sphere proximity filter

`uedcli actor find --help` offers `--within-bbox X0,Y0,Z0,X1,Y1,Z1` and `--overlapping-bbox` —
both axis-aligned BOXES. There is no way to select actors within a given RADIUS of a point (a
sphere/distance predicate), which is the natural query for "everything near this actor/location"
(e.g. finding what's around a landmark to build a local camera shot, or scoping a nearby-cleanup).

A caller wanting this today has to either over-fetch with a generous `--within-bbox` and filter by
distance client-side, or hand-write per-actor distance math against `Location` — both bypass the
verb's `-`-pipeable predicate model.

Found while trying to build a targeted `level photo --game` shot around a specific named actor in a
large level (`dx_lum`'s `downtown-full`) and needing "what's nearby" to compose the scene.
