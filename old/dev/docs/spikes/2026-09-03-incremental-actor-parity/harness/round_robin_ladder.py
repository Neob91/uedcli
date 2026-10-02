#!/usr/bin/env python3
"""Round-robin ladder driver (session-local, not the canonical harness): always advances whichever
tracked level has the SMALLEST absolute last_pass_n by one N (lower-N levels get priority). Starts each level at
max(1, known_ceiling-4) -- re-verifies only the last 5 previously-known-good N's, not the whole
ladder from 1 -- then keeps pushing past the ceiling. On a real gate FAIL, marks that level blocked
(state persisted to JSON) and moves on; never stops the whole run for one level's bail.

Run from the repo root. LEVELS below has this session's absolute map paths (2026-09-16 sandbox) --
update them for a different host/checkout before reusing. Meant to run under a supervisor loop that
restarts it on exit (a bail, an infra crash, a host reboot all just exit the process); state is
fully persisted to STATE_PATH, so a restart resumes exactly where it left off. Pair with a Monitor on
LOG_PATH filtered to "FAIL|ALL LEVELS BLOCKED" to get notified without polling."""
from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

HERE = Path("dev/docs/spikes/2026-09-03-incremental-actor-parity/harness").resolve()
sys.path.insert(0, str(HERE))
import actor_parity as ap   # noqa: E402
import parity_gate as pg    # noqa: E402
from uedcli import trunk    # noqa: E402

STATE_PATH = Path("_scratch/round_robin_state.json").resolve()
LOG_PATH = Path("_scratch/round_robin_ladder.log").resolve()

LEVELS = {
    "unatco":   ("/workspace/uedcli/dev/games/substrate-deusex/Maps/03_NYC_UNATCOHQ.dx", 242),
    "wanchai":  ("/workspace/uedcli/dev/games/substrate-deusex/Maps/06_HongKong_WanChai_Market.dx", 58),
    "bar":      ("/workspace/uedcli/dev/games/substrate-deusex/Maps/02_NYC_Bar.dx", 152),
    "island":   ("/workspace/uedcli/dev/games/substrate-deusex/Maps/01_NYC_UNATCOIsland.dx", 352),
    "oceanlab": ("/workspace/uedcli/dev/games/substrate-deusex/Maps/14_OceanLab_Lab.dx", 202),
}


@dataclass
class LevelState:
    slug: str
    dx: str
    name: str
    total: int
    known_ceiling: int
    next_n: int
    last_pass_n: int
    blocked: bool = False
    fail_reason: str = ""


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def load_or_init_states() -> dict[str, LevelState]:
    if STATE_PATH.exists():
        raw = json.loads(STATE_PATH.read_text())
        return {slug: LevelState(**v) for slug, v in raw.items()}
    states = {}
    for slug, (dx_str, ceiling) in LEVELS.items():
        dx = Path(dx_str).resolve()
        full_trunk, name = ap._resolve_trunk(dx, "deusex")
        total = len(trunk.read_level(full_trunk)[0].order)
        start = max(1, ceiling - 4)
        states[slug] = LevelState(slug=slug, dx=str(dx), name=name, total=total,
                                   known_ceiling=ceiling, next_n=start, last_pass_n=start - 1)
    save_states(states)
    return states


def save_states(states: dict[str, LevelState]) -> None:
    STATE_PATH.write_text(json.dumps({s: asdict(st) for s, st in states.items()}, indent=2))


def try_n(st: LevelState, n: int, timeout: float = 3600.0):
    full_trunk, _name = ap._resolve_trunk(Path(st.dx), "deusex")
    subset = ap.make_subset(full_trunk, st.name, n)
    native = ap.build_native(subset, st.name, n)
    ref = ap.ref_path(st.name, n)
    if not ap.ref_is_reusable(st.name, n):
        ref = ap.build_ref(subset, st.name, n, timeout=timeout)
    ok, fails = pg.gate(str(native), str(ref))
    native.unlink(missing_ok=True)
    shutil.rmtree(subset.parent.parent, ignore_errors=True)
    return ok, (fails[0] if fails else None)


def main() -> int:
    states = load_or_init_states()
    log(f"levels: {[(s, st.next_n, st.total, st.known_ceiling) for s, st in states.items()]}")
    while True:
        active = [st for st in states.values() if not st.blocked]
        if not active:
            log("ALL LEVELS BLOCKED -- stopping. Fix a bail and clear its `blocked` flag to resume.")
            return 1
        st = min(active, key=lambda s: s.last_pass_n)  # lowest ABSOLUTE N gets priority
        n = st.next_n
        ok, reason = False, None
        for attempt in range(3):
            try:
                ok, reason = try_n(st, n)
                break
            except (OSError, ConnectionError) as e:
                # Transient host contention (EMFILE, docker daemon blips) -- not a real gate
                # verdict, so retry a couple times with backoff instead of blocking the level.
                reason = f"EXCEPTION: {e!r}"
                if attempt < 2:
                    log(f"[{st.slug}] N={n}/{st.total} infra error (attempt {attempt + 1}/3): "
                        f"{reason} -- retrying in 15s")
                    time.sleep(15)
            except Exception as e:  # noqa: BLE001 -- anything else blocks this level like a FAIL
                ok, reason = False, f"EXCEPTION: {e!r}"
                break
        if ok:
            st.last_pass_n = n
            st.next_n = n + 1
            past = " (PAST known ceiling)" if n > st.known_ceiling else ""
            log(f"[{st.slug}] N={n}/{st.total} PASS{past}")
        else:
            st.blocked = True
            st.fail_reason = reason or "<no detail>"
            log(f"[{st.slug}] N={n}/{st.total} FAIL -- {st.fail_reason}")
        save_states(states)


if __name__ == "__main__":
    sys.exit(main())
