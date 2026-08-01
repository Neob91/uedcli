"""Offline class classification store — the asset-catalog CLASS arm (slice C3).

One git-tracked shard per class at
`<catalog>/classified/class/<package>/<class>.json` (the path casefolded; the
authored spelling kept in the payload). The payload is EXACTLY
`{kind, ref, tags, description}` — curation is tags + description only, with no
override field (owner ruling, class-arm spec §8.4). Two tag namespaces are
reserved and SHAPE-checked, never meaning (spec §8.2): `faces:` needs an axis
token, `mount:` needs a non-empty (free-text) value.

This mirrors `texture_catalog`'s shard / lock / atomic-write pattern but shares
NO code with it — that module is slated for deletion
(`direction/asset-catalog.md`), so the tag normalizer here is a private copy,
not an import.

Concurrency: each shard is its own file, written temp + `os.replace` under a
per-shard flock, so agents classifying disjoint classes never touch one file and
never conflict — the same ethos as the per-actor `.t3d`.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

KIND = "class"

# A tag in one of the reserved namespaces. Matched AFTER normalization (which
# lowercases), so `faces:+X` is already `faces:+x` by the time it is checked.
_NAMESPACE = re.compile(r"^(mount|faces):(.*)$")
_FACE_AXES = ("+x", "-x", "+y", "-y", "+z", "-z")


class ClassCatalogError(ValueError):
    """A class-classification request the store refuses: a bad ref shape, a
    malformed `faces:`/`mount:` tag, or a conflicting description. Carries a
    message naming the offending value; the CLI turns it into a clean exit 2,
    never a traceback."""


# --------------------------------------------------------------------------- tags

def _norm_tags(tags: list[str]) -> list[str]:
    """Strip, lowercase, de-dupe (order-preserving), drop empties — the class
    engine's OWN normalizer. Behaviour matched to `texture_catalog._norm_tags`
    but deliberately not imported (that module is slated for deletion)."""
    seen: dict[str, None] = {}
    for t in tags:
        seen.setdefault(t.strip().lower(), None)
    return [t for t in seen if t]


def validate_tags(tags: list[str]) -> None:
    """Reject a malformed reserved-namespace tag — SHAPE ONLY, never meaning
    (spec §8.2). Applied to ALREADY-normalized tags. `faces:` must carry one axis
    token (`+x -x +y -y +z -z`); `mount:` must carry a non-empty value (the value
    itself is free text); any other tag passes untouched. Raises
    `ClassCatalogError` naming the offending tag."""
    for t in tags:
        m = _NAMESPACE.match(t)
        if m is None:
            continue
        ns, value = m.group(1), m.group(2)
        if ns == "faces":
            if value not in _FACE_AXES:
                raise ClassCatalogError(
                    f"invalid faces: tag {t!r}: the value must be an axis token "
                    f"({' '.join(_FACE_AXES)})")
        elif not value:                                  # mount: with an empty value
            raise ClassCatalogError(
                f"invalid mount: tag {t!r}: mount: needs a non-empty value")


# --------------------------------------------------------------------------- refs / paths

def parse_ref(ref: str) -> tuple[str, str]:
    """A class ref → `(package, classname)`. A class identity is `Package.Class`:
    exactly two non-empty dotted components. Raises `ClassCatalogError` naming the
    ref otherwise (a bare name, an empty component, or an extra dot can never
    address a shard)."""
    parts = ref.split(".")
    if len(parts) != 2 or not all(parts):
        raise ClassCatalogError(
            f"class ref must be Package.Class (two non-empty components): {ref!r}")
    return parts[0], parts[1]


def shard_path(catalog_dir, ref: str) -> Path:
    """The shard file for `ref`: `<catalog>/classified/class/<package>/<class>.json`,
    every path segment CASEFOLDED so a differently-cased re-set addresses the same
    shard (the authored spelling stays inside the payload)."""
    package, classname = parse_ref(ref)
    return (Path(catalog_dir) / "classified" / "class"
            / package.casefold() / f"{classname.casefold()}.json")


# --------------------------------------------------------------------------- the shard

@dataclass(frozen=True, kw_only=True)
class ClassShard:
    ref: str                       # write-once identity — the authored Package.Class spelling
    tags: list[str]
    description: str

    def to_json(self) -> dict:
        return {"kind": KIND, "ref": self.ref, "tags": self.tags,
                "description": self.description}


def shard_from_json(d: dict) -> ClassShard:
    return ClassShard(ref=d["ref"], tags=list(d.get("tags", [])),
                      description=d.get("description", ""))


def load_shard(path) -> ClassShard | None:
    p = Path(path)
    if not p.exists():
        return None
    return shard_from_json(json.loads(p.read_text()))


def save_shard(path, shard: ClassShard) -> None:
    """Atomic: write a temp in the SAME dir + `os.replace`, so a crash never
    truncates a tracked shard and loses classification."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(shard.to_json(), indent=2, sort_keys=True) + "\n")
    os.replace(tmp, p)


# --------------------------------------------------------------------------- locks

@contextmanager
def shard_lock(lock_dir, ref: str):
    """Per-shard flock in `lock_dir`: disjoint classes lock disjoint files, so
    concurrent agents classifying different classes never serialize. The lock name
    is the casefolded identity (matching the shard's own path key)."""
    package, classname = parse_ref(ref)
    Path(lock_dir).mkdir(parents=True, exist_ok=True)
    lock = Path(lock_dir) / f"class-{package.casefold()}-{classname.casefold()}.lock"
    with open(lock, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


# --------------------------------------------------------------------------- set / merge

def merge_set(prior: ClassShard | None, ref: str, *, tags, description,
              replace: bool) -> ClassShard:
    """Compute the new shard for a `classify set` — pure, no IO. `prior` is the
    loaded shard or None. Rules (spec §5):

    - `tags` UNION-merge through the normalizer (prior ∪ new), then shape-validated;
    - `description`: a DIFFERENT non-empty description raises `ClassCatalogError`
      printing the STORED text, unless `replace`; identical text, or an empty
      prior, is a plain set;
    - `ref` is WRITE-ONCE: an existing shard keeps its authored spelling.

    `tags`/`description` are None when the caller did not supply that field."""
    prior_tags = prior.tags if prior else []
    prior_desc = prior.description if prior else ""
    kept_ref = prior.ref if prior else ref

    if tags is None:
        merged_tags = list(prior_tags)
    else:
        merged_tags = _norm_tags([*prior_tags, *tags])
    validate_tags(merged_tags)

    if description is None:
        new_desc = prior_desc
    elif not prior_desc or replace or description == prior_desc:
        new_desc = description
    else:
        raise ClassCatalogError(
            f"{ref}: a different description is already stored — pass --replace to "
            f"overwrite it. Stored: {prior_desc!r}")

    return ClassShard(ref=kept_ref, tags=merged_tags, description=new_desc)


# --------------------------------------------------------------------------- unset

def unset(prior: ClassShard, *, remove_tags, clear_tags: bool,
          clear_description: bool) -> ClassShard:
    """Compute the shard after a `classify unset` field clear — pure, no IO
    (`--all`, which deletes the whole shard, is the caller's file op, not here).

    - `remove_tags` (a list): drop exactly those tags (normalized; a tag not
      present is a harmless no-op);
    - `clear_tags`: empty the tags list;
    - `clear_description`: empty the description.
    """
    tags = prior.tags
    if clear_tags:
        tags = []
    elif remove_tags:
        drop = set(_norm_tags(remove_tags))
        tags = [t for t in prior.tags if t not in drop]
    desc = "" if clear_description else prior.description
    return ClassShard(ref=prior.ref, tags=tags, description=desc)


# --------------------------------------------------------------------------- queries

def _shard_root(catalog_dir) -> Path:
    return Path(catalog_dir) / "classified" / "class"


def load_all_shards(catalog_dir) -> tuple[list[ClassShard], list[str]]:
    """Every stored class shard, globbed LIVE from the shard tree — there is no
    roll-up index to stale, so a deletion is seen immediately. Returns
    `(shards, unreadable_paths)`; an unreadable/malformed shard is skipped and its
    path collected so the caller can note it on stderr, never a traceback."""
    root = _shard_root(catalog_dir)
    shards: list[ClassShard] = []
    bad: list[str] = []
    for jf in sorted(root.glob("*/*.json")) if root.is_dir() else []:
        try:
            shards.append(shard_from_json(json.loads(jf.read_text())))
        except (ValueError, OSError):
            bad.append(str(jf))
    return shards, bad


def classified_refs(catalog_dir) -> set[str]:
    """The casefolded identity of every class with a shard on disk — the set
    `list --classified/--unclassified` and `status` test membership against."""
    root = _shard_root(catalog_dir)
    out: set[str] = set()
    for jf in root.glob("*/*.json") if root.is_dir() else []:
        out.add(f"{jf.parent.name}.{jf.stem}")           # already casefolded on disk
    return out


def is_classified(catalog_dir, ref: str) -> bool:
    return shard_path(catalog_dir, ref).exists()


def tag_vocabulary(shards: list[ClassShard]) -> list[tuple[str, int]]:
    """The tag vocabulary in use across `shards`, `(tag, count)` sorted by count
    descending then tag — mirrors `texture_catalog.all_tags`, to curb drift."""
    counts: dict[str, int] = {}
    for s in shards:
        for t in s.tags:
            counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items(), key=lambda tc: (-tc[1], tc[0]))
