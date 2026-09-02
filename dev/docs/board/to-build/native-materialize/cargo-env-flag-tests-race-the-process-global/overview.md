+++
priority = "p3"
kind = "debug"
summary = "FIXED same round: cargo tests that set/remove UEDCLI_BSPCSG_* env flags raced parallel test threads (flag re-read at 4+ gate sites -> hybrid pipeline flake; hit live once, 2026-09-02). Fix: uedcli-native/.cargo/config.toml pins RUST_TEST_THREADS=1 (suite runs <0.1s, serial is free). Residual (minor, open): a test panicking between set_var and remove_var still leaks the flag into later tests in the same binary."
+++

# cargo env-flag tests race the process-global flag under parallel test threads

Flagged by the round-15 diff review, then HIT LIVE the same day (2026-09-02): `bin/test`'s cargo run
failed `incremental_points_reproduces_dx_brush3_golden_p_base_order` with a flag-off-shaped result —
a concurrent env-flag test's `remove_var` landed mid-build (`build_geometry_bspcsg` re-reads the
flag per gate site, so a mid-flip builds a hybrid pipeline). Affected tests:
`incremental_points_*` (2), `WORLD_KEEP_POINTS` (3), `POINTS_ORIGIN_REVERSED` (2).

Fixed in the same change: `uedcli-native/.cargo/config.toml` sets `RUST_TEST_THREADS=1`, serializing
libtest for this crate everywhere (3x rerun green; suite <0.1s so serial costs nothing). Still open,
minor: a panic between `set_var` and `remove_var` leaks the flag into LATER tests (serial doesn't
help); a set/remove guard would close that.
