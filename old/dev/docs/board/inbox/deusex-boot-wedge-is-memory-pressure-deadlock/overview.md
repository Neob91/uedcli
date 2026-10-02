+++
priority = "p2"
kind = "debug"
summary = "DeusEx boot wedge is memory-pressure deadlock, not esync — game-entrypoint.sh comment is stale"
+++

# DeusEx boot wedge is memory-pressure deadlock, not esync — game-entrypoint.sh comment is stale

Spike `dev/docs/spikes/2026-08-04-deusex-boot-wedge/` root-caused the `DeusEx.exe` boot wedge on this
host. Findings that touch tracked comments/behavior (need owner yes to act):

- The wedge is a **deadlock** (all threads asleep at 0% CPU; `DeusEx.exe` main in `pipe_read`,
  `wineserver64` in `do_epoll_wait`; `oom_kill=0`; major-faults flat), **triggered by memory pressure**:
  one fresh boot fills the 6 GiB container cap to 98% (arm64 qemu → amd64 wine → x86 DeusEx working set
  + mmap'd packages), and the reclaim/refault churn stalls the wineserver startup handshake into a
  lost-wakeup.
- **Sync mode is irrelevant**: esync+fsync, fsync-only, and pure server-side sync all wedge 100%
  (0/3 each); `taskset -c 0` also 0/3. So `uedcli/game/game-entrypoint.sh`'s comment attributing the
  wedge to an **esync-specific `pipe_read` lost-wakeup fixable by fsync on a 5.16+ kernel** is wrong
  here — this box is kernel 6.12 with `futex_waitv` present (fsync active) and still wedges. The
  fast-relaunch loop helps only by re-rolling the timing race, not by any sync setting.
- **The 6 GiB cap is unraisable from this environment** (`--memory` ineffective under
  `Cgroup Driver: none`; parent slice in the unreachable daemon VM; `drop_caches` denied). So the
  `--game` render path stays blocked on this box until it has memory headroom; it is not a harness bug
  (rendered fine 2026-08-03).

Proposed (await owner): fix the stale sync-theory comment in `game-entrypoint.sh` to say the wedge is
memory-pressure-triggered and sync-independent; and decide whether `preview --game` should hard-fail
early with a clear "needs >6 GiB, this container is capped at 6 GiB" message instead of looping the
relaunch until the guard times out.
