+++
priority = "p1"
kind = "debug"
summary = "post-verify can false-flag a GEOMETRY mismatch when a texture name is ambiguous across two packages the level references"
+++

# native materialize resolves same-name texture to the wrong package

On `dx_lum`'s `downtown-full` level (5765 actors), `UEDCLI_NATIVE_MATERIALIZE=1 level materialize`
built the whole world (CSG + 1016 lights) and only then hit a post-verify mismatch:

```
actor 'Brush1118' differs in GEOMETRY at line 12:
    built:    Begin Polygon Item=OUTSIDE Texture=NYCBar.NYC_GrayMetal_A
    intended: Begin Polygon Item=OUTSIDE Texture=NewYorkCity.NYC_GrayMetal_A
```

The trunk's own `actor.t3d` for `Brush1118` qualifies this poly's texture as
`NewYorkCity.Metal.NYC_GrayMetal_A` — but that SAME brush also has other polys textured
`NYCBar.Wood.un_woodwall_b`, so both `NYCBar` and `NewYorkCity` end up in this level's
`_level_referenced_packages` (`apply.py:55`). `NYC_GrayMetal_A` exists in both packages. In
`native/unbuilt.py`'s `tex_ref` (~line 549-567), the qualifier is deliberately dropped (replicating
a measured real-editor quirk: the importer binds by bare name, not the T3D's qualifier) and
resolution falls to `pkg_stem = min(loaded or candidates, key=...)` — a raw ASCII sort of the
candidate package stems. `"NYCBar"` sorts before `"NewYorkCity"` (`Y`=89 < `e`=101), so `NYCBar`
wins regardless of which package the trunk actually named.

**Open question, not yet confirmed:** the code comment claims this ASCII tiebreak is a measured
real-UnrealEd behavior (cited against a *different* case, `Area51Wall_A`/UNATCO). If that holds
here too, the real editor would ALSO reassign this poly to `NYCBar` on reimport — meaning
`downtown-full`'s trunk, as currently authored, cannot round-trip through post-verify for this
brush via ANY import path (native or the real wine editor), and the "mismatch" is really "the
trunk's stated qualifier doesn't survive faithful reimport," not a native-materialize defect. This
hasn't been checked against a live editor build for this specific two-package collision.

**Impact on verification:** whenever a level references two-or-more packages that both define a
texture of the same bare name, post-verify can report a same-shaped "actor X differs in GEOMETRY"
failure that looks like a real content/geometry problem but may be an unavoidable consequence of
this ASCII-tiebreak resolution rather than a defect in the build. That's confusing to debug (as it
was here) and, on a level authored assuming the qualifier is honored, permanently blocks a clean
`level materialize`/`level photo --game` (no `--no-verify` escape for `photo`) until either the
trunk's texture naming is deduplicated across packages or this is confirmed as expected/inherent
behavior rather than a bug.
