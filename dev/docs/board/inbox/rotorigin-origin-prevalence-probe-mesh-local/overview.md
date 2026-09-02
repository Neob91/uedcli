+++
priority = "p3"
kind = "docs"
summary = "RotOrigin/Origin prevalence probe — mesh-local extents vs world facing"
+++

# RotOrigin/Origin prevalence probe — does mesh-local thin axis == world mount normal?

The class-arm spec §3 carries a build-time probe (a tracked TODO, not an owner question): once the
decoder lands in `uedcli/`, measure on real deco meshes (1) whether the stored `FBox` is already
post-`Scale`/`Origin` or raw vertex space, and (2) **`RotOrigin`/`Origin` prevalence** — how many deco
meshes carry a non-identity `RotOrigin`, the field that breaks the mesh-local → world-facing mapping.
The finding is to land in `dev/docs/unrealed/` (owner-gated, hence this board note rather than a
direct edit).

**Early signal from the committed v69 UED22 corpus (decoder now in `uedcli/umesh.py`).** Non-identity
`RotOrigin` is common, not rare: e.g. `DeusExDeco.ComputerPublic` and `DeusExDeco.ComputerSecurity`
decode `rot_origin=(0, 16384, 0)` (a 90° yaw), while crates decode `(0, 0, 0)`. `Origin` was `(0,0,0)`
on the meshes sampled. So the mesh-local thin extent axis equals the world mount normal **only when
`RotOrigin` is identity**, which is frequently false — world-facing stays **UNVERIFIED**, exactly as
C1 scoped it. C1's reported `extents` are mesh-local seating/footprint facts and assert no facing.

To close: run a corpus-wide count of identity vs non-identity `RotOrigin` (v69 UED22 is available and
sufficient for prevalence; retail v68 confirms values), settle apply-vs-baked for the `FBox`, and
write the finding into `dev/docs/unrealed/` (propose text to the owner). Until then, no facing/azimuth
claim ships (azimuth is a C2 field).
