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
# Run with NO ARGUMENTS to install fully autonomously: with neither a <SOURCE> nor a --url, it
# defaults to the archive.org GOTY installer (DEFAULT_URL below) verified against a pinned checksum
# (DEFAULT_SHA256). That archive.org copy is an UNOFFICIAL redistribution of a game still sold: Deus
# Ex is commercial, so YOU are responsible for having the right to the copy you install — a DRM-free
# GOG copy you own, or your own mirror, is the clean case. Override the default by passing a local
# <SOURCE> or your own --url. See dev/docs/deusex-assets-setup.md ("Where to get Deus Ex").
#
# Unpacking a download ALWAYS runs in the `uedcli-unpack` container (built once, on demand), on
# every host, whether or not the host has the tool — one code path, one set of tool versions. So
# Docker is required to unpack a download; an already-extracted <SOURCE> needs neither.
#
# The baseline you want is 1.112fm, the final official build. GOG/Steam and the GOTY Edition already
# ship at 1.112fm, so there is normally nothing to patch — hence no patch step here. If your source
# is an old unpatched retail disc, apply the official patcher to the working copy and re-run.
#
# Usage:
#   dev/scripts/install-deusex-assets.sh [--game <name>] [--with-maps] [--dry-run]
#       (no SOURCE/--url -> the built-in DEFAULT_URL, autonomous)
#   dev/scripts/install-deusex-assets.sh [--game <name>] [--with-maps] [--dry-run] <SOURCE>
#   dev/scripts/install-deusex-assets.sh [--game <name>] [--with-maps] [--dry-run] \
#       --url <URL> [--url <URL>…] [--sha256 <SUM>…] [--redownload]
#
# <SOURCE> is the install ROOT (dir CONTAINING System/, Textures/, …) or the ACE installer dir
# (CONTAINING deusex.ace). Subdir names are matched case-insensitively (Windows installs vary).
# SOURCE and --url are mutually exclusive; with NEITHER, the built-in DEFAULT_URL fires.
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

# Built-in default source — fires only when NO <SOURCE> and NO --url are given (autonomous run; see
# the header's rights note). The archive.org GOTY offline installer (Inno Setup `.exe`, ~398 MB) with
# a pinned checksum so the built-in download is verified, not blind. Override with <SOURCE> or --url.
DEFAULT_URL='https://archive.org/download/deus_ex_goty_16231/setup_deus_ex_goty_1.112fm%28revision_1.3.0.1%29_%2816231%29.exe'
DEFAULT_SHA256='e964cb441474a6d08a3d0d65a30e06e009ff2d33a527ef10391f257a760e3aa6'

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
    # Autonomous run: no source supplied, so use the built-in default (see the header's rights note).
    echo "no <SOURCE> or --url given — using the built-in default: $DEFAULT_URL" >&2
    urls=("$DEFAULT_URL")
    [[ -n "$DEFAULT_SHA256" ]] && sums=("$DEFAULT_SHA256")
fi
if [[ ${#sums[@]} -gt 0 && ${#sums[@]} -ne ${#urls[@]} ]]; then
    echo "error: --sha256 given ${#sums[@]} time(s) for ${#urls[@]} --url(s) — give one per URL, in" >&2
    echo "       the same order, or none at all." >&2
    exit 2
fi
# Reject a download-only flag alongside a local SOURCE rather than accepting and ignoring it: the
# operator asked for something this invocation cannot do, and silence reads as "done".
if [[ -n "$src" && "$redownload" == 1 ]]; then
    echo "error: --redownload applies to --url downloads; SOURCE ($src) is a local path." >&2
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

# Pick the copy engine: rsync (idempotent, shows what changed) if available, else cp -a + an
# explicit wipe to match rsync's --delete (see sync_tree).
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
    if [[ "$have_rsync" == 1 ]]; then
        mkdir -p "$d"
        rsync -a ${del:+--delete} "$s"/ "$d"/
    else
        # `cp -a` MERGES, so it cannot express --delete on its own. Emptying the destination first
        # is what makes the no-rsync path mean the same thing as the rsync one. Without this, a
        # re-run against a DIFFERENT source leaves both sources' files interleaved and exits 0 —
        # e.g. switching from a wrong download to the right one leaves the wrong `.u` in place, and
        # a stale package on the search path is exactly the kind of fault that shows up much later
        # as an inexplicable build.
        if [[ -n "$del" && -d "$d" ]]; then
            find "$d" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
        fi
        mkdir -p "$d"
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

# Every unpack runs in this image — always, on every host, whether or not the host has the tool.
# One code path, one set of tool versions: a host-tool branch would mean the same artifact unpacked
# by different binaries on different machines, which is the environment-switching this project
# forbids. Docker is therefore required to unpack a download; an already-extracted <SOURCE> needs
# neither. Built on first use, then cached.
UNPACK_IMAGE="uedcli-unpack:latest"
unpack_image_ready=0
ensure_unpack_image() {
    [[ "$unpack_image_ready" == 1 ]] && return 0
    command -v docker >/dev/null 2>&1 || {
        echo "error: Docker is required to unpack a download — every unpacker runs in the" >&2
        echo "       $UNPACK_IMAGE container, so there is nothing to install on the host." >&2
        echo "       Install Docker and re-run, or unpack the artifact yourself and point" >&2
        echo "       <SOURCE> at the resulting install root instead." >&2
        exit 2
    }
    if docker image inspect "$UNPACK_IMAGE" >/dev/null 2>&1; then unpack_image_ready=1; return 0; fi
    echo "  building $UNPACK_IMAGE (one-off, then cached)…"
    # amd64 to match the rest of the stack; on arm64 it runs emulated, fine for decompression.
    # unace is non-free, hence the extra components.
    DOCKER_DEFAULT_PLATFORM=linux/amd64 docker build --platform=linux/amd64 -q -t "$UNPACK_IMAGE" - >/dev/null <<'DOCKERFILE'
FROM debian:stable-slim
RUN echo 'deb http://deb.debian.org/debian stable main contrib non-free non-free-firmware' \
        > /etc/apt/sources.list.d/nonfree.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        innoextract p7zip-full unzip unrar-free unace tar gzip bzip2 xz-utils zstd \
    && rm -rf /var/lib/apt/lists/*
DOCKERFILE
    unpack_image_ready=1
}

# Run one unpacker in $UNPACK_IMAGE. Each <mount-dir> is bind-mounted at its OWN absolute path and
# the workdir set to match, so the argv — which names host paths — means the same inside the
# container as out. --user keeps the extracted tree owned by the invoking user, so no chown-back
# pass is needed and the later rsync can read it.
run_unpacker() {  # <workdir> <mount-dir>… -- <command> [args…]
    local wd="$1" mounts=(); shift
    while [[ $# -gt 0 && "$1" != "--" ]]; do mounts+=(-v "$1:$1"); shift; done
    shift  # the --
    ensure_unpack_image
    docker run --rm --platform=linux/amd64 --user "$(id -u):$(id -g)" \
               "${mounts[@]}" -w "$wd" "$UNPACK_IMAGE" "$@"
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
    # A `.part` is only resumable if it is a partial of THIS url. Without that check a leftover
    # from a different URL (or an aborted redirect-to-HTML body) gets appended to and then promoted
    # to $dest as a "complete" download — same size, wrong bytes, and every later run happily
    # reuses it. The url is recorded beside the part; anything else is discarded and refetched.
    local marker="$dest.url"
    if [[ "$redownload" == 1 ]]; then
        rm -f "$dest" "$dest.part" "$marker"
    fi
    if [[ -s "$dest" ]]; then
        echo "  reusing $(basename "$dest") (already downloaded; --redownload to refetch)"
    else
        if [[ -s "$dest.part" ]]; then
            if [[ -f "$marker" && "$(cat "$marker")" == "$url" ]]; then
                resume=(-C -)
                echo "  resuming $(basename "$dest")"
            else
                echo "  discarding an unrelated partial $(basename "$dest").part"
                rm -f "$dest.part"
            fi
        fi
        printf '%s' "$url" > "$marker"
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
            echo "       url      $url" >&2
            echo "       Either the download is corrupt or it is not the file you expected. It is" >&2
            echo "       kept at $dest for inspection; re-run with --redownload to refetch it." >&2
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
            # Not extracted here — the ACE branch below is the single place `unace` is driven. It is
            # SYMLINKED into the (freshly emptied) unpack dir so that branch and install-root
            # discovery see only THIS run's volumes, not every ACE any earlier run fetched.
            ln -sf "$f" "$UNPACK_DIR/$base"
            echo "  $base: ACE volume, staged for the ACE step" ;;
        # A payload volume belonging to ANOTHER artifact: a GOG installer's `setup_x-1.bin`, or a
        # numbered split part. Its own unpacker reads it directly from the download dir, so it is
        # not unpacked here — and it must not be an error, or the documented multi-part fetch could
        # never work (the glob visits `-1.bin` before the `.exe` that consumes it).
        *.bin|*.[0-9][0-9][0-9]|*.z[0-9][0-9]|*.r[0-9][0-9]|*.part[0-9]*.rar)
            echo "  $base: companion volume, left for its own unpacker" ;;
        *.tar)        run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- tar -xf "$f" -C "$UNPACK_DIR" ;;
        *.tar.gz|*.tgz)
            run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- tar -xzf "$f" -C "$UNPACK_DIR" ;;
        *.tar.bz2|*.tbz2)
            run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- tar -xjf "$f" -C "$UNPACK_DIR" ;;
        *.tar.xz|*.txz)
            run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- tar -xJf "$f" -C "$UNPACK_DIR" ;;
        *.tar.zst)
            run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- tar --zstd -xf "$f" -C "$UNPACK_DIR" ;;
        *.zip)        run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- unzip -q -o "$f" -d "$UNPACK_DIR" ;;
        *.7z|*.iso)   run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- 7z x -y -o"$UNPACK_DIR" "$f" >/dev/null ;;
        *.rar)        run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- unrar x -y "$f" "$UNPACK_DIR/" >/dev/null ;;
        *.exe)
            # A GOG offline installer is Inno Setup, which innoextract unpacks. Other Windows
            # installers (InstallShield, NSIS) are NOT handled — say so rather than producing a
            # subtly incomplete tree.
            echo "  $base: unpacking as an Inno Setup installer"
            run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- innoextract -e -s -q "$f" || {
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

# Every candidate install root inside an unpacked tree — a dir holding System/ + Textures/, or an
# ACE volume set — printed as `depth<TAB>path`, SHALLOWEST first. Installers commonly nest one or two
# levels ("app/", "Deus Ex GOTY/"), so this searches rather than assuming the top.
#
# Depth-ordered, not byte-ordered: an archive can hold a second install-ish tree (a demo, an extras
# dir), and plain `sort` would pick a DEEP child of an early-sorting directory over the real
# top-level install.
discover_source_roots() {  # <dir> -> prints `depth<TAB>path` lines, shallowest first
    local root="$1" line depth d f
    while IFS= read -r line; do
        depth="${line%%	*}"; d="${line#*	}"
        if [[ -n "$(find_subdir "$d" System || true)" && \
              -n "$(find_subdir "$d" Textures || true)" ]]; then
            printf '%s\t%s\n' "$depth" "$d"; continue
        fi
        for f in "$d"/*.[aA][cC][eE]; do
            [[ -e "$f" ]] && { printf '%s\t%s\n' "$depth" "$d"; break; }
        done
    done < <(find "$root" -maxdepth 4 -type d -printf '%d\t%p\n' | sort -k1,1n -k2)
}

# The ONE install root to use, or a clean exit. Two candidates at the same depth is genuine
# ambiguity — two games unpacked side by side — and picking one silently is the "partial result the
# caller mistakes for a complete one" that `CLAUDE.md` forbids, so it names both and stops. A DEEPER
# candidate is not ambiguous: it is nested inside or beside the real install (extras, a demo), and
# the shallowest wins.
pick_source_root() {  # <dir> -> prints the root, or exits 2
    local root="$1" roots shallowest matches
    roots="$(discover_source_roots "$root")"
    if [[ -z "$roots" ]]; then
        echo "error: after unpacking, found no Deus Ex install root (a dir holding System/ +" >&2
        echo "       Textures/) and no ACE volume set under $root." >&2
        echo "       The download may be an installer this script cannot unpack, or not a complete" >&2
        echo "       game copy. Inspect that dir (fetched artifacts are kept in $DOWNLOAD_DIR)," >&2
        echo "       then pass <SOURCE> directly." >&2
        exit 2
    fi
    shallowest="$(printf '%s\n' "$roots" | head -n1 | cut -f1)"
    matches="$(printf '%s\n' "$roots" | awk -F'\t' -v d="$shallowest" '$1==d {print $2}')"
    if [[ "$(printf '%s\n' "$matches" | wc -l)" -gt 1 ]]; then
        echo "error: the unpacked download holds MORE THAN ONE install root at the same level, so" >&2
        echo "       which one to install is ambiguous:" >&2
        # Read line by line: a real install dir is often "Deus Ex GOTY", and an unquoted expansion
        # would split each path across three lines.
        while IFS= read -r m; do
            [[ -n "$m" ]] && echo "         $m" >&2
        done <<< "$matches"
        echo "       Pass <SOURCE> pointing at the one you want instead of --url." >&2
        exit 2
    fi
    printf '%s' "$matches"
}

# Checked even under --dry-run: it is a read-only look at the destination, and a dry run whose whole
# point is "tell me what would happen" must not report success on a machine where the real run will
# refuse. (A dangling substrate symlink is exactly that case.)
check_dest_root

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
            # Two URLs can end in the SAME filename (…/a/game.zip and …/b/game.zip). Sharing one
            # destination would make the second "reuse" the first's bytes — one artifact silently
            # never fetched — so a repeat gets an index prefix and the run says so.
            for prev in "${names[@]}"; do
                if [[ "$prev" == "$name" ]]; then
                    name="$i-$name"
                    echo "  note: URL $((i + 1)) repeats the filename '$(url_filename "${urls[$i]}")';"
                    echo "        saving it as '$name' so it does not collide."
                    break
                fi
            done
            names+=("$name")
        done
        mkdir -p "$DOWNLOAD_DIR"
        # A fresh unpack area every run. Otherwise an artifact left by a PREVIOUS run stays here,
        # gets re-unpacked, and can win install-root discovery — installing content from a URL that
        # was not passed this time, with exit 0 and only the `install root:` line as a hint.
        rm -rf "$UNPACK_DIR"
        mkdir -p "$UNPACK_DIR"
        for i in "${!urls[@]}"; do
            download_one "${urls[$i]}" "$DOWNLOAD_DIR/${names[$i]}" "${sums[$i]:-}"
        done
        echo "Unpacking into $UNPACK_DIR"
        # Only THIS run's artifacts, in the order given — never the whole download dir, which also
        # holds everything earlier runs fetched.
        for i in "${!names[@]}"; do
            unpack_one "$DOWNLOAD_DIR/${names[$i]}"
        done
        src="$(pick_source_root "$UNPACK_DIR")"
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
    if [[ "$dry_run" == 1 ]]; then
        echo "  would extract $ace_src  ->  $WORKING_COPY  (unace x, in $UNPACK_IMAGE)"
    else
        mkdir -p "$WORKING_COPY"
        # unace extracts the whole deusex.c00..c52 volume set automatically from deusex.ace. Both
        # ends are mounted: the volumes live under SOURCE, the extracted tree under the working copy.
        run_unpacker "$src" "$src" "$WORKING_COPY" -- \
                     unace x -y "$(basename "$ace_src")" "$WORKING_COPY"/
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
