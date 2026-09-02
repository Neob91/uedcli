+++
priority = "p1"
kind = "debug"
summary = "Rapid `actor duplicate`+`rotate` in a loop SILENTLY drops trunk writes"
+++

# Rapid `actor duplicate`+`rotate` in a loop SILENTLY drops trunk writes

A tight
back-to-back `duplicate`→`rotate` loop (building a ring of copies) produced **0 persisted actors** —
each `duplicate` returned an empty name to stdout and wrote nothing to the trunk; the identical
command run singly worked immediately after. Reads as a trunk delta-write race / non-atomic batch
mutation under fast successive writes. A retry + per-step count check worked around it. Silent
data-loss on a normal scripted loop is serious — repro: loop `dup=$(actor duplicate X --by 0,0,0
| tail -1); actor rotate "$dup" --by 0,8192,0 --pivot 0,0,0` ~7× fast. (Blind-build test, 2026-07-25.)
