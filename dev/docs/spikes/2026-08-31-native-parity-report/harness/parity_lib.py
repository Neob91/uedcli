"""Pure logic for the native-materialize parity report: content hashing, the on-disk cache layout,
geometry/lighting comparison, the FULL PARITY verdict, and text/JSON report formatting.

No editor, no docker, no `uedcli`/`uedcli_native` import — everything here is offline and unit
testable (see `test_parity_lib.py`). The editor-driving glue (extraction + golden build) lives in
`parity_pipeline.py`; the CLI wiring lives in `parity_report.py`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

CACHE_ROOT_DEFAULT = Path("/tmp/uedcli-parity-cache")


def content_hash(path: Path) -> str:
    """sha256 of the file's bytes — the cache key. The input `.dx` never changes (a shipped game
    asset), so this is a stable, content-addressed key across runs and machines."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True, kw_only=True)
class CacheLayout:
    """Paths inside one cache entry, `<cache_root>/<content_hash>/` — the `/tmp`-cached ARTIFACTS
    only (the self-built golden `.dx` + its build metadata/logs), per the caching spec. The extracted
    T3D trunk is a separate, repo-tree-scratch build concern (`parity_pipeline.build_root`), not part
    of this cache — see that function's docstring for why."""
    root: Path

    @property
    def meta(self) -> Path:
        return self.root / "meta.json"

    @property
    def golden(self) -> Path:
        return self.root / "golden.dx"

    @property
    def build_log(self) -> Path:
        return self.root / "build.log"


def cache_layout(cache_root: Path, hash_hex: str) -> CacheLayout:
    return CacheLayout(root=cache_root / hash_hex)


def read_meta(layout: CacheLayout) -> dict | None:
    try:
        return json.loads(layout.meta.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def write_meta(layout: CacheLayout, meta: dict) -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    tmp = layout.meta.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, indent=2, sort_keys=True))
    tmp.replace(layout.meta)


def is_cache_complete(layout: CacheLayout) -> bool:
    """A cache entry is usable only if the golden `.dx` is on disk AND `meta.json` records a
    completed build — a killed mid-build run leaves a golden-less or `status != "complete"` entry,
    never mistaken for a hit."""
    if not layout.golden.exists():
        return False
    meta = read_meta(layout)
    return meta is not None and meta.get("status") == "complete"


@dataclass(frozen=True, kw_only=True)
class GeometryCounts:
    nodes: int
    surfs: int
    leaves: int
    verts: int
    points: int
    vectors: int


@dataclass(frozen=True, kw_only=True)
class GeometryDelta:
    native: GeometryCounts
    golden: GeometryCounts

    @property
    def d_nodes(self) -> int:
        return self.native.nodes - self.golden.nodes

    @property
    def d_surfs(self) -> int:
        return self.native.surfs - self.golden.surfs

    @property
    def d_leaves(self) -> int:
        return self.native.leaves - self.golden.leaves

    @property
    def d_verts(self) -> int:
        return self.native.verts - self.golden.verts

    @property
    def d_points(self) -> int:
        return self.native.points - self.golden.points

    @property
    def d_vectors(self) -> int:
        return self.native.vectors - self.golden.vectors

    @property
    def exact(self) -> bool:
        """STRICT geometry exactness: all six counts byte-identical (nodes/surfs/leaves AND
        verts/points/vectors). Stricter than `breadth_gate.py`'s "EXACT" label, which only requires
        node/surf/leaf and ignores a verts/points/vectors delta — the FULL PARITY verdict here must
        not repeat that looseness (this is why UNATCO, node/surf/leaf-exact but verts/points/vectors
        off, reports geometry NOT exact)."""
        return self.native == self.golden


@dataclass(frozen=True, kw_only=True)
class LightingSummary:
    total_records: int
    identical_records: int
    shadow_bits_same: int
    shadow_bits_total: int

    @property
    def identical_pct(self) -> float:
        return 100.0 * self.identical_records / self.total_records if self.total_records else 0.0

    @property
    def shadow_bit_pct(self) -> float:
        return (100.0 * self.shadow_bits_same / self.shadow_bits_total
                if self.shadow_bits_total else 0.0)

    @property
    def records_fully_identical(self) -> bool:
        """Every `LightMap` record byte-identical. Vacuously true at 0 total records (no lit
        surfaces at all — a degenerate/trivial level); geometry exactness still gates FULL PARITY
        in that case, so a lightless level can't pass on lighting alone by omission."""
        return self.identical_records == self.total_records


def full_parity(geometry: GeometryDelta, lighting: LightingSummary) -> bool:
    """FULL PARITY: YES iff geometry is byte-identical on every one of the six counts (not just
    node/surf/leaf) AND every LightMap record is byte-identical. See `GeometryDelta.exact`'s
    docstring for why this is stricter than the existing breadth-gate "EXACT" label."""
    return geometry.exact and lighting.records_fully_identical


@dataclass(frozen=True, kw_only=True)
class ParityReport:
    source_dx: str
    content_hash: str
    level_name: str
    cache_hit: bool
    built_at: str | None
    geometry: GeometryDelta
    lighting: LightingSummary
    warnings: tuple[str, ...] = ()

    @property
    def full_parity(self) -> bool:
        return full_parity(self.geometry, self.lighting)


def _geometry_lines(g: GeometryDelta) -> list[str]:
    rows = [
        ("nodes", g.native.nodes, g.golden.nodes, g.d_nodes),
        ("surfs", g.native.surfs, g.golden.surfs, g.d_surfs),
        ("leaves", g.native.leaves, g.golden.leaves, g.d_leaves),
        ("verts", g.native.verts, g.golden.verts, g.d_verts),
        ("points", g.native.points, g.golden.points, g.d_points),
        ("vectors", g.native.vectors, g.golden.vectors, g.d_vectors),
    ]
    return [f"  {label:8} native={n:<8} golden={gd:<8} d={d:+d}" for label, n, gd, d in rows]


def format_text(report: ParityReport) -> str:
    cache_state = f"HIT (built {report.built_at})" if report.cache_hit else "MISS (built this run)"
    lines = [
        "Native materialize parity report",
        f"  source:  {report.source_dx}",
        f"  hash:    {report.content_hash}",
        f"  level:   {report.level_name}",
        f"  cache:   {cache_state}",
        "",
        "Geometry (native build vs self-built UED22 golden):",
        *_geometry_lines(report.geometry),
        f"  -> geometry {'EXACT' if report.geometry.exact else 'NOT EXACT'} "
        f"(all 6 counts must be byte-identical for FULL PARITY)",
        "",
        "Lighting (LightMap records, native vs golden):",
        f"  records: {report.lighting.identical_records}/{report.lighting.total_records} "
        f"byte-identical ({report.lighting.identical_pct:.1f}%)",
        f"  shadow bits (grid+run-matched): {report.lighting.shadow_bits_same}/"
        f"{report.lighting.shadow_bits_total} ({report.lighting.shadow_bit_pct:.2f}%)",
        f"  -> lighting {'FULL' if report.lighting.records_fully_identical else 'PARTIAL'} "
        f"(every record must be byte-identical for FULL PARITY)",
        "",
    ]
    for w in report.warnings:
        lines.append(f"WARNING: {w}")
    if report.warnings:
        lines.append("")
    lines.append(f"FULL PARITY: {'YES' if report.full_parity else 'NO'}")
    return "\n".join(lines)


def format_json(report: ParityReport) -> str:
    d = asdict(report)
    d["full_parity"] = report.full_parity
    d["geometry"]["deltas"] = {
        "nodes": report.geometry.d_nodes, "surfs": report.geometry.d_surfs,
        "leaves": report.geometry.d_leaves, "verts": report.geometry.d_verts,
        "points": report.geometry.d_points, "vectors": report.geometry.d_vectors,
    }
    d["lighting"]["identical_pct"] = report.lighting.identical_pct
    d["lighting"]["shadow_bit_pct"] = report.lighting.shadow_bit_pct
    return json.dumps(d, indent=2, sort_keys=True)
