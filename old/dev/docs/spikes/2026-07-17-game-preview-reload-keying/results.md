# SP-R — reload-keying + warm-delivery GATE: results

**Date:** 2026-07-17 (live, `uedcli-game` image, DeusEx substrate).
**Harness:** [`spike_reload.py`](spike_reload.py) (main), [`extend_namesize.py`](extend_namesize.py)
(NAME_SIZE threshold). Raw log: `_scratch/spike-reload/spike.log` (gitignored).
**Spec gated:** board item `warm-game-remnants` §8 (SP-R), §5.3 (the gate).

## What was tested and why
The warm-container design delivers a changed level into an ALREADY-BOOTED game by dropping a
uniquely-named map into the Maps dir **after boot** (as a **symlink**) and `open`ing it — repeatedly,
across one long-lived container. The shipped `--game` tier only ever proved ONE post-boot delivery of
a **real `docker cp`'d file** in a **fresh** container. Round-4 review flagged the untested deltas as
the one real exposure:
- (b) THE GATE — does an **Nth `open`** of a **post-boot symlinked** stem resolve in a **reused**
  container? (If not → Plan B: `docker cp` a real file / reboot-per-map-change.)
- (a) does a fresh unique name always load fresh content (FName-not-GUID keying, no resident reuse)?
- (c) NAME_SIZE — does a long stem truncate silently and collide (R4-B F1's HIGH)?
- (d) does RSS grow monotonically (permanent FName/linker leak → the reboot bound)?
- (e) does a mission map's on-enter conversation taint the frame (the driver-abort question)?

Method: boot ONE container; per delivery `docker cp` a retail map into an in-container pool dir, then
`ln -sf` it into `/work/dx/Maps/<unique-stem>.dx` **post-boot**, and drive the shipped 3-phase
`TravelToLevel` handshake. `GetCurrentLevelName` (= `PlayerPawn.GetURLMap()`, the file stem) is the
resolution signal; screenshot-hash compares detect content aliasing; `docker stats` tracks RSS.

## Results — the gate is GREEN

| # | Test | Result |
|---|------|--------|
| **b** | **5 post-boot SYMLINKED travels, Nth-open, one reused container** | ✅ **ALL resolved** — `GetURLMap` == the exact unique stem every time (travels #1–#5). The symlink form + repeated open in a warm container works. **No Plan B needed.** |
| **a** | fresh unique name → fresh content | ✅ Each stem loaded its own map (Entry→DX→Endgame shots differ; DX shows the "EIDOS INTERACTIVE" splash, the mission map shows its brick room). |
| **a′** | identical bytes under a NEW name | ✅ `materialized__entry__dddd…` (same bytes as travel #1's Entry) resolved fresh — a new name always gets a fresh linker. |
| **c** | NAME_SIZE collision (differ only past char 63, DIFFERENT content) | ✅ **No collision at 70 chars** — `shotA≠shotB` (Entry vs DX). A 66-char stem also loads. Contradicts a hard 63-char silent-truncation cap. Threshold probe: **_(pending extend_namesize.py)_**. |
| **d** | RSS across 11 travels | ✅ **Essentially flat: 386 → 400 → 393 → 393 → 414 MiB.** No monotonic growth — the permanent-leak concern does not manifest over a realistic session; levels are unloaded/GC'd on travel. |
| **e** | mission map (`08_NYC_Bar`) frame, no driver abort | ✅ **Clean posed frame** — brick room, lit, no conversation camera / HUD / datalink overlay. Confirms the conversation-abort is NOT needed (matches the 10 UNATCO shots). |

Boot: 42 s to READY. Each travel ~8 s. Whole main spike ~2 min.

## Verdicts folded into the spec
1. **§5.3 gate → CONFIRMED live.** Post-boot Nth-`open` + symlink resolution works; the symlink
   delivery form (D4) is validated; Plan B stays documented but unneeded.
2. **§4.6 / Claim 6 memory → downgraded.** RSS flat over 11 travels ⇒ minimal leak; the
   container-scoped reboot bound (N=40) is cheap insurance, not a tight constraint.
3. **D5 / R4-B F1 NAME_SIZE → the 63-char silent-truncation collision did NOT reproduce at 70.**
   Production stems are ≤~46 chars (`materialized__<level>__<hash12>` + short nonce), far below any
   observed threshold; the loud-error length guard is retained as insurance. Threshold pinned below.
4. **§1 / §9 conversation abort → CONFIRMED unnecessary.** Not a build item.

## NAME_SIZE collision threshold (extend_namesize.py)
Entry-vs-DX pairs (DIFFERENT content) differing ONLY past char 63:

| L (chars) | a loads | b loads | shot A | shot B | reading |
|---|---|---|---|---|---|
| 80 | ✅ | ✅ | `f68b…` | `f37b…` | distinct content — **no collision** |
| 120 | ✅ | ✅ | `f68b…` | `b634…` | **no collision** |
| 180 | ✅ | ✅ | `f68b…` | `2ea2…` | **no collision** |
| 250 | ❌ | ❌ | `db35…` | `db35…` | **both FAIL to load** — `open` doesn't resolve; the equal hashes are a false "collision" (pawn stayed on the prior level). A **LOUD** failure (`resolved=False`), not a silent stale-serve. |

**Verdict:** the R4-B F1 fear — a *silent* 63-char truncation that serves stale content — **does NOT
reproduce at any length**. Map names resolve correctly up to ≥180 chars, and an over-long name (~250)
**fails loudly** (the travel never confirms). There is no silent-stale window. Combined with
production stems being ≤~46 chars, the spec's loud length-error guard is belt-and-suspenders on top
of the engine's own loud failure — the "63 usable, silent truncation" claim is **not confirmed** for
DeusEx map URLs.
