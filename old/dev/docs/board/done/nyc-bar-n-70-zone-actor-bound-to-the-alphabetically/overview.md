+++
priority = "p1"
kind = "debug"
summary = "DONE — resolve_zone_actors walked the name-keyed actors dict, so ZoneInfo17 beat ZoneInfo5 to the zone they share. Walk Level.Actors order instead. NYC_Bar N=70 byte-exact."
+++

# NYC_Bar N=70 — the zone bound to the alphabetically-first ZoneInfo

52 gate failures at N=70, all one token: the world `Model`'s `Zones[1].ZoneActor` was `ZoneInfo17`
in native and `ZoneInfo5` in UED22, and every actor's `Region.Zone` followed it (both ZoneInfos are
in zone 1 — `Region` iLeaf 8 and 11, `ZoneNumber` 1 on both sides, so the zoning descent agreed).

`materialize.resolve_zone_actors` took "first actor wins per zone" over `level.actors.items()`.
That dict is keyed by actor name and iterates alphabetically, which puts `ZoneInfo17` at position 68
and `ZoneInfo5` at 69 — the reverse of the trunk order (6 and 24). The editor walks `Level->Actors`.
Fixed by iterating `level.order`. Regression:
`uedcli/tests/test_native_roundtrip.py::test_zone_actor_binding_follows_actor_order_not_the_name_keyed_dict`.

Only visible with two ZoneInfos sharing a zone, which is why it survived to N=70.
