+++
priority = "p?"
kind = "unknown"
summary = "Ghost playtester: offline reachability / walkability check (`level doctor --reach`)"
+++

# Ghost playtester: offline reachability / walkability check (`level doctor --reach`)

Simulate a walking pawn over the built BSP (collision radius + step height + gravity, flood-fill from
PlayerStart) and report: rooms unreachable on foot, doorways too narrow for the collision cylinder,
steps too tall, drops the player can't climb back out of, kill-pits. The tracked PlayerStart-overlap
check catches "can't spawn"; nothing catches "spawns fine but can't get into the keep" — today that
costs a full materialize + game boot + manual walk. Builds on `linecheck.rs`/the collision-topology
work (spike §60). (AI brainstorm 2026-07-16.)
