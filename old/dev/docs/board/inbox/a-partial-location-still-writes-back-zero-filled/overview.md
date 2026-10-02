+++
priority = "p2"
kind = "debug"
summary = "A partial `Location` still WRITES back zero-filled (the compare half is fixed)"
+++

# A partial `Location` still WRITES back zero-filled (the compare half is fixed)

The typed compare (2026-07-25 02:15 UTC) reads an omitted axis as the class default via the
`Actor.location_text` side-channel, so an `Engine.Camera` export `Location=(X=100,Y=200)`
(default `(X=-500,Y=-300,Z=300)`) now COMPARES as Z=300. What is left is the WRITE half: the
numeric triple `parse_t3d` fills is still `(100,200,0)`, so `actor add` of that raw editor T3D
stores `Z=0.000000` in the trunk — the actor really does move 300 uu. Fixing it needs a
class-defaults resolver at the INGEST verb (which has project context, unlike `parse_t3d`, which
is deliberately schema-free — it is also the trunk/stash/prefab/generator-snippet reader).
`Engine.Camera` is the only one of 1346 actor classes that defaults `Location` non-zero, so that
is the whole blast radius. Second, narrower remnant of the same side-channel: a mutation that
lands EXACTLY on the zero-filled triple (`actor move --to 100,200,0` on such an actor) still
parses back equal, so the omitted axis keeps reading as the class default — that one can only
ever cause a spurious ABORT, never a false pass. (2026-07-25 00:36 UTC; compare half fixed and
item re-scoped 2026-07-25 02:15 UTC.)
