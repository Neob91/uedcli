"""`uedcli serve` — build the FastAPI app and run uvicorn (blocks until Ctrl-C). Binds localhost
only, no auth: a local single-user tool, not a network service (spec, "Architecture")."""
from __future__ import annotations

from pathlib import Path

from .. import resources
from ...config import project_maps_dir
from ..errors import CommandError


def run(args) -> int:
    project = resources.resolve_project(args)
    maps_dir = Path(project_maps_dir(project))
    # Validated up front so a bad level name fails clearly rather than binding a socket and only
    # later failing inside `build_scene` with a misleading "no CSG brush actors" (no-half-answer
    # rule, `direction/conventions.md`).
    if not (maps_dir / args.level).is_dir():
        raise CommandError(f"level not found: {args.level!r}")

    from ...serve.app import create_app
    app = create_app(project, args.level)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0
