"""The ONE shared per-actor T3D tree: read/write a set of actors as
`<tree_dir>/actors/<name>/{actor.t3d, order_value[, folder]}`, plus the LexoRank order-value algebra,
the coordination-free name allocator, and the actor-body strip/inject.

This is the single implementation used by ALL THREE T3D trees (direction/trunk-and-editor.md 2026-07-18 23:01 UTC —
"stash, prefab, and trunk MUST share ONE T3D tree format"):

- the git **trunk** (`maps/<level>/`) — via `trunk.py`'s thin re-exports,
- a **stash** entry (`.uedcli/stash/<id>/`) — via `stash_register.py`,
- a library **prefab** (`<prefabs-dir>/<name>/`) — via `stashlib.py`.

The directory name is the single source of truth for an actor's identity: `actor.t3d` is stored with
its Name= header/trailer stripped and its brush model-ref neutralized to a constant, both re-derived
from the dir name on read. Order is a per-actor LexoRank `order_value` sidecar; the CSG order is the
(order_value, name) sort. Any per-tree EXTRAS (a stash/prefab `meta.json` + `packages` list) sit
BESIDE the shared `actors/` tree, written/read by `write_sidecars`/`read_sidecars` (the trunk simply
never calls them). See specs/2026-07-05-uedcli-git-native-model-design.md +
board item `delete-the-ephemeral-spec-specs-2026-07-18` + direction/trunk-and-editor.md (2026-07-05 / 2026-07-18). Pure module — no editor,
no session store.
"""
from __future__ import annotations

import copy
import json
import os
import re
import secrets
import shutil
from pathlib import Path

from .model import Actor, Level, parse_t3d
from .normalize import canonical_actor_t3d

_RANK_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"   # base-36, ascending == lexicographic
_RANK_BASE = len(_RANK_DIGITS)                          # 36
_SUFFIX_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_SUFFIX_LEN = 6
_MODEL_CONST = "Model"                                  # brush model_name in the STORED body


# --- LexoRank order-value algebra ---

def rank_between(a: str | None, b: str | None) -> str:
    """A base-36 string r with a < r < b lexicographically. None = open end (-inf / +inf).
    Grows length when the neighbours are adjacent, so it never exhausts. Precondition a < b
    (both real). Do not allocate against the single smallest digit ('0') as an upper bound —
    `initial_ranks` keeps ranks in the interior so that never arises."""
    assert a is None or b is None or a < b, f"rank_between needs a < b, got {a!r},{b!r}"
    out: list[str] = []
    i = 0
    while True:
        da = _RANK_DIGITS.index(a[i]) if (a is not None and i < len(a)) else 0
        db = _RANK_DIGITS.index(b[i]) if (b is not None and i < len(b)) else _RANK_BASE
        if db - da >= 2:
            out.append(_RANK_DIGITS[(da + db) // 2])
            r = "".join(out)
            # Generated ranks never carry a trailing '0' (the emitted digit is always >= 1), so a
            # gap always exists between two of them. Only a hand-edited / imported pair with no gap
            # (e.g. "a","a0", which are lexicographically adjacent) can reach here with r NOT strictly
            # between — refuse loudly rather than corrupt CSG order.
            if (a is not None and not a < r) or (b is not None and not r < b):
                raise ValueError(
                    f"no order_value exists strictly between {a!r} and {b!r} (adjacent ranks, no gap)")
            return r
        out.append(_RANK_DIGITS[da])   # gap < 2: keep a's digit (0 when padding) and descend
        i += 1


def ranks_between(lo: str | None, hi: str | None, k: int) -> list[str]:
    """`k` distinct ASCENDING ranks strictly between `lo` and `hi` (either `None` = open end), minted
    by iterating `rank_between` (each freshly-minted rank becomes the next `lo`). Used to place a
    block of K actors in a single gap (`actor order`, `actor add --order`). Propagates
    `rank_between`'s `ValueError` when `lo`/`hi` are genuinely-adjacent imported ranks with no gap
    (the caller turns it into a named exit-2). `k == 0` → `[]`."""
    out: list[str] = []
    cur = lo
    for _ in range(k):
        r = rank_between(cur, hi)
        out.append(r)
        cur = r
    return out


def initial_ranks(n: int) -> list[str]:
    """n ascending, distinct ranks spread across the interior — the seed order for a fresh level's
    actors (assigned in their current order)."""
    ranks: list[str] = []
    lo: str | None = None
    for _ in range(n):
        r = rank_between(lo, None)
        ranks.append(r)
        lo = r
    return ranks


# --- random-suffix name allocation (coordination-free identity) ---

def _rand_suffix() -> str:
    return "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(_SUFFIX_LEN))


def alloc_name(stem: str, existing: set[str], *, _rand=_rand_suffix) -> str:
    """A fresh immutable actor name `<stem>_<rand>`; re-rolls on the (astronomically rare) clash
    with `existing` (the current level's names). `_rand` is injectable for tests."""
    while True:
        name = f"{stem}_{_rand()}"
        if name not in existing:
            return name


# --- per-actor stored body: strip/inject Name= and the brush model-ref ---

# Anchored to the `Begin Actor` header line (keep group 1), so a prop VALUE that happens to contain
# ` Name=` is never touched — only the actor's own header token is stripped.
_NAME_HDR = re.compile(r"^(Begin Actor\b.*?) Name=\S+", re.M)
_NAME_TRAILER = re.compile(r'^\s*Name="[^"]*"\n', re.M)    # the trailing `    Name="<x>"` line


def dump_actor_body(actor: Actor) -> str:
    """Canonical single-actor T3D with all identity tokens neutralized: no actor Name=, brush
    model-ref = the constant `Model`. Deterministic (clean git diffs)."""
    a = copy.deepcopy(actor)
    if a.brush is not None:
        a.brush.model_name = _MODEL_CONST
        a.props = [(k, f"Model'MyLevel.{_MODEL_CONST}'" if k == "Brush" else v) for k, v in a.props]
    t = canonical_actor_t3d(a)
    t = _NAME_HDR.sub(r"\1", t, count=1)       # drop ` Name=<x>` from the `Begin Actor` header
    t = _NAME_TRAILER.sub("", t)               # drop the trailing Name="..." line
    return t


def load_actor_body(text: str, name: str) -> Actor:
    """Parse a stored body and re-inject identity from the directory `name`."""
    lvl = parse_t3d(text)                       # exactly one actor; header has no Name → keyed ""
    if not lvl.actors:                          # non-blank but no parseable Begin Actor block
        raise ValueError(f"actors/{name}/actor.t3d: no parseable actor "
                         f"(corrupt, truncated, or unresolved merge markers?)")
    a = next(iter(lvl.actors.values()))
    a.name = name
    if a.brush is not None:
        model = f"{_MODEL_CONST}_{name}"
        a.brush.model_name = model
        a.props = [(k, f"Model'MyLevel.{model}'" if k == "Brush" else v) for k, v in a.props]
    return a


# --- per-actor directory tree read/write ---

def _actors_dir(tree_dir: Path) -> Path:
    return Path(tree_dir) / "actors"


def check_safe_segment(name: str) -> None:
    """Reject an actor name that isn't a single safe directory segment (path-traversal guard for
    every `actors/<name>` join). The ONE shared name→dir scheme across trunk/stash/prefab (spec §3):
    a real UnrealEngine object name can never contain `/`, `\\`, or `.`/`..` or be empty, so this
    only fires on a genuinely malformed name — surfaced by callers as a clean, value-naming exit 2."""
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"actor name is not a safe directory segment: {name!r}")


def write_actor_tree(tree_dir: Path, level: Level, ranks: dict[str, str],
                     *, deleted: frozenset[str] | set[str] = frozenset(),
                     only: set[str] | None = None) -> None:
    """Write `level` into the per-actor-dir tree as a DELTA. `ranks` maps each actor name → its
    order_value (LexoRank) and MUST cover every actor. Actors in `level.actors` are (re)written —
    ALL of them when `only` is None, else exactly the names in `only` (the caller's changed set;
    `TrunkLevelSource.save` passes the content-diff vs its load snapshot so an untouched actor's
    dir is never stomped from a stale model). Only the dirs named in `deleted` — the CALLER'S OWN
    deletions (its loaded set minus its current set) — are pruned. An on-disk actor dir neither
    (re)written nor in `deleted` is LEFT ALONE: it belongs to a concurrent writer (per-actor dirs
    make disjoint edits compose), and the old make-disk-match-memory full rewrite silently
    destroyed concurrent adds/edits/deletes (direction/trunk-and-editor.md 2026-07-18 — trunk delta writes).

    Per-actor writes are ATOMIC and ordered: `order_value` lands first, then `actor.t3d` via
    tmp + `os.replace` — a lock-free reader (loads take no flock) sees either the old or the new
    COMPLETE body, never a truncated one, and `read_actor_tree`'s admission gate (`actor.t3d`
    exists) never admits a dir whose rank hasn't landed."""
    missing = set(level.actors) - set(ranks)
    if missing:
        raise ValueError(f"write_actor_tree: no order_value for actor(s): {', '.join(sorted(missing))}")
    for name in level.actors:
        check_safe_segment(name)
    adir = _actors_dir(tree_dir)
    adir.mkdir(parents=True, exist_ok=True)
    for name in deleted:                              # prune ONLY the caller's own deletions
        check_safe_segment(name)
        d = adir / name
        if name not in level.actors and d.is_dir():   # tolerate an already-gone dir (racing delete)
            shutil.rmtree(d)
    for name, actor in level.actors.items():
        if only is not None and name not in only:
            continue
        d = adir / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "order_value").write_text(ranks[name] + "\n")
        tmp = d / f".actor.t3d.tmp{os.getpid()}"
        try:
            tmp.write_text(dump_actor_body(actor))
            os.replace(tmp, d / "actor.t3d")          # atomic: readers never see a torn body
        finally:
            tmp.unlink(missing_ok=True)
        # The `folder` sidecar: a uedcli-side organization path, NOT in the T3D body/map (see
        # model.Actor.folder). Written ATOMICALLY (tmp + os.replace, like actor.t3d) — loads take
        # no flock, so a plain write_text would let a lock-free reader see a truncated first line and
        # misreport the actor as ungrouped, skewing a concurrent `actor find --folder`. When the
        # folder is None (unset), REMOVE any existing file so `actor folder unset` truly clears it.
        fpath = d / "folder"
        if actor.folder is not None:
            ftmp = d / f".folder.tmp{os.getpid()}"
            try:
                ftmp.write_text(actor.folder + "\n")
                os.replace(ftmp, fpath)
            finally:
                ftmp.unlink(missing_ok=True)
        else:
            fpath.unlink(missing_ok=True)
        # The `labels` sidecar: a uedcli-side FLAT set (sorted-set analog of `folder`), NOT in the
        # T3D body/map. Written ATOMICALLY (tmp + os.replace, like `folder`) so a lock-free reader
        # never sees a torn line. Sorted, one per line. When the set is empty, REMOVE any existing
        # file so `actor label clear` truly clears it (mirrors the folder-unset branch).
        lpath = d / "labels"
        if actor.labels:
            ltmp = d / f".labels.tmp{os.getpid()}"
            try:
                ltmp.write_text("\n".join(sorted(actor.labels)) + "\n")
                os.replace(ltmp, lpath)
            finally:
                ltmp.unlink(missing_ok=True)
        else:
            lpath.unlink(missing_ok=True)


def remove_actor(tree_dir: Path, name: str) -> None:
    """Delete an actor's `actors/<name>/` directory. Errors (naming the value) if it is absent or
    not a safe directory segment."""
    check_safe_segment(name)
    d = _actors_dir(tree_dir) / name
    if not d.is_dir():
        raise ValueError(f"remove_actor: no such actor directory: {name!r}")
    shutil.rmtree(d)


def append_rank(ranks: dict[str, str]) -> str:
    """A new order_value ordering AFTER every current actor (append). Empty level → the first rank."""
    highest = max(ranks.values()) if ranks else None
    return rank_between(highest, None)


def read_actor_tree(
        tree_dir: Path) -> tuple[Level, dict[str, str], dict[str, str], dict[str, str | None]]:
    """Read the per-actor-dir tree → (Level, name→order_value, name→raw stored body text,
    name→folder). `level.order` is the (order_value, name) sort. A missing/empty tree → an empty
    level. The raw-body map is the load-time snapshot `TrunkLevelSource.save` content-diffs against
    so it writes only what its process actually changed (direction/trunk-and-editor.md 2026-07-18 — trunk delta
    writes). The name→folder map is the folder half of that snapshot: a folder-ONLY change leaves
    body+rank byte-identical, so the delta diff MUST compare it too or the write is silently dropped.
    An EMPTY `actor.t3d` is skipped like a missing one: it can only be a crashed pre-atomic-write
    leftover, and admitting it would make every later read of the tree die parsing an empty body.
    Each actor's `folder` is loaded into `actor.folder` (absent/empty file → None). Note: only
    sub-DIRECTORIES of `actors/` are iterated, so a legacy flat `actors/<name>.t3d` FILE is ignored
    (stash_register/stashlib treat such a stale tree as absent)."""
    adir = _actors_dir(tree_dir)
    level = Level()
    ranks: dict[str, str] = {}
    bodies: dict[str, str] = {}
    folders: dict[str, str | None] = {}
    if adir.is_dir():
        for d in sorted(p for p in adir.iterdir() if p.is_dir()):
            body = d / "actor.t3d"
            if not body.is_file():
                continue
            text = body.read_text()
            if not text.strip():                      # torn/crashed leftover — never a valid actor
                continue
            name = d.name
            actor = load_actor_body(text, name)
            fp = d / "folder"
            folder = fp.read_text().strip() if fp.is_file() else ""
            actor.folder = folder or None             # absent/empty → ungrouped
            lp = d / "labels"
            actor.labels = (frozenset(ln.strip() for ln in lp.read_text().splitlines() if ln.strip())
                            if lp.is_file() else frozenset())  # absent/empty → no labels
            level.actors[name] = actor
            bodies[name] = text
            folders[name] = actor.folder
            rv = d / "order_value"
            ranks[name] = rv.read_text().strip() if rv.is_file() else ""
    level.order = sorted(level.actors, key=lambda n: (ranks.get(n, ""), n))
    return level, ranks, bodies, folders


# --- the beside-`actors/` sibling metadata (stash/prefab EXTRAS; the trunk has none) ---

def write_sidecars(tree_dir: Path, *, packages: list[str], meta: dict) -> None:
    """Write the per-tree extras that sit BESIDE `actors/`: `packages` (newline list, trailing
    newline when non-empty) and `meta.json` (`json.dumps(sort_keys=True)`). Stash/prefab call this;
    the trunk never does. `write_actor_tree` has already `mkdir`'d the tree, but be robust for a
    caller that writes sidecars first."""
    tree_dir = Path(tree_dir)
    tree_dir.mkdir(parents=True, exist_ok=True)
    (tree_dir / "packages").write_text("\n".join(packages) + ("\n" if packages else ""))
    (tree_dir / "meta.json").write_text(json.dumps(meta, sort_keys=True))


def read_sidecars(tree_dir: Path) -> tuple[list[str], dict]:
    """Read the beside-`actors/` extras → (packages, meta). Missing files → `([], {})` (mirrors the
    all-empty-on-missing contract of `read_stash`)."""
    tree_dir = Path(tree_dir)
    pf = tree_dir / "packages"
    mf = tree_dir / "meta.json"
    packages = [ln for ln in pf.read_text().splitlines() if ln] if pf.is_file() else []
    meta = json.loads(mf.read_text()) if mf.is_file() else {}
    return packages, meta


# --- duplicate-order_value detection (the doctor/materialize warn source) ---

def duplicate_ranks(ranks: dict[str, str]) -> list[tuple[str, list[str]]]:
    """Order_values shared by >1 actor → [(order_value, [names sorted]), ...] sorted by value.
    Empty when every actor has a distinct order_value."""
    by_value: dict[str, list[str]] = {}
    for name, value in ranks.items():
        by_value.setdefault(value, []).append(name)
    return [(v, sorted(ns)) for v, ns in sorted(by_value.items()) if len(ns) > 1]
