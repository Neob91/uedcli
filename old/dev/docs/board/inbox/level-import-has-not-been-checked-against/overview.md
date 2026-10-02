+++
priority = "p1"
kind = "implement"
summary = "`level import` has NOT been checked against the official exporter — the load-bearing fidelity gate is still unrun"
+++

# `level import` has NOT been checked against the official exporter — the load-bearing fidelity gate is still unrun

Everything else of the feature is built, tested and
documented (the verb, the write path, the decode, the docs); what is missing is the one check that
proves uedcli decodes a map the way the *engine's own tool* would export it. That check compares an
import against a UCC `MAP EXPORT` of the SAME retail map through the shared
`level_order`+`normalize`+`canonical_level_hash` lens (plan Slice 5.1) plus the live
`verify_dx_matches(original, materialize(import(original)))` round trip (Slice 5.2). **It needs two
things the 2026-07-27 build machine did not have:** the retail `.dx` corpus (copyrighted, correctly
gitignored — `dev/scripts/install-deusex-assets.sh` populates it from a game copy you supply, and
it never downloads) and the `dx-lum-uned` editor container. Run it on a machine that has both.
Until then the honest claim is: the decoder reads real editor-built maps and produces parseable,
round-trip-stable, correctly-shaped T3D, with value FORMS checked only where a committed editor
export happened to cover them. Recorded in `rationale/mapimport.md` "What is NOT yet verified".
*(2026-07-27.)*
