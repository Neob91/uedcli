+++
priority = "p1"
kind = "bug"
summary = "docker stats CPUPerc reads ~50-58% for a FULLY IDLE editor container on this box (in-container top shows 0.0% across all processes; observed on the 21h-idle stub too, 2026-09-02). build_ued_golden._wait_idle's <30%-for-8-reads barrier can therefore NEVER fire, so every editor build/golden rebuild times out at 1800s — very likely the real mechanism behind this session's corpus-sweep obj-load TimeoutErrors, previously attributed to concurrency. Workaround exists; _wait_idle itself not fixed."
+++

# `docker stats` CPU% is bogus on this box; `_wait_idle` can never see idle

Observed live 2026-09-02 (pass1-trace round): `docker stats --no-stream --format {{.CPUPerc}}` on
`uned-stub-310165e9` (idle 21h) returns 54-58% while `docker exec ... top -b -n 1` inside the same
container shows 0.0% CPU for every process and 87.5% idle. Every uned container on the box reads
~50% regardless of actual activity (rootless dockerd/linuxkit sampling artifact; not diagnosed
further).

Consequence: `dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py::_wait_idle`
(threshold 30%, 8 consecutive quiet reads) never fires, so every `MAP LOAD`/`MAP REBUILD`/obj-load
wait runs to its TimeoutError. The 2026-09-02 sweep failures ("editor not idle after 1800s
[obj-load]", attributed to 3+ concurrency at 87-96% CPU) are consistent with THIS instead — the
UNATCO golden cache entry died the same way at concurrency 1-2.

Workaround (proven, same round): wait on the editor PROCESS instead — read `utime+stime` from
`/proc/<pid>/stat` of `unrealed.exe` inside the container, twice over 1.5s; idle editor reads
~0-6%. Implemented as `wait_editor_idle` in
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/pass1_brush_trace_unatco.py`; both
pass1 live captures succeeded with it on a box where the `docker stats` barrier had just produced
an empty capture.

Not done: porting the fix into `build_ued_golden.py`/`build_ued_lit_golden.py` (shared by the
sweep and every golden rebuild) — that harness is in active concurrent use this session.
