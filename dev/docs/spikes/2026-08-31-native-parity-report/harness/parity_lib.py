"""Pure logic for the native-materialize parity report: content hashing, the on-disk cache layout,
geometry/lighting comparison, the FULL PARITY verdict, and text/JSON report formatting.

No editor, no docker, no `uedcli`/`uedcli_native` import — everything here is offline and unit
testable (see `test_parity_lib.py`). The editor-driving glue (extraction + golden build) lives in
`parity_pipeline.py`; the CLI wiring lives in `parity_report.py`.
"""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import asdict, dataclass, fields
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


def _bit_exact_eq(a, b) -> bool:
    """Bit-exact equality, correct for float32 fields (`plane`) where bare `!=` is wrong two ways:
    `-0.0 != 0.0` is `False` in Python, so a genuine on-disk byte divergence (plausible from BSP
    plane-equation math -- cross products, subtractions) would be silently missed; and two
    bit-identical NaN payloads compare `!=` `True`, a false positive. Packing to the on-disk f32
    bytes and comparing those sidesteps both. Recurses into tuples (`plane`/`i_zone`/`i_leaf`/
    `pan`); plain int/enum fields compare with `==`, already exact."""
    if isinstance(a, float) and isinstance(b, float):
        return struct.pack("<f", a) == struct.pack("<f", b)
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(_bit_exact_eq(x, y) for x, y in zip(a, b))
    return a == b


@dataclass(frozen=True, kw_only=True)
class FieldDiff:
    """One `native[index].field` disagreement with `golden[index].field`, per `_bit_exact_eq`:
    BIT-exact, no epsilon, no "close enough"."""
    index: int
    field: str
    native: object
    golden: object


@dataclass(frozen=True, kw_only=True)
class ArrayContentResult:
    """Index-for-index field comparison of one native/golden array (nodes or surfs) -- POSITIONAL:
    `native[i]` is compared against `golden[i]` for every `i`, never matched up structurally. The
    goal is byte-identical `.dx` output, which is order-sensitive: a native build that produces an
    "equivalent" tree in a different order still serializes to different bytes, so reordering must
    show up as a diff, not be tolerated away."""
    array_name: str
    native_len: int
    golden_len: int
    diffs: tuple[FieldDiff, ...] = ()

    @property
    def compared(self) -> int:
        """How many indices were actually compared -- the common prefix length."""
        return min(self.native_len, self.golden_len)

    @property
    def diverging_indices(self) -> tuple[int, ...]:
        return tuple(dict.fromkeys(d.index for d in self.diffs))

    @property
    def indices_differ(self) -> int:
        return len(self.diverging_indices)

    @property
    def fields_differ(self) -> int:
        return len(self.diffs)

    @property
    def exact(self) -> bool:
        """Byte-identical content: equal length AND zero field diffs across the compared range. A
        length mismatch fails this even with a diff-free common prefix -- two different-length
        arrays can never serialize to the same bytes."""
        return self.native_len == self.golden_len and not self.diffs


def compare_array_content(native, golden, *, array_name: str) -> ArrayContentResult:
    """Index-for-index field diff of two same-shape dataclass sequences (`umodel.BspNode` or
    `BspSurf` instances, or any object exposing `dataclasses.fields`). Generic over whatever fields
    the dataclass declares, so a future field added to `BspNode`/`BspSurf` is covered automatically
    -- never a hand-maintained field list that can silently drift out of sync with the real struct."""
    diffs = []
    for i in range(min(len(native), len(golden))):
        n, g = native[i], golden[i]
        for f in fields(n):
            nv, gv = getattr(n, f.name), getattr(g, f.name)
            if not _bit_exact_eq(nv, gv):
                diffs.append(FieldDiff(index=i, field=f.name, native=nv, golden=gv))
    return ArrayContentResult(array_name=array_name, native_len=len(native), golden_len=len(golden),
                              diffs=tuple(diffs))


@dataclass(frozen=True, kw_only=True)
class ContentComparison:
    """Index-for-index content comparison of the three arrays that define the BSP tree's real
    topology and per-face data: nodes, surfs, and leaves -- the same "tree structure" triple this
    investigation's own reporting format is built on (`native-materialize-findings.md`). Exists
    because `GeometryDelta`'s count-only compare cannot tell "genuinely identical tree" from "same
    counts, different tree" -- two trees can agree on `len(nodes)`/`len(surfs)`/`len(leaves)` while
    heavily disagreeing per-index (the `freeclinic08`/`nsfhq04` finding: "37/141 brushes differ,
    summing to 102 absolute delta against a net -38" -- heavy disagreement that cancels out in the
    aggregate count)."""
    nodes: ArrayContentResult
    surfs: ArrayContentResult
    leaves: ArrayContentResult

    @property
    def exact(self) -> bool:
        return self.nodes.exact and self.surfs.exact and self.leaves.exact


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


def full_parity(geometry: GeometryDelta, content: ContentComparison, lighting: LightingSummary) -> bool:
    """FULL PARITY: YES iff geometry is byte-identical on every one of the six counts (not just
    node/surf/leaf), the node/surf CONTENT is index-for-index byte-identical (not just counts --
    see `ContentComparison`'s docstring for why counts alone are not enough), and every LightMap
    record is byte-identical. See `GeometryDelta.exact`'s docstring for why the count half is
    already stricter than the existing breadth-gate "EXACT" label."""
    return geometry.exact and content.exact and lighting.records_fully_identical


@dataclass(frozen=True, kw_only=True)
class ParityReport:
    source_dx: str
    content_hash: str
    level_name: str
    cache_hit: bool
    built_at: str | None
    geometry: GeometryDelta
    content: ContentComparison
    lighting: LightingSummary
    warnings: tuple[str, ...] = ()

    @property
    def full_parity(self) -> bool:
        return full_parity(self.geometry, self.content, self.lighting)


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


def _content_array_lines(r: ArrayContentResult, *, max_diffs_shown: int = 30) -> list[str]:
    if r.native_len != r.golden_len:
        head = (f"  {r.array_name:8} LENGTH MISMATCH native={r.native_len:<8} golden={r.golden_len:<8}"
                f" ({r.compared} common index(es) compared)")
        if not r.diffs:
            # A clean common prefix does NOT mean identical -- the length itself differs, so this
            # array can never serialize byte-identical. Say so explicitly rather than claiming
            # "content identical", which `ArrayContentResult.exact` (correctly) also refuses here.
            return [head + " -- common prefix agrees, but length differs (NOT exact)"]
    else:
        head = f"  {r.array_name:8} native={r.native_len:<8} golden={r.golden_len:<8}"
        if not r.diffs:
            return [head + "  content identical"]
    lines = [head, f"    {r.indices_differ} index(es) differ across {r.fields_differ} field(s):"]
    for d in r.diffs[:max_diffs_shown]:
        lines.append(f"      [{d.index}] {d.field}: native={d.native!r} golden={d.golden!r}")
    if r.fields_differ > max_diffs_shown:
        lines.append(f"      ... and {r.fields_differ - max_diffs_shown} more field diff(s)")
    return lines


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
        "Content (index-for-index nodes/surfs/leaves vs golden -- catches divergence counts alone "
        "miss):",
        *_content_array_lines(report.content.nodes),
        *_content_array_lines(report.content.surfs),
        *_content_array_lines(report.content.leaves),
        f"  -> content {'EXACT' if report.content.exact else 'NOT EXACT'} "
        f"(every node/surf/leaf field must match at every index for FULL PARITY)",
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
    for name, r in (("nodes", report.content.nodes), ("surfs", report.content.surfs),
                    ("leaves", report.content.leaves)):
        d["content"][name]["indices_differ"] = r.indices_differ
        d["content"][name]["fields_differ"] = r.fields_differ
        d["content"][name]["exact"] = r.exact
    d["content"]["exact"] = report.content.exact
    d["lighting"]["identical_pct"] = report.lighting.identical_pct
    d["lighting"]["shadow_bit_pct"] = report.lighting.shadow_bit_pct
    return json.dumps(d, indent=2, sort_keys=True)
