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
        pending timer, so only the timer started by the LAST call in the burst ever fires."""
        if self._timer_task is not None:
            self._timer_task.cancel()
        self._timer_task = asyncio.ensure_future(self._fire_after_quiet())

    async def _fire_after_quiet(self) -> None:
        await asyncio.sleep(self.debounce_s)
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
