+++
priority = "p?"
kind = "unknown"
summary = "RESOLVED (live-confirmed 2026-07-19) — the DeusEx base texture library is now fully reachable"
+++

# RESOLVED (live-confirmed 2026-07-19) — the DeusEx base texture library is now fully reachable

The
  old root cause (the dev container mounting only `$REPO_ROOT=LUM`, so the parent `DX/` was unmounted and
  `DX/Textures` globbed to zero) is gone: uedcli runs HOST-NATIVE since 2026-07-14, and config `paths`
  are bare dirs. `[games.deusex].paths` already lists `.../DX/Textures`; `project show` resolves 264
  packages (54 base `.utx` tagged `[base]`), and a base-only package (`Airfield.utx`, 108 textures) syncs
  and decodes clean. No mount, no stopgap-copy needed. (Was: `[flag for Andrzej]` p1.)

<!-- ── diagonal expansion (2026-07-12): grid-aligned diagonal walls via vertex-shear ── -->

<!-- ── composition + grouping ideas (2026-07-12, Andrzej) ── -->
