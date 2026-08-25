+++
priority = "p3"
kind = "chore"
summary = "`uedcli` outside a project prints stray debug lines (`plaintext False`, `swingperiod True`, …) from schema/catalog loading"
+++

# `uedcli` outside a project leaks debug output

Running `uedcli` outside a project prints stray debug lines to the terminal (`plaintext False`,
`swingperiod True`, …) — leaked debug output in schema/catalog loading. Track down and remove.

The other half of this item — the stale `NumPolys/10` comments in `uedcli-native/src/bspcsg.rs`,
which contradicted the `NumPolys/20` the code has always used — is fixed (both sites: the
`REPARTITION FindBestSplit params` block and `find_best_split_exact`'s doc comment). `/20` is the
`imul 0x66666667; sar edx,3` idiom, re-read from the binary 2026-08-25.
