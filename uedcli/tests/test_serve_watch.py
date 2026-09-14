"""`TrunkWatcher`'s debounce/coalesce logic (plan Task 4): N rapid changes within the debounce
window fire `on_change` exactly once, with the post-burst state — never once per raw change.
Plain `asyncio.run()` (no pytest-asyncio: not one of this project's declared deps)."""
from __future__ import annotations

import asyncio

from uedcli.serve.watch import TrunkWatcher


def test_rapid_burst_fires_on_change_exactly_once(tmp_path):
    async def _run():
        calls = []
        watcher = TrunkWatcher(tmp_path, lambda: calls.append(1), debounce_s=0.05)

        for _ in range(5):                          # a rapid burst well inside the debounce window
            watcher.notify()
            await asyncio.sleep(0.01)

        assert calls == []                          # not fired yet -- still inside the window
        await asyncio.sleep(0.1)                    # let the last timer settle
        assert calls == [1]                         # exactly once, not once per notify()

    asyncio.run(_run())


def test_two_separated_bursts_fire_twice():
    async def _run():
        calls = []
        watcher = TrunkWatcher("/nonexistent", lambda: calls.append(1), debounce_s=0.03)

        watcher.notify()
        await asyncio.sleep(0.06)
        assert calls == [1]

        watcher.notify()
        await asyncio.sleep(0.06)
        assert calls == [1, 1]                      # a second, separated burst fires again

    asyncio.run(_run())


def test_on_change_may_be_a_coroutine():
    async def _run():
        calls = []

        async def _on_change():
            calls.append(1)

        watcher = TrunkWatcher("/nonexistent", _on_change, debounce_s=0.02)
        watcher.notify()
        await asyncio.sleep(0.06)
        assert calls == [1]

    asyncio.run(_run())


def test_stop_cancels_a_pending_timer():
    async def _run():
        calls = []
        watcher = TrunkWatcher("/nonexistent", lambda: calls.append(1), debounce_s=0.02)
        watcher.notify()
        watcher.stop()
        await asyncio.sleep(0.06)
        assert calls == []

    asyncio.run(_run())
