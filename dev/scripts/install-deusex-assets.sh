#!/usr/bin/env bash
# Set up a complete, working Deus Ex install for uedctl — end to end — from a SOURCE you supply.
#
# Given <SOURCE> (REQUIRED: a path to an installed Deus Ex, OR a raw retail ACE installer dir),
# this does everything:
#   1. Assembles a full working game copy under  dev/games/<game>/   (default <game>=deusex).
#        - SOURCE is a raw ACE installer (has deusex.ace + deusex.c00..) -> extract with `unace x`.
#        - SOURCE is an installed game     (has System/ + Textures/)      -> copy the whole tree.
#   2. Populates the uedctl substrate asset tree  uned/DeusExAssets/  FROM that working copy — the
#      curated subset the editor/build containers mount: System/ (v68 `.u` code, for stubbing) +
#      Textures/ *.utx, Sounds/ *.uax, Music/ *.umx (content), + Maps/ *.dx with --with-maps.
#
# Everything written is copyrighted Deus Ex content. BOTH dev/games/ and uned/DeusExAssets/ are
# gitignored and NEVER committed. This script NEVER downloads anything — you supply SOURCE.
#
# SOURCE should be a complete Deus Ex copy — a GOG/Steam GOTY install is ideal (already the final
# 1.112fm build). See dev/docs/deusex-assets-setup.md ("Where to get Deus Ex").
#
# Usage:
#   dev/scripts/install-deusex-assets.sh [--game <name>] [--with-maps] [--dry-run] <SOURCE>
#
# <SOURCE> is the install ROOT (dir CONTAINING System/, Textures/, …) or the ACE installer dir
# (CONTAINING deusex.ace). Subdir names are matched case-insensitively (Windows installs vary).
# Re-runnable: it syncs, so running again only copies what changed.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Both destinations are anchored relative to the tool root, NOT beside this script (it lives in
# dev/scripts/): the working copy under dev/games/, and the substrate tree at uned/DeusExAssets/
# (the latter fixed by code in tool_assets.py `uned_dir()`). `cd` only into always-present dirs
# (dev/, the tool root) and append the leaf as a string — the leaf dirs are created later.
GAMES_PARENT="$(cd "$SELF_DIR/.." && pwd)/games"          # Tools/uedctl/dev/games
DEST_ROOT="$(cd "$SELF_DIR/../.." && pwd)/uned/DeusExAssets"

# Print the header comment block (everything after the shebang up to the first non-comment line),
# stripping the leading "# " — robust to the header's length changing.
usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,"");print;next} {exit}' "${BASH_SOURCE[0]}"; }

game="deusex"
with_maps=0
dry_run=0
src=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --game)      shift; [[ $# -ge 1 ]] || { echo "error: --game needs a value" >&2; exit 2; }
                     game="$1" ;;
        --with-maps) with_maps=1 ;;
        --dry-run)   dry_run=1 ;;
        -h|--help)   usage; exit 0 ;;
        -*)          echo "unknown option: $1" >&2; exit 2 ;;
        *)           [[ -z "$src" ]] || { echo "error: unexpected extra argument: $1 (SOURCE already set to $src)" >&2; exit 2; }
                     src="$1" ;;
    esac
    shift
done

if [[ -z "$src" ]]; then
    echo "error: missing <SOURCE> (path to an installed Deus Ex or a raw ACE installer)." >&2
    echo "       Run with --help." >&2
    exit 2
fi
if [[ ! -d "$src" ]]; then
    echo "error: SOURCE is not a directory: $src" >&2
    exit 2
fi

WORKING_COPY="$GAMES_PARENT/$game"

# Resolve a subdir of a dir case-insensitively (System vs system, etc.); empty if absent.
find_subdir() {  # <parent> <wanted-name>
    local parent="$1" want="$2" d
    for d in "$parent"/*/; do
        d="${d%/}"
        [[ -e "$d" ]] || continue
        if [[ "${d##*/}" == "$want" ]] || \
           [[ "$(printf '%s' "${d##*/}" | tr '[:upper:]' '[:lower:]')" == \
              "$(printf '%s' "$want" | tr '[:upper:]' '[:lower:]')" ]]; then
            printf '%s' "$d"; return 0
        fi
    done
    return 1
}

# Pick the copy engine: rsync (idempotent, shows what changed) if available, else cp -a.
have_rsync=0; command -v rsync >/dev/null 2>&1 && have_rsync=1

sync_tree() {  # <src-dir> <dst-dir> [--delete]
    local s="$1" d="$2" del="${3:-}"
    mkdir -p "$d"
    if [[ "$have_rsync" == 1 ]]; then
        rsync -a ${del:+--delete} "$s"/ "$d"/
    else
        cp -a "$s"/. "$d"/
    fi
}

# --- Step 1: assemble the full working game copy under dev/games/<game>/ -----------------------

ace_src=""  # the .ace archive inside SOURCE, if this is a raw installer
for f in "$src"/*.[aA][cC][eE]; do [[ -e "$f" ]] && { ace_src="$f"; break; }; done

install_sys="$(find_subdir "$src" System || true)"
install_tex="$(find_subdir "$src" Textures || true)"

echo "Target working copy : $WORKING_COPY"
echo "Target substrate    : $DEST_ROOT"
echo "Source              : $src   (rsync=$have_rsync, dry_run=$dry_run, with_maps=$with_maps, game=$game)"

if [[ -n "$ace_src" ]]; then
    echo "SOURCE looks like a raw ACE installer ($(basename "$ace_src"))."
    if ! command -v unace >/dev/null 2>&1; then
        if [[ "$dry_run" == 1 ]]; then
            echo "  would extract $ace_src -> $WORKING_COPY, but 'unace' is NOT installed" >&2
        else
            echo "error: SOURCE is an ACE archive but 'unace' is not installed." >&2
            echo "       Install it (e.g. 'apt-get install unace') and re-run, or extract the ACE" >&2
            echo "       yourself and point SOURCE at the extracted install root." >&2
            exit 2
        fi
    fi
    if [[ "$dry_run" == 1 ]]; then
        echo "  would extract $ace_src  ->  $WORKING_COPY  (unace x)"
    else
        mkdir -p "$WORKING_COPY"
        # unace extracts the whole deusex.c00..c52 volume set automatically from deusex.ace.
        ( cd "$src" && unace x -y "$(basename "$ace_src")" "$WORKING_COPY"/ )
        echo "  extracted ACE -> $WORKING_COPY"
    fi
elif [[ -n "$install_sys" && -n "$install_tex" ]]; then
    echo "SOURCE looks like an installed game."
    if [[ "$dry_run" == 1 ]]; then
        echo "  would copy the whole install  $src  ->  $WORKING_COPY"
    else
        sync_tree "$src" "$WORKING_COPY" --delete
        echo "  working copy synced -> $WORKING_COPY"
    fi
else
    echo "error: SOURCE '$src' is neither a Deus Ex install (System/ + Textures/) nor an ACE" >&2
    echo "       installer (a *.ace archive). Point it at the install ROOT or the installer dir." >&2
    exit 2
fi

# The working copy is now the single source for step 2 (in a dry run it may not exist yet).
wc_sys="$(find_subdir "$WORKING_COPY" System || true)"
if [[ "$dry_run" != 1 ]]; then
    if [[ -z "$wc_sys" ]]; then
        echo "error: no System/ in the working copy $WORKING_COPY after setup — extraction/copy failed." >&2
        exit 2
    fi
    if ! ls "$wc_sys"/[Dd]eus[Ee]x.u >/dev/null 2>&1; then
        echo "warning: $wc_sys has no DeusEx.u — is SOURCE a complete install? Continuing anyway." >&2
    fi
fi

# --- Step 2: populate uned/DeusExAssets/ from the working copy ---------------------------------

copy_subtree() {  # <dest-name>
    local name="$1"
    local s; s="$(find_subdir "$WORKING_COPY" "$name" || true)"
    local dst="$DEST_ROOT/$name"
    if [[ "$dry_run" == 1 ]]; then
        echo "  would copy $name  <-  $WORKING_COPY/$name"
        return 0
    fi
    [[ -n "$s" && -d "$s" ]] || { echo "  skip $name (not in working copy)"; return 0; }
    sync_tree "$s" "$dst" --delete
    echo "  $name: $(find "$dst" -maxdepth 1 -type f | wc -l | tr -d ' ') files"
}

echo "Populating substrate tree $DEST_ROOT from the working copy:"
copy_subtree System
copy_subtree Textures
copy_subtree Sounds
copy_subtree Music
[[ "$with_maps" == 1 ]] && copy_subtree Maps

if [[ "$dry_run" == 1 ]]; then
    echo "Dry run only — nothing written."
    exit 0
fi

# Quick sanity report + the ACE-has-no-music caveat.
echo "Done. Present now under $DEST_ROOT:"
for sub_ext in "System:u" "Textures:utx" "Sounds:uax" "Music:umx" "Maps:dx"; do
    sub="${sub_ext%%:*}"; ext="${sub_ext##*:}"
    # `|| true`: a subtree with zero matches makes the glob literal and `ls` exit non-zero, which
    # pipefail would propagate and `set -e` would treat as a fatal error mid-report. Not fatal here.
    n=$(ls "$DEST_ROOT/$sub"/*."$ext" 2>/dev/null | wc -l | tr -d ' ') || true
    printf "  %-9s %s .%s\n" "$sub" "$n" "$ext"
done
if [[ -n "$ace_src" ]] && ! ls "$DEST_ROOT/Music"/*.umx >/dev/null 2>&1; then
    echo "note: no .umx music — the retail ACE ships none (dev/docs/deusex-assets-setup.md). Add" >&2
    echo "      Music/*.umx from another source into $WORKING_COPY/Music and re-run if you need it." >&2
fi
echo
echo "Working game copy: $WORKING_COPY   (full, gitignored)"
echo "Substrate tree is the v68 install source for stub-building + texture sync; uedctl mounts it"
echo "per-command (no container restart needed). See dev/docs/deusex-assets-setup.md."
