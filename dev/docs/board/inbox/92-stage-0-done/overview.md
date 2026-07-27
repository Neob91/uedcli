+++
priority = "p2"
kind = "owner-question"
summary = "§92 STAGE 0 done — parity BASIS corrected to bare `MAP REBUILD` (GOOD); a PROVISIONAL default change to confirm"
+++

# §92 STAGE 0 done — parity BASIS corrected to bare `MAP REBUILD` (GOOD); a PROVISIONAL default change to confirm

Built the `MAP REBUILD;BSP REBUILD GOOD OPTGEOM ZONES`
golden (editor did NOT wedge — the two prior wedges were a false-idle artifact; fix = generous
barrier `--quiet-reads 30`, now the required setting for BSP-REBUILD goldens at UNATCO scale).
**Measured finding overturning the plan's hypothesis:** `BSP REBUILD GOOD` re-partitions to **7273
nodes — MORE than OPTIMAL (6859)**, so it does NOT reproduce native's csgRebuild partition (§92 §2
option (b) REJECTED). native's TRUE node basis is the **bare `MAP REBUILD` golden (6314)** →
native **+111 nodes (+1.76%)**, +82 surfs, +146 vectors (surfs/vectors invariant to all 4 rebuild
paths). **PROVISIONAL CALL I made (please confirm):** changed `build_ued_golden.py`'s
`--rebuild-cmd` DEFAULT from `OPTIMAL OPTGEOM ZONES` to a bare `MAP REBUILD` (native's node/surf/
vector basis) — the clean-leaf `GOOD OPTGEOM ZONES` variant is now opt-in. This means the two
parity bases are SEPARATE (no single rebuild path gives both native's node partition AND a clean
refs/leaf==1.0 leaf array); `bsp_health_check.py` still flags a bare golden's stale leaves (correct
— means "don't use its LEAVES", not "its nodes are wrong"). If you'd rather the default stay a
clean-leaf ZONES golden, say so.
