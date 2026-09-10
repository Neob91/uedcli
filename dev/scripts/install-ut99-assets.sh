#!/usr/bin/env bash
# Set up a complete, working UnrealTournament (1999/GOTY) install for uedcli — end to end — from a
# source you supply.
#
# You supply the game EITHER as a local <SOURCE> directory OR as one or more --url downloads:
#   1. Assembles a full working game copy under  dev/games/<game>/   (default <game>=ut99).
#        - an installed game (has System/ + Textures/) -> copy the whole tree.
#        - a CD-ISO image  (has System/ + Textures/ at its top level, same as an install) -> unpack,
#          then treat the result as an installed game.
#        - with --url -> download, unpack, then treat the result as one of the above.
#   2. Populates a staging tree  uned/UT99Assets/  FROM that working copy — the same curated subset
#      uned/DeusExAssets carries for Deus Ex: System/ (the stock GOTY CD's `.u` code) + Textures/
#      *.utx, Sounds/ *.uax, Music/ *.umx (content), + Maps/ *.unr[.uz] with --with-maps. NOTHING IN
#      uedcli READS uned/UT99Assets/ YET — no project/substrate config points at it (only Deus Ex is
#      wired up today) — this script only stages the tree; wiring it in is separate, later work.
#
# Everything written here is UnrealTournament game content. BOTH dev/games/ and uned/UT99Assets/ are
# gitignored and NEVER committed.
#
# Run with NO ARGUMENTS to install fully autonomously: with neither a <SOURCE> nor a --url, it
# defaults to the archive.org mirror of the retail UT Game of the Year Edition CD1 (DEFAULT_URL
# below), verified against a pinned checksum (DEFAULT_SHA256; matches the MD5 OldUnreal's own
# official installer expects for this exact file, cross-checked when this default was pinned — see
# DEFAULT_SHA256 below). OldUnreal's own installer (github.com/OldUnreal/FullGameInstallers) uses
# this same archive.org item as its own download source, and Epic approved free redistribution of
# the UT GOTY disc image (archive.org, Nov 2024) — but you are responsible for having the right to
# whatever copy you install; override the default with your own <SOURCE> or --url if you'd rather
# supply your own (a disc you own, GOG, etc).
#
# Unpacking a download ALWAYS runs in the `uedcli-unpack` container (built once, on demand, shared
# with install-deusex-assets.sh), on every host, whether or not the host has the tool — one code
# path, one set of tool versions.
#
# NOT DONE HERE (both are real gaps, left for you or a follow-up run, matching this script's own
# "smallest change" scope):
#   - OldUnreal's own compatibility patch. This installs the STOCK 1999/2000 GOTY CD build; OldUnreal's
#     official installer additionally fetches and applies a patch from
#     github.com/OldUnreal/UnrealTournamentPatches after the base install. Apply it yourself if you
#     need a modern-patched build.
#   - Map decompression. The GOTY CD ships most Maps/*.unr as *.unr.uz (UT's own compression); this
#     script copies them as-is with --with-maps. Decompressing needs `ucc.exe decompress` (a Windows
#     binary) — not run here. System/Textures/Sounds/Music (what asset resolution actually needs) are
#     NOT compressed on the CD, so this only affects --with-maps.
#
# Usage:
#   dev/scripts/install-ut99-assets.sh [--game <name>] [--with-maps] [--dry-run]
#       (no SOURCE/--url -> the built-in DEFAULT_URL, autonomous)
#   dev/scripts/install-ut99-assets.sh [--game <name>] [--with-maps] [--dry-run] <SOURCE>
#   dev/scripts/install-ut99-assets.sh [--game <name>] [--with-maps] [--dry-run] \
#       --url <URL> [--url <URL>…] [--sha256 <SUM>…] [--redownload]
#
# <SOURCE> is the install ROOT (dir CONTAINING System/, Textures/, …) — an installed game or an
# already-extracted CD-ISO. Subdir names are matched case-insensitively (Windows installs vary).
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
# dev/scripts/): the working copy under dev/games/, and the substrate tree at uned/UT99Assets/.
GAMES_PARENT="$(cd "$SELF_DIR/.." && pwd)/games"          # Tools/uedcli/dev/games
DEST_ROOT="$(cd "$SELF_DIR/../.." && pwd)/uned/UT99Assets"

# Print the header comment block (everything after the shebang up to the first non-comment line),
# stripping the leading "# " — robust to the header's length changing.
usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,"");print;next} {exit}' "${BASH_SOURCE[0]}"; }

game="ut99"
with_maps=0
dry_run=0
src=""
redownload=0
urls=()
sums=()

# Built-in default source — fires only when NO <SOURCE> and NO --url are given (autonomous run; see
# the header's rights note). The archive.org mirror of the retail UT GOTY CD1 (a plain ISO9660 image,
# ~620 MB) with a pinned checksum so the built-in download is verified, not blind. Override with
# <SOURCE> or --url.
DEFAULT_URL='https://archive.org/download/ut-goty/UT_GOTY_CD1.iso'
# sha256, computed directly from the file. Cross-checked against OldUnreal's own installer's
# expected md5 for this exact file (e5127537f44086f5ed36a9d29f992c00, from its install.php) so the
# trust chain is re-derivable without re-fetching 620 MB.
DEFAULT_SHA256='e184984ca88f001c5ddd52035d76cd64e266e26c74975161b5ed72366c74704f'

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
# The download/unpack scratch lives OUTSIDE the working copy, not under it — same reasoning as
# install-deusex-assets.sh: step 1 syncs the discovered install root INTO $WORKING_COPY with
# rsync --delete, and a scratch dir inside the destination would get wiped mid-copy.
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

# $DEST_ROOT may be a SYMLINK to wherever the operator keeps the game (same convention as
# uned/DeusExAssets). A symlink whose target is gone still passes `-e`-style existence checks yet
# makes `mkdir -p` fail with a bare "File exists" — name it here, before any work happens.
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
        # is what makes the no-rsync path mean the same thing as the rsync one — see
        # install-deusex-assets.sh's sync_tree for the failure mode this guards.
        if [[ -n "$del" && -d "$d" ]]; then
            find "$d" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
        fi
        mkdir -p "$d"
        cp -a "$s"/. "$d"/
    fi
}

# --- Step 0 (only with --url): fetch, unpack, and find the install root ------------------------

# A tool this step needs but the host lacks is a CLEAN exit naming the tool and how to get it —
# never a half-unpacked tree.
need_tool() {  # <command> <apt-package> <what-for>
    command -v "$1" >/dev/null 2>&1 && return 0
    echo "error: '$1' is required to $3 but is not installed." >&2
    echo "       Install it (e.g. 'apt-get install $2') and re-run, or unpack the download" >&2
    echo "       yourself and point <SOURCE> at the resulting install root instead." >&2
    exit 2
}

# Every unpack runs in this image — always, on every host, whether or not the host has the tool.
# SAME image install-deusex-assets.sh builds (uedcli-unpack:latest): shared, built once, cached.
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
    # SAME name, SAME Dockerfile as install-deusex-assets.sh's copy — whichever script runs first
    # builds it and the other reuses it (docker image inspect short-circuits above). Keep the two
    # Dockerfile blocks identical, or the second build silently wins with a different tool set.
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
# the workdir set to match, so the argv means the same inside the container as out.
run_unpacker() {  # <workdir> <mount-dir>… -- <command> [args…]
    local wd="$1" mounts=(); shift
    while [[ $# -gt 0 && "$1" != "--" ]]; do mounts+=(-v "$1:$1"); shift; done
    shift  # the --
    ensure_unpack_image
    docker run --rm --platform=linux/amd64 --user "$(id -u):$(id -g)" \
               "${mounts[@]}" -w "$wd" "$UNPACK_IMAGE" "$@"
}

# The filename to save a URL under: its last path segment, with any ?query/#fragment stripped.
url_filename() {  # <url>
    local n="${1%%[?#]*}"
    n="${n##*/}"
    printf '%s' "$n"
}

download_one() {  # <url> <dest> <expected-sha256-or-empty>
    local url="$1" dest="$2" want="$3" resume=()
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

# Unpack one artifact into $UNPACK_DIR, dispatching on its name.
unpack_one() {  # <file>
    local f="$1" base low
    base="$(basename "$f")"
    low="$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]')"
    case "$low" in
        # A companion volume belonging to ANOTHER artifact (a numbered split part). Its own
        # unpacker reads it directly from the download dir, so it is not unpacked here.
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
        # The default source is an .iso (a plain ISO9660 CD image — the UT GOTY CD is NOT an
        # InstallShield CAB set, unlike some later Unreal-engine titles; 7z reads it directly).
        *.7z|*.iso)   run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- 7z x -y -o"$UNPACK_DIR" "$f" >/dev/null ;;
        *.rar)        run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- unrar x -y "$f" "$UNPACK_DIR/" >/dev/null ;;
        *.exe)
            echo "  $base: unpacking as an Inno Setup installer"
            run_unpacker "$UNPACK_DIR" "$CACHE_DIR" -- innoextract -e -s -q "$f" || {
                echo "error: innoextract could not unpack $base." >&2
                echo "       Only Inno Setup installers are supported here. OldUnreal's own" >&2
                echo "       FullGameInstallers .exe releases are NOT Inno Setup — they are an" >&2
                echo "       NSIS wrapper that DOWNLOADS the real game ISO at install time (this is" >&2
                echo "       exactly why DEFAULT_URL points at that ISO directly, not the .exe). For" >&2
                echo "       any other installer, run it (or unpack it) yourself and point <SOURCE>" >&2
                echo "       at the resulting install root." >&2
                exit 2
            } ;;
        *)
            echo "error: don't know how to unpack '$base'." >&2
            echo "       Supported: .tar[.gz|.bz2|.xz|.zst], .zip, .7z, .iso, .rar, and Inno Setup" >&2
            echo "       .exe. Unpack it yourself and pass <SOURCE> instead." >&2
            exit 2 ;;
    esac
}

# Every candidate install root inside an unpacked tree — a dir holding System/ + Textures/ —
# printed as `depth<TAB>path`, SHALLOWEST first. Installers/CD images commonly nest one level; this
# searches rather than assuming the top.
#
# Depth-ordered, not byte-ordered: an archive can hold a second install-ish tree, and plain `sort`
# would pick a DEEP child of an early-sorting directory over the real top-level install.
discover_source_roots() {  # <dir> -> prints `depth<TAB>path` lines, shallowest first
    local root="$1" line depth d
    while IFS= read -r line; do
        depth="${line%%	*}"; d="${line#*	}"
        if [[ -n "$(find_subdir "$d" System || true)" && \
              -n "$(find_subdir "$d" Textures || true)" ]]; then
            printf '%s\t%s\n' "$depth" "$d"
        fi
    done < <(find "$root" -maxdepth 4 -type d -printf '%d\t%p\n' | sort -k1,1n -k2)
}

# The ONE install root to use, or a clean exit. Two candidates at the same depth is genuine
# ambiguity, and picking one silently is the "partial result the caller mistakes for a complete
# one" that CLAUDE.md forbids, so it names both and stops. A DEEPER candidate is not ambiguous.
pick_source_root() {  # <dir> -> prints the root, or exits 2
    local root="$1" roots shallowest matches
    roots="$(discover_source_roots "$root")"
    if [[ -z "$roots" ]]; then
        echo "error: after unpacking, found no UnrealTournament install root (a dir holding" >&2
        echo "       System/ + Textures/) under $root." >&2
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
        while IFS= read -r m; do
            [[ -n "$m" ]] && echo "         $m" >&2
        done <<< "$matches"
        echo "       Pass <SOURCE> pointing at the one you want instead of --url." >&2
        exit 2
    fi
    printf '%s' "$matches"
}

# Checked even under --dry-run: a dry run whose whole point is "tell me what would happen" must not
# report success on a machine where the real run will refuse.
check_dest_root

if [[ ${#urls[@]} -gt 0 ]]; then
    echo "Fetching ${#urls[@]} artifact(s) into $DOWNLOAD_DIR"
    if [[ "$dry_run" == 1 ]]; then
        for i in "${!urls[@]}"; do
            echo "  would fetch ${urls[$i]}  ->  $DOWNLOAD_DIR/$(url_filename "${urls[$i]}")"
            [[ -n "${sums[$i]:-}" ]] && echo "      verifying sha256 ${sums[$i]}"
        done
        echo "  would unpack into $UNPACK_DIR and locate the install root inside it,"
        echo "  then assemble $WORKING_COPY and populate $DEST_ROOT (with_maps=$with_maps)."
        echo "Dry run only — nothing written. Re-run without --dry-run to fetch."
        exit 0
    else
        need_tool curl curl "download a --url"
        names=()
        for i in "${!urls[@]}"; do
            name="$(url_filename "${urls[$i]}")"
            if [[ -z "$name" ]]; then
                echo "error: cannot derive a filename from URL '${urls[$i]}'." >&2
                echo "       Point --url at a FILE (…/setup.exe, …/game.iso), not a directory." >&2
                exit 2
            fi
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
        # A fresh unpack area every run — otherwise an artifact left by a PREVIOUS run stays here,
        # gets re-unpacked, and can win install-root discovery.
        rm -rf "$UNPACK_DIR"
        mkdir -p "$UNPACK_DIR"
        for i in "${!urls[@]}"; do
            download_one "${urls[$i]}" "$DOWNLOAD_DIR/${names[$i]}" "${sums[$i]:-}"
        done
        echo "Unpacking into $UNPACK_DIR"
        for i in "${!names[@]}"; do
            unpack_one "$DOWNLOAD_DIR/${names[$i]}"
        done
        src="$(pick_source_root "$UNPACK_DIR")"
        echo "  install root: $src"
    fi
fi

# --- Step 1: assemble the full working game copy under dev/games/<game>/ -----------------------

install_sys="$(find_subdir "$src" System || true)"
install_tex="$(find_subdir "$src" Textures || true)"

echo "Target working copy : $WORKING_COPY"
echo "Target substrate    : $DEST_ROOT"
echo "Source              : $src   (rsync=$have_rsync, dry_run=$dry_run, with_maps=$with_maps, game=$game)"

if [[ -n "$install_sys" && -n "$install_tex" ]]; then
    echo "SOURCE looks like an installed game (or an extracted CD image)."
    if [[ "$dry_run" == 1 ]]; then
        echo "  would copy the whole install  $src  ->  $WORKING_COPY"
    else
        sync_tree "$src" "$WORKING_COPY" --delete
        echo "  working copy synced -> $WORKING_COPY"
    fi
else
    echo "error: SOURCE '$src' has no System/ + Textures/ — point it at the install ROOT." >&2
    exit 2
fi

# The working copy is now the single source for step 2 (in a dry run it may not exist yet).
wc_sys="$(find_subdir "$WORKING_COPY" System || true)"
if [[ "$dry_run" != 1 ]]; then
    if [[ -z "$wc_sys" ]]; then
        echo "error: no System/ in the working copy $WORKING_COPY after setup — extraction/copy failed." >&2
        exit 2
    fi
    if ! ls "$wc_sys"/[Bb]ot[Pp]ack.u >/dev/null 2>&1; then
        echo "warning: $wc_sys has no BotPack.u (the gameplay package) — is SOURCE a complete install? Continuing anyway." >&2
    fi
fi

# --- Step 2: populate uned/UT99Assets/ from the working copy -----------------------------------

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

# Quick sanity report. Maps counts *.unr* (not just *.unr*): most GOTY-CD maps ship *.unr.uz
# (compressed, see the note below), so a plain *.unr count would misleadingly read near-zero.
echo "Done. Present now under $DEST_ROOT:"
for sub_ext in "System:u" "Textures:utx" "Sounds:uax" "Music:umx"; do
    sub="${sub_ext%%:*}"; ext="${sub_ext##*:}"
    n=$(ls "$DEST_ROOT/$sub"/*."$ext" 2>/dev/null | wc -l | tr -d ' ') || true
    printf "  %-9s %s .%s\n" "$sub" "$n" "$ext"
done
if [[ "$with_maps" == 1 ]]; then
    n=$(ls "$DEST_ROOT/Maps"/*.unr* 2>/dev/null | wc -l | tr -d ' ') || true
    printf "  %-9s %s .unr*\n" "Maps" "$n"
fi
if [[ "$with_maps" == 1 ]] && ls "$DEST_ROOT/Maps"/*.unr.uz >/dev/null 2>&1; then
    n_uz=$(ls "$DEST_ROOT/Maps"/*.unr.uz 2>/dev/null | wc -l | tr -d ' ')
    echo "note: $n_uz map(s) under Maps/ are *.unr.uz (compressed) — decompressing needs" >&2
    echo "      'ucc.exe decompress' (a Windows binary), not run here. See the header note." >&2
fi
echo
echo "Working game copy: $WORKING_COPY   (full, gitignored)"
echo "Substrate tree at $DEST_ROOT is staged (stock GOTY CD build) but not yet wired into uedcli —"
echo "no project/substrate config reads it yet (see the header note)."
