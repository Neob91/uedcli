"""`substrate stub` — convert a v68 code package into a v69 stub `.u`."""
from __future__ import annotations

import sys

from ... import config
from .. import resources
from ..errors import CommandError, ProjectError


def run(args) -> int:
    """Substrate build utilities. `substrate stub <pkg>` converts a v68 code package into a v69
    stub `.u` (explicit escape hatch; the lazy auto-trigger is the resolution hook). STATELESS.
    Project-scoped: the v68 SOURCE + content deps come from the composed config CODE/CONTENT dirs
    (decisions.md 2026-07-14 — config-drive stub source), so it needs a resolved project + games
    config, exactly like `level materialize`."""
    if args.sub != "stub":
        raise CommandError(f"unimplemented substrate sub-verb: {args.sub}")
    from ... import stub, container_assets
    from ...stub_cache import list_manifests

    if args.list:
        for m in list_manifests(config.stub_cache_root()):
            print(f"{m.file}\t{m.built_at}")
        return 0
    if not args.package:
        print("substrate stub: a package name is required (or use --list)", file=sys.stderr)
        return 2
    project = resources.resolve_project(args)                     # no project ⇒ ProjectError → exit 2
    user_config = config.load_user_config()
    if user_config is None:                              # hard error — decision 2026-07-06 05:12
        raise ProjectError(
            "no per-user games config (~/.uedcli/config.toml): substrate stub needs the game's base "
            "package paths; create it with a [games.<name>] paths dir list")
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = container_assets.resource_mounts(search_dirs)
    try:
        with stub.ephemeral_build_container(mounts=mounts,
                                            state_dir=config.state_dir(project.root, create=True)
                                            ) as container:
            path = stub.ensure_stub(args.package, container=container, search_dirs=search_dirs,
                                    mounts=mounts, force=args.force)
    # StubBuild/StubClosure, plus every `dxpkg.parse_header` refusal — an unsupported version, bad
    # magic, or a corrupt/truncated package (SchemaError, a ValueError subclass).
    except (RuntimeError, ValueError) as e:
        print(f"substrate stub {args.package}: {e}", file=sys.stderr)
        return 2
    print(path)
    return 0
