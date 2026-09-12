+++
priority = "p2"
kind = "implement"
summary = "Cut bin/test wall time and fix a shared-tmp collision that corrupts concurrent runs"
+++

# Speed up the offline test suite

`bin/test` (`pytest uedcli -q` + `cargo test`) measured at **26.5 min pytest + ~25s Rust ≈ 27
min total**, so pytest is ~99% of it. Full baseline, root causes, and a per-item feasibility
assessment: `spec.md`.
