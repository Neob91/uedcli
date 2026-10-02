"""Trunk file-watcher for `uedcli serve` (plan Task 4): debounced, coalescing — a rapid burst of
writes (many verbs in one AI task) fires `on_change` exactly ONCE, after the burst settles, not
once per verb (spec, "Debounce / coalesce semantics"). `TrunkWatcher` owns only the "when"; the
caller decides "what" (re-fetch the scene, snapshot, broadcast a WS reload — Slice 1 wires the WS
broadcast in `app.py`)."""
from __future__ import annotations

import asyncio
from pathlib import Path


class TrunkWatcher:
    """Watches `level_dir` for filesystem changes and calls `on_change()` once per settled
    write-burst. `notify()` is the debounce primitive — call it once per raw change; N calls within
    `debounce_s` of each other (re)start one timer, so only the LAST one's timer ever fires. Real
    filesystem watching (`run()`, via `watchfiles.awatch`) just feeds `notify()`; the debounce logic
    itself doesn't depend on it, so it's testable without touching a real filesystem."""

    def __init__(self, level_dir, on_change, *, debounce_s: float = 0.4):
        self.level_dir = Path(level_dir)
        self.on_change = on_change
        self.debounce_s = debounce_s
        self._timer_task: asyncio.Task | None = None
        self._watch_task: asyncio.Task | None = None

    def notify(self) -> None:
        """Register one raw change and (re)start the debounce timer. A burst of calls inside
        `debounce_s` of each other collapses to one `on_change` — each call cancels the previous
        PENDING timer, so only the timer started by the LAST call in the burst ever fires.
        `_timer_task` only ever holds the debounce-SLEEP phase (`_wait_then_dispatch`) — once that
        elapses, the actual `on_change()` call runs as its own, untracked task
        (`_dispatch`, spawned by `_wait_then_dispatch`), so a `notify()` arriving while `on_change()`
        is already in flight (e.g. mid `await ws.send_json`) cancels only a fresh pending timer, never
        the broadcast itself (review finding: this used to `.cancel()` the SAME task that ran
        `on_change()`, so a rapid notify during an in-flight broadcast silently killed it)."""
        if self._timer_task is not None:
            self._timer_task.cancel()
        self._timer_task = asyncio.ensure_future(self._wait_then_dispatch())

    async def _wait_then_dispatch(self) -> None:
        await asyncio.sleep(self.debounce_s)
        asyncio.ensure_future(self._dispatch())

    async def _dispatch(self) -> None:
        result = self.on_change()
        if asyncio.iscoroutine(result):
            await result

    async def run(self) -> None:
        """Watch `level_dir` for real until cancelled, calling `notify()` per raw batch
        `watchfiles.awatch` reports. `watchfiles`'s own internal batching is irrelevant here — our
        `notify()`/`debounce_s` timer is what defines "settled", independent of it."""
        import watchfiles
        async for _changes in watchfiles.awatch(self.level_dir):
            self.notify()

    @property
    def started(self) -> bool:
        """Whether `start()` has been called and `stop()` hasn't since -- lets a caller that may
        see this watcher more than once (e.g. `app.py`'s `/ws`, reached on every connect) check
        before calling `start()` again: `start()` itself is NOT idempotent, since calling it twice
        would replace `_watch_task` and leak the old one."""
        return self._watch_task is not None

    def start(self) -> asyncio.Task:
        self._watch_task = asyncio.ensure_future(self.run())
        return self._watch_task

    def stop(self) -> None:
        if self._watch_task is not None:
            self._watch_task.cancel()
            self._watch_task = None
        if self._timer_task is not None:
            self._timer_task.cancel()
            self._timer_task = None
