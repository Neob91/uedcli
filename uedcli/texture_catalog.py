"""Offline texture classification store — the asset-catalog TEXTURE arm (slice T2).

One git-tracked shard per texture IDENTITY, mirroring `class_catalog`'s shard / lock /
atomic-write shape but keyed by CONTENT identity, not ref. The payload is EXACTLY
`{kind, identity, ref, tags, description, colors}`:

- `identity` — the Layer-1 key and the shard's path key: a 64-hex `sha256(w,h,RGB)` for a
  texture with pixels, or the casefolded `Package.Name` for a procedural (name where content
  does not exist). A `.` in the identity discriminates the two (a hex hash carries none).
- `ref` — the WRITE-ONCE authored `Package[.Group].Name` that first produced this identity,
  kept for outdated-tracking; a later differently-named ref with the same pixels does not
  overwrite it (and `set` refuses over it).
- `tags` / `description` — the LLM's classification.
- `colors` — the ordered palette colour names (a pre-fill the LLM may override); `[]` ⇒ derive
  live at search time.

`set` over an EXISTING shard REFUSES (`--force` REPLACES — it does not union tags, and it
wipes an omitted description; owner ruled 2026-08-02, `direction/asset-catalog.md`). This
diverges from `class_catalog.merge_set`, which union-merges — deliberate, texture-scoped.

Shares NO code with `class_catalog` (that module's own rule): a private copy of the tag
normalizer, not an import.

Concurrency: each shard is its own file, written temp + `os.replace` under a per-shard flock,
so agents classifying disjoint textures never touch one file — the per-actor `.t3d` ethos.
"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

KIND = "texture"


class TextureCatalogError(ValueError):
    """A texture-classification request the store refuses: a `set` over an already-classified
    identity without `--force`. Carries a message naming the offending value; the CLI turns it
    into a clean exit 2, never a traceback."""


# --------------------------------------------------------------------------- tags

def _norm_tags(tags: list[str]) -> list[str]:
    """Strip, lowercase, de-dupe (order-preserving), drop empties — the texture engine's OWN
    normalizer. Behaviour matched to `class_catalog._norm_tags` but deliberately not imported
    (the two stores share no code)."""
    seen: dict[str, None] = {}
    for t in tags:
        seen.setdefault(t.strip().lower(), None)
    return [t for t in seen if t]


# --------------------------------------------------------------------------- identity / paths

def is_name_identity(identity: str) -> bool:
    """True for a name identity (`Package.Name`, procedural), False for a content hash. A 64-hex
    hash never carries a `.`, so the dot is a reliable discriminator."""
    return "." in identity


def _shard_root(catalog_dir) -> Path:
    return Path(catalog_dir) / "classified" / "texture"


def shard_path(catalog_dir, identity: str) -> Path:
    """The shard file for `identity`. A content hash fans out under its first two hex
    (`<hh>/<hash>.json`) so one dir never holds thousands; a name identity lives under
    `name/<package>/<name>.json`, every segment casefolded."""
    root = _shard_root(catalog_dir)
    if is_name_identity(identity):
        package, name = identity.split(".", 1)
        return root / "name" / package.casefold() / f"{name.casefold()}.json"
    return root / identity[:2] / f"{identity}.json"


# --------------------------------------------------------------------------- the shard

@dataclass(frozen=True, kw_only=True)
class TextureShard:
    identity: str                  # the Layer-1 key == the shard's path key
    ref: str                       # write-once authored Package[.Group].Name
    tags: list[str]
    description: str
    colors: list[str]

    def to_json(self) -> dict:
        return {"kind": KIND, "identity": self.identity, "ref": self.ref,
                "tags": self.tags, "description": self.description, "colors": self.colors}


def shard_from_json(d: dict) -> TextureShard:
    return TextureShard(identity=d["identity"], ref=d["ref"], tags=list(d.get("tags", [])),
                        description=d.get("description", ""), colors=list(d.get("colors", [])))


def load_shard(path) -> TextureShard | None:
    p = Path(path)
    if not p.exists():
        return None
    return shard_from_json(json.loads(p.read_text()))


def save_shard(path, shard: TextureShard) -> None:
    """Atomic: write a temp in the SAME dir + `os.replace`, so a crash never truncates a tracked
    shard and loses classification."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(shard.to_json(), indent=2, sort_keys=True) + "\n")
    os.replace(tmp, p)


# --------------------------------------------------------------------------- locks

@contextmanager
def shard_lock(lock_dir, identity: str):
    """Per-shard flock in `lock_dir`: disjoint identities lock disjoint files, so concurrent
    agents classifying different textures never serialize. The lock name is the sanitized
    (casefolded, dot→dash) identity."""
    Path(lock_dir).mkdir(parents=True, exist_ok=True)
    lock = Path(lock_dir) / f"texture-{identity.casefold().replace('.', '-')}.lock"
    with open(lock, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


# --------------------------------------------------------------------------- set / unset

def merge_set(prior: TextureShard | None, *, identity: str, ref: str, tags, description,
              colors, force: bool) -> TextureShard:
    """Compute the new shard for a `classify set` — pure, no IO. `prior` is the loaded shard or
    None. Rules (`direction/asset-catalog.md` "Identity", owner 2026-08-02):

    - an EXISTING shard REFUSES unless `force` — `set` does not accrete onto a texture
      classification; `--force` REPLACES it wholesale (no tag union, an omitted description is
      wiped to "");
    - `ref` is WRITE-ONCE: a replaced shard keeps the ref that first produced this identity.

    `tags`/`description`/`colors` are the fully-resolved fields (colours already pre-filled by the
    caller when the row omitted them); None ⇒ the field's empty value."""
    if prior is not None and not force:
        raise TextureCatalogError(
            f"{ref}: identity {identity} is already classified (as ref {prior.ref!r}) — pass "
            f"--force to replace it")
    kept_ref = prior.ref if prior is not None else ref
    return TextureShard(identity=identity, ref=kept_ref, tags=_norm_tags(tags or []),
                        description=description or "", colors=list(colors or []))


def unset(prior: TextureShard, *, remove_tags, clear_tags: bool, clear_description: bool,
          clear_colors: bool) -> TextureShard:
    """Compute the shard after a `classify unset` field clear — pure, no IO (`--all`, which
    deletes the whole shard, is the caller's file op). `--colors` clears the colour override, so
    search falls back to live-derive."""
    tags = prior.tags
    if clear_tags:
        tags = []
    elif remove_tags:
        drop = set(_norm_tags(remove_tags))
        tags = [t for t in prior.tags if t not in drop]
    return TextureShard(identity=prior.identity, ref=prior.ref, tags=tags,
                        description="" if clear_description else prior.description,
                        colors=[] if clear_colors else prior.colors)


# --------------------------------------------------------------------------- queries

def _iter_shard_files(catalog_dir) -> list[Path]:
    root = _shard_root(catalog_dir)
    if not root.is_dir():
        return []
    hashed = [p for p in root.glob("*/*.json") if p.parent.name != "name"]
    named = list(root.glob("name/*/*.json"))
    return sorted(hashed + named)


def _identity_of_path(p: Path) -> str:
    """The identity a shard file encodes, reconstructed from its PATH (no read): a name shard
    (grandparent dir `name`) → `<package>.<name>`; a hash shard → the filename stem."""
    if p.parent.parent.name == "name":
        return f"{p.parent.name}.{p.stem}"
    return p.stem


def load_all_shards(catalog_dir) -> tuple[list[TextureShard], list[str]]:
    """Every stored texture shard, globbed LIVE from the shard tree (no roll-up index to stale).
    Returns `(shards, unreadable_paths)`; an unreadable/malformed shard is skipped and its path
    collected so the caller can note it on stderr, never a traceback."""
    shards: list[TextureShard] = []
    bad: list[str] = []
    for jf in _iter_shard_files(catalog_dir):
        try:
            shards.append(shard_from_json(json.loads(jf.read_text())))
        except (ValueError, OSError):
            bad.append(str(jf))
    return shards, bad


def classified_identities(catalog_dir) -> set[str]:
    """The identity of every texture with a shard on disk — the set `list --classified/
    --unclassified` and `status` test membership against (after decoding a ref to its identity)."""
    return {_identity_of_path(p) for p in _iter_shard_files(catalog_dir)}


def tag_vocabulary(shards: list[TextureShard]) -> list[tuple[str, int]]:
    """The tag vocabulary in use across `shards`, `(tag, count)` sorted by count descending then
    tag — mirrors `class_catalog.tag_vocabulary`, to curb drift."""
    counts: dict[str, int] = {}
    for s in shards:
        for t in s.tags:
            counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items(), key=lambda tc: (-tc[1], tc[0]))


# --------------------------------------------------------------------------- search (ranked discovery)

def score(ref: str, tags: list[str], description: str, terms: list[str]) -> int | None:
    """Relevance of one texture corpus entry against ALREADY-LOWERCASED `terms`, for
    `texture search`. AND across terms; each matched term contributes its BEST tier:

      5  the term equals the leaf texture Name  (exact)
      4  the term equals a stored tag
      3  the term is a substring of the `Package[.Group].Name` ref
      2  the term is a substring of a stored tag
      1  the term is a substring of the description

    The leaf is `rsplit(".", 1)[-1]` — the Name even for a 3-part `Package.Group.Name` ref (the
    fix over `class_catalog.score`'s `split(".", 1)[-1]`, which would yield `Group.Name`). Summed
    per-term best tiers; the caller sorts by score DESCENDING then ref ascending."""
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
