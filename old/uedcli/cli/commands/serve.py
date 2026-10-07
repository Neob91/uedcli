"""`uedcli serve` — build the FastAPI app and run uvicorn (blocks until Ctrl-C). Binds localhost
only, no auth: a local single-user tool, not a network service (spec, "Architecture")."""
from __future__ import annotations

from .. import resources


def run(args) -> int:
    project = resources.resolve_project(args)

    from ...serve.app import create_app
    app = create_app(project)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0
