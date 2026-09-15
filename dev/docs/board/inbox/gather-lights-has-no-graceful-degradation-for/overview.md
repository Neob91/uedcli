+++
priority = "p3"
kind = "implement"
summary = "gather_lights has no graceful degradation for an unresolvable actor class"
+++

# gather_lights has no graceful degradation for an unresolvable actor class

Found reviewing `9ef77567` (`scene.py::_is_hidden_ed` fail-open fix). `build_scene_payload`
(`uedcli/serve/scene.py`) calls `build_scene` (`uedcli/preview_native.py`) before its own
`_is_hidden_ed` loop runs. `build_scene` unconditionally calls
`native.materialize.gather_lights(level, defaults=defaults)`, which resolves every actor's class
through the shared `defaults` memo with no guard — an unresolvable class raises `uprops.SchemaError`
straight out of the whole `/scene` request, before `_is_hidden_ed`'s own try/except (which only
protects its own resolution call) ever runs.

This means the CLI's own established convention — `cli/rendering.py::_is_hidden_ed`'s
fail-open-on-unresolvable-class disposition, now also used by `scene.py::_is_hidden_ed` — is NOT
what a `uedcli serve` `/scene` request actually gets when a level has one bad actor class: the
request still hard-fails in `gather_lights`, same as `level materialize`'s own no-fallback-default
rule (by design there, but not documented as a deliberate choice for the GUI scene endpoint).

Verified live: a level with an actor whose class doesn't resolve raises `SchemaError` from
`gather_lights`, never reaching `_is_hidden_ed`.

Not fixed here — `native.materialize.py` (`gather_lights` included) is governed by the
byte-parity campaign in `NATIVE-MATERIALIZE.md` with its own process; any fix needs to go through
that, or through a `scene.py`-side guard around the `build_scene` call instead (open design
question, not decided here).
