+++
priority = "p?"
kind = "debug"
summary = "The asset-catalog class arm needs four changes to actually close the decoration findings it cites"
+++

# The asset-catalog class arm needs four changes to actually close the decoration findings it cites

`spec.md` §6 motivates itself with exactly
the owner finding *"an agent can see a crate and still has to guess its footprint, and whether its
origin sits at the base or the centre"* (`spikes/levelbuild-friction/owner-reports.md` finding 7).
As specced it closes the *vertical* half only. From the 2026-07-26 review of that finding:

1. **Report the mesh bbox as SIGNED MESH-LOCAL EXTENTS, not a `W×D×H` size triple.** This is the
   load-bearing one. A size triple answers seating and says nothing about **facing** — but UE1
   collision is a rotation-invariant upright cylinder (`docs/leveldesign/general/actors.md`: "always
   upright regardless of the actor's rotation", and "a mesh's shape never collides"), so
   `CollisionRadius`/`CollisionHeight` carry *zero* facing information. The mesh-local bbox is the
   only place it can come from: as `x: -4..+4, y: -32..+32, z: -48..+16` the thin axis IS the mount
   normal and the asymmetry locates the origin relative to the mounting face. Same decoder output,
   different rendering of it. Owner finding 7's floating subway button is the horizontal half that
   a size triple cannot fix.
2. **`class preview` must state its camera azimuth in mesh-local rotator units.** The `--out` naming
   already carries an angle suffix (`deusexdeco-barstool-iso.png`), but a picture of a wall lamp does
   not say *which yaw* points it at the player — so the agent still guesses, which is how a flat
   light ends up 90° off. A field on the row, no new rendering. Stretch, same rasterizer:
   `class preview --rotate P,Y,R` renders a candidate pose in ~254 ms (the spec's own measured cost)
   and replaces a ~2.5-min `--game` batch as the pose oracle.
3. **Mount convention belongs in the classification shards, and is then paid once.** "Wall-mounted,
   face on local +X, flush at wall+2" cannot be derived, and §0 forbids the tool inferring it — but
   an LLM reading the thumbnail plus the extents can write it, which is the loop §5a already
   describes. §3b makes it a git-committed per-project shard with union-merge `tags`, so the DX
   decoration corpus is classified **once** and every later level inherits correct mounting.
   `texture_catalog._norm_tags` only strips and lowercases, so a `mount:wall` / `faces:+x` namespace
   survives intact — but nothing reserves or validates it, so the convention needs writing down.
4. **§8 "What the catalog unlocks" undersells the spec, and §13 sequences by value.** It claims only
   ObjectProperty-ref validation, then honestly downgrades even that ("may not need the catalog at
   all"). The strongest available claim is missing: *props stopped sinking into floors, floating off
   walls and facing the wrong way — measured on three shipped levels.* The class arm is already #2 in
   §13 and needs no new decoders (§9's last bullet), so the placement facts are the cheapest
   high-value slice in the spec and the spec does not say so.

**Honest limit:** this fixes the *facts* half. It cannot tell you a button belongs on *that* wall —
that is intent, and stays with the independent-reviewer question (owner-reports.md open question 1).
*(2026-07-27.)*
