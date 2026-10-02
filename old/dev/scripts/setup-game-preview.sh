#!/usr/bin/env bash
# Get `uedcli level photo --game` working end to end on a fresh machine — one command.
#
# `level photo --game` renders truly-lit in-game frames of a level by booting the real game
# engine headless in a container. That needs four things a fresh clone does NOT have, and which
# no single step otherwise provisions:
#   1. the `ued-x86-runtime` base image (wine + Xvfb + the committed UED22 UCC) — nothing builds it;
#   2. the game's own files (copyrighted, user-supplied, gitignored) — via install-deusex-assets.sh;
#   3. `~/.uedcli/config.toml` `[games.<game>].paths` pointing at those files — hand-written today;
#   4. a project `uedcli.toml` selecting the game — hand-written today.
# The `uedcli-game` image itself is built automatically on first photo, so it is NOT a step here.
#
# This script does 1-4 (idempotently — a re-run only does what is still missing), then by default
# VERIFIES by rendering one real frame through `bin/uedcli level photo --game`.
#
# The game files are copyrighted Deus Ex content. You supply the copy (a DRM-free GOG copy you own,
# or your own mirror is the clean case); see dev/docs/deusex-assets-setup.md "Where to get Deus Ex".
#
# Usage:
#   dev/scripts/setup-game-preview.sh [--game <name>] [--no-verify] [--dry-run] <SOURCE>
#   dev/scripts/setup-game-preview.sh [--game <name>] [--no-verify] [--dry-run] --url <URL>…
#   dev/scripts/setup-game-preview.sh [--game <name>] [--no-verify]                  # reuse an install
#
# <SOURCE>/--url are passed straight to install-deusex-assets.sh (see its --help for the accepted
#   forms: an installed game dir, a raw ACE installer dir, or a download URL). --with-maps is ALWAYS
#   added — the boot map (00_Training.dx) lives in the game's Maps/, so a preview cannot boot without
#   it. Omit both SOURCE and --url to reuse an install already under dev/games/<game>/.
# --game <name>   the substrate name (default deusex); selects [games.<name>] and dev/games/<name>/.
# --no-verify     provision only; skip the trial render (which builds the game image and boots wine).
# --dry-run       print what each step would do; write and build nothing.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # dev/scripts
TOOL_ROOT="$(cd "$SELF_DIR/../.." && pwd)"                   # the uedcli tool root
INSTALLER="$SELF_DIR/install-deusex-assets.sh"

usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,"");print;next} {exit}' "${BASH_SOURCE[0]}"; }

game="deusex"
verify=1
dry_run=0
src=""
urls=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --game)      shift; [[ $# -ge 1 ]] || { echo "error: --game needs a value" >&2; exit 2; }
                     game="$1" ;;
        --url)       shift; [[ $# -ge 1 ]] || { echo "error: --url needs a value" >&2; exit 2; }
                     urls+=("--url" "$1") ;;
        --no-verify) verify=0 ;;
        --dry-run)   dry_run=1 ;;
        -h|--help)   usage; exit 0 ;;
        -*)          echo "unknown option: $1" >&2; exit 2 ;;
        *)           [[ -z "$src" ]] || { echo "error: unexpected extra argument: $1 (SOURCE already set to $src)" >&2; exit 2; }
                     src="$1" ;;
    esac
    shift
done
if [[ ${#urls[@]} -gt 0 && -n "$src" ]]; then
    echo "error: pass EITHER <SOURCE> ($src) OR --url, not both." >&2
    exit 2
fi

# The game name must be a substrate `preview_game.py` knows how to boot (its exe/boot-map/window
# table). Reject an unknown one HERE, before building images or downloading a game — the preview
# would otherwise fail only at render time after all the provisioning work.
KNOWN="$(sed -n '/^SUBSTRATES = {/,/^}/p' "$TOOL_ROOT/uedcli/preview_game.py" \
         | grep -oE '^\s*"[a-z0-9_]+":' | tr -d ' ":' || true)"
if [[ -n "$KNOWN" ]] && ! grep -qx "$game" <<<"$KNOWN"; then
    echo "error: game '$game' is not a known --game preview substrate (known: $(echo $KNOWN | tr ' ' ','))." >&2
    echo "       Use one of those, or add its row to preview_game.SUBSTRATES first." >&2
    exit 2
fi

WORKING_COPY="$TOOL_ROOT/dev/games/$game"
UEDCLI_HOME="${UEDCLI_HOME:-$HOME/.uedcli}"
USER_CONFIG="$UEDCLI_HOME/config.toml"
PROJECT_TOML="$TOOL_ROOT/uedcli.toml"

say()  { printf '\n== %s ==\n' "$*"; }
would() { echo "  would $*"; }

# A missing prerequisite tool exits 2 naming it and how to get it — never a half-provisioned tree.
need_tool() {  # <command> <how-to-get-it>
    command -v "$1" >/dev/null 2>&1 && return 0
    echo "error: '$1' is required but not installed — $2" >&2
    exit 2
}

# --- Preflight ---------------------------------------------------------------------------------
say "preflight"
need_tool docker "install Docker and start its daemon"
if ! docker info >/dev/null 2>&1; then
    echo "error: the Docker daemon is not reachable (docker info failed) — start it and re-run." >&2
    exit 2
fi
[[ -x "$TOOL_ROOT/bin/uedcli" ]] || { echo "error: $TOOL_ROOT/bin/uedcli not found or not executable." >&2; exit 2; }
[[ -x "$INSTALLER" ]] || { echo "error: $INSTALLER not found — expected beside this script." >&2; exit 2; }
echo "  docker ok; bin/uedcli present"

# --- Step 1: the ued-x86-runtime base image ----------------------------------------------------
# The tag built here MUST match what uedcli/game/Dockerfile's FROM and build-image.sh's `docker
# run` use — uned/docker-compose.yml builds+runs `ued-x86-runtime:latest`; `dx-lum-uned` is only
# that image's standing CONTAINER name, never an image tag (mixing the two up is what silently
# breaks the first `level photo --game` with a Docker Hub "pull access denied" for `dx-lum-uned`).
say "step 1: ued-x86-runtime base image"
if docker image inspect ued-x86-runtime:latest >/dev/null 2>&1; then
    echo "  present — skip"
elif [[ "$dry_run" == 1 ]]; then
    would "build ued-x86-runtime:latest from $TOOL_ROOT/uned/"
else
    echo "  building (wine + Xvfb + the committed UED22 UCC; a few minutes)…"
    # amd64: the whole stack is x86 (wine runs x86 DeusEx). On an arm64 host it builds+runs under
    # qemu emulation; on amd64 it is native. Either way the images must be amd64.
    export DOCKER_DEFAULT_PLATFORM=linux/amd64
    if docker compose version >/dev/null 2>&1; then
        ( cd "$TOOL_ROOT/uned" && docker compose build )
    else
        docker build --platform=linux/amd64 -t ued-x86-runtime "$TOOL_ROOT/uned"
    fi
    echo "  built ued-x86-runtime:latest"
fi

# --- Step 2: the game files --------------------------------------------------------------------
say "step 2: Deus Ex files (dev/games/$game/)"
have_install=0
[[ -n "$(find "$WORKING_COPY/System" -maxdepth 1 -iname 'DeusEx.exe' 2>/dev/null)" ]] && have_install=1
if [[ "$have_install" == 1 && ${#urls[@]} -eq 0 && -z "$src" ]]; then
    echo "  reusing the install already at $WORKING_COPY"
elif [[ "$dry_run" == 1 ]]; then
    would "run install-deusex-assets.sh --with-maps --game $game ${src:-${urls[*]:-<built-in default URL>}}"
else
    # No <SOURCE>/--url and no install: install-deusex-assets.sh falls back to its built-in default
    # URL (autonomous), so a bare `setup-game-preview.sh` provisions everything with no inputs.
    # --with-maps is required: the boot map lives in the game's Maps/, and a preview cannot boot
    # without it (preview_game._find_boot_map). ${urls[@]+…} keeps `set -u` happy when urls is empty
    # (a plain SOURCE run) on bash < 4.4.
    "$INSTALLER" --with-maps --game "$game" ${src:+"$src"} ${urls[@]+"${urls[@]}"}
fi

# The boot hard-requires DeusEx.exe (System) AND 00_Training.dx (Maps). A reuse of a maps-less
# install would otherwise fail deep in the verify with no remedy — name it here.
if [[ "$dry_run" != 1 ]]; then
    [[ -n "$(find "$WORKING_COPY/System" -maxdepth 1 -iname 'DeusEx.exe' 2>/dev/null)" ]] \
        || { echo "error: no DeusEx.exe under $WORKING_COPY/System after step 2." >&2; exit 2; }
    [[ -n "$(find "$WORKING_COPY/Maps" -maxdepth 1 -iname '00_Training.dx' 2>/dev/null)" ]] \
        || { echo "error: no Maps/00_Training.dx under $WORKING_COPY — the preview boot map is missing." >&2
             echo "       Re-run with your Deus Ex <SOURCE>/--url so the maps get installed (--with-maps)." >&2
             exit 2; }
fi

# The composed [games.<game>].paths, in order, as ABSOLUTE canonical dirs. Only dirs that exist are
# listed — so a music-less ACE setup, say, does not put a dead path on the search list. System
# (DeusEx.exe) and Maps (00_Training.dx) are the two the boot hard-requires; the rest is content.
# Canonicalized so config carries real dirs even when dev/games/<game> is a symlink to an install.
game_paths() {
    local out=() d
    for d in System Maps Textures Sounds Music; do
        [[ -d "$WORKING_COPY/$d" ]] && out+=("$(cd "$WORKING_COPY/$d" && pwd -P)")
    done
    ( IFS=:; printf '%s' "${out[*]}" )
}

# --- Step 3: ~/.uedcli/config.toml [games.<game>] ----------------------------------------------
say "step 3: $USER_CONFIG"
if [[ "$dry_run" == 1 ]]; then
    would "ensure [games.$game].paths = \"$(game_paths)\" in $USER_CONFIG"
else
    [[ -d "$WORKING_COPY/System" ]] || { echo "error: $WORKING_COPY/System is missing after step 2." >&2; exit 2; }
    PATHS="$(game_paths)" GAME="$game" CFG="$USER_CONFIG" python3 - <<'PY'
import os, sys, tomllib
from pathlib import Path
cfg, game, paths = Path(os.environ["CFG"]), os.environ["GAME"], os.environ["PATHS"]
block = f'[games.{game}]\npaths = "{paths}"\n'
if not cfg.exists():
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(block)
    print(f"  wrote {cfg} with [games.{game}]")
    sys.exit(0)
data = tomllib.loads(cfg.read_text())
have = data.get("games", {}).get(game)
if have is None:
    # Append the block; never rewrite what is already there (other games, comments, ordering).
    text = cfg.read_text()
    cfg.write_text(text + ("" if text.endswith("\n") else "\n") + "\n" + block)
    print(f"  added [games.{game}] to {cfg}")
elif have.get("paths") == paths:
    print(f"  [games.{game}] already correct — skip")
else:
    # Never clobber the user's global config. Name the conflict and the exact fix, exit 2.
    sys.stderr.write(
        f"error: {cfg} already has [games.{game}] with different paths:\n"
        f"         have: {have.get('paths')!r}\n"
        f"         want: {paths!r}\n"
        f"       Edit it to the wanted value (or remove that block) and re-run.\n")
    sys.exit(2)
PY
fi

# --- Step 4: project uedcli.toml ---------------------------------------------------------------
say "step 4: $PROJECT_TOML"
if [[ -f "$PROJECT_TOML" ]]; then
    cur="$(python3 -c 'import tomllib,sys; print(tomllib.load(open(sys.argv[1],"rb")).get("game",""))' "$PROJECT_TOML" 2>/dev/null || true)"
    if [[ "$cur" == "$game" ]]; then
        echo "  present (game = \"$game\") — skip"
    else
        # Never clobber the project file, but do NOT continue: the verify below resolves the game
        # FROM this file, so a mismatch would verify the wrong game (mirrors step 3's guard).
        echo "error: $PROJECT_TOML already selects game = \"${cur:-<unset>}\", not \"$game\"." >&2
        echo "       Edit it to \"$game\" (or remove it) and re-run." >&2
        exit 2
    fi
elif [[ "$dry_run" == 1 ]]; then
    would "write $PROJECT_TOML with game = \"$game\""
else
    printf 'game = "%s"\n' "$game" > "$PROJECT_TOML"
    echo "  wrote $PROJECT_TOML (game = \"$game\")"
fi

# --- Step 5: verify with a real render ---------------------------------------------------------
if [[ "$verify" == 0 ]]; then
    say "done (provision only; skipped --verify)"
    echo "  Try it (from $TOOL_ROOT):  bin/uedcli level photo --game 'at:0,0,64;rot:0,0' --out-dir /tmp/uedpv"
    echo "  (pose grammar + backends: docs/reference/level/photo.md)"
    exit 0
fi
if [[ "$dry_run" == 1 ]]; then
    say "done (dry run)"; exit 0
fi

say "step 5: verify — rendering one in-game frame (builds the game image + boots wine; ~2-3 min)"
BOOT_MAP="$(find "$WORKING_COPY/Maps" -maxdepth 1 -iname '00_Training.dx' 2>/dev/null | head -n1)"
[[ -n "$BOOT_MAP" ]] || { echo "error: no 00_Training.dx under $WORKING_COPY/Maps to verify with." >&2; exit 2; }
OUT="$(mktemp -d)"
# bin/uedcli finds the project by walking up from the cwd, so run the verify from $TOOL_ROOT where
# step 4 wrote uedcli.toml — else a caller in another directory hits "no project".
cd "$TOOL_ROOT"
# Orbit the map's own PlayerStart so the frame looks at real geometry without hardcoding a pose.
# Its instance NAME varies per map (PlayerStart0/1/…), so discover it from the running game first
# (--list-actors is a --game --map query, docs/reference/level/photo.md). This first boot is the
# slow one; the orbit render reuses the warm container. Keep stderr — if the boot/build fails, PS
# is empty and its error is the thing to show, not "no PlayerStart".
DISC_ERR="$OUT/.discover.err"
PS="$(bin/uedcli level photo --game --map "$BOOT_MAP" \
        --list-actors Engine.PlayerStart --sample 1 2>"$DISC_ERR" | awk 'NR==1{print $1}')"
if [[ -z "$PS" ]]; then
    echo "error: could not discover an Engine.PlayerStart in $(basename "$BOOT_MAP") — the first" >&2
    echo "       --game boot/render failed:" >&2
    tail -n 6 "$DISC_ERR" | sed 's/^/         /' >&2
    exit 2
fi
SHOT="orbit:@$PS;radius:300;azimuth:0;elev:2000"
if bin/uedcli level photo --game --map "$BOOT_MAP" "$SHOT" --out-dir "$OUT" --size 640x480; then
    frame="$(find "$OUT" -name '*.png' | head -n1)"
    if [[ -n "$frame" ]]; then
        echo
        echo "SUCCESS: level photo --game rendered $frame"
        echo "  Everything is wired. Your first trunk photo: bin/uedcli level photo --game <SHOT> --out-dir DIR"
        exit 0
    fi
    echo "error: photo reported success but produced no PNG in $OUT." >&2
    exit 1
fi
echo "error: the verify render failed. The stack is provisioned; re-run just the render to retry:" >&2
echo "       bin/uedcli level photo --game --map \"$BOOT_MAP\" \"$SHOT\" --out-dir DIR" >&2
exit 1
