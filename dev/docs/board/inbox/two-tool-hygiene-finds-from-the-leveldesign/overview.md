+++
priority = "p3"
kind = "chore"
summary = "two tool-hygiene finds from the leveldesign docs re-review` — (a) `uedcli-native/src/ bspcsg.rs:44` and `:1172` carry stale `NumPolys/10` comments that contradi"
+++

# two tool-hygiene finds from the leveldesign docs re-review` — (a) `uedcli-native/src/ bspcsg.rs:44` and `:1172` carry stale `NumPolys/10` comments that contradi

two tool-hygiene finds from the leveldesign docs re-review` — (a) `uedcli-native/src/
bspcsg.rs:44` and `:1172` carry stale `NumPolys/10` comments that contradict the code two lines below
(the stride is `NumPolys/20` for GOOD — the `*0x66666667 >> 35` idiom); fix the comments. (b) running
`uedcli` outside a project prints stray debug lines to the terminal (`plaintext False`, `swingperiod
True`, …) — looks like leaked debug output in schema/catalog loading; track down and remove.
