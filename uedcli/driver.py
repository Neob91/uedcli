"""Editor driver — wraps wine_ctl.py over `docker exec`. Every console verb goes
through `wine_ctl exec`; reads go through `wine_ctl edit-copy` (EDIT COPY → X
clipboard) and `MAP EXPORT`. Window resolution is cached inside wine_ctl per
editor lifespan, so per-command cost is sub-second after the first call.
"""
from __future__ import annotations

import shlex
import struct
import subprocess
import time

WINE_CTL = "/opt/uned/wine_ctl.py"
_EDITOR_LOG = "/opt/UED22/Editor.log"

# --- container probes ---------------------------------------------------------
# Every container-side FILE READ ON THE `map_save` VERIFICATION PATH goes through
# `Driver._container_probe`, which prefixes the in-container shell snippet with this tag. See that
# method for why the tag — and not the exit code — is what tells "the container is dead" from "the
# file is not there yet". (The driver's OTHER `docker exec` calls — `_wine_ctl`, `dexec_bash`,
# `set_clipboard`, `log_size`, `read_log_since`, `dismiss_blocking_dialog` — do NOT go through it
# and are still unbounded; `board/inbox.md` carries that chore.)
PROBE_TAG = "uedcli-probe"
# Hard bound on ONE `docker exec` probe. Every probe here is a sub-second `stat`/`od`, so anything
# near this is dockerd itself not answering — and per the tool's "never an open-ended wait" rule a
# hung dockerd must surface as a named error, not as an infinite block inside a bounded poll loop.
PROBE_TIMEOUT = 60.0

# --- Unreal package structure (the `.dx`/`.unr` completeness check) ------------
# Every UE1 package starts with 9 little-endian uint32s: magic, version, package flags, then the
# (count, file-offset) pair of each of the three object tables — names, exports, imports.
# `upackage.py` parses the same 9 fields; this module only needs the header, so it does not import
# it (the driver must stay usable with nothing but a container). `test_driver` pins the two
# spellings of the magic equal so the copy cannot drift.
PKG_MAGIC = 0x9E2A83C1
PKG_HEADER_BYTES = 36


def to_z_path(host_path: str) -> str:
    r"""/work/x.t3d → Z:\work\x.t3d (wine's Z: maps to /)."""
    p = host_path.lstrip("/")
    return "Z:\\" + p.replace("/", "\\")


class DriverError(RuntimeError):
    pass


def package_header_problem(header: bytes, size: int) -> str | None:
    """Structural sanity of an Unreal package file (`.dx`/`.unr`/`.u`/…) judged from its first
    `PKG_HEADER_BYTES` bytes plus the file's total `size`. Returns `None` when the file looks
    COMPLETE, otherwise a one-line human reason it does not.

    **Why a structural check exists at all.** A size that has stopped changing proves only that the
    writer went quiet — not that it finished; a part-written file's size holds just as steady as a
    finished one's, so stability can never tell *finished* from *stalled* and something inside the
    file has to say so. The header is that something: every UE1 package opens with magic
    `0x9E2A83C1`, then the (count, file-offset) pair of each of its three object tables — names,
    exports, imports — and those tables are written INSIDE the file, so a complete package has
    non-zero counts, all three offsets between the end of the header and EOF, AND enough bytes after
    each offset to hold that many entries at their minimum encoded size.

    **How the editor writes the file** (📖 extracted 2026-07-25 from the editor's own `core.dll`
    string table — `unrealed/commands.md` "MAP SAVE writes Save.tmp"): `UObject::SavePackage`
    serializes into a temp `Save.tmp`, runs `RewriteSummary` (the header is patched LAST, in the
    temp), and only then `Moving '%s' to '%s'` onto the destination. **Whether that move is a rename
    or a byte copy is NOT known** — the import table settles nothing: `core.dll` imports no
    `MoveFile*`/`CopyFile*`, but it also imports **no file-READ API at all** (no `ReadFile`, no
    file mapping) although reading packages is most of what it does, so at least its read path is
    resolved by some route the import table does not show, and an absence there is not evidence of
    anything. So: if the move is atomic, a truncated
    file can never appear at this path at all and this check is pure insurance; if it is a copy, a
    wedge mid-copy leaves a destination whose header is already valid but whose tables run past the
    bytes copied so far, which is exactly what the offset/room branches below catch. **No truncated
    destination has ever actually been observed** — the one historical report was retracted
    (`spikes/2026-07-15-native-materialize/sections/91-leaves-overproduction.md`). The check is kept
    because it costs one 36-byte read at the accept point, it is the only signal that *could*
    separate finished from stalled, and it independently catches "the file at this path is not a
    package at all" (a stale artefact, a wrong path, a zero-filled placeholder).

    **What it does NOT catch, quantified** (re-measured 2026-07-25 by
    `spikes/2026-07-25-map-save-mechanism/measure_header_window.py` over the 264 packages the real
    composed search path resolves — 120 `.dx`, 60 `.utx`, 47 `.u`, 35 `.umx`, 2 `.uax`):
    - **A truncation inside the last table's own bytes.** Over the **101 EDITOR-written maps** (the
      120 `.dx` on the path minus the 19 `Native*.dx` this tool's own native build wrote — those are
      not `MAP SAVE` output and must not set the bar for it) the required end lands at
      **98.4–99.7 %** of the real size (median 99.5 %), against **93.5–98.9 %** (median 98.3 %) for
      an offsets-only rule. So a write that died in the last ~1.6 % of a map still passes; the rule
      shrinks the blind window several-fold, it does not close it. Closing it properly needs a full
      table parse, which needs the bytes on the HOST (`upackage.load_package` after `docker cp`) —
      deliberately not done here, since the driver checks a container-side file and `apply`'s own
      post-verify already re-reads the installed map.
    - **A size-preserving in-place overwrite.** If a pre-existing destination were rewritten in place
      without truncation, `size` would never move, so the stability signal is satisfied throughout and
      this check would compare the NEW header against the OLD, larger size. Unreachable for the two
      production callers (fresh uuid paths, so nothing pre-exists) and unlikely in general — the temp
      file is opened `CreateFileW`-style, which truncates — but it is a real hole for a fixed-path
      caller. The `board/inbox.md` `Save.tmp` spike settles it while watching the destination.

    The zero-COUNT branch is defence in depth rather than a format law, and it DOES reject some real
    packages: `uned/UED22/WinDrv.u` and `Window.u` are legitimate 64-byte stubs with all three counts
    zero. None of the 264 packages on the search path is like that, and `map_save`'s only inputs are
    editor-written maps, so the branch is safe where it is used — but it is a heuristic about maps,
    not a fact about the format, and `package_header_problem` must not be reused as a general
    package validator on that basis.

    This is deliberately a *completeness* check, not a validity check: it never decodes a table, so a
    finished-but-semantically-odd map is accepted (the caller's own verify gate judges content)."""
    if size < PKG_HEADER_BYTES:
        return f"{size} byte(s) is smaller than a package header ({PKG_HEADER_BYTES} bytes)"
    if len(header) < PKG_HEADER_BYTES:
        # Reachable without any probe fault: the file can SHRINK between the stat that reported
        # `size` and the header read (the same race `container_file_head` names for a vanished file),
        # so this must not read as "the container is broken".
        return (f"the header read back only {len(header)} of {PKG_HEADER_BYTES} bytes although the "
                f"file stat'd at {size} — it is being rewritten or truncated under us")
    magic, _ver, _flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
        struct.unpack_from("<9I", header, 0)
    if magic != PKG_MAGIC:
        return f"bad package magic {magic:#010x} (expected {PKG_MAGIC:#010x}) — not a package (yet)"
    # Minimum bytes ONE entry of each table can possibly occupy, derived from
    # `upackage._parse_package`'s field order:
    #   name   5 — `read_name` has TWO forms and 5 is exact for BOTH: `version < 64` is a
    #              NUL-terminated string (≥1 byte) + u32 ObjectFlags; v≥64 is a compact-index length
    #              (≥1 byte) + that many chars (a zero-length name is legal) + u32. Do NOT "tighten"
    #              this to 6 for a v≥64-only path — it would reject a legal package, at a 600 s
    #              timeout. (Both forms occur here: 242 packages on this path are v68, 18 v69, 4 v61.)
    #   import 7 — three compact indices (≥1 each) + an i32.
    #   export 12 — two compact indices + an i32 + a compact index + a u32 + a compact size.
    # Strict LOWER bounds, so no complete package can fail them — verified over all 264 packages the
    # composed path resolves, where the tightest (`Quotes_Music.umx`) still leaves 4 bytes of slack.
    for label, count, off, per_entry in (("name", namecnt, nameoff, 5),
                                         ("export", expcnt, expoff, 12),
                                         ("import", impcnt, impoff, 7)):
        if count == 0:
            return (f"the header declares 0 {label} table entries — no map this editor writes does "
                    f"(see the docstring), so the header was never filled in")
        if not PKG_HEADER_BYTES <= off < size:
            return (f"the header puts the {label} table at offset {off}, outside the {size}-byte "
                    f"file — the tables were never written")
        if off + count * per_entry > size:
            return (f"the {label} table needs at least {count * per_entry} byte(s) from offset "
                    f"{off}, past the end of the {size}-byte file — it is only part-written")
    return None


class Driver:
    def __init__(self, container: str = "dx-lum-uned"):
        self.container = container

    def _wine_ctl(self, *args: str, capture: bool = False) -> str:
        cmd = ["docker", "exec", self.container, "python3", WINE_CTL, *args]
        res = subprocess.run(
            cmd, text=True, capture_output=capture, check=False
        )
        if res.returncode != 0:
            raise DriverError(f"{' '.join(args)} failed: {(res.stderr or '').strip()}")
        return res.stdout if capture else ""

    def exec(self, line: str) -> None:
        self._wine_ctl("exec", line)

    def click(self, x: int, y: int, button: int = 1) -> None:
        """A real XTEST click at window-relative (x,y) — makes that viewport pane current AND forces
        the llvmpipe repaint that command-driven redraws don't (the stale-framebuffer trap). Used by
        `level preview` after posing the pane. (`wine_ctl click` takes x,y POSITIONALLY.)"""
        self._wine_ctl("click", str(x), str(y), "--button", str(button))

    def dexec_bash(self, script: str) -> str:
        """Run an arbitrary bash pipeline inside the editor container (e.g. the `wmctrl` sweep that
        shoves the floating Log/Textures windows off-screen). Returns stdout; raises on non-zero."""
        res = subprocess.run(["docker", "exec", self.container, "bash", "-c", script],
                             text=True, capture_output=True, check=False)
        if res.returncode != 0:
            raise DriverError(f"dexec_bash failed: {(res.stderr or '').strip()}")
        return res.stdout

    def edit_copy(self) -> str:
        return self._wine_ctl("edit-copy", capture=True)

    def set_clipboard(self, content: str) -> None:
        """Load the X CLIPBOARD selection (which wine reads for EDIT PASTE) with
        `content`. Mirror of edit_copy's `xclip -o` read. Brushes are added via
        set_clipboard + edit_paste because IMPORTADD'd brushes are not selectable."""
        res = subprocess.run(
            ["docker", "exec", "-i", "-e", "DISPLAY=:99", self.container,
             "xclip", "-selection", "clipboard", "-i"],
            input=content, text=True, capture_output=True, check=False,
        )
        if res.returncode != 0:
            raise DriverError(f"set_clipboard failed: {(res.stderr or '').strip()}")

    def edit_paste(self) -> None:
        self.exec("EDIT PASTE")

    def screenshot(self, host_path: str) -> None:
        from . import xfer
        work = xfer.work_path("png")
        self._wine_ctl("shot", work)
        xfer.cp_out(self.container, work, host_path)
        xfer.remove(self.container, work)

    # --- console verb helpers -------------------------------------------------
    def set_grid(self, x: int, y: int, z: int) -> None:
        self.exec(f"MAP GRID X={x} Y={y} Z={z}")

    def map_export(self, host_path: str) -> None:
        self.exec(f"MAP EXPORT FILE={to_z_path(host_path)}")

    def map_importadd(self, host_path: str) -> None:
        self.exec(f"MAP IMPORTADD FILE={to_z_path(host_path)}")

    def brush_import(self, host_path: str) -> None:
        self.exec(f"BRUSH IMPORT FILE={to_z_path(host_path)}")

    def brush_export(self, host_path: str) -> None:
        self.exec(f"BRUSH EXPORT FILE={to_z_path(host_path)}")

    def brush_moveto(self, x: int, y: int, z: int) -> None:
        self.exec(f"BRUSH MOVETO X={x} Y={y} Z={z}")

    def select_none(self) -> None:
        self.exec("ACTOR SELECT NONE")

    def select_inside(self) -> None:
        self.exec("ACTOR SELECT INSIDE")

    def actor_delete(self) -> None:
        self.exec("ACTOR DELETE")

    def selectname(self, name: str) -> None:
        """Real select-by-name (replaces the current selection; no-ops on a missing name).
        Works for point actors AND brushes, including IMPORTADD brushes that SELECT INSIDE
        can't reach (unrealed/commands.md `ACTOR`/selection)."""
        self.exec(f"SELECTNAME NAME={name}")

    def camera_align(self, name: str | None = None) -> None:
        """Re-pose all viewports onto the selection (or `name`'s actor). For a POINT actor this sets
        camera POSITION only — its `Rotation` is *stored* but never reaches the headless render
        (calibration spike 2026-07-12; the old rotation-adopt claim was verified only via a MAP SAVE
        readback, never pixels). For a BRUSH actor it repositions AND aims the camera to FRAME the
        brush, and the render DOES reflect it — this is how `level preview` auto-frames. See
        unrealed/commands.md `CAMERA ALIGN` + rendering.md "Posed shots"."""
        self.exec("CAMERA ALIGN" if name is None else f"CAMERA ALIGN NAME={name}")

    def map_save(self, container_path: str, *, timeout: float = 600.0, poll: float = 1.0,
                 stable_reads: int = 3, settle: float = 3.0, recheck: float = 30.0) -> int:
        """`MAP SAVE` the current level to `container_path` (a container-side POSIX path, wine-mapped
        to `Z:\\…`), WAIT for the file to be COMPLETELY written, and return its size in bytes.

        Why a wait at all: `exec` is **fire-and-forget** — `wine_ctl exec` types the line into the
        editor's Command box, presses Return, settles 0.3 s and returns, so it is back long before
        UnrealEd has written anything (`unrealed/commands.md` "Driving is fire-and-forget";
        `unrealed/quirks.md` §"a reused editor loses the next MAP SAVE"). `MAP SAVE` also answers
        nothing over the console, so the ONLY signal that the save happened is the file itself.

        The check has to separate THREE outcomes that a naive size poll conflates — finished,
        stalled, and container-dead — so it stacks four independent signals:

        1. **A pre-`MAP SAVE` stat that the file must differ from.** Recorded before the command is
           typed; a file whose `(size, mtime)` still equals the pre-save reading proves the editor
           wrote NOTHING, even when a complete map from an earlier run is sitting at that path.
           *Both production callers pass a fresh uuid path* — `apply._save_and_swap_verified` and
           `native.csg_golden.capture_case` — so `before` is `None` there and this signal is dormant;
           it guards the FIXED-path callers, i.e. the spikes that save to a constant name
           (both probes in `spikes/2026-07-25-frotator-import-normalization/`, and
           `uned/spikes/relight_big.py`) and anyone re-saving over a real map.
        2. **`stable_reads` equal readings spanning at least `settle` seconds.** "Two equal reads one
           poll apart" accepted any write that merely went quiet for one second; requiring several
           equal reads across a minimum wall-clock window makes an ordinary mid-write pause fall
           short of the bar. (Cost: a save is accepted at least `settle` seconds after the file stops
           growing — a few seconds added to every `level materialize`.)
        3. **A structural check of the written package** (`package_header_problem`). The only signal
           that *could* tell *finished* from *stalled* — a part-written map holds its size just as
           steadily as a finished one, so no amount of stability can distinguish them, while the
           bytes can. Whether a truncated file can actually reach this path is UNPROVEN: the editor
           serializes into a `Save.tmp`, patches the header last, then moves that onto this path, and
           the move's mechanism (rename vs copy) is not determined — see `package_header_problem` and
           `unrealed/commands.md` "MAP SAVE writes Save.tmp". Kept as cheap insurance (one 36-byte
           read at the accept point) that also rejects a stale non-package sitting at the path. A file
           that is stable-but-incomplete is NOT accepted and NOT an immediate error: polling continues
           until `timeout`, then raises naming the structural reason.
        4. **A liveness check that does not trust exit codes** (`_container_probe`) — so a dead
           container raises at once instead of being misread as "no file yet" for the full timeout.
           **Scope of the boundedness claim:** it covers the POLL LOOP only. The `MAP SAVE` line
           itself goes out through `_wine_ctl`, which still has no `subprocess` timeout, so a dockerd
           that hangs on *that* call parks this method one line before the bounded loop begins
           (`board/inbox.md` chore — `_wine_ctl` drives minutes-long editor verbs and needs its own
           bound chosen, not this one copied).

        Raises `DriverError` naming the path, the last thing observed, and the elapsed time if no
        complete file appears within `timeout` seconds — the crash-prone editor can wedge so `MAP
        SAVE` writes NOTHING at all, and without this that surfaces far downstream as an opaque
        `docker cp` exit 1 blaming the wrong subsystem (the closed 'semisolid breaks MAP SAVE'
        report — the real cause was a transient wedge)."""
        before = self.container_stat(container_path)
        self.exec(f"MAP SAVE FILE={to_z_path(container_path)}")
        started = time.monotonic()
        deadline = started + timeout
        prev: int | None = None                     # size of the previous reading
        runs = 0                                    # consecutive readings at `prev`
        stable_since = 0.0                          # when `prev` was FIRST read
        checked: tuple[int, float] | None = None     # (size, when) of the last header check
        why = "no file appeared"
        while True:
            now = time.monotonic()
            cur = self.container_stat(container_path)
            if cur is None:
                why, prev, runs, checked = "no file appeared", None, 0, None
            elif before is not None and cur == before:
                why, prev, runs, checked = (
                    f"the file is unchanged from before MAP SAVE ({cur[0]} byte(s), same mtime) — "
                    f"the editor wrote nothing"), None, 0, None
            else:
                size = cur[0]
                if size == prev:
                    runs += 1
                else:
                    prev, runs, stable_since = size, 1, now
                if size <= 0:
                    why = "the file is still empty (0 bytes)"
                elif runs < stable_reads or now - stable_since < settle:
                    why = f"still being written (at {size} byte(s))"
                elif checked is not None and checked[0] == size and now - checked[1] < recheck:
                    # A verdict at this size is `recheck` seconds fresh — don't re-probe; keep `why`.
                    # The staleness is BOUNDED rather than permanent on purpose: the destination's
                    # header is not known to be immutable once written (whether the editor's move is
                    # a rename or a copy is undetermined — see `package_header_problem`), so a cache
                    # that never expires could hold a pre-patch verdict for the whole timeout and fail
                    # a file that has since become valid.
                    pass
                else:
                    checked = (size, now)           # ≤ 1 header read per `recheck`, not one per poll
                    problem = self.package_problem(container_path, size)
                    if problem is None:
                        return size                 # stable AND structurally complete ⇒ finished
                    why = f"stalled at {size} byte(s) — {problem}"
            if now >= deadline:
                # Report the ELAPSED time, not the configured bound: one iteration can block up to
                # PROBE_TIMEOUT per probe, so the two are not the same number.
                raise DriverError(
                    f"MAP SAVE never produced a finished file at {container_path}: {why} (after "
                    f"{time.monotonic() - started:.0f}s, bound {timeout:.0f}s). The editor accepted "
                    f"the command but did not complete the save — check the editor log; it most "
                    f"likely wedged.")
            time.sleep(poll)

    # --- container-side file probes -------------------------------------------
    def _container_probe(self, script: str, what: str) -> str:
        """Run a tiny shell `script` inside the editor container and return its stdout with the
        liveness sentinel stripped. Raises `DriverError` naming the container if the container did
        not run it.

        **Liveness is decided by a SENTINEL in the output, never by the exit code.** Measured on this
        machine 2026-07-25: a *stopped* container, a *missing* container and a *permission* error all
        make `docker exec` exit **1** — the very code `stat` uses for "no such file" — so an exit code
        cannot tell a dead container from an absent file. (The older rule "only exit 1 means no file,
        anything else is docker failing" therefore had an unreachable failure branch, and every real
        container death was silently reclassified as "not written yet".) Instead the script's first
        act is to `printf` a fixed tag: that tag can only reach stdout if docker really started a
        shell inside a live container, so its ABSENCE *is* the container failure and its presence
        makes the exit code irrelevant.

        The `docker exec` itself is bounded by `PROBE_TIMEOUT` and a timeout becomes a `DriverError`,
        so a hung dockerd cannot park a caller forever ("never an open-ended wait")."""
        cmd = ["docker", "exec", self.container, "sh", "-c", f"printf '{PROBE_TAG} '; {script}"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False,
                                 timeout=PROBE_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise DriverError(f"cannot {what} in container {self.container}: `docker exec` did not "
                              f"answer within {PROBE_TIMEOUT:.0f}s (dockerd hung?)") from None
        except OSError as e:                        # docker binary missing/unrunnable
            raise DriverError(f"cannot {what} in container {self.container}: "
                              f"cannot run docker ({e})") from None
        out = res.stdout or ""
        if not out.startswith(PROBE_TAG + " "):
            raise DriverError(
                f"cannot {what} in container {self.container}: the container did not run the probe "
                f"(docker exec exit {res.returncode}) — it is most likely stopped, gone or "
                f"unreachable: {(res.stderr or '').strip() or 'no stderr'}")
        return out[len(PROBE_TAG) + 1:]

    def container_stat(self, container_path: str) -> tuple[int, str] | None:
        """`(size_in_bytes, mtime_token)` of a file INSIDE the editor container, or `None` if the file
        does not exist. (Nothing the editor writes is on the host filesystem — `/work` is
        container-local — so this has to run through `docker exec`.)

        The mtime is an OPAQUE STRING, never a number: `stat -c %.9Y` renders the fractional seconds
        with the container locale's decimal separator (a comma under some locales), and if that
        coreutils build does not support the `%.9` precision it echoes the directive back verbatim.
        The value is only ever compared for equality ("did this file change?"), so no parsing is
        needed. On such a build the token is a constant and `map_save`'s pre-save comparison degrades
        to SIZE equality — which is not free: a fixed-path re-save producing a byte-identical size
        would then read as "the editor wrote nothing" for the full timeout. (The container image ships
        GNU coreutils 9.1, where `%.9Y` works — checked 2026-07-25.)

        **"Absent" and "`stat` FAILED" are answered separately, and only absence is `None`.** The
        probe tests existence itself and reports `missing`; a `stat` that then fails anyway (a
        permission error, a coreutils that rejects the format) reports `statfail`, and an
        unrecognisable reply is neither — both raise `DriverError`. Collapsing those into "not there"
        is how a broken probe turns into `map_save` polling a perfectly good file for its whole
        timeout and then blaming the editor."""
        path = shlex.quote(container_path)
        out = self._container_probe(
            f"if [ -e {path} ]; then stat -c '%s %.9Y' -- {path} 2>/dev/null || printf statfail; "
            f"else printf missing; fi",
            f"stat {container_path}")
        parts = out.split()
        if parts == ["missing"]:
            return None
        if parts and parts[0] != "statfail":
            try:
                return int(parts[0]), (parts[1] if len(parts) > 1 else "")
            except ValueError:
                pass
        raise DriverError(
            f"cannot stat {container_path} in container {self.container}: the file is there but "
            f"`stat` did not answer with a size (probe said {out.strip()!r}) — check the path's "
            f"permissions and that the container has GNU coreutils")

    def container_file_head(self, container_path: str, nbytes: int) -> bytes | None:
        """The first `nbytes` bytes of a container-side file — fewer if the file is shorter, empty if
        it is empty, and **`None` if `od` could not read it at all**, which in practice means the file
        was unlinked between the caller's stat and this read. `od -tu1` renders the bytes as decimal
        numbers so the probe stays a TEXT channel and keeps the same liveness sentinel as every other
        probe.

        `None` rather than a raise, because the caller that matters (`map_save`) is a poll loop for
        which "it is not there right now" is an ordinary transient state — raising would abort a save
        wait over a race the very next poll recovers from. A reply that is neither a byte list nor the
        sentinel IS a raise: that is a broken probe, not a missing file."""
        out = self._container_probe(
            f"od -An -v -tu1 -N {int(nbytes)} -- {shlex.quote(container_path)} 2>/dev/null "
            f"|| printf odfail",
            f"read the first {int(nbytes)} bytes of {container_path}")
        if out.split() == ["odfail"]:
            return None
        vals = []
        for tok in out.split():
            try:
                v = int(tok)
            except ValueError:
                v = -1
            if not 0 <= v <= 255:
                raise DriverError(
                    f"cannot read {container_path} in container {self.container}: the byte-dump "
                    f"probe answered {out.strip()!r}, which is not a list of byte values")
            vals.append(v)
        return bytes(vals)

    def package_problem(self, container_path: str, size: int) -> str | None:
        """Read `container_path`'s package header out of the container and structurally check it
        against `size`. `None` = it looks like a COMPLETE package; otherwise a one-line reason —
        including for a file that vanished between the stat and the read, which is a reason not to
        accept it, not an error (see `container_file_head`)."""
        header = self.container_file_head(container_path, PKG_HEADER_BYTES)
        if header is None:
            return "it disappeared between the stat and the header read"
        return package_header_problem(header, size)

    def map_load_dx(self, host_path: str) -> None:
        """Open a .dx level (preserves BSP/lightmaps/myLevel). Not used by the store-centric
        read/edit path (which reads the store, not the editor); kept for a future shaded-preview
        / screenshot flow."""
        self.exec(f"MAP LOAD FILE={to_z_path(host_path)}")

    def map_new(self) -> None:
        """Start a brand-new empty level. `materialize` uses this (FULL RE-IMPORT) before
        re-adding the merged actors; `apply` then saves the materialized level to the .dx."""
        self.exec("MAP NEW")

    def rebuild(self) -> None:
        self.exec("MAP REBUILD")

    # --- CSG (subtractive model + composition) --------------------------------
    # Subtractive CSG: Unreal's world is SOLID by default; CSG_Subtract brushes carve
    # empty space, CSG_Add re-fills it (creation/list order = CSG precedence). uedcli
    # authors the CsgOper as an actor prop (see builders.make_brush_actor) and applies
    # it on rebuild — no special driver verb needed to place a subtract brush. These
    # verbs cover the rest of the subtractive workflow.

    def map_sendto(self, where: str) -> None:
        """Reorder the selected brush in the CSG order (`FIRST`/`LAST`). Order
        determines the result — a later subtract carves earlier adds."""
        w = where.upper()
        if w not in ("FIRST", "LAST"):
            raise DriverError(f"map_sendto: where must be FIRST/LAST, got {where!r}")
        self.exec(f"MAP SENDTO {w}")

    def select_by_csg(self, kind: str) -> None:
        """Select brushes by CSG type: ADDS / SUBTRACTS / SEMISOLIDS / NONSOLIDS."""
        k = kind.upper()
        if k not in ("ADDS", "SUBTRACTS", "SEMISOLIDS", "NONSOLIDS"):
            raise DriverError(f"select_by_csg: bad kind {kind!r}")
        self.exec(f"MAP SELECT {k}")


    # --- preview / camera helpers ---------------------------------------------
    def jumpto(self, x, y, z) -> None:
        """Center all viewports on a world coord (position only — there is no console camera
        rotation; the operator orients in VNC). See unrealed/commands.md."""
        self.exec(f"JUMPTO {x},{y},{z}")

    def rmode(self, n: int) -> None:
        """Set the current viewport's render mode (6 = PlainTex fullbright)."""
        self.exec(f"RMODE {n}")

    def light_apply(self) -> None:
        """Build lighting (does not need a geometry rebuild; a MAP REBUILD wipes it)."""
        self.exec("LIGHT APPLY")

    # --- log read primitives (export_and_qualify's OBJ DEPENDENCIES read) -----
    def log_size(self) -> int:
        """Current byte length of the editor's log file — the offset to read forward from
        after driving a verb whose output only the log captures (e.g. OBJ DEPENDENCIES)."""
        res = subprocess.run(["docker", "exec", self.container, "stat", "-c", "%s",
                              _EDITOR_LOG], capture_output=True, text=True, check=True)
        return int(res.stdout.strip())

    def read_log_since(self, offset: int) -> str:
        """Log text written after `offset` (from a prior log_size()). The log is buffered/
        flush-laggy and NUL-padded (spikes/2026-06-19-read-surface-texture-package.md) — strip
        NULs; callers settle (sleep + a trailing noisy command) before calling this."""
        res = subprocess.run(["docker", "exec", self.container, "tail", "-c", f"+{offset + 1}",
                              _EDITOR_LOG], capture_output=True, text=True, check=True)
        return res.stdout.replace("\x00", "")

    def obj_dependencies(self, package: str) -> None:
        """Walk `package`'s reachable object graph; prints every referenced object (incl. each
        brush's per-poly bound Texture, package-qualified) to the log. See
        spikes/2026-06-19-read-surface-texture-package.md."""
        self.exec(f"OBJ DEPENDENCIES PACKAGE={package}")

    def obj_load(self, package: str, file_path: str) -> None:
        """Explicitly load `package` from `file_path` into the editor's object pool. Being on
        `[Core.System] Paths` does NOT auto-demand-load a package referenced only via a
        qualified `Texture=` inside imported T3D (unrealed/quirks.md "T3D format" / unrealed/t3d.md, confirmed
        live 2026-06-20) — every content package materialize touches must be OBJ LOADed
        explicitly before the import that references it."""
        self.exec(f"OBJ LOAD FILE={to_z_path(file_path)} PACKAGE={package}")

    def dismiss_blocking_dialog(self) -> bool:
        """Find and dismiss a stuck modal dialog — confirmed live 2026-06-20: the "Cleaning
        up..." GC-progress dialog (window titled literally `xmessage`) that pops up around a
        GC pass (`Collecting garbage`/`Purging garbage`, itself triggered by `MAP
        NEW`/`IMPORTADD`/etc.) never auto-closes under headless SoftDrv — it sat for 60+s
        unattended in testing — and blocks every subsequent console command from reaching the
        Command box until dismissed. Dismiss via `windowactivate` + a window-LESS `key Return`
        (NOT `xdotool key --window <id>` — wine ignores synthetic `--window` events, see
        unrealed/commands.md). Returns whether one was found and dismissed; a no-op (returns
        False) when none is present, so callers can call this defensively on every retry."""
        res = subprocess.run(["docker", "exec", self.container, "wmctrl", "-l"],
                             capture_output=True, text=True, check=True)
        win_id = next((parts[0] for line in res.stdout.splitlines()
                       if len(parts := line.split(None, 3)) == 4 and parts[3] == "xmessage"),
                      None)
        if win_id is None:
            return False
        subprocess.run(["docker", "exec", "-e", "DISPLAY=:99", self.container,
                        "xdotool", "windowactivate", "--sync", win_id],
                       check=True, capture_output=True, text=True)
        subprocess.run(["docker", "exec", "-e", "DISPLAY=:99", self.container,
                        "xdotool", "key", "Return"], check=True, capture_output=True, text=True)
        return True
