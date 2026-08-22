"""The editor is a per-command EPHEMERAL resource: every editor-driving verb (`level
materialize`/`preview`, the `stash` CSG generators) mints its own throwaway container from a fresh
`uuid7` id, drives it, and tears it down — there is no session and no standing per-project editor
(direction/containers.md 2026-07-06 05:12; architecture.md "The editor is a per-command ephemeral resource").
This module owns the container naming + lifecycle (`ensure_editor`/`stop_editor`).
The docker/editor calls are integration-only and mocked in unit tests."""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from . import config, container_assets, tool_assets
from .driver import WINE_CTL, DriverError

# --- hard bounds on the container-lifecycle `docker` calls ---------------------
# Every `subprocess.run` in this module carries a `timeout=`. A docker daemon that stops answering
# used to park the whole verb with no output and no way to tell it from a slow editor — the failure
# mode `dev/docs/rules/background-work.md` exists to forbid ("never leave one on a single
# open-ended wait"). The three bounds differ because the calls do genuinely different work:
#
#   PROBE   — a sub-second query/teardown (`docker ps`, `docker rm -f`, `docker volume rm`, one
#             `wine_ctl status` poll). Anything near a minute is dockerd not answering, not work.
#   LAUNCH  — `docker compose run`, which on a cold machine creates a volume and a container (and
#             may pull) before returning. Generous, because exceeding it aborts a legitimate start.
#
# A bound is NOT a retry budget: `ensure_editor`'s existing `ready_timeout`/`start_attempts` still
# govern how long the EDITOR may take to come up. These only stop `docker` itself hanging forever.
PROBE_TIMEOUT = 60.0
LAUNCH_TIMEOUT = 600.0


def editor_container(editor_id: str) -> str:
    """`uned-<uuid7>` — the ephemeral editor's container name, stable across calls for one id.
    Drops any legacy `session/` prefix and any `-slug` so it keys on the bare uuid7 (5 dash-groups)."""
    tail = editor_id[len("session/"):] if editor_id.startswith("session/") else editor_id
    uuid = "-".join(tail.split("-")[:5])     # uuid7 is 8-4-4-4-12; a -slug would follow
    return f"uned-{uuid}"


class EditorNotReadyError(TimeoutError):
    """The editor container never became ready within the readiness timeout, across every bounded
    start attempt. Raised by `ensure_editor` after it has reaped the failed container and exhausted
    its retries — a CLEAR, named error carrying the container name, attempt count and per-attempt
    timeout, so the crash-prone editor's intermittent startup death surfaces as an intelligible
    message (CLAUDE.md "never let a Python exception reach the CLI user") instead of a bare
    `TimeoutError`. Subclasses `TimeoutError` so the dispatcher's existing top-level editor-error
    handler (`dispatch.py`, catching `(DriverError, TimeoutError)`) surfaces it as a clean
    `editor error: …` / exit 2 with no change needed there."""
    pass


def _compose_dir() -> str:
    """Absolute path to the dir holding docker-compose.yml (parallel-editors.md). PACKAGE-RELATIVE
    (`tool_assets.uned_dir()` — direction/projects-and-config.md 2026-07-17 20:58 §6): a tool-install asset, found from
    any cwd with no repo-root walk and no env var."""
    return str(tool_assets.uned_dir())


def _wineprefix_volume(editor_id: str) -> str:
    return f"uned-wp-{editor_container(editor_id)[len('uned-'):]}"


def _is_running(container: str) -> bool:
    """Is this container up? BOUNDED (`PROBE_TIMEOUT`) — a `docker ps` that never answers is a dead
    daemon, and it must raise a named `DriverError` (which the materialize/preview guards turn into
    a clean exit 2) rather than hanging `ensure_editor` before it has even tried to start."""
    try:
        res = subprocess.run(["docker", "ps", "-q", "-f", f"name=^{container}$"],
                             capture_output=True, text=True, check=True, timeout=PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise DriverError(f"`docker ps` did not answer within {PROBE_TIMEOUT:.0f}s while checking "
                          f"container {container} (dockerd hung?)") from None
    return bool(res.stdout.strip())


def _reap_container(container: str) -> None:
    """`docker rm -f <container>` — force-remove a stale/leaked ephemeral editor container (running
    OR exited) so a fresh `docker compose run --name <container>` can re-take the name. Best-effort:
    `check=False`, output swallowed — a missing container is not an error (nothing to reap). Used by
    `ensure_editor`'s bounded readiness retry to clear the wedged container before re-spinning.

    Bounded (`PROBE_TIMEOUT`) and the timeout SWALLOWED, like `preview_game.stop_game`: this runs on
    the failure path, so a wedged `rm` must not replace the real error with a hang."""
    try:
        subprocess.run(["docker", "rm", "-f", container],
                       capture_output=True, text=True, check=False, timeout=PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        pass


def _wait_ready(container: str, timeout: float) -> None:
    """Poll wine_ctl status until the editor window RESOLVES (parallel-editors.md). Require a numeric
    `window=<id>`, NOT the substring `window=`: for the first seconds after launch `status` prints
    `window=<unresolved: could not find an UnrealEd window>` (window not yet mapped), which a bare
    substring check treats as ready — then the very next `exec` fails "could not find an UnrealEd
    window". The `\\d` guard waits for the real handle.

    **Each poll's `docker exec` is BOUNDED**, at `PROBE_TIMEOUT` or whatever is left of the
    readiness deadline, whichever is smaller. Without a bound the deadline loop was decorative: one
    `docker exec` that never returned parked the wait forever *inside* an iteration, so `timeout`
    could not expire and `ensure_editor`'s retry never fired. A poll that times out counts as "not
    ready yet" rather than an error — the deadline is what ends the wait, exactly as for a poll that
    answers with an unresolved window.
    """
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        try:
            res = subprocess.run(
                ["docker", "exec", container, "python3", WINE_CTL, "status"],
                capture_output=True, text=True, check=False,
                timeout=min(PROBE_TIMEOUT, left))
        except subprocess.TimeoutExpired:
            continue                # a wedged probe is "not ready"; the deadline ends the wait
        if "alive=True" in res.stdout and re.search(r"window=\d", res.stdout):
            return
        time.sleep(1.0)
    raise TimeoutError(f"editor {container} not ready within {timeout}s")


def _base_ini_path() -> Path:
    """The editor's `UnrealEd.ini` (the pre-bake source, which already carries the SoftDrv
    `Device=` the bake also sets — so it matches the baked `/opt/UED22/UnrealEd.ini` for the keys
    `level preview` overrides)."""
    return Path(_compose_dir()) / "UED22" / "UnrealEd.ini"


# The editor's engine ini (holds `[Core.System] Paths`); baked at `/opt/UED22/unrealtournament.ini`,
# with an identical pre-bake host copy under `uned/UED22/`. Flat + lowercase basename, confirmed
# live 2026-06-20 (packages.py `_EDITOR_INI`).
_ENGINE_INI_CONTAINER = "/opt/UED22/unrealtournament.ini"


def _base_engine_ini_path() -> Path:
    return Path(_compose_dir()) / "UED22" / "unrealtournament.ini"


def replace_core_system_paths(base_bytes: bytes, path_lines: list[str]) -> bytes:
    """Return `base_bytes` (the baked engine ini) with the `[Core.System]` section's `Paths=` lines
    REPLACED by `path_lines` (each written as `<line>\\r\\n`), every other key/section left BYTE-
    EXACT. Operates on raw bytes and preserves the ini's CRLF line endings — a `read_text`
    universal-newline round-trip turns CRLF→LF and wine GPFs at boot (spike-verified,
    dev/docs/spikes/2026-07-14-paths-wildcard/README.md). The new block is inserted where the FIRST
    existing `Paths=` line sat (dropping the rest); if `[Core.System]` has no `Paths=` line, it is
    inserted at the section's end. `path_lines` come from `container_assets.paths_ini_lines(mounts)`
    (the FULL set incl. `/stubs`+`/opt/UED22`), so the baked substrate Paths are regenerated, not
    preserved (direction/containers.md 2026-07-14 02:55)."""
    new_block = [ln.encode() + b"\r" for ln in path_lines]

    def _token(line: bytes) -> bytes:
        return line.rstrip(b"\r").strip()

    def _is_header(line: bytes) -> bool:
        t = _token(line)
        return t.startswith(b"[") and t.endswith(b"]")

    out: list[bytes] = []
    in_cs = False
    inserted = False
    insert_at = None            # index in `out` for the block if the section has no Paths= line:
    #                             right after the header, then bumped past each non-blank body line,
    #                             so the block lands after the last real content, never after a
    #                             trailing blank / next-section boundary (reviewer #2, 2026-07-14).
    for raw in base_bytes.split(b"\n"):
        if _is_header(raw):
            if in_cs and not inserted:            # leaving [Core.System] with no Paths seen
                out[insert_at:insert_at] = new_block
                inserted = True
            in_cs = _token(raw).lower() == b"[core.system]"
            out.append(raw)
            if in_cs:
                insert_at = len(out)              # default: immediately after the header line
            continue
        if in_cs and _token(raw).startswith(b"Paths="):
            if not inserted:
                out.extend(new_block)             # the new block takes the first Paths= slot
                inserted = True
            continue                              # drop the original Paths line
        out.append(raw)
        if in_cs and not inserted and _token(raw):
            insert_at = len(out)                  # block goes AFTER the last non-blank body line
    if in_cs and not inserted:                    # [Core.System] was the last section, no Paths line
        out[insert_at:insert_at] = new_block
    return b"\n".join(out)


def _force_headless_render_device(base_bytes: bytes) -> bytes:
    """Return the engine ini with `[Engine.Engine]`'s three render-device keys set to the software
    rasteriser (`SoftDrv`), every other byte preserved (CRLF intact — a bare-LF ini GPFs wine at
    boot). Section-scoped: a like-named `GameRenderDevice=None` under a device's own
    `[*.…RenderDevice]` section is left alone.

    Why SoftDrv, uniformly on every host: the materialize / CSG-generator editors drive the console
    headless (no visible viewport), so the device only has to satisfy the editor's own startup. Under
    FEX+wine-10 on arm64 the baked `OpenGLDrv` makes the Mesh browser's startup viewport assert
    `RenDev` and the editor drops to Recovery Mode, which cannot `MAP SAVE`; SoftDrv removes the
    assertion (spike `dev/docs/spikes/2026-08-06-materialize-under-fex/`). It is equally correct on
    native x86, so the device is the SAME on every host — not an arch branch (owner ruling
    2026-08-06)."""
    want = b"SoftDrv.SoftwareRenderDevice"
    keys = {b"GameRenderDevice", b"WindowedRenderDevice", b"RenderDevice"}
    out: list[bytes] = []
    in_engine = False
    for raw in base_bytes.split(b"\n"):
        token = raw.rstrip(b"\r").strip()
        if token.startswith(b"[") and token.endswith(b"]"):
            in_engine = token.lower() == b"[engine.engine]"
            out.append(raw)
            continue
        if in_engine and b"=" in token and token.split(b"=", 1)[0].strip() in keys:
            eol = b"\r" if raw.endswith(b"\r") else b""
            out.append(token.split(b"=", 1)[0].strip() + b"=" + want + eol)
            continue
        out.append(raw)
    return b"\n".join(out)


def _engine_ini_path(container: str, state_dir: Path) -> Path:
    """Deterministic host path for a container's crafted engine ini (so `stop_editor` cleans it up).
    Under `<state_dir>/tmp/` for the same host<->daemon-visibility reason as `_override_ini_path`."""
    d = Path(state_dir) / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{container}.paths.ini"


def _write_engine_ini(container: str, mounts, state_dir: Path) -> str:
    """Write the crafted engine ini (baked ini, `[Core.System] Paths` regenerated from `mounts`, the
    render device forced to headless `SoftDrv`) BYTE-EXACT and return its ABSOLUTE host path.
    `mounts=None` → just `/stubs`+`/opt/UED22` on Paths (no `/resources`)."""
    path = _engine_ini_path(container, state_dir)
    crafted = _force_headless_render_device(
        replace_core_system_paths(_base_engine_ini_path().read_bytes(),
                                  container_assets.paths_ini_lines(mounts or [])))
    path.write_bytes(crafted)
    return str(path)


def engine_ini_mount(container: str, mounts, state_dir: Path) -> tuple[str, list[str]]:
    """Craft this container's engine ini (its `[Core.System] Paths` regenerated from `mounts`) and
    return `(host_ini_path, ["-v", "<host>:<container>"])` — the PRE-LAUNCH, read-write bind-mount
    of `unrealtournament.ini` shared by the GUI editor (`ensure_editor`) and the no-GUI build
    container (`stub.ephemeral_build_container`). Read-write because wine (and `UCC make`'s
    `cat > ini`) rewrite the ini; `:ro` → EACCES → GPF. The caller unlinks `host_ini_path`
    (`_engine_ini_path(container, state_dir)`) when the container is torn down."""
    path = _write_engine_ini(container, mounts, state_dir)
    return path, ["-v", f"{path}:{_ENGINE_INI_CONTAINER}"]


def apply_ini_overrides(base_text: str, overrides: dict[str, dict[str, str]]) -> str:
    """Return `base_text` with each `overrides[section][key]=value` applied under that `.ini`
    section header (e.g. `{"U2Viewport2": {"RendMap": "6"}}` sets `RendMap=6` inside
    `[U2Viewport2]`). Section-aware; only rewrites keys that already exist in the section. Preserves
    each line's line ending — the baked `UnrealEd.ini` is CRLF and wine's parser is ending-sensitive,
    so a rewritten value keeps its `\r` (else the exact overridden keys would go bare-LF)."""
    wanted = {f"[{s}]": kv for s, kv in overrides.items()}
    sec = None
    out = []
    for line in base_text.split("\n"):
        eol = "\r" if line.endswith("\r") else ""
        content = line[:-1] if eol else line
        stripped = content.strip()
        if stripped.startswith("["):
            sec = stripped
        elif sec in wanted and "=" in content:
            key = content.split("=", 1)[0].strip()
            if key in wanted[sec]:
                content = f"{key}={wanted[sec][key]}"
        out.append(content + eol)
    return "\n".join(out)


def _override_ini_path(container: str, state_dir: Path) -> Path:
    """Deterministic host path for a container's override ini (so `stop_editor` can clean it up).
    Under `<state_dir>/tmp/`, NOT the system tempdir: the docker daemon must SEE this file to
    bind-mount it, and a sandboxed shell's `/tmp` is private to the sandbox — the daemon resolves
    `/tmp/...` against its own, finds nothing, auto-creates a DIRECTORY there, and the
    file-onto-file mount then fails with "not a directory". The project tree is shared
    host<->daemon at an identical real path (the compose asset mounts already rely on this), so a
    project-relative scratch path mounts correctly."""
    d = Path(state_dir) / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{container}.preview.ini"


def _write_override_ini(container: str, overrides: dict[str, dict[str, str]], state_dir: Path) -> str:
    """Write the container's override `UnrealEd.ini` (overrides applied to the baked base); return
    its ABSOLUTE host path (docker `-v` resolves a relative source against the compose dir)."""
    path = _override_ini_path(container, state_dir)
    path.write_text(apply_ini_overrides(_base_ini_path().read_text(), overrides))
    return str(path)


def ensure_editor(editor_id: str, *, state_dir: Path, mounts=None, ready_timeout: float = 90.0,
                  start_attempts: int = 3,
                  ini_overrides: dict[str, dict[str, str]] | None = None) -> str:
    """Start this ephemeral editor's container if not already running; return its name. Reuses a
    running one (idempotent). Per-id wineprefix volume; publishes noVNC via `-p 0:6080` — an
    EPHEMERAL host port (C1): `--service-ports` would republish the FIXED 127.0.0.1:6080 that the
    standing `dx-lum-uned` already binds → "port already allocated", so no ephemeral editor could
    start while the standing one is up. The ephemeral port is read back by `_published_vnc_port`
    (`docker port`).

    `mounts`: the `container_assets.resource_mounts(<whole composed dir set>)` list (one uniform
    scheme — direction/containers.md 2026-07-14 19:21) — bind-mount each composed config dir read-only at
    `/resources/<n>` AND craft the engine ini so `[Core.System] Paths` covers
    `/stubs`+`/opt/UED22`+those mounts (`/stubs` first, so a v69 stub shadows any v68 `.u`). The crafted ini is written
    BYTE-EXACT (CRLF preserved) and bind-mounted over `/opt/UED22/unrealtournament.ini` PRE-LAUNCH,
    READ-WRITE (wine rewrites inis on exit; a `:ro` mount → EACCES → GPF); cleaned up in
    `stop_editor`. `mounts=None` → no `/resources` mounts, Paths = just `/stubs`+`/opt/UED22` (a
    package-less CSG generator). The pre-launch ini bind-mount is only safe because the entrypoint no
    longer `sed -i`s that same file (a single-file bind mount defeats sed's rename-over and kills
    boot); the entrypoint's `/deusex` Paths block was removed in the asset-wiring cutover (Part C,
    2026-07-14), so nothing else touches `[Core.System] Paths` post-launch.

    `ini_overrides` (`level preview`): bind-mount a temp `UnrealEd.ini` with those `[section]` key
    overrides over the baked `/opt/UED22/UnrealEd.ini`, so the editor boots in the requested render
    mode / viewport layout — single boot, no restart. Mounted READ-WRITE (wine rewrites the ini on
    exit; a `:ro` mount → EACCES → GPF).

    `state_dir` (required): the resolved project's `.uedcli/` state dir (`config.state_dir`),
    threaded from the dispatching verb — hosts the crafted/override ini temps that `stop_editor`
    cleans up.

    `start_attempts` (bounded readiness retry): UnrealEd is crash-prone and intermittently dies at
    startup — the container comes up but its editor window never resolves, so `_wait_ready` times
    out. That is the single most frequent interruption in the build→preview loop, so a readiness
    timeout is not fatal on the first try: up to `start_attempts` times we reap the wedged container
    (`docker rm -f`, clearing the leaked name) and re-spin a fresh one, re-waiting each time. Only
    when every attempt has timed out do we raise `EditorNotReadyError` (a clear, named error, never
    a bare `TimeoutError` traceback). The bound keeps a genuinely dead editor from looping forever
    (dev/docs/rules/background-work.md — a wedged job must never wait open-endedly).

    Worst-case wait is ≈ `start_attempts × ready_timeout` (the default 3 × 90s = 270s), since each
    attempt runs its own full readiness wait before the next re-spin — so a caller passing a tight
    `ready_timeout` should remember it is multiplied by the attempt count.

    Retry limitation — CONTAINER only, not the wineprefix: each re-spin reaps only the container,
    then re-mounts the SAME per-id wineprefix volume (`uned-wp-<id>`); it is never torn down between
    attempts. So the retry recovers a transient container / X-display startup race (a fresh container
    over an intact wineprefix), but NOT a corrupted wineprefix — every attempt would re-mount the
    same bad prefix and time out identically. A full `docker volume rm` between attempts would fix
    that but costs a ~0.5 GB wine re-init per retry, so it is deliberately NOT done (deferred as a
    possible future option)."""
    container = editor_container(editor_id)

    def _spin_up() -> None:
        if _is_running(container):
            return
        extra = []
        if ini_overrides:
            extra += ["-v",
                      f"{_write_override_ini(container, ini_overrides, state_dir)}:/opt/UED22/UnrealEd.ini"]
        # Craft + bind-mount the engine ini (Paths from the threaded mounts) PRE-LAUNCH, read-write.
        # Safe because the entrypoint no longer `sed -i`s this file (asset-wiring Part C removed the
        # `/deusex` Paths block); a single-file bind mount would otherwise defeat sed's rename-over.
        _ini_path, ini_mount = engine_ini_mount(container, mounts, state_dir)
        extra += [*ini_mount, *container_assets.docker_mount_args(mounts or [])]
        # UEDCLI_STUB_CACHE feeds the compose file's `/stubs` volume source
        # (`${UEDCLI_STUB_CACHE:-${HOME}/.uedcli/cache/stubs}`), so the mount follows
        # `config.stub_cache_root()` — i.e. honors `$UEDCLI_HOME` — instead of a hardcoded
        # `${HOME}` path that could mount an empty default dir and silently lose the v69
        # stub shadowing (board chore, fixed 2026-07-18). Created here so the mount source
        # always exists.
        env = {**os.environ,
               "UEDCLI_STUB_CACHE": str(config.stub_cache_root(create=True))}
        # BOUNDED at LAUNCH_TIMEOUT: `docker compose run -d` returns once the container is created,
        # but on a cold machine that includes creating the wineprefix volume (and, first time, a
        # pull), so the bound is generous. A launch that blows it raises a named DriverError rather
        # than hanging before the readiness wait — which cannot help, since it has not started yet.
        try:
            subprocess.run(
                ["docker", "compose", "run", "-d", "-p", "0:6080", "--name", container,
                 "-v", f"{_wineprefix_volume(editor_id)}:/wineprefix", *extra, "uned"],
                cwd=_compose_dir(), env=env, capture_output=True, text=True, check=True,
                timeout=LAUNCH_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise DriverError(f"`docker compose run` did not start editor container {container} "
                              f"within {LAUNCH_TIMEOUT:.0f}s (dockerd hung?)") from None

    attempts = max(1, start_attempts)
    for attempt in range(attempts):
        if attempt > 0:
            # A prior attempt's readiness wait timed out: reap the wedged/leaked container so the
            # name is free, then re-spin a fresh one from scratch.
            _reap_container(container)
        _spin_up()
        try:
            _wait_ready(container, ready_timeout)
            return container
        except TimeoutError:
            if attempt + 1 >= attempts:
                _reap_container(container)     # don't strand the wedged container on final give-up
                raise EditorNotReadyError(
                    f"editor {container} not ready within {ready_timeout}s after {attempts} "
                    f"start attempt(s); reaped the container and gave up")
    return container    # unreachable (loop returns or raises); keeps the type checker happy


def stop_editor(editor_id: str, state_dir: Path) -> None:
    """Tear down this ephemeral editor's container + its wineprefix volume (free the ~0.5 GB); remove
    any override/engine ini the boot wrote under `<state_dir>/tmp/` (no leak per preview mode-group /
    materialize).

    Every docker call here is BOUNDED (`PROBE_TIMEOUT`) with the timeout SWALLOWED — the same
    discipline as `preview_game.stop_game`. This runs from a `finally:` in `apply.run_materialize`,
    so a wedged teardown would otherwise swallow the real failure and hang the verb *after* the work
    was already done; the local ini temps below are still unlinked either way."""
    container = editor_container(editor_id)
    for cmd in (["docker", "rm", "-f", container],
                ["docker", "volume", "rm", _wineprefix_volume(editor_id)]):
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=False,
                           timeout=PROBE_TIMEOUT)
        except subprocess.TimeoutExpired:
            pass
    _override_ini_path(container, state_dir).unlink(missing_ok=True)
    _engine_ini_path(container, state_dir).unlink(missing_ok=True)
