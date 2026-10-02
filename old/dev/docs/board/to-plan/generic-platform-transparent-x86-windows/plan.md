# Plan — build sequence

De-risk the two ends under FEX first (spec U1/U2), then refactor onto one runtime.

1. **Spike both ends under FEX+wine-10, pin recipes** → `dev/docs/spikes/`:
   - Materialize: `unrealed.exe` completes `MAP IMPORTADD` + `MAP REBUILD` + `MAP SAVE` to a real
     `.dx` (configure SoftDrv headless render device; suppress the startup browser viewports so
     `RenDev` can't assert). Diff the `.dx` against the x86-native materialize output.
   - Game: `DeusEx.exe` binds `:7777` and renders a frame under the 16 GiB cap on no-CD binaries.
   - Gate: both must pass before step 2. If either can't, stop and report — don't build the image
     around an unproven end.

2. **Runtime image (multi-arch `ued-x86-runtime`)** from the spike recipes: arm64 (FEX + pinned
   wine-10 userland + RootFS + native Xvfb), amd64 (native wine + Xvfb). The `run_x86` shim. A `bin/`
   script builds/pins the wine-10 userland (U4).

3. **Python launcher** generalizing `ensure_editor` + game bring-up: container start + mounts, Xvfb,
   ini-craft (`replace_core_system_paths`), `run_x86` launch, wedge-relaunch, caller-supplied ready
   signal, driver interface.

4. **Port `level materialize`** onto the launcher (editor profile). Verify on arm: materialize
   produces a saved `.dx`; add a golden/regression test that fails without the runtime.

5. **Port `level photo --game`** onto the launcher (game profile). Verify on arm: `--game` renders
   a frame.

6. **Delete the superseded paths** (no back-compat): fold `game-entrypoint.sh` arm handling and the
   old editor entrypoint into the runtime; remove the duplicated bring-up.

7. **Tests + docs.** CLI behavior is unchanged (materialize/`--game` just work on arm now), so
   `docs/usage.md` likely needs no change; update if any observable behavior shifts. Confirm U3 on an
   x86 host if available.

Notes: FEX arm64 image is large (~35 GB in the spike) — slim or accept. Docker-daemon instability in
the spike env is environmental, orthogonal.
