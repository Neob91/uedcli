+++
priority = "p3"
kind = "chore"
summary = "pair_touches and _planar_void_contact share ~25 lines of contact-region pipeline"
+++

# pair_touches and _planar_void_contact share ~25 lines of contact-region pipeline

Flagged in final review of `actor-survey-csg-tier-resolved-geometry-and`: real duplication, not a
bug, and out of scope for that diff (already large; a late refactor risks new bugs).

`pair_touches` (`uedcli/actor_survey.py:1804-1822`) and `_planar_void_contact` (same file,
`2005-2023`) both: get candidate planes from `contact_planes`, slice each actor on its own
`_self_consistent_plane`, skip if either side's `plane_slices` is empty, build both actors' plane
frames, reproject `b`'s slice into `a`'s frame, clip the two with `relation._clip_2d`, and reject a
region under `_MIN_CONTACT_AREA`. They diverge only after that: `pair_touches` probes the surviving
region with `_region_probes` and calls `_contact_at`; `_planar_void_contact` probes with the denser
`_region_grid_probes` and calls `ctx.probe.solidity.point_is_solid`.

A future session could extract the shared "candidate planes -> clipped region" pipeline into a
helper both call, parameterized on the probe-point set and the per-point test.
