"""`(status, message)` classification shared by the CLI's process-error guard (`cli/dispatch.py`)
and `uedcli serve`'s HTTP exception handler — factored out of `dispatch.py`'s except-chain so the
two surfaces can't drift (`dev/docs/board/to-plan/uedcli-human-gui/plan.md` Task 1).

Preserves the CLI's exact stderr message text (`"invalid coordinate: …"`, `"invalid brush
geometry: …"`, etc. — pinned by `test_dispatch_error_boundary.py`), so `dispatch.py` calling this
changes no CLI-visible behavior. Adds one arm the CLI chain never had: `NativePreviewError` (a
plain `Exception`, `level photo --native`'s primary solve failure) — `serve`'s scene/atlas
endpoints hit it directly, where the CLI's own `level photo` call site already catches it locally.

`BrokenPipeError` is deliberately NOT classified here (and stays a separate arm in `dispatch.py`):
it returns exit 0 and reassigns `sys.stdout` as a side effect, so it doesn't reduce to `(int, str)`,
and it is not a `serve` concern (no stdout pipe to lose over HTTP)."""
from __future__ import annotations

import json

from ..classindex import ClassRefError
from ..config import ConfigError
from ..driver import DriverError
from ..geometry import GeometryError
from ..model import CoordinateError
from ..pkg_cache import CacheWriteError as PkgCacheWriteError
from ..preview_native import NativePreviewError
from ..schema_cache import CacheWriteError
from ..uprops import SchemaError
from ..cli.errors import CommandError


def error_to_status(exc: Exception) -> tuple[int, str]:
    """Classify a domain error into `(http_status, message)`. Arm order mirrors `dispatch.py`'s
    former except-chain exactly, which matters where a subclass relationship exists
    (`TimeoutError`/`EditorNotReadyError` before the `OSError` backstop). Raises `TypeError` for
    anything outside this closed set — a genuinely unclassified exception — so the caller (an HTTP
    handler, or `dispatch.py`) decides what that renders as, rather than this function guessing."""
    if isinstance(exc, json.JSONDecodeError):
        # Malformed request body (`PUT /api/level`'s `await request.json()`) — a clean 422 naming
        # the problem, consistent with every other validation failure in that route, rather than
        # falling through to the `TypeError` backstop (an unlogged 500).
        return 422, f"invalid JSON body: {exc}"
    if isinstance(exc, CommandError):                 # incl. ProjectError, LevelSelectionError
        return 422, exc.message
    if isinstance(exc, ConfigError):
        return 422, str(exc)
    if isinstance(exc, CoordinateError):
        # A coordinate that cannot be written as T3D at all (non-finite, or past emit.MAX_COORD).
        return 422, f"invalid coordinate: {exc}"
    if isinstance(exc, GeometryError):
        # Degenerate/invalid brush geometry from a model-side verb.
        return 422, f"invalid brush geometry: {exc}"
    if isinstance(exc, (DriverError, TimeoutError)):
        # Any editor-driving failure (`serve` never drives the editor itself, but the shared
        # classification must still cover it for `dispatch.py`'s reuse).
        return 502, f"editor error: {exc}"
    if isinstance(exc, ClassRefError):
        return 422, str(exc)
    if isinstance(exc, SchemaError):
        return 500, f"schema error: {exc}"
    if isinstance(exc, (CacheWriteError, PkgCacheWriteError)):
        return 500, str(exc)
    if isinstance(exc, NativePreviewError):
        # `level photo --native`'s / `build_scene`'s primary solve failure (bad geometry, an
        # unresolvable texture/package) — not in the old CLI chain (level.py catches it locally),
        # but `serve`'s scene/atlas endpoints hit it directly.
        return 422, str(exc)
    if isinstance(exc, OSError):
        # Filesystem backstop; ordered AFTER TimeoutError (an OSError subclass).
        return 500, f"filesystem error: {exc}"
    raise TypeError(f"error_to_status: not a classified domain error: {type(exc).__name__}: {exc}")
