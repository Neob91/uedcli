# level photo

**`level photo`** renders **still first-person shots** of the current level from arbitrary camera
poses. A **two-tier** command behind one verb, sharing one batched **pose grammar**. Read-only — it
never writes the trunk or a committed map.

```
level photo SHOT… --out-dir DIR [--game | --native] [--size WxH] [--fov DEG]
              [--map PATH] [--rebuild] [--keep-alive]
level photo --list-actors Package.Class [--sample N] [--game --map PATH]   # discovery mode
```

## The pose grammar (SHOT tokens)

One shot per positional token, fields `;`-separated (angles in **unreal rotation units**: 16384 =
90°, 65536 = a full turn; append `;name:STEM` to name the output PNG, default `shot-01`, `shot-02`,
…):

- `at:X,Y,Z;rot:PITCH,YAW` — camera eye at a world point, aimed by angles (positive pitch looks up).
  **All angles (`rot`, `azimuth`, `elev`) are unreal rotation units: 16384 = 90°, 65536 = a full turn.**
- `at:X,Y,Z;look:X,Y,Z` — camera eye at a point, aimed AT another point.
- `at:@Actor;…` / `…;look:@Actor` / `orbit:@Actor;radius:R;azimuth:A[;elev:B]` — pose relative to a
  named actor (resolved against the trunk, or with `--game --map` against the **running game**).
  `orbit` places the camera on a ring of R uu around the actor, aimed inward.

## Backends

- **`--game` (the DEFAULT)** — the faithful lit tier. Delivers the map into a **warm per-user
  headless game container** (booted once ~90s, then REUSED across photo runs; self-terminates after
  10 min idle) and captures **truly-lit first-person frames** (real lighting/sky/textures). Pitch is
  clamped host-side to ±89.9°; movers render at rest pose. First batch ~1–3 min (boot + travel);
  later batches skip the boot. It is the default because it shows lighting/meshes/sky and the offline
  draft mis-renders overlapping-subtract geometry silently.
  - **Prerequisites.** Docker, and the game's own files on the composed package search path (its
    `System/` and content), configured under `~/.uedcli/config.toml` `[games.*].paths`. On a fresh
    machine, `dev/scripts/setup-game-preview.sh /path/to/DeusEx` (or `--url <installer>`, or no
    argument at all to use its built-in checksum-pinned default download) provisions the whole path
    in one command — the base image, the game files, the config, and a verify render; run it with
    `--help`. The image is built and the preview package compiled automatically on first use — **no
    UnrealEd/UCC toolchain to install** (the generic preview compiles its engine-only helper with
    the container's own UCC).
  - **`--map PATH`** shoots a **prebuilt** map file instead of the selected trunk (skips the
    materialize cache); actor-relative shots resolve against the running game.
  - **`--rebuild`** forces a fresh materialize under a new unique name (guarantees the game reloads it).
  - **`--keep-alive`** PINs the warm container (disables idle death) and prints its **noVNC URL** for
    live inspection (dev-debug; release the pin with `docker rm -f`).
  - Without `--map`, this tier **materializes the trunk internally** — post-verify included, with no
    `--no-verify` escape — so it inherits `level materialize`'s requirement that every actor class be
    fully qualified and its package present on the search paths. An unresolvable class exits 2 naming
    the actor, before anything is built.
- **`--native`** — the opt-in offline draft. **No container at all**: the native CSG core carves the
  trunk in-process and a software rasterizer renders **textured, flat-shaded** perspective stills in
  seconds. Movers render at base pose; point actors, meshes, sky, lighting, and translucency do NOT
  render (translucent/masked faces render opaque). Scaled, mirrored, and sheared brushes render (the
  transform is baked into the geometry, and the texture frame follows it too — texels stretch/shear
  with the surface). `--fov DEG` (default 75) applies here; `--map` /
  `--rebuild` / `--keep-alive` are rejected with `--native`.

**Shared:** `--out-dir DIR` (required unless `--list-actors`; created if absent), `--size WxH`
(default 1280×960).

## Discovery mode

**`--list-actors Package.Class`** (with `--game --map`) prints the running map's actors of that class
as `Name x y z` instead of shooting (e.g. `Engine.PathNode` blankets every walkable spot) — to
discover `@Actor` refs for shots. `--sample N` prints N evenly-spread; no screenshots, `--out-dir`
not needed.

See also: [`level materialize`](materialize.md), [`dev/scripts/setup-game-preview.sh`](../../../dev/scripts/setup-game-preview.sh).
