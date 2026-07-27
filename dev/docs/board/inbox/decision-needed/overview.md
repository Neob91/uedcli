+++
priority = "p3"
kind = "chore"
summary = "DECISION NEEDED"
+++

# DECISION NEEDED

usability-nit leftover: --prefab-dir position` — `prefab` takes `--prefab-dir` on the
PARENT parser (documented `prefab [--prefab-dir DIR] <sub>`, usage.md:550), so it must come BEFORE the
subverb; `stash promote` takes it on the subcommand (`stash promote ID --prefab-dir X`, after). The
usability probe wants these consistent. **DECISION NEEDED** (each has a cost): (a) ADD `--prefab-dir`
to each prefab subcommand too so the after-subverb form ALSO works (additive, keeps the documented
form — but the flag then lives in two places); (b) MOVE it to the subcommands only (consistent, but
breaks the documented `prefab --prefab-dir X list` form + its docs); or (c) just document the
difference. Deferred from the 2026-07-19 nits batch (the other nits landed) pending this call.
