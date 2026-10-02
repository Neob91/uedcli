+++
priority = "p2"
kind = "implement"
summary = "`event link` / `unlink` — AUTHOR the Tag↔Event wiring `event graph` only reads"
+++

# `event link` / `unlink` — AUTHOR the Tag↔Event wiring `event graph` only reads

`event graph` (built 2026-07-18) lints trigger wiring (edge A→B when `A.Event == B.Tag`) but no verb SETS it. Spec `event link <source> <target>` (set `source.Event := target.Tag`, minting a Tag if the target lacks one) + `event unlink`, model-side over the trunk — the natural completion of event-graph. Consider multi-event array props (Dispatcher `OutEvents`, Counter). (Surfaced 2026-07-19 usability probe.)
