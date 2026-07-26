"""Pure helpers for stash/prefab capture, placement, and the durable library. No git, no editor —
the model is the only input/output. Stash/prefab apply is a MODEL-SIDE merge into the selected
level's trunk; this module supplies the value transforms (capture normalization, translation, group
rewrite, package extraction) and the file I/O."""
from __future__ import annotations

import copy
import os
import re
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from uedcli.emit import clean, fmt_coord
from uedcli.model import Actor, Level, Vec3, parse_t3d
from uedcli.normalize import canonical_actor_t3d
from uedcli.writes import union_bounds
from uedcli import t3dtree

_ENGINE_PACKAGES = frozenset({"Engine"})
_ZERO: Vec3 = (Decimal(0), Decimal(0), Decimal(0))
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
_STAGING_DIR = ".staging"


class OldFormatPrefab(Exception):
    """Raised by `read_prefab` for a pre-per-actor-tree prefab (a single `Begin Map` blob `<name>.t3d`
    + `<name>.json`). Migration is a HARD CUTOVER (decisions.md 2026-07-18 23:01 UTC addendum, sub-choice
    1): there is NO dual-read of the old format — the user re-captures the prefab under the new layout.
    Dispatch surfaces this as a clean exit-2 message naming the prefab, never a traceback."""


def _package_of(ref: str | None) -> str | None:
    if not ref or "." not in ref:
        return None
    return ref.split(".", 1)[0]


def referenced_packages(actors: list[Actor]) -> set[str]:
    """Distinct non-Engine TEXTURE packages referenced by `actors` (each brush poly's Texture
    prefix). Class packages are NOT collected: T3D writes `Class=` UNQUALIFIED, so a class package
    can't be string-derived — those are not recorded in the trunk (there is no package manifest);
    they're derived on demand from the .dx import table (dxpkg) and ensure-loaded at materialize.
    This is the stash's OWN texture-dep set."""
    pkgs: set[str] = set()
    for a in actors:
        if a.brush is None:
            continue
        for poly in a.brush.polys:
            pkg = _package_of(poly.texture)
            if pkg and pkg not in _ENGINE_PACKAGES:
                pkgs.add(pkg)
    return pkgs


def validate_member_name(name: str) -> None:
    """Guard a stash id / prefab name used in git-tree and filesystem paths. Rejects empty,
    absolute, `..`, backslash, and any segment outside [A-Za-z0-9._-] so `--id`/`--as` can't escape
    the store/library root. Forward slashes are allowed (prefab subdirs like `hangar/archway`)."""
    if not name or name.startswith("/") or "\\" in name:
        raise ValueError(f"invalid name {name!r}: empty, absolute, or contains a backslash")
    segments = name.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        raise ValueError(f"invalid name {name!r}: empty or '.'/'..' path segment")
    if any(not _SAFE_SEGMENT.fullmatch(seg) for seg in segments):
        raise ValueError(f"invalid name {name!r}: segments must match [A-Za-z0-9._-]")


def translate(actors: list[Actor], delta: Vec3) -> list[Actor]:
    """Deep copies of `actors` with `delta` added to each Location. Vertices are local to
    Location, so only Location moves (geometry rides along)."""
    out = []
    for a in actors:
        b = copy.deepcopy(a)
        loc = b.location or _ZERO
        b.location = (loc[0] + delta[0], loc[1] + delta[1], loc[2] + delta[2])
        out.append(b)
    return out


def normalize_for_capture(actors: list[Actor]) -> tuple[list[Actor], Vec3]:
    """Shift `actors` so the union bbox-min corner is the origin. Returns the shifted copies and
    the original world anchor (the pre-shift bbox-min) for no---at replay. Requires a non-empty
    set — `union_bounds([])` would otherwise raise an opaque unpack error."""
    if not actors:
        raise ValueError("normalize_for_capture: no actors to capture")
    lo, _hi = union_bounds(actors)
    return translate(actors, (-lo[0], -lo[1], -lo[2])), lo


def with_group(actor: Actor, group: str | None) -> Actor:
    """Copy with Group replaced (or removed if group is None). Group is UnrealEd's native cohesion
    mechanism; a captured group name is meaningless in a new level, so apply always replaces it."""
    b = copy.deepcopy(actor)
    b.props = [(k, v) for (k, v) in b.props if k != "Group"]
    if group is not None:
        b.props.append(("Group", group))
    return b


def with_folder(actor: Actor, folder: str | None) -> Actor:
    """Copy with the uedcli-side `folder` field set (or cleared if None). Independent of `with_group`
    (the T3D `Group` prop) — the two are orthogonal placement dimensions. Since the unify-T3D-trees
    change (decisions.md 2026-07-18 23:01 UTC addendum, sub-choice 2) a captured stash/prefab member
    DOES persist its own `folder` sidecar (full trunk parity), so a placed actor defaults to its
    STORED folder; `stash/prefab apply --folder` OVERRIDES that at placement, and absent both the
    actor is unfoldered (folder=None)."""
    b = copy.deepcopy(actor)
    b.folder = folder
    return b


def format_summary(set_id: str, actors: list[Actor]) -> str:
    """The `x,y,z..x,y,z` bbox is tolerance-snapped and formatted like every other reported
    coordinate (`emit.clean` + `emit.fmt_coord`). It used to render `tuple(int(c) for c in lo)`, and
    `int()` on a Decimal TRUNCATES toward zero: rotator noise at 227.999994 printed as 227 — a whole
    unit wrong, worse than showing the noise — and a genuine -2.5 min corner printed as -2, shrinking
    the reported box below the real one."""
    lo, hi = union_bounds(actors) if actors else (_ZERO, _ZERO)

    def _vec(v):
        return ",".join(fmt_coord(clean(c)) for c in v)

    out = [f"{set_id}: {len(actors)} actors   bbox {_vec(lo)}..{_vec(hi)}",
           f"  {'name':<20} {'class':<14} {'polys':>5}"]
    for a in actors:
        npolys = len(a.brush.polys) if a.brush else 0
        out.append(f"  {a.name:<20} {a.cls:<14} {npolys:>5}")
    return "\n".join(out)


# --- shared stash/prefab wrapper helpers (both boxes are per-actor T3D trees via `t3dtree`) ---

def _level_from_blobs(full_level: dict[str, str], order: list[str],
                      folders: dict[str, str | None] | None = None) -> Level:
    """Assemble a `Level` from the wrapper currency `full_level` (name→canonical T3D blob WITH Name=)
    + `order`, re-keying each parsed actor to its DICT name (the identity) and stamping the optional
    per-member `folder`. This is the seam that hands real `Actor`s to `t3dtree.write_actor_tree`,
    whose `dump_actor_body` then strips the identity tokens — so the STORED `actor.t3d` is byte-
    identical to the trunk's. A blob carries no folder (folder is a uedcli-side sidecar, never in
    T3D), so the folder channel is threaded separately."""
    folders = folders or {}
    level = Level()
    for n in order:
        if n not in full_level:
            continue
        lvl = parse_t3d("Begin Map\n" + full_level[n] + "\nEnd Map\n")
        if not lvl.actors:
            continue
        a = next(iter(lvl.actors.values()))
        a.name = n
        a.folder = folders.get(n)
        level.actors[n] = a
    level.order = [n for n in order if n in level.actors]
    return level


def _read_ranks_if_present(dest: Path) -> dict[str, str]:
    """`{name: order_value}` from an existing per-actor tree at `dest`, `{}` when absent or a stale
    flat tree (no per-actor sidecar dirs). Lets a rewrite PRESERVE surviving actors' ranks (merge-
    clean, no churn) rather than re-mint every save."""
    dest = Path(dest)
    if not (dest / "actors").is_dir():
        return {}
    _lvl, ranks, _b, _f = t3dtree.read_actor_tree(dest)
    return ranks


def _ranks_for(order: list[str], prior: dict[str, str]) -> dict[str, str]:
    """Assign an `order_value` to each name in `order`: a SURVIVING actor keeps its prior rank; a
    NEW actor is minted strictly AFTER every current + already-assigned rank (append). Fresh capture
    (`prior={}`) lays ranks down in capture order (== `initial_ranks(len(order))`). Mirrors
    `TrunkLevelSource.save`'s preserve-then-append rule, so all three trees rank identically (the
    consistency invariant)."""
    ranks: dict[str, str] = {}
    for n in order:
        if n in prior:
            ranks[n] = prior[n]
        else:
            ranks[n] = t3dtree.append_rank({**prior, **ranks})
    return ranks


def write_tree_box(dest: Path, *, full_level: dict[str, str], order: list[str],
                   packages: list[str], meta: dict, folders: dict[str, str | None] | None = None,
                   force: bool = False) -> None:
    """Write a stash/prefab box as a per-actor T3D tree at `dest`: `actors/<name>/{actor.t3d,
    order_value[, folder]}` + sibling `packages` + `meta.json` (via `t3dtree`). Ranks are PRESERVED
    across rewrites (`_read_ranks_if_present` → `_ranks_for`) so an unchanged actor's files are
    byte-identical rewrite-to-rewrite (merge-clean). The whole tree is built in a `.staging/` scratch
    and swapped in with a single `os.replace`, so a rewrite never leaves a HALF-written or ghost-actor
    box — a reader sees either the whole prior box or the whole new one. (A crash in the narrow
    `rmtree(dest)`→`os.replace` window of a FORCE rewrite can leave NO box, with the new tree stranded
    under `.staging/` where the listers ignore it; the prior box is then gone. Acceptable: a prefab is
    git-recoverable and a stash is throwaway. This matches the pre-unification stash behavior.)
    Refuses an existing `dest` without `force`. The caller has already validated the box name +
    containment."""
    dest = Path(dest)
    if dest.exists() and not force:
        raise FileExistsError(f"already exists: {dest.name} (use --force)")
    prior = _read_ranks_if_present(dest)
    level = _level_from_blobs(full_level, order, folders)
    ranks = _ranks_for(level.order, prior)
    staging_root = dest.parent / _STAGING_DIR
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=staging_root))
    try:
        t3dtree.write_actor_tree(staging, level, ranks)
        t3dtree.write_sidecars(staging, packages=packages, meta=meta)
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, dest)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def read_tree_box(dest: Path) -> tuple[dict[str, str], list[str], list[str], dict, dict[str, str | None]]:
    """Read a per-actor T3D box at `dest` → (full{name:blob-WITH-Name}, order, packages, meta,
    folders). `full` re-emits `canonical_actor_t3d` (Name= back from the dir name) so downstream
    consumers are unchanged; `order` is the (order_value, name) sort; `folders` maps name→its stored
    folder (or None)."""
    level, _ranks, _bodies, folders = t3dtree.read_actor_tree(dest)
    full = {n: canonical_actor_t3d(level.actors[n]) for n in level.order}
    packages, meta = t3dtree.read_sidecars(dest)
    return full, level.order, packages, meta, folders


# --- prefab library (durable, git-committed; a per-actor T3D tree `<name>/`) ---

def write_prefab(root, name: str, *, full_level: dict[str, str], order: list[str],
                 packages: list[str], meta: dict, folders: dict[str, str | None] | None = None,
                 force: bool = False) -> None:
    """Write a prefab as a per-actor T3D tree `<root>/<name>/{actors/…, packages, meta.json}` (spec
    2026-07-18 §1). `validate_member_name` + a resolved-path containment check keep `--as ../x` from
    escaping the library root; the per-member `folders` sidecar gives full trunk parity."""
    validate_member_name(name)
    root = Path(root).resolve()
    dest = (root / name).resolve()
    if not (dest == root or dest.is_relative_to(root)):
        raise ValueError(f"prefab name escapes the library root: {name!r}")
    if dest.exists() and not force:
        raise FileExistsError(f"prefab already exists: {name} (use --force)")
    write_tree_box(dest, full_level=full_level, order=order, packages=packages, meta=meta,
                   folders=folders, force=force)


def read_prefab(root, name: str) -> tuple[dict[str, str], list[str], list[str], dict, dict[str, str | None]]:
    """Read a prefab → (full, order, packages, meta, folders). Migration is a HARD CUTOVER: an
    OLD-format prefab (a `<name>.t3d` FILE with no new `<name>/` dir) raises `OldFormatPrefab` (the
    user re-captures it) rather than being auto-converted (decisions.md 2026-07-18 addendum,
    sub-choice 1)."""
    root = Path(root)
    dest = root / name
    if not dest.is_dir():
        if (root / f"{name}.t3d").is_file():
            raise OldFormatPrefab(
                f"old-format prefab {name!r} — re-capture it (the on-disk format changed)")
        raise FileNotFoundError(f"prefab not found: {name!r}")
    return read_tree_box(dest)


def list_prefabs(root) -> list[str]:
    """Prefab names under `root`. A NEW prefab is a DIR carrying `meta.json` (like `list_stashes`),
    at any depth (nested names). An OLD-format prefab is a `<name>.t3d` FILE with NO `actors`
    component in its path (so a new tree's `<name>/actors/<actor>/actor.t3d` is never miscounted) —
    still LISTED so `read_prefab` can surface the actionable hard-cutover error on use rather than a
    misleading "not found". `.staging` (in-flight writes) is skipped."""
    root = Path(root)
    if not root.exists():
        return []

    def _staged(p: Path) -> bool:
        return _STAGING_DIR in p.relative_to(root).parts

    new = {p.parent.relative_to(root).as_posix() for p in root.rglob("meta.json") if not _staged(p)}
    old = {p.relative_to(root).as_posix()[:-4] for p in root.rglob("*.t3d")
           if "actors" not in p.relative_to(root).parts and not _staged(p)}
    return sorted(new | old)
