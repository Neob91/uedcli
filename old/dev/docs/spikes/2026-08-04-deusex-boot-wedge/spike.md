# Spike: why retail v68 `DeusEx.exe` wedges at boot on this host (2026-08-04)

**Question.** Root-cause why `DeusEx.exe` wedges at the "Deus Ex (Starting)" splash on this box —
OOM, deadlock, or CPU-detect — and find a config that boots it reliably (which unblocks the engine
render path).

## TL;DR

- **Root cause = DEADLOCK, not OOM, not CPU-detect.** At the wedge every thread is asleep at 0% CPU:
  `DeusEx.exe` main thread blocked in `pipe_read` (the wineserver reply pipe), `wineserver64` idle in
  `do_epoll_wait`, all wine helper threads in `futex_wait_queue`. `oom_kill=0` — the process is never
  killed. `pgmajfault` is **flat** during the wedge (~1/s), not the runaway churn of active OOM
  thrash. The `DeusEx.log` is frozen at the 21-line CPU-detect banner. This is a lost-wakeup: the game
  sent a wineserver request and blocks reading the reply that never wakes it.
- **Trigger = memory pressure at the 6 GiB cap.** A single **fresh** boot's working set (arm64 qemu
  translating amd64 wine translating x86 DeusEx, plus the mmap'd packages) fills the container to
  **5.9–6.3 GiB / 6.0 GiB cap (98%)**, driving heavy reclaim/refault of executable pages
  (`memory.events max` climbs to ~68 700; ~905 000 major faults during load). That refault churn under
  emulation is what stalls the startup IPC into the lost-wakeup. It is intrinsic to one boot, not an
  artifact of a reused container.
- **The documented "esync-only `pipe_read` lost-wakeup, fixable by fsync on kernel 5.16+" theory is
  wrong on this box.** Sync mode is irrelevant: esync+fsync, fsync-only, and pure server-side sync all
  wedge **100%** (0/3 each). Single-CPU pinning also wedges (0/3). See the correction below.
- **No config booted (0/12 across sync + cpuset).** The only lever that would plausibly fix a
  memory-pressure deadlock — more memory / less pressure — is **unavailable here**: the 6 GiB cap is
  unraisable and `drop_caches` is denied (see "Environment"). So the render path stays blocked on this
  box until it has memory headroom. The harness is sound (it rendered on 2026-08-03, ~12 s link); that
  was a lower-pressure moment.

## Decisive evidence (fresh container, `WINEESYNC=1 WINEFSYNC=1`, t=98 s)

```
mem.current=6342344704 mem.max=6442450944          # 98.4% of the 6 GiB cap
mem.events: ... max 68715 oom 0 oom_kill 0 ...      # heavy reclaim, ZERO oom-kill
pgfault=540346613 pgmajfault=905578                  # majflt FLAT vs prior tick (not thrashing)
loglines=21                                          # frozen at the CPU-detect banner
  DeusEx.exe   tid=305 state=S wchan=pipe_read         cputicks=88   # static — blocked on wineserver reply
  wine         tid=329 state=S wchan=futex_wait_queue  cputicks=0
  wineserver64 tid=347 state=S wchan=do_epoll_wait     cputicks=186  # idle, request never arrives
```
No thread in state `R`; total active cputicks over the final interval = **0**. Full log:
`evidence/baseline-wedge.sample.log`, summary `evidence/baseline-analysis.txt`.

OOM vs deadlock, decided by the numbers: OOM would show a rising `oom_kill`/`oom` count or a thread
pinned in `R` with major-faults climbing; instead `oom_kill=0`, faults flat, all threads parked in
wait wchans → **deadlock**. CPU-detect ruled out: the banner is *printed* (the RDTSC loop already ran);
the freeze is after it, in the wineserver handshake, not inside CPU detection.

## Mitigation matrix — `evidence/matrix.result` (N=3 each, warm reused container)

| Config | Knobs | LINK |
|--------------|------------------------------------------|------|
| esync-fsync  | `WINEESYNC=1 WINEFSYNC=1` (current default) | 0/3 |
| fsync-only   | `WINEESYNC=0 WINEFSYNC=1`                    | 0/3 |
| server-side  | `WINEESYNC=0 WINEFSYNC=0`                    | 0/3 |
| cpuset1      | default sync, `taskset -c 0`                | 0/3 |

Every launch froze at `log=21`. Sync mode and CPU count do not move the result, which is why the cause
is memory-pressure timing, not a sync-primitive bug. (`taskset -c 0` confirmed working — all wine/game
threads showed `psr=0`.)

## Environment (qemu / cap specifics)

- **6 GiB cap is unraisable from here.** `docker run --memory=8g|12g|20g` all yield container
  `memory.max = 6442450944` exactly. `docker info` reports `Cgroup Driver: none`, so `--memory` writes
  no cgroup limit; the 6 GiB comes from a parent slice in the rootless daemon VM. A `--privileged`
  container sees `/proc/1/cgroup = 0::/` and `nsenter` into the VM's mount ns is denied — the VM is not
  reachable to reconfigure. `drop_caches` is denied (`/proc/sys/vm/drop_caches` read-only, rootless).
- **binfmt interpreter is preloaded (F flag) from the daemon VM** — no `qemu-*` binary inside the
  container, so its version is not readable here. `WINEARCH=win32` ⇒ the guest is x86-32, so the
  interpreter is **qemu-i386** (x86→arm64), not qemu-x86_64.
- **mttcg is not a qemu-user knob.** qemu-user runs one host thread per guest thread with no
  system-mode single-threaded-TCG toggle; `taskset -c 0` is the serialization test, and it still
  wedged — so this is not a fixable multi-core memory-ordering race either.
- **Kernel is 6.12.76 and HAS `futex_waitv`** (fsync-capable) — contradicting the stale "5.15 kernel,
  WINEFSYNC inert" note in `uedcli/game/game-entrypoint.sh`. fsync engages here and still wedges.

## Correction to the codebase (filed to the board)

`uedcli/game/game-entrypoint.sh` (and the generic-hud spike) attribute the wedge to an **esync-specific
`pipe_read` lost-wakeup** curable by fsync on a 5.16+ kernel. On this host the kernel is 6.12 (fsync
active) and **all three sync modes wedge 100%** — the wedge is memory-pressure-triggered and
sync-independent. The `pipe_read` block is the wineserver request pipe, which exists in every sync
mode. The entrypoint's fast-relaunch loop still helps only because it re-rolls the timing race; nothing
in the sync configuration prevents the deadlock. Board item records this so the comment can be fixed
with the owner's approval.

## Not pinned with a unit test

The finding is an environmental/timing root cause, not a stable fact about the binary or a golden, so
per `rules/spikes.md` no regression test is added. The re-runnable harness + captured evidence are the
committed artifact.

## Files

- `harness/instrument_boot.sh` — single-launch boot with 2 s sampling (memory.events / stat + per-thread
  State/wchan/cputicks); classifies link vs wedge.
- `harness/run_trial.sh` — host orchestrator: fresh container per trial, stages inputs, runs the
  instrument, copies `sample.log` out. Supports `DOCKER_MEM` / `DOCKER_CPUSET` cap tests.
- `harness/matrix_incontainer.sh` — the sync/cpuset matrix inside one warm container (wineboot once,
  many launches). `harness/matrix.sh` — the fresh-container variant.
- `harness/analyze_sample.py` — summarizes a sample log to the OOM-vs-deadlock verdict.
- `evidence/` — `baseline-wedge.sample.log`, `baseline-analysis.txt`, `matrix.result`.
