+++
priority = "p2"
kind = "owner-question"
summary = "Where does builder input validation belong: the CLI or the builders library?"
+++

# Where does builder input validation belong: the CLI or the builders library?

Item #10.4 put the positive-dimension guard in `dispatch._POSITIVE_BUILD_DIMS` /
`_check_positive_build_dims` (CLI layer) because the spec asked for "one exit-2 message shape
naming the offending FLAG", and only the CLI knows flag spellings. Consequence a round-1 reviewer
measured: the *library* is still unguarded — `builders.cube(-32.0, 64, 64)` and
`builders.staircase(4, -32.0, 16, 64)` both return happy inside-out brushes, silently. Meanwhile
the SIBLING constraints of the same family (`steps >= 1`, `sides >= 3`,
`0 < degrees_per_step < 180`, `inner_radius > 0`) all live in `builders.py` and raise
`GeometryError`. So one class of builder input is validated at the CLI and a neighbouring class at
the library, and the table has to mirror argparse `dest` names into `dispatch.py` to bridge them.
Non-CLI callers at risk: the native materialize path, `stash`/`prefab` code if it ever grows a
builder route, and #12's `extrude`/`revolve` helpers. Options: (a) keep as is and accept the split;
(b) duplicate the check in `builders.py` as a `GeometryError` so both doors are guarded, accepting
two messages for one condition; (c) move it wholly into `builders.py` and lose the flag-named
message the spec asked for. **This was not decided by the spec and is not the AI's call.**
