+++
priority = "p3"
kind = "debug"
summary = "RESOLVED by other work, kept for the measurement. The lit bake was OOM-killed at ~7 min on UNATCO in 2026-07; re-measured 2026-08-27 on the same trunk it is 12.2 s for the WHOLE native build. No perf work is needed."
+++

# Native materialize `LIGHT APPLY` bake (`bake_lighting`, Rust) is far too slow / resource-heavy for a full DX level

**Resolved — do not act on this.** Re-measured 2026-08-27: a full native LIT build of the same 1437-
actor UNATCO trunk (CSG + bake + assembly + write, 2.65 MB out) takes **12.2 s** with no memory
pressure on a 24 GB / 14-core host.

Two things changed under the original measurement, neither of them a perf fix:

* the shipping lit build now goes through the `bspcsg` core rather than the coarse point-in-solid
  one, so the tree the per-lumel LOS walks is far cleaner, and
* the front-side plane cull (`light_in_front`) landed the same day this item was filed, cutting the
  lights each surface does per-lumel work for by roughly half.

Original text: an unbounded LIT build of the UNATCO trunk was SIGTERM'd (systemd-oom, exit 143) at
~7 min; unlit builds were the only ones that completed. (Found 2026-07-17.)
