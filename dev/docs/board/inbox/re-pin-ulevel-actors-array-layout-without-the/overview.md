+++
priority = "p3"
kind = "chore"
summary = "Re-pin ULevel Actors-array layout without the deleted native writer"
+++

# Re-pin ULevel Actors-array layout without the deleted native writer

Removing the native-materialize path deleted `native/level_write.py`, which took with it
`test_engine_facts.py::test_level_actors_array_is_int_num_max_then_compact_refs`. That test
pinned the `Engine.Level` Actors-array on-disk layout (`[i32 Num][i32 Max]` then `Num` signed
FCompactIndex refs, ref 0 = null slot, Actors[0] = LevelInfo) by round-tripping the encode
mirror `write_level_body` through the production `upackage` reader.

That layout is still load-bearing: `mapimport` (`level import`) DECODES it. The fact is now
pinned only on the read side (if at all), not by a committed writer round-trip.

Re-pin it against a committed fixture or `mapimport`'s own decode of a small known body, so a
layout drift still trips a test — without resurrecting the deleted writer.
