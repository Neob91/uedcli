"""Offline audio classification store — the asset-catalog SOUND + MUSIC arms.

One git-tracked shard per classified object at `<catalog>/classified/<kind>/<seg…>/<name>.json`,
every path segment casefolded, where the segments are the object's IDENTITY split on dots
(`Package/Name` for a 2-part identity, `Package/Group…/Name` for a collision 3-part one). The
payload is EXACTLY `{kind, ref, tags, description}`; `ref` is the stored identity (write-once
authored spelling), curation is tags + description only.

This mirrors `class_catalog`'s shard / per-shard flock / temp+`os.replace` shape but shares NO code
with it — a private copy (the class module's own rule; those modules are independently owned).

Two deliberate divergences from the class engine:

- **Variable-arity ref.** `class_catalog.parse_ref` hard-rejects any non-2-part ref, and its shard
  path rebuilds the key from a fixed 2-segment path. Audio identity is 2-part OR 3-part, so this arm
  owns a ref parser accepting ≥2 non-empty components and a shard layout that encodes the full key.
- **Write rule: refuse, then `--force`.** `set` over an existing shard REFUSES (naming the ref);
  `--force` REPLACES it wholesale. No tag union-merge and no per-field merge — so `--force` drops any
  stored description a forcing `set` omits (`board/sound-corpus-remeasure/spec.md` §7;
  `direction/safety.md`: never silently overwrite authored classification).
"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class AudioCatalogError(ValueError):
    """An audio-classification request the store refuses: a bad ref shape, or a `set` over an
    already-classified object without `--force`. Carries a message naming the offending value; the
    CLI turns it into a clean exit 2, never a traceback."""


# --------------------------------------------------------------------------- tags

def norm_tags(tags: list[str]) -> list[str]:
    """Strip, lowercase, de-dupe (order-preserving), drop empties. Audio tags carry no reserved
    namespaces (unlike the class arm's `mount:`/`faces:`), so there is no shape check."""
    seen: dict[str, None] = {}
    for t in tags:
        seen.setdefault(t.strip().lower(), None)
    return [t for t in seen if t]


# --------------------------------------------------------------------------- refs / paths

def parse_ref(ref: str) -> list[str]:
    """An audio identity → its dotted components. Identity is `Package.Name` or the full dotted
    `Package.Group.Name`: at least two non-empty components. Raises `AudioCatalogError` naming the
    ref otherwise (a bare name or an empty component can never address a shard)."""
    parts = ref.split(".")
    if len(parts) < 2 or not all(parts):
        raise AudioCatalogError(
            f"audio ref must be Package.Name or Package.Group.Name (≥2 non-empty components): {ref!r}")
    return parts


def _shard_root(catalog_dir, kind: str) -> Path:
    return Path(catalog_dir) / "classified" / kind


def shard_path(catalog_dir, kind: str, ref: str) -> Path:
    """The shard file for identity `ref` under `kind`: the dotted components as casefolded path
    segments, `<…>.json` at the leaf. Casefolded so a differently-cased identity addresses one
    shard; the authored spelling stays inside the payload."""
    parts = [p.casefold() for p in parse_ref(ref)]
    return _shard_root(catalog_dir, kind).joinpath(*parts[:-1], f"{parts[-1]}.json")


# --------------------------------------------------------------------------- the shard

@dataclass(frozen=True, kw_only=True)
class AudioShard:
    kind: str                      # "sound" | "music"
    ref: str                       # write-once identity — the authored Package[.Group].Name spelling
    tags: list[str]
    description: str

    def to_json(self) -> dict:
        return {"kind": self.kind, "ref": self.ref, "tags": self.tags,
                "description": self.description}


def shard_from_json(d: dict) -> AudioShard:
    return AudioShard(kind=d["kind"], ref=d["ref"], tags=list(d.get("tags", [])),
                      description=d.get("description", ""))


def load_shard(path) -> AudioShard | None:
    """The shard at `path`, or None when absent. A tracked shard that is unreadable or malformed
    (a git merge-conflicted file is invalid JSON) raises `AudioCatalogError` naming the path — never
    a bare `JSONDecodeError`/`KeyError` traceback to the user."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return shard_from_json(json.loads(p.read_text()))
    except (ValueError, KeyError, OSError) as e:
        raise AudioCatalogError(f"unreadable classification shard {p}: {e}")


def save_shard(path, shard: AudioShard) -> None:
    """Atomic: write a temp in the SAME dir + `os.replace`, so a crash never truncates a tracked
    shard and loses classification."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(shard.to_json(), indent=2, sort_keys=True) + "\n")
    os.replace(tmp, p)


# --------------------------------------------------------------------------- locks

@contextmanager
def shard_lock(lock_dir, kind: str, ref: str):
    """Per-shard flock in `lock_dir`: disjoint objects lock disjoint files, so concurrent agents
    classifying different objects never serialize. The lock name is the casefolded kind+identity."""
    Path(lock_dir).mkdir(parents=True, exist_ok=True)
    key = "-".join(p.casefold() for p in parse_ref(ref))
    lock = Path(lock_dir) / f"{kind}-{key}.lock"
    with open(lock, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


# --------------------------------------------------------------------------- set (refuse / force)

def set_shard(prior: AudioShard | None, kind: str, ref: str, *, tags, description,
              force: bool) -> AudioShard:
    """Compute the shard for a `classify set` — pure, no IO. `prior` is the loaded shard or None.

    - An existing shard (`prior is not None`) REFUSES unless `force`, raising `AudioCatalogError`
      naming the ref and printing the stored payload.
    - Otherwise writes EXACTLY the supplied tags/description — no union, no per-field merge. So a
      forcing `set` that omits a field drops the stored value (a wholesale replace).
    - `ref` is write-once: an existing (forced) shard keeps its first authored spelling.

    `tags`/`description` are None when the caller did not supply that field."""
    if prior is not None and not force:
        raise AudioCatalogError(
            f"{ref} is already classified — pass --force to replace it. "
            f"Stored: {prior.to_json()}")
    return AudioShard(kind=kind, ref=prior.ref if prior else ref,
                      tags=norm_tags(tags or []), description=description or "")


# --------------------------------------------------------------------------- unset

def unset(prior: AudioShard, *, remove_tags, clear_tags: bool,
          clear_description: bool) -> AudioShard:
    """Compute the shard after a `classify unset` field clear — pure, no IO (`--all`, which deletes
    the whole shard, is the caller's file op). `remove_tags` drops exactly those tags (a tag not
    present is a harmless no-op); `clear_tags` empties the list; `clear_description` empties it."""
    tags = prior.tags
    if clear_tags:
        tags = []
    elif remove_tags:
        drop = set(norm_tags(remove_tags))
        tags = [t for t in prior.tags if t not in drop]
    desc = "" if clear_description else prior.description
    return AudioShard(kind=prior.kind, ref=prior.ref, tags=tags, description=desc)


# --------------------------------------------------------------------------- queries

def load_all_shards(catalog_dir, kind: str) -> tuple[list[AudioShard], list[str]]:
    """Every stored shard of `kind`, globbed LIVE from the shard tree. Returns `(shards,
    unreadable_paths)`; an unreadable/malformed shard is skipped and its path collected so the
    caller can note it on stderr, never a traceback."""
    root = _shard_root(catalog_dir, kind)
    shards: list[AudioShard] = []
    bad: list[str] = []
    for jf in sorted(root.rglob("*.json")) if root.is_dir() else []:
        try:
            shards.append(shard_from_json(json.loads(jf.read_text())))
        except (ValueError, KeyError, OSError):
            bad.append(str(jf))
    return shards, bad


def classified_refs(catalog_dir, kind: str) -> set[str]:
    """The casefolded identity of every object of `kind` with a shard on disk — rebuilt from the
    shard's path (segments joined with dots), the set `list --classified/--unclassified` and
    `status` test membership against."""
    root = _shard_root(catalog_dir, kind)
    out: set[str] = set()
    for jf in root.rglob("*.json") if root.is_dir() else []:
        rel = jf.relative_to(root).with_suffix("")            # already casefolded on disk
        out.add(".".join(rel.parts))
    return out


def is_classified(catalog_dir, kind: str, ref: str) -> bool:
    return shard_path(catalog_dir, kind, ref).exists()


def tag_vocabulary(shards: list[AudioShard]) -> list[tuple[str, int]]:
    """The tag vocabulary across `shards`, `(tag, count)` sorted by count descending then tag."""
    counts: dict[str, int] = {}
    for s in shards:
        for t in s.tags:
            counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items(), key=lambda tc: (-tc[1], tc[0]))


# --------------------------------------------------------------------------- search (ranked discovery)

def score(ref: str, tags: list[str], description: str, terms: list[str]) -> int | None:
    """Relevance of one audio corpus entry against ALREADY-LOWERCASED `terms`, for `sound/music
    search`. AND across terms: every term must match something, else the entry drops (None). Each
    matched term scores its BEST tier — highest first:

      5  the term equals the leaf object name  (exact `Name`)
      4  the term equals a stored tag          (exact tag)
      3  the term is a substring of the dotted ref
      2  the term is a substring of a stored tag
      1  the term is a substring of the description

    The leaf is taken with `rsplit(".", 1)[-1]`, so a 3-part `Package.Group.Name` still ranks its
    exact NAME at tier 5 (the class arm's `split(".", 1)` copy would yield `Group.Name` and miss it).
    """
    ref_l = ref.lower()
    leaf_l = ref.rsplit(".", 1)[-1].lower()
    tags_l = [t.lower() for t in tags]
    desc_l = description.lower()
    total = 0
    for term in terms:
        if term == leaf_l:
            total += 5
        elif term in tags_l:
            total += 4
        elif term in ref_l:
            total += 3
        elif any(term in t for t in tags_l):
            total += 2
        elif term in desc_l:
            total += 1
        else:
            return None
    return total
