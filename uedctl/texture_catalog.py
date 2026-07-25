"""The offline texture catalog: discover/export textures and maintain a tracked, hash-versioned
per-package manifest that LLM/human classification accretes onto. Pure + offline-testable — no
docker/editor calls live here (the container seam is `texture.batchexport_textures`). See
dev/docs/specs/2026-06-22-uedctl-texture-tool-design.md."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image

# A fixed, closed color vocabulary (the one place a fixed taxonomy fits — colors ARE a closed set,
# unlike the open `tags`). Reference RGBs chosen as canonical centroids; ORDER is load-bearing —
# it is the tie-break for equal-share colors and for an equidistant per-pixel snap.
PALETTE: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("black", (0, 0, 0)),
    ("white", (255, 255, 255)),
    ("grey", (128, 128, 128)),
    ("red", (200, 30, 30)),
    ("orange", (220, 120, 30)),
    ("yellow", (225, 215, 60)),
    ("green", (40, 150, 60)),
    ("blue", (40, 80, 190)),
    ("purple", (120, 50, 160)),
    ("pink", (230, 130, 170)),
    ("brown", (110, 70, 40)),
    ("tan", (200, 175, 130)),
)
PALETTE_NAMES: tuple[str, ...] = tuple(name for name, _ in PALETTE)

COLOR_MIN_SHARE = 0.12
COLOR_CAP = 3
THUMB = 64


@dataclass(frozen=True, kw_only=True)
class ExportedTexture:        # one freshly-exported PCX, decoded
    stem: str; name: str; group: str | None
    width: int; height: int; image_hash: str; colors: list[str]


@dataclass(frozen=True, kw_only=True)
class TextureEntry:
    name: str; group: str | None; ref: str
    width: int; height: int; image_hash: str
    colors: list[str]; colors_source: str         # "auto" | "set"
    tags: list[str]; description: str
    stale: bool; removed: bool


@dataclass(frozen=True, kw_only=True)
class Manifest:
    package: str; package_file: str; package_hash: str
    textures: dict[str, TextureEntry]             # keyed by PCX stem


def parse_pcx_stem(stem: str) -> tuple[str | None, str]:
    """Split a batchexport PCX stem into (group, name). UCC writes group-prefixed filenames
    (`Skins.Wood.pcx` → stem `Skins.Wood`); a groupless texture exports as bare `Wood`. The NAME
    is the last dotted component (a texture Name carries no dot); the group is the rest, or None."""
    group, dot, name = stem.rpartition(".")
    return (group, name) if dot else (None, stem)


def nearest_color(rgb: tuple[int, int, int]) -> str:
    """Nearest palette name by squared RGB distance; an equidistant tie breaks by PALETTE order."""
    best_name, best_d2 = PALETTE[0][0], None
    for name, (pr, pg, pb) in PALETTE:
        d2 = (rgb[0] - pr) ** 2 + (rgb[1] - pg) ** 2 + (rgb[2] - pb) ** 2
        if best_d2 is None or d2 < best_d2:        # strict < => earlier PALETTE entry wins ties
            best_name, best_d2 = name, d2
    return best_name


def derive_colors(img) -> list[str]:
    """The texture's named colors. Compute the histogram on the ACTUAL pixels (so shares are exact);
    only downsample with NEAREST when the image is larger than THUMB in a dimension, purely as a
    sampling cap for big textures (NEAREST is deterministic across Pillow versions — no
    quantize/median-cut). Snap each pixel to the nearest of the 12 names, keep names with
    >= COLOR_MIN_SHARE, up to COLOR_CAP, sorted by descending share then PALETTE order. A coarse
    browse aid, not a precise readout (see spec Concerns)."""
    rgb = img.convert("RGB")
    if rgb.width > THUMB or rgb.height > THUMB:
        rgb = rgb.resize((min(THUMB, rgb.width), min(THUMB, rgb.height)),
                         Image.Resampling.NEAREST)
    pixels = list(rgb.getdata())
    total = len(pixels)
    tally: dict[str, int] = {}
    for px in pixels:
        name = nearest_color(px)
        tally[name] = tally.get(name, 0) + 1
    order = {name: i for i, name in enumerate(PALETTE_NAMES)}
    kept = [(name, n) for name, n in tally.items() if n / total >= COLOR_MIN_SHARE]
    kept.sort(key=lambda kn: (-kn[1], order[kn[0]]))
    names = [name for name, _ in kept[:COLOR_CAP]]
    if not names and tally:                        # high-entropy image: no name clears 12% — keep
        names = [max(tally.items(),                 # the single most-frequent (tie by PALETTE order)
                     key=lambda kn: (kn[1], -order[kn[0]]))[0]]
    return names


def image_hash(img) -> str:
    """sha256 over the RGB-DECODED pixels + dims — NOT the PNG file bytes (encoder-nondeterministic)
    and NOT the paletted `tobytes()` (which is index-only and misses a palette-only recolor)."""
    rgb = img.convert("RGB")
    h = hashlib.sha256()
    h.update(b"%d:%d:" % rgb.size)
    h.update(rgb.tobytes())
    return "sha256:" + h.hexdigest()


def assign_refs(package: str, stems: list[tuple[str, str | None, str]]) -> dict[str, str]:
    """Map each stem to its catalog `ref`. Normally the 2-part `Package.Name` (a 2-part ref binds
    regardless of group, per the surface spec). The genuine ambiguity is intra-package cross-group
    same-`Name`: two stems collapsing to one `Package.Name`. Those get the 3-part
    `Package.Group.Name` (binds too, honoring the group) so `brush poly set` never gets an ambiguous ref."""
    counts: dict[str, int] = {}
    for _stem, _group, name in stems:
        counts[name.lower()] = counts.get(name.lower(), 0) + 1
    refs: dict[str, str] = {}
    for stem, group, name in stems:
        if counts[name.lower()] > 1 and group is not None:
            refs[stem] = f"{package}.{group}.{name}"
        else:
            refs[stem] = f"{package}.{name}"
    return refs


def to_json(m: Manifest) -> dict:
    return {"package": m.package, "package_file": m.package_file, "package_hash": m.package_hash,
            "textures": {stem: {"name": e.name, "group": e.group, "ref": e.ref,
                                "width": e.width, "height": e.height, "image_hash": e.image_hash,
                                "colors": e.colors, "colors_source": e.colors_source,
                                "tags": e.tags, "description": e.description,
                                "stale": e.stale, "removed": e.removed}
                         for stem, e in m.textures.items()}}


def from_json(d: dict) -> Manifest:
    return Manifest(
        package=d["package"], package_file=d["package_file"], package_hash=d["package_hash"],
        textures={stem: TextureEntry(**t) for stem, t in d["textures"].items()})


def manifest_path(catalog_dir, package: str) -> Path:
    return Path(catalog_dir) / f"{package}.json"


def load_manifest(path) -> Manifest | None:
    p = Path(path)
    if not p.exists():
        return None
    return from_json(json.loads(p.read_text()))


def save_manifest(path, m: Manifest) -> None:
    """Atomic: write a temp in the SAME dir + os.replace, so a crash never truncates a tracked
    manifest and loses classification."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(to_json(m), indent=2, sort_keys=True) + "\n")
    os.replace(tmp, p)


def reconcile(prior: Manifest | None, *, package: str, package_file: str,
              package_hash: str, exported: list[ExportedTexture]) -> Manifest:
    """A single deterministic pass. Phase A resolves same-stem cases (consuming their prior entry).
    Phase B matches the remaining new stems (sorted) against still-unclaimed removed/absent priors
    by image_hash (rename carry-over, inherit-once). Finally, unconsumed prior stems become removed."""
    prior_textures = dict(prior.textures) if prior else {}
    refs = assign_refs(package, [(e.stem, e.group, e.name) for e in exported])
    by_stem = {e.stem: e for e in exported}
    out: dict[str, TextureEntry] = {}
    consumed: set[str] = set()

    # Phase A: stems present in BOTH package and manifest.
    for stem, e in by_stem.items():
        prev = prior_textures.get(stem)
        if prev is None:
            continue
        consumed.add(stem)
        changed = prev.image_hash != e.image_hash
        if prev.colors_source == "set":
            colors, source = prev.colors, "set"            # human override — never re-derive
        elif changed:
            colors, source = e.colors, "auto"              # re-derive auto colors only on a change
        else:
            colors, source = prev.colors, "auto"           # unchanged pixels -> truly untouched
        out[stem] = replace(prev, ref=refs[stem], width=e.width, height=e.height,
                            image_hash=e.image_hash, colors=colors, colors_source=source,
                            removed=False, stale=(changed or (prev.stale and not prev.removed)))
        # resurrection of an unchanged removed entry keeps a clean (not stale) classification
        if prev.removed and not changed:
            out[stem] = replace(out[stem], stale=False)

    # Phase B: new stems (no same-stem prior), sorted; match unclaimed removed/absent priors.
    claimable = {s: p for s, p in prior_textures.items() if s not in consumed}
    for stem in sorted(s for s in by_stem if s not in out):
        e = by_stem[stem]
        match = next((s for s in sorted(claimable)
                      if claimable[s].image_hash == e.image_hash), None)
        if match is not None:                                  # a rename — inherit once
            src = claimable.pop(match)
            colors, source = ((e.colors, "auto") if src.colors_source == "auto"
                              else (src.colors, "set"))
            out[stem] = TextureEntry(
                name=e.name, group=e.group, ref=refs[stem], width=e.width, height=e.height,
                image_hash=e.image_hash, colors=colors, colors_source=source,
                tags=src.tags, description=src.description, stale=True, removed=False)
        else:                                                  # genuinely new
            out[stem] = TextureEntry(
                name=e.name, group=e.group, ref=refs[stem], width=e.width, height=e.height,
                image_hash=e.image_hash, colors=e.colors, colors_source="auto",
                tags=[], description="", stale=False, removed=False)

    # Finally: prior stems neither updated (A) nor claimed as a rename source (B) are gone.
    for stem, prev in claimable.items():
        out[stem] = replace(prev, removed=True, stale=False)

    return Manifest(package=package, package_file=package_file, package_hash=package_hash,
                    textures=out)


def bucket(e: TextureEntry) -> str:
    """Exactly one bucket per entry, by precedence removed > stale > classified > unclassified."""
    if e.removed:
        return "removed"
    if e.stale:
        return "stale"
    if e.tags or e.description:
        return "classified"
    return "unclassified"


def validate_colors(names: list[str]) -> None:
    bad = [n for n in names if n not in PALETTE_NAMES]
    if bad:
        raise ValueError(f"unknown color(s): {', '.join(bad)} — valid: {', '.join(PALETTE_NAMES)}")


def _norm_tags(tags: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for t in tags:
        seen.setdefault(t.strip().lower(), None)
    return [t for t in seen if t]


def classify_set(m: Manifest, ref: str, *, tags, description, colors) -> Manifest:
    """Replace the provided fields on the entry addressed by `ref`; set colors_source="set" and
    clear `stale`. Raises ValueError (clean CLI error) on unknown ref, removed texture, or a bad
    color name. At least one field must be provided."""
    if tags is None and description is None and colors is None:
        raise ValueError("classify set needs at least one of --tags/--description/--colors")
    stem = next((s for s, e in m.textures.items() if e.ref == ref), None)
    if stem is None:
        raise ValueError(f"texture not found: {ref}")
    e = m.textures[stem]
    if e.removed:
        raise ValueError(f"texture removed from package: {ref} — re-run 'texture sync' if it returned")
    if colors is not None:
        validate_colors(colors)
    updated = replace(
        e,
        tags=_norm_tags(tags) if tags is not None else e.tags,
        description=description if description is not None else e.description,
        colors=list(colors) if colors is not None else e.colors,
        colors_source="set" if colors is not None else e.colors_source,
        stale=False)
    return replace(m, textures={**m.textures, stem: updated})


def status_counts(manifests: list[Manifest]) -> dict:
    keys = ("total", "classified", "unclassified", "stale", "removed")
    def empty():
        return {k: 0 for k in keys}
    per: dict[str, dict] = {}
    grand = empty()
    for m in manifests:
        c = empty()
        for e in m.textures.values():
            c["total"] += 1
            c[bucket(e)] += 1
        per[m.package] = c
        for k in keys:
            grand[k] += c[k]
    return {"per_package": per, "total": grand}


def _entries(manifests, package):
    for m in manifests:
        if package and m.package.lower() != package.lower():
            continue
        for e in m.textures.values():
            if not e.removed:
                yield e


def _score(e: TextureEntry, terms: list[str]) -> int | None:
    """Sum of per-term tier scores (exact name 5 > exact tag 4 > name-substr 3 > tag-substr 2 >
    desc-substr 1); None if any term matches nothing (AND)."""
    name, tags, desc = e.name.lower(), [t.lower() for t in e.tags], e.description.lower()
    total = 0
    for term in terms:
        if term == name:
            total += 5
        elif term in tags:
            total += 4
        elif term in name:
            total += 3
        elif any(term in t for t in tags):
            total += 2
        elif term in desc:
            total += 1
        else:
            return None
    return total


def search(manifests, query, *, tags, colors, package) -> list[str]:
    terms = (query or "").lower().split()
    tag_set = [t.lower() for t in (tags or [])]
    color_set = [c.lower() for c in (colors or [])]
    scored: list[tuple[int, str]] = []
    for e in _entries(manifests, package):
        if tag_set and not all(t in [x.lower() for x in e.tags] for t in tag_set):
            continue
        if color_set and not any(c in e.colors for c in color_set):
            continue
        if terms:
            s = _score(e, terms)
            if s is None:
                continue
        else:
            s = 0
        scored.append((s, e.ref))
    scored.sort(key=lambda sr: (-sr[0], sr[1]))      # score desc, then ref asc
    return [ref for _s, ref in scored]


def all_tags(manifests, *, package) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for e in _entries(manifests, package):
        for t in e.tags:
            counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items(), key=lambda tc_: (-tc_[1], tc_[0]))


def _file_hash(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


@contextmanager
def _package_lock(lock_dir, package):
    Path(lock_dir).mkdir(parents=True, exist_ok=True)
    lock = Path(lock_dir) / f"texture-{package}.lock"
    with open(lock, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def _decode_exported(host_pcxs, images_pkg_dir) -> list[ExportedTexture]:
    Path(images_pkg_dir).mkdir(parents=True, exist_ok=True)
    out: list[ExportedTexture] = []
    for pcx in sorted(host_pcxs):
        stem = Path(pcx).stem
        group, name = parse_pcx_stem(stem)
        img = Image.open(pcx)
        # Temp + os.replace: the images cache is PER-USER and CROSS-project, but the sync flock is
        # per-PROJECT — two projects syncing the same package concurrently must never leave a torn
        # PNG for the other to read (review fix, 2026-07-18).
        target = Path(images_pkg_dir) / f"{stem}.png"
        tmp = target.with_name(target.name + f".tmp{os.getpid()}")
        try:
            img.convert("RGB").save(tmp, format="PNG")
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)     # a failed save must not strand .tmp litter (review fix)
        out.append(ExportedTexture(stem=stem, name=name, group=group,
                                   width=img.width, height=img.height,
                                   image_hash=image_hash(img), colors=derive_colors(img)))
    return out


def sync_package(*, package, package_file, container, catalog_dir, images_root, force,
                 batchexport, lock_dir) -> Manifest | None:
    """Build/refresh one package's manifest. Hash the package FILE; skip (return the loaded
    manifest) if unchanged and not force. Else batchexport → decode host-side → reconcile → atomic
    save, all under a per-package flock in `lock_dir` (REQUIRED — the caller derives it from the
    project state dir, `<root>/.uedctl/locks/`; the old `catalog_dir.parent/.uedctl/locks` fallback
    was deleted with the 2026-07-17 layout reorg). `batchexport(container, package, host_dir) ->
    [pcx]` is injected (the real seam is `texture.batchexport_textures`)."""
    mpath = manifest_path(catalog_dir, package)
    with _package_lock(lock_dir, package):
        prior = load_manifest(mpath)
        new_hash = _file_hash(package_file)
        if prior is not None and prior.package_hash == new_hash and not force:
            return prior
        with tempfile.TemporaryDirectory() as work:
            pcxs = batchexport(container, package, work)      # by BARE NAME (UCC resolves via Paths)
            if not pcxs:
                return prior                                  # no textures/unreachable -> no manifest
            exported = _decode_exported(pcxs, Path(images_root) / package)
        m = reconcile(prior, package=package, package_file=os.path.basename(package_file),
                      package_hash=new_hash, exported=exported)
        save_manifest(mpath, m)
        return m
