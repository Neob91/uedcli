"""`level preview --game` — the faithful in-game backend. Its spec is
`spec-ingame-preview-design.md` in board item `level-preview-game` (gate-folded 2026-07-16),
alongside that item's `plan.md`.

Drives a WARM per-user GAME container (`uedcli-game`, built on demand by
`uedcli/game/build-image.sh`), whose console-spawned TCP link (`UedPreview.u`) freezes and
cleans the world at possession (D9). The host side here is deliberately THIN (spec
2026-07-17 one-exec): the D5 delivered-map naming + `/resources/preview` mount, the reuse
gate (ONE `docker inspect`), and the batch drive (ONE `docker exec` of the in-container
`preview_batch.py`, which does deliver + 3-phase travel + per-shot `PrepareCamera` (settle-
gated) + X-grab, streaming framed PNGs back). No per-op docker exec, no `docker stats`, no
heartbeat — the entrypoint bash watchdog owns idle-death. All waits are bounded; every
failure is a named `GamePreviewError` (→ exit 2, never a traceback).

uplayctl is the REFERENCE DESIGN only (spec D1) — nothing here imports, shells out to,
or shares an image with it."""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

from . import config
from .preview_shots import ResolvedShot, Shot, resolve_pose, shot_filename
from .rotation import deg_to_uu
from .uuid7 import uuid7

GAME_IMAGE = "uedcli-game"
LINK_PORT = 7777
# Host-side pitch clamp (spec §3 gate fold): the engine's own clamp picks the pole by the
# sign of aLookUp, and headless aLookUp==0 clamps an over-range pitch to STRAIGHT DOWN.
PITCH_CLAMP_DEG = 89.9
# Boot budget: the entrypoint's SMART relaunch loop is up to 8 tries; a wedge fast-relaunches
# (~40s), a progressing-but-slow boot gets ~160s. Worst realistic case a few good tries.
BOOT_TIMEOUT_S = 900
TRAVEL_TIMEOUT_S = 480          # cold big-map travel can take minutes (game-boot memory)


class GamePreviewError(Exception):
    """User-facing --game preview failure (→ stderr + exit 2)."""


# The host-side per-substrate table (spec §5 gate fold — the .uc driver seam can't cover
# host concerns: exe/ini names, the boot map, the X-grab window-title pattern).
SUBSTRATES = {
    "deusex": dict(
        exe="DeusEx.exe",
        boot_map="00_Training.dx",           # staged from the game's own Maps dir
        window_title="deus ex",
        window_exclude=("running", "starting", "recovery", "config"),
    ),
}


def _substrate_row(game: str) -> dict:
    row = SUBSTRATES.get(game)
    if row is None:
        raise GamePreviewError(
            f"game {game!r} has no --game preview substrate entry yet (known: "
            f"{', '.join(sorted(SUBSTRATES))}); add its row to preview_game.SUBSTRATES")
    return row


def _run(cmd: list[str], *, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# --------------------------------------------------------------------- delivered-map naming (D5)
# Every map delivered to the game is written under <root>/.uedcli/preview/ with a HASH-named,
# kind-PREFIXED, DOT-FREE, LOWERCASED, length-CAPPED stem (spec §5.1 / decisions 2026-07-17):
#   trunk  → materialized__<level>__<hash12>[__<nonce>].dx   (nonce only on --rebuild)
#   --map  → copied__<contenthash12>.<ext>                   (ext ∈ .dx .unr)
# A unique filename is what forces the running engine to load fresh content (SP-R §8a: package
# identity is filename-derived) — so no interior dot (UE1's Package.Object sep), lowercased (the
# farm link is lowercased; `open` resolves via wine case-folding), non-numeric first segment (the
# prefix), and never a SILENT over-length truncation (a loud error instead — SP-R found names
# resolve to ≥180 chars and fail LOUDLY ~250, so STEM_MAX=120 is safe insurance).
STEM_MAX = 120
PREVIEW_KEEP = 8                                  # newest-N per prefix retained (spec §5.1)


def _lower_slug(s: str) -> str:
    """Lowercase, dot-free, filesystem/FName-safe — collapse any run of other chars to '-'."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _short_nonce() -> str:
    """A short (≤8-char) base32 nonce for --rebuild — a never-resident name → fresh load,
    without blowing the FName budget the way a uuid7/ns-timestamp would (spec §5.1)."""
    return base64.b32encode(os.urandom(5)).decode().rstrip("=").lower()[:8]


def _compose_stem(prefix: str, ident: str, hash12: str, nonce: str | None = None) -> str:
    """`<prefix>__<ident>__<hash12>[__<nonce>]`, guaranteeing hash(+nonce) survive within
    STEM_MAX: an over-long <ident> is replaced by a short hash of itself; if even that can't
    fit, a LOUD error (never a silent truncation that would drop the unique tail)."""
    ident = _lower_slug(ident) or "x"
    tail = "__".join([hash12, *([nonce] if nonce else [])])

    def build(idt: str) -> str:
        return f"{prefix}__{idt}__{tail}"

    stem = build(ident)
    if len(stem) > STEM_MAX:
        room = STEM_MAX - len(build(""))          # chars left for <ident>
        if room < 1:
            raise GamePreviewError(
                f"preview map-name budget exhausted for prefix {prefix!r} (hash/nonce alone "
                f"exceed {STEM_MAX}) — should be impossible; report it")
        stem = build(hashlib.sha256(ident.encode()).hexdigest()[:min(room, 12)])
    return stem


def _preview_dir(project) -> Path:
    """`<root>/.uedcli/preview/` — the delivered-map cache in the self-ignoring state dir
    (created, with its `*` .gitignore, on first use)."""
    return config.state_subdir(project.root, "preview", create=True)


def _prune_prefix(d: Path, prefix: str, *, protect: Path) -> None:
    """Keep the newest PREVIEW_KEEP files whose stem starts with `prefix__`; unlink the rest
    (never the current `protect`). --rebuild nonce variants count as siblings."""
    sibs = sorted((p for p in d.glob(f"{prefix}__*") if p.is_file()),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for p in sibs[PREVIEW_KEEP:]:
        if p != protect:
            p.unlink(missing_ok=True)


def materialized_dx(project, level_name: str, level, *, rebuild: bool) -> Path:
    """Materialize the trunk into `materialized__<level>__<hash12>[__<nonce>].dx` under
    .uedcli/preview/. Reuse the hash-named file iff current AND not --rebuild (--rebuild
    always mints a fresh nonce'd name → guaranteed reload)."""
    from .apply import run_materialize
    from .dispatch import _composed_dirs, _composed_load_set, _schema_resolver_for
    from .normalize import canonical_level_hash

    d = _preview_dir(project)
    h = canonical_level_hash(level)[:12]
    nonce = _short_nonce() if rebuild else None
    target = d / f"{_compose_stem('materialized', level_name, h, nonce)}.dx"
    if target.is_file() and not rebuild:
        target.touch()                            # keep the stable cache newest vs --rebuild nonces (B-L4)
        _prune_prefix(d, "materialized", protect=target)
        return target
    result = run_materialize(level=level, packages=_composed_load_set(project),
                             search_dirs=_composed_dirs(project),
                             schema_resolver=_schema_resolver_for(project),
                             state_dir=config.state_dir(project.root, create=True),
                             out_path=str(target), overwrite=True)
    if result.rc != 0:
        raise GamePreviewError(f"materialize for preview failed: {result.message}")
    _prune_prefix(d, "materialized", protect=target)
    return target


def copied_map(project, map_path: str) -> Path:
    """Copy a prebuilt `--map` file to `copied__<contenthash12>.<ext>` under .uedcli/preview/
    (namespaced so a user `--map` can never clash with an autogenerated `materialized__`
    name — spec §D8). `.dx` and `.unr` only (spec D7)."""
    src = Path(map_path)
    if not src.is_file():
        raise GamePreviewError(f"--map file not found: {map_path}")
    ext = src.suffix.lower()
    if ext not in (".dx", ".unr"):
        raise GamePreviewError(
            f"--map must be a .dx or .unr map file, got {src.suffix!r}: {map_path}")
    d = _preview_dir(project)
    h = hashlib.sha256(src.read_bytes()).hexdigest()[:12]
    # Carry the ext INTO the stem (`copied__<hash>__dx`) so byte-identical `.dx`/`.unr` inputs
    # get distinct, unambiguous stems on the Paths glob (spec §6 / B-L2), not one shared stem.
    target = d / f"copied__{h}__{ext[1:]}{ext}"
    if not target.is_file():
        tmp = d / (target.name + ".tmp")
        shutil.copy2(src, tmp)
        tmp.replace(target)                       # atomic swap into place
    else:
        target.touch()
    _prune_prefix(d, "copied", protect=target)
    return target


def trunk_has_playerstart(level) -> bool:
    """The D8 model-side pre-check for trunk previews (before any boot)."""
    return any((a.cls or "").split(".")[-1] == "PlayerStart" for a in level.actors.values())


# --------------------------------------------------------------------- image build

def _game_source_hash(game_dir: Path) -> str:
    """Hash the image-affecting sources (uscript, Dockerfile, entrypoint, preview_batch.py,
    build-image.sh) — NOT staging/ (build output) or inputs/ (the large, stable toolchain).
    A match means a rebuild would be a no-op, so we can skip `build-image.sh` on the hot path."""
    h = hashlib.sha256()
    files = []
    for sub in ("uscript",):
        files += sorted((game_dir / sub).rglob("*"))
    files += [game_dir / n for n in ("Dockerfile", "game-entrypoint.sh", "preview_batch.py",
                                     "build-image.sh")]
    files += [game_dir.parent / "preview_shots.py"]     # baked into the image (COPY via staging)
    for p in sorted(files):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def ensure_image(project, user_config, row: dict) -> None:
    """Build/refresh the uedcli-game image. FAST-PATH: if the image exists AND the game sources
    are byte-unchanged since the last successful build (host-side hash marker), skip
    `build-image.sh` entirely — a full `docker build` even fully cached costs ~1-2s, which would
    blow the ≤1s warm-preview budget. Named errors for missing toolchain / docker / build failure."""
    game_dir = Path(__file__).parent / "game"
    if not (game_dir / "inputs" / "edit" / "hUCC.exe").is_file():
        raise GamePreviewError(
            f"the v469 UCC toolchain is not provisioned at {game_dir / 'inputs' / 'edit'} — "
            "see uedcli/game/inputs/README.md (user-supplied, gitignored)")

    src = _game_source_hash(game_dir)
    marker = config.user_cache_home() / "game-image.sha256"   # honors $UEDCLI_HOME (review fix)
    if marker.is_file() and marker.read_text().strip() == src:
        return                                          # sources unchanged since last build → skip
        # (no `docker image inspect` here — it costs a ~0.3s round-trip on every warm preview; an
        #  externally-deleted image surfaces at boot as a named `docker run` error, which is rare.)

    dirs = config.composed_search_dirs(project, user_config)
    gsys = _game_system_dir(dirs, row)
    boot = _find_boot_map(dirs, row)
    content = [d for d in dirs if d != gsys]
    try:
        r = _run(["bash", str(game_dir / "build-image.sh"), gsys, boot, *content],
                 timeout=1800)
    except FileNotFoundError:
        raise GamePreviewError("docker/bash unavailable — --game needs the container "
                               "toolchain") from None
    except subprocess.TimeoutExpired:
        raise GamePreviewError("uedcli-game image build timed out (30 min)") from None
    if r.returncode != 0:
        tail = (r.stdout + r.stderr).strip().splitlines()[-8:]
        raise GamePreviewError("uedcli-game image build failed:\n  " + "\n  ".join(tail))
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(src)
    except OSError:
        pass


def _game_system_dir(dirs: list[str], row: dict) -> str:
    """The composed dir holding the game exe (case-insensitive) — the System code dir."""
    for d in dirs:
        try:
            names = {p.name.lower() for p in Path(d).iterdir()}
        except OSError:
            continue
        if row["exe"].lower() in names:
            return d
    raise GamePreviewError(
        f"no composed config dir contains the game executable {row['exe']!r} — check "
        "~/.uedcli/config.toml [games.*].paths (the game's System dir must be listed)")


def _find_boot_map(dirs: list[str], row: dict) -> str:
    want = row["boot_map"].lower()
    for d in dirs:
        try:
            for p in Path(d).iterdir():
                if p.name.lower() == want:
                    return str(p)
        except OSError:
            continue
    raise GamePreviewError(
        f"boot map {row['boot_map']!r} not found on the composed config paths")


# --------------------------------------------------------------------- container + link

def _novnc(name: str) -> str:
    port = _run(["docker", "port", name, "6080"], timeout=15).stdout
    return port.strip().rsplit(":", 1)[-1] if port.strip() else "?"


def _wait_ready(name: str) -> None:
    """Block until the link port is listening (the entrypoint's relaunch loop handles wine
    boot wedges); rm -f + raise on a boot death or the whole-boot timeout."""
    deadline = time.time() + BOOT_TIMEOUT_S
    while time.time() < deadline:
        chk = _run(["docker", "exec", name, "bash", "-c",
                    f"netstat -ltn 2>/dev/null | grep -q ':{LINK_PORT} ' && echo up"],
                   timeout=30)
        if "up" in chk.stdout:
            return
        if not _run(["docker", "ps", "-q", "-f", f"name=^{name}$"], timeout=15).stdout.strip():
            logs = _run(["docker", "logs", "--tail", "8", name], timeout=15)
            stop_game(name)
            raise GamePreviewError("game container died during boot:\n  "
                                   + logs.stderr.strip() + logs.stdout.strip())
        time.sleep(3)
    stop_game(name)
    raise GamePreviewError(
        f"game link never came up within {BOOT_TIMEOUT_S}s (wine boot wedge beyond the "
        "relaunch budget — retry, or inspect with --keep-alive)")


def _run_game_container(*, name: str, project, user_config, row: dict,
                        size: tuple[int, int], labels: dict[str, str],
                        preview_src: str | None, idle_s: int) -> list:
    """docker-run one game container (ephemeral OR warm) and wait for READY. `preview_src`
    (host .uedcli/preview dir) is bind-mounted read-only at PREVIEW_MOUNT — OUTSIDE the
    `/resources/r*` farm namespace so it never touches the esync-fragile boot enumeration
    (spec §5.2). Returns the resource Mounts."""
    from .container_assets import docker_mount_args, resource_mounts
    dirs = config.composed_search_dirs(project, user_config)
    gsys_host = _game_system_dir(dirs, row)
    mounts = resource_mounts(dirs)
    gsys_container = next(m.container_dir for m in mounts if m.host_dir == gsys_host)
    label_args = [a for k, v in labels.items() for a in ("--label", f"{k}={v}")]
    preview_args = (["-v", f"{os.path.realpath(preview_src)}:{PREVIEW_MOUNT}:ro"]
                    if preview_src else [])
    idle_args = ["-e", f"UED_IDLE_S={idle_s}"] if idle_s else []
    cmd = ["docker", "run", "-d", "--name", name, *label_args, "-e", "LAUNCH_UED=0",
           "-e", f"UED_GAME_SYSTEM={gsys_container}", "-e", f"UED_GAME_EXE={row['exe']}",
           "-e", f"UED_SIZE_X={size[0]}", "-e", f"UED_SIZE_Y={size[1]}", *idle_args,
           "-p", "127.0.0.1::6080", *docker_mount_args(mounts), *preview_args, GAME_IMAGE]
    r = _run(cmd, timeout=120)
    if r.returncode != 0:
        raise GamePreviewError(f"game container failed to start: {r.stderr.strip()}")
    _wait_ready(name)
    return mounts


def start_game(project, user_config, row: dict, size: tuple[int, int]) -> tuple[str, str]:
    """Boot a PER-COMMAND EPHEMERAL game container (no warm reuse, no preview mount). Kept
    for offline spikes/tests; the `--game` render path uses the warm container (§ below)."""
    name = f"uedgame-{uuid7()}"
    _run_game_container(name=name, project=project, user_config=user_config, row=row,
                        size=size, labels={}, preview_src=None, idle_s=0)
    return name, _novnc(name)


def stop_game(name: str) -> None:
    """Best-effort `docker rm -f`, BOUNDED (never hang the lock-held path — reviewer A-H2):
    a wedged rm times out and is swallowed rather than blocking forever."""
    try:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        pass


# ------------------------------------------------------------------- warm container (D1–D3)
# ONE reusable game container per Unix user (`uedcli-game-preview-<uid>`), serialized by a
# per-user flock, self-terminating after idle (the entrypoint bash watchdog). Reuse is gated on a
# fingerprint LABEL read in ONE `docker inspect`; a mismatch reboots fresh (spec §4). The WHOLE
# per-batch drive is ONE `docker exec` of the in-container preview_batch.py (deliver+travel+shots),
# not per-op execs (spec 2026-07-17 one-exec). Idle watchdog + marker live in the entrypoint (kept).
LABEL_FP = "uedcli.preview.fp"
# Bounded flock acquire. Must EXCEED the worst-case legit hold — the whole retry loop under the lock
# (up to REBOOT_BUDGET+1 attempts × a boot + a slow cold-map batch) — so a concurrent invocation
# waits out a healthy holder rather than erroring against it (reviewers M2). 1h; message is non-destructive.
WARM_LOCK_TIMEOUT_S = 3600
IDLE_S = 600                    # entrypoint watchdog kills the container after this idle
REBOOT_BUDGET = 3               # per-batch transparent reboot-retries before giving up
PREVIEW_MOUNT = "/resources/preview"


def _warm_name() -> str:
    return f"uedcli-game-preview-{os.getuid()}"


def _acquire_lock() -> int:
    """Serialize warm-container access with a per-user flock on an open fd (a SIGKILLed
    holder auto-releases). Bounded acquire → a named error, never an unbounded wait. The lock
    lives in the per-user home via `config._user_home()`, so `$UEDCLI_HOME` is honored like
    everything else per-user (spec 2026-07-17 §5)."""
    p = config._user_home() / "game-preview.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.time() + WARM_LOCK_TIMEOUT_S
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.time() > deadline:
                os.close(fd)
                raise GamePreviewError(
                    f"another uedcli --game preview has held the container lock for "
                    f">{WARM_LOCK_TIMEOUT_S//60} min — it is probably still running; retry "
                    f"shortly. Only if you are certain none is running: `docker rm -f "
                    f"{_warm_name()}` and remove {config._user_home() / 'game-preview.lock'}"
                ) from None
            time.sleep(1)


def _release_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _image_id() -> str:
    r = _run(["docker", "image", "inspect", "--format", "{{.Id}}", GAME_IMAGE], timeout=30)
    return r.stdout.strip()


def _overlay_stat(project, user_config) -> list:
    """(path, size, mtime) for the PROJECT-OVERLAY packages only — base game packages are
    immutable so excluded (spec §4.1). A texture/script edit under an existing name → a
    changed tuple → fingerprint mismatch → reboot."""
    exts = (".u", ".dx", ".unr", ".utx", ".uax", ".umx")
    out: list = []
    for d, prov in config._composed_dirs_with_provenance(project, user_config):
        if prov != "project":
            continue
        try:
            for p in sorted(Path(d).iterdir()):
                if p.suffix.lower() in exts and p.is_file():
                    st = p.stat()
                    out.append([str(p), st.st_size, int(st.st_mtime)])
        except OSError:
            continue
    return out


def _fingerprint(mount_pairs: list[str], size: tuple[int, int], project, user_config) -> str:
    blob = json.dumps({"image": _image_id(), "mounts": mount_pairs, "size": list(size),
                       "overlay": _overlay_stat(project, user_config)}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _mount_pairs(mounts, preview_src: str) -> list[str]:
    pairs = [f"{os.path.realpath(m.host_dir)}:{m.container_dir}" for m in mounts]
    pairs.append(f"{os.path.realpath(preview_src)}:{PREVIEW_MOUNT}")
    return pairs


def _inspect(name: str) -> tuple[bool, str] | None:
    """ONE `docker inspect` → (running, fingerprint-label), or None if no such container.
    Collapses the old ~6 reuse-gate probes (ps/label/stats/ping/…) into a single hot-path call."""
    r = _run(["docker", "inspect", "--format",
              '{{.State.Running}}\t{{index .Config.Labels "' + LABEL_FP + '"}}', name], timeout=15)
    if r.returncode != 0:
        return None
    running, _, fp = r.stdout.strip().partition("\t")
    return running == "true", fp


def _is_pinned(name: str) -> bool:
    return "y" in _run(["docker", "exec", name, "bash", "-c",
                        "[ -e /work/.pinned ] && echo y"], timeout=15).stdout


def _pin(name: str) -> None:
    _run(["docker", "exec", name, "bash", "-c", ": > /work/.pinned"], timeout=15)


def _boot_warm(name: str, fp: str, project, user_config, row, size, preview_src) -> None:
    _run_game_container(name=name, project=project, user_config=user_config, row=row,
                        size=size, labels={LABEL_FP: fp}, preview_src=preview_src, idle_s=IDLE_S)


def acquire_warm_container(project, user_config, row, size) -> tuple[str, str]:
    """Connect-or-create on the reserved-name container, gated by ONE `docker inspect`: reuse iff
    running AND the fingerprint label matches; else (re)boot. A pinned container with a DIFFERENT
    fingerprint errors rather than being clobbered (only checked on mismatch — a rare cold path).
    Caller MUST hold the flock."""
    from .container_assets import resource_mounts
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    preview_src = str(_preview_dir(project))
    fp = _fingerprint(_mount_pairs(mounts, preview_src), size, project, user_config)
    name = _warm_name()

    state = _inspect(name)
    if state is not None:
        running, cur_fp = state
        if running and cur_fp == fp:
            return name, _novnc(name)                   # reuse — the whole hot path is this + run_batch
        if running and cur_fp != fp and _is_pinned(name):
            raise GamePreviewError(
                f"the pinned game-preview container {name} is running with a DIFFERENT config "
                f"(image/mounts/size/overlay changed); release it with `docker rm -f {name}`")
        stop_game(name)                                 # stopped, or fp-mismatch (unpinned) → replace
    _boot_warm(name, fp, project, user_config, row, size, preview_src)
    return name, _novnc(name)


def _parse_frames(data: bytes, expected: int) -> list[bytes]:
    """Parse preview_batch.py's stdout stream: per shot a JSON status line, then iff ok a 4-byte
    big-endian length + the PNG. A `{ok:false}` frame or a malformed/truncated stream raises a NAMED
    error (never a raw `struct.error`/`JSONDecodeError` traceback — reviewer L1); a short count (rc0
    but fewer frames than shots) also raises rather than silently under-delivering."""
    pngs, i, n = [], 0, len(data)
    try:
        while i < n:
            nl = data.find(b"\n", i)
            if nl < 0:
                break
            status = json.loads(data[i:nl] or b"{}")
            i = nl + 1
            if not status.get("ok"):
                raise GamePreviewError("preview batch shot failed: " + str(status.get("err", "?")))
            (ln,) = struct.unpack(">I", data[i:i + 4])
            i += 4
            if i + ln > n:
                raise GamePreviewError("preview batch stream truncated mid-PNG")
            pngs.append(data[i:i + ln])
            i += ln
    except (json.JSONDecodeError, struct.error) as e:
        raise GamePreviewError(f"preview batch stream malformed ({type(e).__name__})") from None
    if len(pngs) != expected:
        raise GamePreviewError(f"preview batch returned {len(pngs)} of {expected} shots")
    return pngs


def run_batch(name: str, req: dict) -> list[bytes]:
    """The WHOLE batch in ONE `docker exec` of the in-container preview_batch.py: JSON request on
    stdin, length-framed PNG stream on stdout. A nonzero exit or a `{ok:false}`/malformed frame raises
    (→ the caller reboot-retries). Bounded timeout must EXCEED the batch's OWN internal worst case
    (travel ~565s + ~90s/shot) so a healthy-but-slow game isn't killed by the host (reviewer M1)."""
    nshots = len(req.get("shots") or req.get("unresolved") or [])
    timeout = 600 + 100 * max(1, nshots) + 60
    proc = _exec_batch(name, req, timeout)
    if proc.returncode != 0:
        # The batch reports its failure in the FIRST stdout {ok:false} frame (err message), not on
        # stderr — surface THAT so the caller's "actor not found ⇒ don't reboot-retry" guard can
        # see it and the user gets a real error, not "no output" (reviewers H1/H2).
        err = _first_batch_error(proc.stdout) or proc.stderr.decode(errors="replace").strip()[-300:]
        raise GamePreviewError(f"preview batch failed: {err or 'no output'}")
    return _parse_frames(proc.stdout, nshots)


def _first_batch_error(data: bytes) -> str:
    """The `err` from the first `{ok:false}` status line in the batch stream, or '' if none."""
    nl = data.find(b"\n")
    if nl < 0:
        return ""
    try:
        status = json.loads(data[:nl] or b"{}")
    except json.JSONDecodeError:
        return ""
    return "" if status.get("ok") else str(status.get("err", ""))


def _exec_batch(name: str, req: dict, timeout: float):
    try:
        return subprocess.run(
            ["docker", "exec", "-i", name, "python3", "/opt/uedpreview/preview_batch.py"],
            input=json.dumps(req).encode(), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise GamePreviewError("preview batch timed out (game wedged?)") from None


def list_actors(*, project, user_config, game: str, map_path: str, cls: str, sample: int) -> str:
    """QUERY mode: travel to a `--map` and print its actors of `cls` (or N evenly-sampled) as
    `Name x y z` lines — for discovering `@actor` refs to compose into preview shots. No screenshots."""
    lock_fd = None
    try:
        row = _substrate_row(game)
        dx = copied_map(project, map_path)
        ensure_image(project, user_config, row)
        req = {"deliver": dx.name, "stem": dx.stem, "rebuild": False,
               "list_class": cls, "sample": int(sample)}
        lock_fd = _acquire_lock()
        budget = REBOOT_BUDGET
        while True:
            container, _ = acquire_warm_container(project, user_config, row, (640, 480))
            proc = _exec_batch(container, req, 700)
            if proc.returncode == 0:
                return proc.stdout.decode(errors="replace")
            budget -= 1
            tail = proc.stderr.decode(errors="replace").strip()
            if proc.returncode == 2 or budget < 0:      # rc 2 = PERMANENT (unknown class) → don't reboot
                raise GamePreviewError(f"list-actors failed: {tail[-300:] or 'no output'}")
            stop_game(container)
    except GamePreviewError:
        raise
    except Exception as e:                              # never a raw traceback (contract: exit-2)
        raise GamePreviewError(f"list-actors failed ({type(e).__name__}: {e})") from e
    finally:
        if lock_fd is not None:
            _release_lock(lock_fd)


# --------------------------------------------------------------------- orchestration

def _resolve_all(shots: list[Shot], level) -> list[ResolvedShot]:
    from .preview_native import NativePreviewError, actor_aim_point
    resolved = []
    for shot in shots:
        try:
            if level is None:
                if isinstance(shot.look, str) or shot.orbit is not None:
                    raise GamePreviewError(
                        "actor-relative shots (look:@/orbit:@) need the trunk — use "
                        "absolute at:/rot:/look:X,Y,Z with --map")
                resolved.append(resolve_pose(shot, lambda n: (_ for _ in ()).throw(KeyError(n))))
            else:
                resolved.append(resolve_pose(shot, lambda n: actor_aim_point(level, n)))
        except (ValueError, NativePreviewError) as e:      # unknown actor / bad pose → named (A-H1)
            raise GamePreviewError(str(e)) from None
    return resolved


def render_shots(*, shots: list[Shot], out_dir: Path, size: tuple[int, int],
                 project, user_config, game: str,
                 level=None, level_name: str | None = None,
                 map_path: str | None = None, rebuild: bool = False,
                 keep_alive: bool = False) -> int:
    """Render every SHOT via the game engine, into the WARM per-user container (reused across
    invocations; spec §4). Trunk mode (`level`+`level_name`) materializes into the hash-named
    preview cache; `--map` copies a prebuilt `.dx`/`.unr` in. Returns shots written."""
    from .preview_native import NativePreviewError  # noqa: F401 (parallel taxonomy)

    import dataclasses
    lock_fd = None
    try:
        row = _substrate_row(game)

        # Build the delivered map INTO <root>/.uedcli/preview/ (bind-mounted at PREVIEW_MOUNT, so it
        # is already visible in the warm container — no docker cp). Also decide WHERE poses resolve:
        # trunk holds its own actors (resolve HOST-side); a retail `--map` has no trunk, so `@actor`
        # poses resolve in the BATCH against the running game (spec 2026-07-17 actor-relative).
        if map_path is not None:
            dx = copied_map(project, map_path)
            shot_field = {"unresolved": [dataclasses.asdict(s) for s in shots]}
        else:
            if level is None or level_name is None:
                raise GamePreviewError("no trunk level to preview (select one, or pass --map)")
            if not trunk_has_playerstart(level):
                raise GamePreviewError(
                    f"level {level_name!r} has no PlayerStart — the game cannot spawn a pawn "
                    "(spec D8); add one (actor build Engine.PlayerStart ... | actor add -)")
            dx = materialized_dx(project, level_name, level, rebuild=rebuild)
            resolved = _resolve_all(shots, level)       # host owns deg->uu + the ±89.9° pitch clamp
            shot_field = {"shots": [
                [int(round(rs.eye[0])), int(round(rs.eye[1])), int(round(rs.eye[2])),
                 deg_to_uu(max(-PITCH_CLAMP_DEG, min(PITCH_CLAMP_DEG, rs.pitch))),
                 deg_to_uu(rs.yaw)] for rs in resolved]}

        ensure_image(project, user_config, row)

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise GamePreviewError(f"cannot create --out-dir {out_dir}: {e}") from None

        req = {"deliver": dx.name, "stem": dx.stem, "rebuild": rebuild,
               "window_title": row["window_title"], "window_exclude": list(row["window_exclude"]),
               **shot_field}

        lock_fd = _acquire_lock()
        budget = REBOOT_BUDGET
        while True:
            container, vnc = acquire_warm_container(project, user_config, row, size)
            try:
                pngs = run_batch(container, req)        # ONE docker exec: deliver+travel+all shots
                break
            except GamePreviewError as e:
                if "actor not found" in str(e):         # a bad @actor won't fix on reboot — fail loud
                    raise
                budget -= 1
                if budget < 0:
                    raise
                stop_game(container)                    # reboot-retry: replace + re-run the batch

        taken: set[str] = set()
        written = 0
        for i, png in enumerate(pngs):
            (out_dir / shot_filename(shots[i], i, taken)).write_bytes(png)
            written += 1
        if keep_alive:
            _pin(container)
            print(f"--keep-alive: warm game container {container} pinned (idle watchdog off) "
                  f"— watch http://localhost:{vnc}/vnc.html ; release with "
                  f"`docker rm -f {container}`")
        return written
    except GamePreviewError:
        raise
    except Exception as e:                        # any stray error (setup, docker hang, parse) must
        raise GamePreviewError(                   # be a named exit-2, never a bare traceback (L2)
            f"--game preview failed unexpectedly ({type(e).__name__}: {e})") from e
    finally:
        if lock_fd is not None:
            _release_lock(lock_fd)
