#!/usr/bin/env bash
# Set up a complete, working Deus Ex install for uedcli — end to end — from a source you supply.
#
# You supply the game EITHER as a local <SOURCE> directory OR as one or more --url downloads:
#   1. Assembles a full working game copy under  dev/games/<game>/   (default <game>=deusex).
#        - a raw ACE installer  (has deusex.ace + deusex.c00..) -> extract with `unace x`.
#        - an installed game    (has System/ + Textures/)       -> copy the whole tree.
#        - with --url           -> download, unpack, then treat the result as one of the above.
#   2. Populates the uedcli substrate asset tree  uned/DeusExAssets/  FROM that working copy — the
#      curated subset the editor/build containers mount: System/ (v68 `.u` code, for stubbing) +
#      Textures/ *.utx, Sounds/ *.uax, Music/ *.umx (content), + Maps/ *.dx with --with-maps.
#
# Everything written is copyrighted Deus Ex content. BOTH dev/games/ and uned/DeusExAssets/ are
# gitignored and NEVER committed.
#
# NO SOURCE IS BUILT IN. `--url` fetches whatever URL YOU pass and nothing else; there is no default,
# no bundled list, and no lookup. Deus Ex is a commercial game still sold today, so YOU are
# responsible for having the right to the copy you point this at — a DRM-free GOG copy you own, or
# your own mirror of it, is the clean case. See dev/docs/deusex-assets-setup.md ("Where to get
# Deus Ex") for the options and what is known about each.
#
# The baseline you want is 1.112fm, the final official build. GOG/Steam and the GOTY Edition already
# ship at 1.112fm, so there is normally nothing to patch — hence no patch step here. If your source
# is an old unpatched retail disc, apply the official patcher to the working copy and re-run.
#
# Usage:
#   dev/scripts/install-deusex-assets.sh [--game <name>] [--with-maps] [--dry-run] <SOURCE>
#   dev/scripts/install-deusex-assets.sh [--game <name>] [--with-maps] [--dry-run] \
#       --url <URL> [--url <URL>…] [--sha256 <SUM>…] [--redownload]
#
# <SOURCE> is the install ROOT (dir CONTAINING System/, Textures/, …) or the ACE installer dir
# (CONTAINING deusex.ace). Subdir names are matched case-insensitively (Windows installs vary).
# SOURCE and --url are mutually exclusive; exactly one is required.
#
# --url may be repeated (a multi-part download; ALL parts land in one dir before unpacking).
# --sha256 verifies a download, positionally matched to the --url of the same index; give it for
#   every URL or none. Unverified downloads are allowed but reported as such.
# --redownload refetches even when the file is already present (default: reuse, resume a partial).
# Re-runnable throughout: it syncs, so running again only copies what changed.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Both destinations are anchored relative to the tool root, NOT beside this script (it lives in
# dev/scripts/): the working copy under dev/games/, and the substrate tree at uned/DeusExAssets/
# (the latter fixed by code in tool_assets.py `uned_dir()`). `cd` only into always-present dirs
# (dev/, the tool root) and append the leaf as a string — the leaf dirs are created later.
GAMES_PARENT="$(cd "$SELF_DIR/.." && pwd)/games"          # Tools/uedcli/dev/games
DEST_ROOT="$(cd "$SELF_DIR/../.." && pwd)/uned/DeusExAssets"

# Print the header comment block (everything after the shebang up to the first non-comment line),
# stripping the leading "# " — robust to the header's length changing.
usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,"");print;next} {exit}' "${BASH_SOURCE[0]}"; }

game="deusex"
with_maps=0
dry_run=0
src=""
redownload=0
urls=()
sums=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --game)      shift; [[ $# -ge 1 ]] || { echo "error: --game needs a value" >&2; exit 2; }
                     game="$1" ;;
        --url)       shift; [[ $# -ge 1 ]] || { echo "error: --url needs a value" >&2; exit 2; }
                     urls+=("$1") ;;
        --sha256)    shift; [[ $# -ge 1 ]] || { echo "error: --sha256 needs a value" >&2; exit 2; }
                     sums+=("$1") ;;
        --redownload) redownload=1 ;;
        --with-maps) with_maps=1 ;;
        --dry-run)   dry_run=1 ;;
        -h|--help)   usage; exit 0 ;;
        -*)          echo "unknown option: $1" >&2; exit 2 ;;
        *)           [[ -z "$src" ]] || { echo "error: unexpected extra argument: $1 (SOURCE already set to $src)" >&2; exit 2; }
                     src="$1" ;;
    esac
    shift
done

# SOURCE and --url are two ways to say the same thing, so requiring exactly one keeps it obvious
# which supplied the bytes — and stops a stray path silently winning over a --url (or the reverse).
if [[ ${#urls[@]} -gt 0 && -n "$src" ]]; then
    echo "error: pass EITHER <SOURCE> ($src) OR --url, not both." >&2
    exit 2
fi
if [[ ${#urls[@]} -eq 0 && -z "$src" ]]; then
    echo "error: missing source — give a <SOURCE> directory (an installed Deus Ex or a raw ACE" >&2
    echo "       installer) or one or more --url downloads. Run with --help." >&2
    exit 2
fi
if [[ ${#sums[@]} -gt 0 && ${#sums[@]} -ne ${#urls[@]} ]]; then
    echo "error: --sha256 given ${#sums[@]} time(s) for ${#urls[@]} --url(s) — give one per URL, in" >&2
    echo "       the same order, or none at all." >&2
    exit 2
fi
if [[ -n "$src" && ! -d "$src" ]]; then
    echo "error: SOURCE is not a directory: $src" >&2
    exit 2
fi

WORKING_COPY="$GAMES_PARENT/$game"
# The download/unpack scratch lives OUTSIDE the working copy, not under it. Step 1 syncs the
# discovered install root INTO $WORKING_COPY with rsync --delete; if the scratch sat inside the
# destination, that sync would be reading from a tree it is simultaneously deleting — it would wipe
# the download cache mid-copy (and with it the artifact being unpacked).
CACHE_DIR="$GAMES_PARENT/.cache/$game"
DOWNLOAD_DIR="$CACHE_DIR/download"         # fetched artifacts, kept so a re-run needn't refetch
UNPACK_DIR="$CACHE_DIR/unpacked"           # what they unpack to, before the install root is found

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

# $DEST_ROOT is commonly a SYMLINK to wherever the operator keeps the game. A symlink whose target
# is gone still passes `-e`-style existence checks yet makes `mkdir -p` fail with a bare
# "File exists", which reads as a permissions problem rather than the real one — so name it here,
# before any work happens. (This bites when a repo carrying such a symlink is used on a second
# machine, where the absolute target does not exist.)
check_dest_root() {
    if [[ -L "$DEST_ROOT" && ! -e "$DEST_ROOT" ]]; then
        echo "error: $DEST_ROOT is a symlink whose target does not exist:" >&2
        echo "         -> $(readlink "$DEST_ROOT")" >&2
        echo "       That path is not present on this machine. Point the symlink at this machine's" >&2
        echo "       copy, or remove it so this script can create a real directory there." >&2
        exit 2
    fi
    if [[ -e "$DEST_ROOT" && ! -d "$DEST_ROOT" ]]; then
        echo "error: $DEST_ROOT exists but is not a directory — remove it and re-run." >&2
        exit 2
    fi
}

sync_tree() {  # <src-dir> <dst-dir> [--delete]
    local s="$1" d="$2" del="${3:-}"
    mkdir -p "$d"
    if [[ "$have_rsync" == 1 ]]; then
        rsync -a ${del:+--delete} "$s"/ "$d"/
    else
        cp -a "$s"/. "$d"/
    fi
}

# --- Step 0 (only with --url): fetch, unpack, and find the install root ------------------------

# A tool this step needs but the host lacks is a CLEAN exit naming the tool and how to get it —
# never a half-unpacked tree. `$2` is the apt package (usually, but not always, the command name).
need_tool() {  # <command> <apt-package> <what-for>
    command -v "$1" >/dev/null 2>&1 && return 0
    echo "error: '$1' is required to $3 but is not installed." >&2
    echo "       Install it (e.g. 'apt-get install $2') and re-run, or unpack the download" >&2
    echo "       yourself and point <SOURCE> at the resulting install root instead." >&2
    exit 2
}

# The filename to save a URL under: its last path segment, with any ?query/#fragment stripped.
# A URL that yields no usable name (a bare directory URL) is rejected rather than guessed at.
url_filename() {  # <url>
    local n="${1%%[?#]*}"
    n="${n##*/}"
    printf '%s' "$n"
}

download_one() {  # <url> <dest> <expected-sha256-or-empty>
    local url="$1" dest="$2" want="$3" resume=()
    if [[ -s "$dest" && "$redownload" != 1 ]]; then
        echo "  reusing $(basename "$dest") (already downloaded; --redownload to refetch)"
    else
        [[ "$redownload" == 1 ]] && rm -f "$dest" "$dest.part"
        # Resume only when a partial exists: `-C -` on a fresh file makes some servers 416.
        [[ -s "$dest.part" ]] && resume=(-C -)
        echo "  fetching $url"
        curl -fL --retry 3 --retry-delay 2 --progress-bar "${resume[@]}" \
             -o "$dest.part" "$url"
        mv "$dest.part" "$dest"
    fi
    if [[ -n "$want" ]]; then
        need_tool sha256sum coreutils "verify a --sha256"
        local got; got="$(sha256sum "$dest" | cut -d' ' -f1)"
        if [[ "$got" != "$want" ]]; then
            echo "error: $(basename "$dest") failed its --sha256 check." >&2
            echo "       expected $want" >&2
            echo "       got      $got" >&2
            echo "       The download is corrupt or is not the file you expected; it has been kept" >&2
            echo "       at $dest for inspection. Delete it and re-run to refetch." >&2
            exit 2
        fi
        echo "    sha256 ok"
    else
        echo "    (no --sha256 given — content NOT verified)"
    fi
}

# Unpack one artifact into $UNPACK_DIR, dispatching on its name. An ACE volume set is deliberately
# NOT unpacked here: the existing ACE branch below already handles a directory of them, so it stays
# the single place `unace` is driven.
unpack_one() {  # <file>
    local f="$1" base low
    base="$(basename "$f")"
    low="$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]')"
    case "$low" in
        *.ace|*.c[0-9][0-9])
            echo "  $base: ACE volume, left for the ACE step" ;;
        *.tar)        need_tool tar tar "unpack $base";  tar -xf "$f" -C "$UNPACK_DIR" ;;
        *.tar.gz|*.tgz)   need_tool tar tar "unpack $base";  tar -xzf "$f" -C "$UNPACK_DIR" ;;
        *.tar.bz2|*.tbz2) need_tool tar tar "unpack $base";  tar -xjf "$f" -C "$UNPACK_DIR" ;;
        *.tar.xz|*.txz)   need_tool tar tar "unpack $base";  tar -xJf "$f" -C "$UNPACK_DIR" ;;
        *.tar.zst)    need_tool tar tar "unpack $base";  tar --zstd -xf "$f" -C "$UNPACK_DIR" ;;
        *.zip)        need_tool unzip unzip "unpack $base"; unzip -q -o "$f" -d "$UNPACK_DIR" ;;
        *.7z|*.iso)   need_tool 7z p7zip-full "unpack $base"; 7z x -y -o"$UNPACK_DIR" "$f" >/dev/null ;;
        *.rar)        need_tool unrar unrar "unpack $base"; unrar x -y "$f" "$UNPACK_DIR/" >/dev/null ;;
        *.exe)
            # A GOG offline installer is Inno Setup, which innoextract unpacks natively. Other
            # Windows installers (InstallShield, NSIS) are NOT handled — say so rather than
            # producing a subtly incomplete tree.
            need_tool innoextract innoextract "unpack the Windows installer $base"
            echo "  $base: unpacking as an Inno Setup installer"
            ( cd "$UNPACK_DIR" && innoextract -e -s -q "$f" ) || {
                echo "error: innoextract could not unpack $base." >&2
                echo "       Only Inno Setup installers (e.g. GOG offline installers) are supported" >&2
                echo "       here. For any other installer, run it (or unpack it) yourself and point" >&2
                echo "       <SOURCE> at the resulting install root." >&2
                exit 2
            } ;;
        *)
            echo "error: don't know how to unpack '$base'." >&2
            echo "       Supported: .ace volume sets, .tar[.gz|.bz2|.xz|.zst], .zip, .7z, .iso," >&2
            echo "       .rar, and Inno Setup .exe. Unpack it yourself and pass <SOURCE> instead." >&2
            exit 2 ;;
    esac
}

# The install root inside an unpacked tree: the shallowest dir holding System/ + Textures/, or an
# ACE volume set. Installers commonly nest one or two levels ("app/", "Deus Ex GOTY/"), so this
# searches rather than assuming the top.
discover_source_root() {  # <dir> -> prints the root, or nothing
    local root="$1" d
    while IFS= read -r d; do
        if [[ -n "$(find_subdir "$d" System || true)" && \
              -n "$(find_subdir "$d" Textures || true)" ]]; then
            printf '%s' "$d"; return 0
        fi
        # An ACE set anywhere in the tree also counts — the ACE branch takes it from here.
        local f
        for f in "$d"/*.[aA][cC][eE]; do
            [[ -e "$f" ]] && { printf '%s' "$d"; return 0; }
        done
    done < <(find "$root" -maxdepth 4 -type d | sort)
    return 1
}

[[ "$dry_run" == 1 ]] || check_dest_root

if [[ ${#urls[@]} -gt 0 ]]; then
    echo "Fetching ${#urls[@]} artifact(s) into $DOWNLOAD_DIR"
    echo "  NOTE: this downloads exactly the URL(s) you passed. Deus Ex is a commercial game still"
    echo "        sold today — you are responsible for having the right to this copy."
    if [[ "$dry_run" == 1 ]]; then
        for i in "${!urls[@]}"; do
            echo "  would fetch ${urls[$i]}  ->  $DOWNLOAD_DIR/$(url_filename "${urls[$i]}")"
            [[ -n "${sums[$i]:-}" ]] && echo "      verifying sha256 ${sums[$i]}"
        done
        echo "  would unpack into $UNPACK_DIR and locate the install root inside it,"
        echo "  then assemble $WORKING_COPY and populate $DEST_ROOT (with_maps=$with_maps)."
        # Everything past this point branches on what the download actually CONTAINS (an install
        # tree vs an ACE set), which a dry run has not fetched — so stop here rather than report a
        # plan derived from an empty source.
        echo "Dry run only — nothing written. Re-run without --dry-run to fetch."
        exit 0
    else
        need_tool curl curl "download a --url"
        # Derive every filename FIRST, so a malformed URL fails before any directory is created or
        # any byte is fetched.
        names=()
        for i in "${!urls[@]}"; do
            name="$(url_filename "${urls[$i]}")"
            if [[ -z "$name" ]]; then
                echo "error: cannot derive a filename from URL '${urls[$i]}'." >&2
                echo "       Point --url at a FILE (…/setup.exe, …/game.zip), not a directory." >&2
                exit 2
            fi
            names+=("$name")
        done
        mkdir -p "$DOWNLOAD_DIR" "$UNPACK_DIR"
        for i in "${!urls[@]}"; do
            download_one "${urls[$i]}" "$DOWNLOAD_DIR/${names[$i]}" "${sums[$i]:-}"
        done
        echo "Unpacking into $UNPACK_DIR"
        for f in "$DOWNLOAD_DIR"/*; do
            [[ -f "$f" ]] || continue
            case "$f" in *.part) continue ;; esac
            unpack_one "$f"
        done
        # An ACE set was left in the download dir, so that is where the install root may be.
        src="$(discover_source_root "$UNPACK_DIR" || discover_source_root "$DOWNLOAD_DIR" || true)"
        if [[ -z "$src" ]]; then
            echo "error: after unpacking, found no Deus Ex install root (a dir with System/ +" >&2
            echo "       Textures/) and no ACE volume set under:" >&2
            echo "         $UNPACK_DIR" >&2
            echo "         $DOWNLOAD_DIR" >&2
            echo "       The download may be an installer this script cannot unpack, or not a" >&2
            echo "       complete game copy. Inspect those dirs, then pass <SOURCE> directly." >&2
            exit 2
        fi
        echo "  install root: $src"
    fi
fi

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
echo "Substrate tree is the v68 install source for stub-building + texture sync; uedcli mounts it"
echo "per-command (no container restart needed). See dev/docs/deusex-assets-setup.md."
