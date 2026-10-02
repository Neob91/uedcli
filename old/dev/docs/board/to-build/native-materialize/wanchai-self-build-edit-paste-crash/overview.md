+++
priority = "p3"
kind = "debug"
summary = "build_ued_lit_golden.py's self-build of 06_HongKong_WanChai_Market.dx (1303-brush trunk) crashed UnrealEd 3/3 tries in this environment, always at the level's first EDIT PASTE right after MAP NEW. Same trunk/pipeline previously succeeded (the confirmed golden this session already relies on). Not root-caused; may be environment/load-specific, not a code regression."
+++

# Wanchai self-build EDIT PASTE crash reproducible (3/3) in this environment

Found while live-testing the new parity report tool
(`dev/docs/spikes/2026-08-31-native-parity-report/`) end to end against
`dev/games/substrate-deusex/Maps/06_HongKong_WanChai_Market.dx`. The tool's pipeline delegates the
self-build step to the existing, already-proven `build_ued_lit_golden.py`
(`dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/`) — no new driving code.

Three separate attempts (fresh ephemeral editor container each time) all crashed identically:

```
[obj-load] idle after ...
[map-new] idle after ...
error: UnrealEd has crashed — a 'Critical Error' dialog is open
...
uedcli.driver.DriverError: exec EDIT PASTE failed:
```

Always at the level's FIRST `EDIT PASTE` (the 1303-brush world-brush batch), right after `MAP NEW`
— before any `MAP REBUILD`/`LIGHT APPLY` step is even reached. Host resources were not the cause at
the time (`free -g`: 18G available; `uptime`: load 1.3-1.6 on 14 cores; no orphaned containers).

This is NOT a new regression the tool's own code introduced — `build_ued_lit_golden.py` is unmodified,
reused as-is (subprocess), and this exact trunk (`dev/games/trunks/tmp-wanchai-market`, matching
actor-for-actor: this tool's own fresh extraction also landed on 2288 actors, matching the historical
trunk's own count) previously built successfully — `_scratch/wanchai-relight-2026-08-29/golden.dx`
(provenance-confirmed in `native-materialize-findings.md`) is the proof, and this session's own
`light_spotcheck_wanchai.py` numbers (3418/4530) depend on that exact file still being good.

**Worked around, not root-caused:** to still verify the new tool's COMPARISON logic on real
Wanchai-scale data, `golden.dx` was manually seeded from that pre-existing, confirmed golden while
the TRUNK was this tool's own live extraction — result matched the ledger exactly (nodes/surfs/leaves
EXACT 11648/5284/3371, verts +74, points +16, vectors −8, lighting 3418/4530 (75.5%), shadow bits
98.79%), so the tool's own logic is not in question here — only whether a FRESH self-build of Wanchai
still works in this environment right now.

Not investigated further (out of scope for the tool-building task that found it): whether this is
transient (concurrent load from the ~11 other active worktrees/agents this session), a real
Wine/editor regression since 2026-08-29, or something about running from a NEW ephemeral project root
each time (`_scratch/uedcli-parity-cache/<hash>/trunk/`, freshly created `uedcli.toml` per run) vs the
durable `dev/games/trunks/tmp-wanchai-market` project the confirmed golden was built from. A future
attempt should retry a plain, unmodified `build_ued_lit_golden.py --trunk dev/games/trunks/tmp-wanchai-market
--out <path>` run directly (bypassing this tool entirely) to isolate whether the crash is
tool-invocation-specific or a real Wanchai-scale `EDIT PASTE` regression.
