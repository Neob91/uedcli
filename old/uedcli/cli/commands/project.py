"""`project show` — read-only project/search-path diagnostic (no ambient level needed)."""
from __future__ import annotations

from ... import config
from .. import resources
from ..errors import ProjectError


def run(args) -> int:
    """Print the resolved project root, its game, the three managed dirs (maps/prefabs/catalog),
    and the composed package search path with per-entry shadow provenance (project overlay shadows
    game base). Read-only eyeball diagnostic — the format is not a machine contract."""
    project = resources.resolve_project(args)                     # no project ⇒ ProjectError → exit 2
    user_config = config.load_user_config()
    if user_config is None:                              # separate hard error — decision 2026-07-06 05:12
        raise ProjectError(
            "no per-user games config (~/.uedcli/config.toml): needed to resolve the game's base "
            "package paths; create it with a [games.<name>] paths dir list")
    files = config.composed_search_files(project, user_config)   # missing game ⇒ ConfigError → exit 2
    if getattr(args, "json", False):
        import json
        print(json.dumps({
            "root": str(project.root),
            "game": project.game,
            "maps": str(config.project_maps_dir(project)),
            "prefabs": str(config.project_prefabs_dir(project)),
            "catalog": str(config.project_catalog_dir(project)),
            "search_path": [{"path": str(path), "provenance": provenance}
                            for path, provenance in files],
        }, indent=2))
        return 0
    print(f"root:     {project.root}")
    print(f"game:     {project.game}")
    print(f"maps:     {config.project_maps_dir(project)}")
    print(f"prefabs:  {config.project_prefabs_dir(project)}")
    print(f"catalog:  {config.project_catalog_dir(project)}")
    print(f"search path ({len(files)} package(s), project shadows base):")
    for path, provenance in files:
        print(f"  {f'[{provenance}]':<9} {path}")   # [project]/[base] tags, path column aligned
    return 0
