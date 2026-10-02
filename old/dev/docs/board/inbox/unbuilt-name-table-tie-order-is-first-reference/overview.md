+++
priority = "p?"
kind = "unknown"
summary = "unbuilt name-table tie order is first-reference intern order, not generative yet (owner-excluded from parity bar)"
+++

# unbuilt name-table tie order is first-reference intern order, not generative yet (owner-excluded from parity bar)

The unbuilt writer's generative save-table model (`uedcli/native/saveorder.py`) reproduces UED22
import tables byte-exactly on every golden, and name tables exactly on the three toy levels. On
UNATCO/OceanLab the name table differs only within SAME-COUNT ties: map-time actor names intern in
first-REFERENCE order (an actor name referenced by an earlier actor's property interns early), not
spawn order, and the unstable MSVC qsort then propagates the tie order. Owner-excluded from the
parity bar ("name-table tail order"), so recorded rather than forced. Closing it generatively
needs the first-reference walk modeled over property VALUES during import — the trace evidence is
in `dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness/unatco_maps.dump.txt`.
