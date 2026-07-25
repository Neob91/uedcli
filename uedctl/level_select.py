"""Which level a content verb edits, now that there is no session to bind one (decisions 2026-07-05
19:07). The level is an **ambient environment variable `$UEDCTL_LEVEL`** (a bare level name), read by
`resolve_level` as the default when a verb has no explicit `--tree` (decisions 2026-07-20 — this
replaces the old machine-local `.uedctl/current-level` pointer file, which was a live cross-session
race). The env value is passed IN by the caller (`resolve_level(env_level=…)`), mirroring
`config.resolve_project(env_project=…)`; this module never reads `os.environ` itself.
"""
from __future__ import annotations

from pathlib import Path


class LevelSelectionError(Exception):
    """No level could be resolved / an invalid level was named — carries a user-facing message."""


def _check_safe_level(level: str) -> None:
    """A level name must be a single safe directory segment (it becomes `maps/<level>/`). A
    leading dot is rejected too: `.locks` is the maps-dir lock home (self-ignored), so a dotted
    level would collide with it / hide from git (review fix, 2026-07-18)."""
    if (not level or level in (".", "..") or level.startswith(".")
            or "/" in level or "\\" in level or "\n" in level):
        raise LevelSelectionError(f"invalid level name: {level!r}")


def list_levels(maps_dir: Path) -> list[str]:
    """Every level under `maps_dir`: an immediate subdirectory that holds an `actors/` tree (the
    structural marker of a T3D trunk — `level create` scaffolds exactly this). Dotted dirs (`.locks`,
    the maps-dir lock home) are skipped. Sorted case-insensitively, ties broken by exact name, for a
    stable human- and pipe-friendly order. Returns [] when `maps_dir` is absent or not a directory."""
    maps_dir = Path(maps_dir)
    if not maps_dir.is_dir():
        return []
    names = [
        d.name for d in maps_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "actors").is_dir()
    ]
    return sorted(names, key=lambda n: (n.lower(), n))


# The "no level" error names BOTH ways to set the level (decisions 2026-07-20 — clean break from the
# old pointer; the message is the whole migration story, so it must be self-contained).
NO_LEVEL_MSG = (
    "no level: set the environment variable (export UEDCTL_LEVEL=<name>) "
    "or pass a level explicitly (--tree level/<name>)"
)


def resolve_level(*, env_level: str | None, maps_dir: Path) -> str:
    """The ambient level from `$UEDCTL_LEVEL` (passed in as `env_level`) — the default source when a
    verb gets no explicit `--tree`. Normalization order (exact): strip → blank ⇒ unset → single-safe-
    segment check → must exist under `maps_dir`. Raises `LevelSelectionError` (→ the CLI's exit 2)
    when unset, malformed, or nonexistent — never a silent empty-level read.

    A value containing `/` is the common mistake of copying the flag's `KIND/NAME` shape into the
    bare-name env var; its error hints the grammar rather than the opaque `invalid level name`."""
    name = (env_level or "").strip()
    if not name:                                          # unset or blank/whitespace ⇒ no level
        raise LevelSelectionError(NO_LEVEL_MSG)
    if "/" in name or "\\" in name:                       # grammar hint: env is a BARE name, not KIND/NAME
        raise LevelSelectionError(
            f"$UEDCTL_LEVEL is a bare level name, not KIND/NAME: {name!r} "
            "(use e.g. UEDCTL_LEVEL=castle, or --tree level/castle on the command)")
    _check_safe_level(name)                               # dotted/empty/backslash/newline → clean error
    if not (Path(maps_dir) / name).is_dir():
        raise LevelSelectionError(f"$UEDCTL_LEVEL names a level that does not exist: {name!r}")
    return name
