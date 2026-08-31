# Installing full Deus Ex assets into the substrate

The committed `uned/UED22` editor substrate ships only stripped editor code (the
version-69 `.u` the editor loads). To materialize/photo real maps, and to stub
v68 Deus Ex code packages into v69 (see "Package stubbing" in
[`architecture.md`](architecture.md)), uedcli also needs the game's content
(textures/sounds/music) and the original v68 `.u` code. Those are copyrighted Deus
Ex game files: user-supplied, gitignored, never committed. This is how to put them
in place.

## Where to get Deus Ex (and the patch)

Deus Ex is commercial with no free official source; supply your own copy. You only
need the files on disk (the game is never run), so any of these works:

- Buy it (~$8–10, already patched). [GOG.com](https://www.gog.com/en/game/deus_ex)
  (DRM-free GOTY Edition) or Steam. Both ship at `1.112fm`, so nothing to patch —
  point the script at the installed folder; a DRM-free GOG copy is easiest to sync from.
- Internet Archive (free download, copyright-gray).
  [archive.org/details/deus_ex_goty_16231](https://archive.org/details/deus_ex_goty_16231)
  hosts a GOTY download — an unofficial redistribution of a game still sold
  commercially, not a licensed free source.

The baseline you want is `1.112fm`, the final official build. GOG/Steam and the GOTY
Edition already ship at it, so none of the sources above needs patching — hence
`install-deusex-assets.sh` has no patch step. `1.112fm` also added multiplayer, hence
the "MP" in the standalone `DeusExMPPatch1112fm.exe`, but it is the complete
single-player baseline; only an old unpatched retail disc would need that patcher.

## TL;DR

One command takes an obtained copy to a wired-up setup. Point it at a SOURCE — either
an installed Deus Ex (a folder with `System/`, `Textures/`, …) or a raw retail ACE
installer (a folder with `deusex.ace`):

```bash
cd Tools/uedcli
dev/scripts/install-deusex-assets.sh /path/to/DeusEx              # installed game OR ACE installer
dev/scripts/install-deusex-assets.sh --with-maps /path/to/DeusEx # also the retail .dx maps
dev/scripts/install-deusex-assets.sh --dry-run /path/to/DeusEx   # show what it would do, write nothing
```

Or give it a `--url` to fetch instead of a local path (see
[Fetching with `--url`](#fetching-with---url)):

```bash
dev/scripts/install-deusex-assets.sh --with-maps --url https://example.invalid/DeusEx.zip
```

Exactly one of SOURCE or `--url` is required. From it the script does two things:

1. Assembles a full working game copy under `Tools/uedcli/dev/games/<game>/` (default
   `<game>=deusex`; override with `--game`). An ACE installer is extracted with
   `unace`; an installed game has its whole tree copied.
2. Populates the substrate tree `Tools/uedcli/uned/DeusExAssets/` from that working
   copy — the curated subset uedcli's editor/build containers mount.

Both `dev/games/` and `uned/DeusExAssets/` are gitignored and never committed. No
config edits and no container restart: uedcli reaches `uned/DeusExAssets/` per-command.
Every container (GUI editor + the build container `stub.ephemeral_build_container`)
bind-mounts the whole composed config dir set at `/resources/<n>` via the one
`container_assets.resource_mounts` scheme, with a crafted `[Core.System] Paths`
(`/stubs`+`/opt/UED22` first, then the mounts) — no `docker-compose.yml` `/deusex`
mount or boot-time entrypoint Paths wiring (`direction/containers.md`, 2026-07-14 19:21). `--dry-run`
shows what it would do; re-running only syncs changes.

## What you need

A `1.112fm`-level Deus Ex SOURCE — an installed game or the raw retail ACE installer
(see [Where to get Deus Ex](#where-to-get-deus-ex-and-the-patch)). uedcli expects the
original package versions: textures are package version 61/68, the code `.u` are
version 68. Only a patch re-versioning the packages to something exotic could surprise
the stubber; standard patched installs are fine. You only need the files on disk;
uedcli never runs the game.

## Fetching with `--url`

`--url` downloads the artifact you name, unpacks it, finds the install root inside, and
continues as if you had passed that root as SOURCE. There is no built-in source: no
default URL, no bundled list, no lookup. Deus Ex is still sold commercially, so the
right to the copy you point it at is yours to establish — a DRM-free GOG copy you own,
or your own mirror of one, is the clean case.

```bash
# one artifact, content-verified
dev/scripts/install-deusex-assets.sh --with-maps \
    --url https://example.invalid/DeusEx-GOTY.zip \
    --sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

# a multi-part download: repeat --url; every part lands in one dir before unpacking
dev/scripts/install-deusex-assets.sh --url https://example.invalid/deusex.ace \
                                     --url https://example.invalid/deusex.c00
```

- `--sha256 SUM` verifies a download, matched positionally to the `--url` of the same
  index. Give one per URL or none; a mismatch stops the run and keeps the file for
  inspection. Without it the run says plainly that content was not verified.
- `--redownload` refetches even when the file is already there. By default a completed
  download is reused and a partial one resumed, so an interrupted 3 GB fetch costs
  nothing to retry.
- Formats unpacked: `.ace` volume sets (via `unace`), `.tar[.gz|.bz2|.xz|.zst]`,
  `.zip`, `.7z`, `.iso`, `.rar`, and Inno Setup `.exe` (what a GOG offline installer is,
  via `innoextract`). Anything else — notably InstallShield or NSIS installers — exits
  2 naming the file: unpack it yourself and pass SOURCE.
- **Unpacking always runs in a container**, on every host, whether or not the host has
  the tool — one code path and one set of tool versions everywhere. The run builds a
  small `uedcli-unpack` image on first use (cached after) and invokes the unpacker
  inside it, so nothing needs installing on the host. Docker is therefore required to
  unpack a download; without it the run exits 2 saying so. An already-extracted SOURCE
  is copied as-is and needs neither.
- Where things land: artifacts in `dev/games/.cache/<game>/download/`, unpacked in
  `.../unpacked/`. Both sit outside the working copy `dev/games/<game>/` on purpose —
  step 1 syncs the install root into the working copy with `--delete`, which would
  otherwise delete the download cache while reading from it.
- `--dry-run` with `--url` prints the fetch plan and stops, because what happens next
  depends on what the download contains.

If `uned/DeusExAssets` is a symlink whose target is missing, the script says so and
names the target rather than failing with a bare `mkdir: File exists`. That happens when
a checkout carrying such a symlink is used on a second machine where the absolute path
does not exist.

## What gets copied, and why each part matters

Step 1 puts the whole SOURCE into the working copy `Tools/uedcli/dev/games/<game>/` (a
complete, playable install you can also point a launcher at). Step 2 copies these
subtrees from that working copy into `Tools/uedcli/uned/DeusExAssets/`:

| Subtree | Becomes | Needed for |
|---|---|---|
| `System/` | `DeusExAssets/System/` | the v68 `.u` code packages — inputs for package stubbing (`umodel` reads them for meshes; UED22's UCC decompiles them). The DLLs/exe come along harmlessly; only the `.u` are used. |
| `Textures/` | `DeusExAssets/Textures/` (`*.utx`) | content — resolving a map's texture packages when materializing/previewing. |
| `Sounds/` | `DeusExAssets/Sounds/` (`*.uax`) | content (sounds). |
| `Music/` | `DeusExAssets/Music/` (`*.umx`) | content (music). |
| `Maps/` (only with `--with-maps`) | `DeusExAssets/Maps/` (`*.dx`) | only if you want to materialize the retail maps themselves. The mod's own maps live in the repo's top-level `Maps/`, not here. |

Everything else in the install (`Help/`, `Save/`, `sound.pak`, installer leftovers) is
inert and not needed.

## How it's wired

Two seams already know about `DeusExAssets/`; copying the files in is all that's required:

- Per-command container mounts + `[Core.System] Paths`: since the asset-wiring cutover
  (2026-07-14) there is no static `docker-compose.yml` mount and no entrypoint Paths
  wiring. Each editor/build command composes its own read-only bind mounts + a crafted
  `unrealtournament.ini` bind-mounted pre-launch: every container mounts the whole
  composed config dir set at `/resources/<n>` (one uniform `resource_mounts` scheme).
  The build container (`stub.ephemeral_build_container`, for stub-build + `texture sync`)
  reads a v68 `.u` decompile source from its `/resources/<n>` path by explicit path; the
  GUI editor (`editor.ensure_editor`) mounts the same set, with `/stubs` first on
  `[Core.System] Paths` so a v69 stub shadows any v68 `.u`.
- Host-side resolution: `packages.substrate_code_dirs` resolves manifests against
  `DeusExAssets/{Textures,Sounds,Music}` (content only — never `System/`, so the editor
  is never asked to `OBJ LOAD` a v68 `.u`). The stub pipeline reaches
  `DeusExAssets/System/*.u` through its own separate install root, off the normal load path.

## Manual alternative (if you'd rather not use the script)

This skips the `dev/games/` working copy and populates `uned/DeusExAssets/` directly
from an install:

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

Subdir names are case-sensitive on Linux — match your install's casing (the script
handles case differences for you).

## Verify it worked

```bash
cd Tools/uedcli/uned
for s in System:u Textures:utx Sounds:uax Music:umx; do
  d=${s%%:*}; e=${s##*:}; printf "%-9s %s .%s\n" "$d" "$(ls DeusExAssets/$d/*.$e 2>/dev/null | wc -l)" "$e"
done
# A complete retail install yields roughly: System ~17 .u, Textures ~57 .utx,
# Sounds ~2 .uax, Music ~35 .umx.
```

A live end-to-end check is `uedcli level materialize` / `level photo` on a base-content
map (it fails fast and names any still-missing package), or `uedcli substrate stub <pkg>`
once package stubbing lands.

## Caveats

- Never committed. Both `uned/DeusExAssets/` and the `dev/games/` working copy are in
  `.gitignore`. These are commercial game assets we have no right to redistribute; the
  build and the offline test suite must (and do) work without them. Only
  `integration`-marked verification of real maps needs them present.
- No editor restart after adding/refreshing content: every editor/build command is a
  fresh per-command container that composes its mounts + Paths at launch, so new content
  is picked up on the next invocation (asset-wiring cutover 2026-07-14 — no standing
  editor to restart, no boot-time Paths wiring).
- `_scratch/` is wrong for these — that dir is throwaway and gets wiped. The working copy
  (`dev/games/<game>/`) and the asset tree (`uned/DeusExAssets/`) are the durable,
  gitignored homes the script writes. `uned/deusex-installer/` is a separate gitignored
  spot you may keep a raw installer in, but the script no longer reads it — it takes any
  `SOURCE` path you pass.

## The raw retail installer (ACE archive)

Starting from the raw retail installer rather than an installed game, point SOURCE at
the installer directory: `install-deusex-assets.sh` detects `deusex.ace` and extracts it
into the working copy. It requires `unace` on `PATH` (e.g. `apt-get install unace`);
missing, the script fails fast with that instruction. The mechanism, for reference:

The game files are a multi-volume ACE archive: `deusex.ace` plus 53 volumes
`deusex.c00`–`deusex.c52` (~151 MB compressed) alongside `Install.exe`/`install.dat`
(the Windows front-end, not needed). `unace x -y deusex.ace <target>/` decompresses the
whole set, following `deusex.c00`–`.c52` automatically (each `CRC OK`). Verified
2026-06-22: 213 files, ~487 MB, every volume CRC-clean. Gotcha: the bundled `unace`'s
listing (`unace l`) prints `*UNREGISTERED VERSION*` and stops after volume 1 (~25 files)
— cosmetic; the extraction follows all 53 volumes. Don't read the truncated listing as an
incomplete archive.

`.umx` music is not in the retail ACE — its `Music/` carries no `.umx`. An ACE-sourced
setup has no music until you drop `Music/*.umx` (from another source) into
`dev/games/<game>/Music/` and re-run; the script warns when it finishes an ACE setup with
no `.umx` present. A GOG/Steam install already includes the music, so prefer one of those.

## Toolchain: which UCC decompiles v68 → v69

The retail install ships no `UCC.exe`, no `UnrealEd.exe`, no `Editor.u` — `System/` holds
only `DeusEx.exe` + `Setup.exe`; the editor/compiler toolchain is not part of the retail
game. The Deus Ex SDK (`DeusExSDK1112f.exe`) does ship a v68 `System/UCC.exe`, but it has
no `Editor.u` and no `batchexport` commandlet (that commandlet is UT-era; Deus Ex, an
Unreal-1-era title, predates it), so it cannot decompile. The committed UED22 v469
`UCC.exe` (`uned/UED22/`) is what reads the v68 `.u` format and exports its source,
resolving v68 imports by name against the loaded v69 packages (live-verified in
`spikes/2026-06-21-deusex-package-stubbing-roundtrip.md`). So the only toolchain needed
beyond this content tree is `uned/UED22/` (committed) + `Tools/umodel_win32/` for mesh
extraction; the Deus Ex SDK is not a build input.
