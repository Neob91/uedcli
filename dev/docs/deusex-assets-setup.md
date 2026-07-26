# Installing full Deus Ex assets into the substrate

The committed `uned/UED22` editor substrate ships only **stripped editor CODE** (the
version-69 `.u` the editor loads). To do real work — materialize/preview actual maps, and
**stub** v68 Deus Ex code packages into v69 (see the "Package stubbing" section of
[`architecture.md`](architecture.md)) — uedcli also needs the game's
**content** (textures/sounds/music) and the original **v68 `.u` code** as inputs. Those are
copyrighted Deus Ex game files: **user-supplied, gitignored, never committed.** This is how
you put them in place.

## Where to get Deus Ex (and the patch)

Deus Ex is a **commercial game** — there is no official free-of-charge source; you supply your own
copy. For uedcli you only need the files on disk (the game is never run), so any of these works:

- **Buy it (simplest, ~$8–10, already patched).** [GOG.com](https://www.gog.com/en/game/deus_ex)
  (DRM-free GOTY Edition) or Steam. Both ship at `1.112fm` already, so there is nothing to patch —
  point the script straight at the installed folder; a DRM-free GOG copy is the easiest to sync from.
- **Internet Archive (free download, copyright-gray).**
  [archive.org/details/deus_ex_goty_16231](https://archive.org/details/deus_ex_goty_16231) hosts a
  GOTY download. It is freely downloadable but is an unofficial redistribution of a game still sold
  commercially — not a licensed free source. Use with that understanding.

**On the patch:** the baseline you want is `1.112fm`, the final official Deus Ex build. GOG/Steam / the
GOTY Edition already ship at `1.112fm`, so with any of the sources above there is nothing to patch —
which is why `install-deusex-assets.sh` has no patch step. (For the record, `1.112fm` also added
multiplayer, hence the "MP" in the standalone `DeusExMPPatch1112fm.exe`, but it is the complete
**single-player** baseline; only an old unpatched retail disc would ever need that patcher.)

## TL;DR

One command takes you from an obtained copy to a fully wired-up setup. Point it at a **SOURCE** —
either an installed Deus Ex (a folder containing `System/`, `Textures/`, …) **or** a raw retail ACE
installer (a folder containing `deusex.ace`):

```bash
cd Tools/uedcli
dev/scripts/install-deusex-assets.sh /path/to/DeusEx              # installed game OR ACE installer
dev/scripts/install-deusex-assets.sh --with-maps /path/to/DeusEx # also the retail .dx maps
dev/scripts/install-deusex-assets.sh --dry-run /path/to/DeusEx   # show what it would do, write nothing
```

SOURCE is **required** — the script never downloads anything. From it, the script does two things:

1. **Assembles a full working game copy** under `Tools/uedcli/dev/games/<game>/` (default
   `<game>=deusex`; override with `--game`). If SOURCE is an ACE installer it extracts it with
   `unace`; if SOURCE is an installed game it copies the whole tree.
2. **Populates the substrate tree** `Tools/uedcli/uned/DeusExAssets/` from that working copy — the
   curated subset uedcli's editor/build containers mount.

Both `dev/games/` and `uned/DeusExAssets/` are **gitignored and never committed**. No config edits and
no container restart — uedcli reaches `uned/DeusExAssets/` per-command: every container (GUI editor +
the build container `stub.ephemeral_build_container`) bind-mounts the WHOLE composed config dir set at
`/resources/<n>` via the ONE `container_assets.resource_mounts` scheme, with a crafted
`[Core.System] Paths` (`/stubs`+`/opt/UED22` first, then the mounts) — no `docker-compose.yml`
`/deusex` mount or boot-time entrypoint Paths wiring anymore (decisions.md 2026-07-14 19:21).
`--dry-run` shows what it would do; re-running only syncs changes.

## What you need

A `1.112fm`-level Deus Ex **SOURCE** — either an installed game or the raw retail ACE installer (see
[Where to get Deus Ex](#where-to-get-deus-ex-and-the-patch) above). uedcli expects the original package
versions: textures are package version 61/68, the code `.u` are version 68. (A patch that
*re-versions* the packages to something exotic is the only thing that could surprise the stubber;
standard patched installs are fine.)

You only need the files on disk — uedcli never runs the Deus Ex game.

## What gets copied, and why each part matters

Step 1 puts the **whole** SOURCE into the working copy `Tools/uedcli/dev/games/<game>/` (a complete,
playable install you can also point a launcher at). Step 2 then copies these subtrees from that working
copy into `Tools/uedcli/uned/DeusExAssets/`:

| Subtree | Becomes | Needed for |
|---|---|---|
| `System/` | `DeusExAssets/System/` | the **v68 `.u` code packages** — inputs for package **stubbing** (`umodel` reads them for meshes; UED22's UCC decompiles them). The DLLs/exe come along harmlessly; only the `.u` are used. |
| `Textures/` | `DeusExAssets/Textures/` (`*.utx`) | **content** — resolving a map's texture packages when materializing/previewing. |
| `Sounds/` | `DeusExAssets/Sounds/` (`*.uax`) | content (sounds). |
| `Music/` | `DeusExAssets/Music/` (`*.umx`) | content (music). |
| `Maps/` (only with `--with-maps`) | `DeusExAssets/Maps/` (`*.dx`) | only if you want to materialize the **retail** maps themselves. The mod's own maps live in the repo's top-level `Maps/`, not here. |

Everything else in the install (`Help/`, `Save/`, `sound.pak`, the installer leftovers) is
inert and not needed.

## How it's wired (so you don't have to configure anything)

Two seams already know about `DeusExAssets/` — copying the files in is all that's required:

- **Per-command container mounts + `[Core.System] Paths`:** since the asset-wiring cutover
  (2026-07-14) there is NO static `docker-compose.yml` mount and NO entrypoint Paths wiring. Each
  editor/build command composes its own read-only bind mounts + a crafted `unrealtournament.ini`
  bind-mounted pre-launch: every container mounts the WHOLE composed config dir set at
  `/resources/<n>` (one uniform `resource_mounts` scheme). The build container
  (`stub.ephemeral_build_container`, for stub-build + `texture sync`) reads a v68 `.u` decompile
  source from its `/resources/<n>` path by explicit path; the GUI editor (`editor.ensure_editor`)
  mounts the same set, with `/stubs` first on `[Core.System] Paths` so a v69 stub shadows any v68 `.u`.
- **Host-side resolution:** `packages.substrate_code_dirs` resolves manifests against
  `DeusExAssets/{Textures,Sounds,Music}` (content only — **never** `System/`, so the editor is
  never asked to `OBJ LOAD` a v68 `.u`). The stub pipeline reaches `DeusExAssets/System/*.u`
  through its own separate install root, off the normal load path.

## Manual alternative (if you'd rather not use the script)

This skips the `dev/games/` working copy and populates `uned/DeusExAssets/` directly from an install:

```bash
DST=Tools/uedcli/uned/DeusExAssets
mkdir -p "$DST"
cp -a /path/to/DeusEx/System   "$DST"/   # v68 .u code (for stubbing)
cp -a /path/to/DeusEx/Textures "$DST"/   # *.utx content
cp -a /path/to/DeusEx/Sounds   "$DST"/   # *.uax content
cp -a /path/to/DeusEx/Music    "$DST"/   # *.umx content
# optional, retail maps only:
cp -a /path/to/DeusEx/Maps     "$DST"/
```

Subdir names are case-sensitive on Linux — match your install's casing (the script handles
case differences for you).

## Verify it worked

```bash
cd Tools/uedcli/uned
for s in System:u Textures:utx Sounds:uax Music:umx; do
  d=${s%%:*}; e=${s##*:}; printf "%-9s %s .%s\n" "$d" "$(ls DeusExAssets/$d/*.$e 2>/dev/null | wc -l)" "$e"
done
# A complete retail install yields roughly: System ~17 .u, Textures ~57 .utx,
# Sounds ~2 .uax, Music ~35 .umx.
```

A live end-to-end check is `uedcli level materialize` / `level preview` on a base-content map (it
fails fast and names any still-missing package), or `uedcli substrate stub <pkg>` once package
stubbing lands.

## Caveats

- **Never committed.** Both `uned/DeusExAssets/` and the `dev/games/` working copy are in
  `.gitignore`. These are commercial game assets we have no right to redistribute; the build and the
  offline test suite must (and do) work without them. Only `integration`-marked verification of real
  maps needs them present.
- **No editor restart needed** after adding/refreshing content: every editor/build command is a
  fresh per-command container that composes its mounts + Paths at launch, so new content is picked
  up on the next invocation (asset-wiring cutover 2026-07-14 — there's no standing editor to restart
  and no boot-time Paths wiring).
- **`_scratch/` is wrong** for these — that dir is throwaway and gets wiped. The working copy
  (`dev/games/<game>/`) and the asset tree (`uned/DeusExAssets/`) are the durable, gitignored homes
  the script writes. (`uned/deusex-installer/` is a separate gitignored spot you *may* keep a raw
  installer in, but the script no longer reads it — it takes any `SOURCE` path you pass.)

## The raw retail installer (ACE archive) — handled automatically

If you're starting from the raw retail installer rather than an installed game, just point SOURCE at
the installer directory: `install-deusex-assets.sh` detects the `deusex.ace` archive and extracts it
into the working copy for you. It requires `unace` on `PATH` (e.g. `apt-get install unace`); if it is
missing the script fails fast with that instruction. The mechanism, for reference:

The game files are a **multi-volume ACE archive**: `deusex.ace` plus 53 volumes `deusex.c00`–`deusex.c52`
(~151 MB compressed) alongside `Install.exe`/`install.dat` (the Windows front-end, not needed).
`unace x -y deusex.ace <target>/` decompresses the whole set, following `deusex.c00`–`.c52`
automatically (each `CRC OK`). Verified 2026-06-22: 213 files, ~487 MB, every volume CRC-clean.
**Gotcha:** the bundled `unace`'s *listing* (`unace l`) prints `*UNREGISTERED VERSION*` and stops
after volume 1 (~25 files) — cosmetic; the *extraction* follows all 53 volumes. Don't read the
truncated listing as an incomplete archive.

**`.umx` music is NOT in the retail ACE** — its `Music/` carries no `.umx`. So an ACE-sourced setup has
no music until you drop `Music/*.umx` (from another source) into `dev/games/<game>/Music/` and re-run;
the script warns when it finishes an ACE setup with no `.umx` present. A GOG/Steam install already
includes the music, so prefer one of those if you can.

## Toolchain: which UCC decompiles v68 → v69

The retail install ships **NO `UCC.exe`, NO `UnrealEd.exe`, NO `Editor.u`** — `System/` holds only
`DeusEx.exe` + `Setup.exe`; the editor/compiler toolchain is not part of the retail game. The Deus Ex
SDK (`DeusExSDK1112f.exe`) *does* ship a v68 `System/UCC.exe`, but it has **no `Editor.u` and no
`batchexport` commandlet** (that commandlet is UT-era; Deus Ex, an Unreal-1-era title, predates it),
so it cannot decompile. The **committed UED22 v469 `UCC.exe`** (`uned/UED22/`) is what reads the v68
`.u` format and exports its source, resolving v68 imports by name against the loaded v69 packages
(live-verified in `spikes/2026-06-21-deusex-package-stubbing-roundtrip.md`). So the only toolchain
needed beyond this content tree is `uned/UED22/` (committed) + `Tools/umodel_win32/` for mesh
extraction; **the Deus Ex SDK is not a build input.**
