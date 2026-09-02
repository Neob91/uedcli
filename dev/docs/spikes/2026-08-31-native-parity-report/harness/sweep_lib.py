"""Pure logic for the corpus-wide parity sweep: the 18-level corpus list, the per-level result shape,
and JSON (de)serialization. No docker, no subprocess, no multiprocessing -- everything here is
offline and unit testable (`test_sweep_lib.py`). The process-spawning driver lives in
`sweep_corpus.py`; the xlsx adapter lives in `sweep_to_xlsx.py`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CORPUS = (
    "DX.dx",
    "02_NYC_Bar.dx",
    "03_NYC_UNATCOHQ.dx",
    "09_NYC_ShipFan.dx",
    "04_NYC_Underground.dx",
    "06_HongKong_WanChai_Market.dx",
    "10_Paris_Club.dx",
    "06_HongKong_Helibase.dx",
    "06_HongKong_WanChai_Garage.dx",
    "11_Paris_Underground.dx",
    "10_Paris_Chateau.dx",
    "15_Area51_Entrance.dx",
    "00_TrainingFinal.dx",
    "08_NYC_FreeClinic.dx",
    "03_NYC_747.dx",
    "12_Vandenberg_Gas.dx",
    "14_OceanLab_Lab.dx",
    "04_NYC_NSFHQ.dx",
)
"""The 18-level OG Deus Ex breadth corpus, filenames under the substrate's `Maps/` dir. Cross-checked
2026-09-02 against every `source_dx` recorded in the live `/tmp/uedcli-parity-cache/*/meta.json`
entries (the ground truth of what has actually been measured this session) and against the breadth
table in `native-materialize-findings.md` ("Breadth table refreshed (2026-09-01)") -- both agree on
this exact set of 18."""

SKIPPED = {
    "99_Endgame4.dx": "offline UCC batchexport can't resolve Engine.CameraPoint (extraction-mechanism "
                       "gap, not a contradiction of the live-editor-ingest geometry-exact finding)",
    "DXMP_Smuggler.dx": "crashes at EDIT PASTE right after MAP NEW (same signature as the Wanchai "
                         "self-build crash, wanchai-self-build-edit-paste-crash)",
    "04_NYC_Street.dx": "crashes at EDIT PASTE right after MAP NEW (same signature)",
}
"""Known-unbuildable levels, reported as SKIPPED rather than silently omitted. Reason strings per
`native-materialize-findings.md`, "Breadth golden-caching pass across the 21-level corpus"."""

MAPS_SUBDIR = "dev/games/deusex/Maps"


def repo_root(start: Path) -> Path:
    """Walk up from `start` to the main checkout root -- the nearest ancestor with a REAL `.git`
    directory (not a worktree's `.git` gitlink FILE, which points at
    `<main>/.git/worktrees/<name>` and is therefore skipped). Works identically whether `start` sits
    in the main checkout or in any git-worktree checkout of it."""
    for parent in (start, *start.parents):
        if (parent / ".git").is_dir():
            return parent
    raise RuntimeError(f"no main checkout root (a real .git dir) found above {start}")


def shared_trunk_cache_root(start: Path) -> Path:
    """A trunk-extraction cache root shared by every worktree on this box, unlike
    `parity_pipeline.build_root()`'s own per-worktree `_scratch/` (its docstring explains why that one
    must live under the repo tree rather than `/tmp` -- a bind-mount constraint that applies here too,
    so this also stays under the repo tree, just at a FIXED location outside any single disposable
    worktree). Anchored under `<main checkout>/.claude/worktrees/`, the exact directory
    `tool_assets.umodel_dir()` already shares incidentally across worktrees
    (`board/inbox/docker-mount-source-permission-fails-from-main`) -- gitignored
    (`.claude/worktrees/` in `.gitignore`), so it never gets committed, and survives any one
    worktree's own creation/removal since it is a SIBLING of the worktree directories, not inside any
    of them."""
    return repo_root(start) / ".claude" / "worktrees" / "uedcli-parity-trunk-cache"


def maps_dir(start: Path) -> Path:
    return repo_root(start) / MAPS_SUBDIR


@dataclass(frozen=True, kw_only=True)
class LevelResult:
    """One level's row in the sweep -- the sweep's own JSON output format (a list of these), fully
    decoupled from both `parity_lib.ParityReport` (the underlying report shape) and the xlsx column
    layout (`sweep_to_xlsx.py` maps this to columns, not the other way around)."""
    level: str
    dx_path: str
    status: str  # OK | SKIPPED | TIMED_OUT | PIPELINE_ERROR | ERROR
    elapsed_s: float | None = None
    golden_cache_hit: bool | None = None
    nodes_match: bool | None = None
    surfs_match: bool | None = None
    leaves_match: bool | None = None
    verts_match: bool | None = None
    points_match: bool | None = None
    vectors_match: bool | None = None
    geometry_match_count: int | None = None
    content_exact_fraction: float | None = None
    content_length_mismatch: bool | None = None
    lighting_byte_identical_pct: float | None = None
    lighting_shadow_bit_pct: float | None = None
    full_parity: bool | None = None
    notes: str = ""


def content_exact_fraction(content: dict) -> float:
    """A single 0..1 scalar summarizing index-for-index STRUCTURAL content agreement across the
    nodes/surfs/leaves arrays (`parity_lib.ContentComparison`, via its JSON form from
    `parity_lib.format_json`) -- weighted by how many indices were actually compared (the common
    prefix length per array), so a huge exact array doesn't get diluted by a tiny divergent one or
    vice versa. Deliberately distinct from `geometry_match_count` (which only checks the six ARRAY
    LENGTHS/counts): this is the field the owner asked to have surfaced explicitly, because a level
    can match every count while its actual node/surf/leaf DATA differs at every index -- exactly the
    case `ContentComparison`'s own docstring names (`freeclinic08`/`nsfhq04`, "37/141 brushes differ,
    summing to 102 absolute delta against a net -38"). Vacuous 1.0 when nothing was compared (e.g. a
    degenerate empty level) -- geometry/length checks gate FULL PARITY in that case regardless."""
    # `parity_lib.format_json` does not carry `ArrayContentResult.compared` (a `@property`, not a
    # dataclass field -- `asdict()` only serializes fields), so it's re-derived here from the two
    # lengths it DOES carry: `compared` is the common-prefix length, `min(native_len, golden_len)`.
    total_compared = sum(min(content[name]["native_len"], content[name]["golden_len"])
                         for name in ("nodes", "surfs", "leaves"))
    if total_compared == 0:
        return 1.0
    total_diverging = sum(content[name]["indices_differ"] for name in ("nodes", "surfs", "leaves"))
    return 1.0 - total_diverging / total_compared


def content_length_mismatch(content: dict) -> bool:
    """True if ANY of nodes/surfs/leaves has a native/golden length mismatch -- a level can never
    serialize byte-identical in that case even if the common-prefix content is diff-free, so this must
    stay visible alongside `content_exact_fraction` rather than being folded into (and hidden by) it."""
    return any(content[name]["native_len"] != content[name]["golden_len"]
               for name in ("nodes", "surfs", "leaves"))


def level_result_from_report_json(*, level: str, dx_path: str, elapsed_s: float,
                                   report: dict) -> LevelResult:
    """Build a `LevelResult` from `parity_report.py --json`'s parsed output (`parity_lib.format_json`
    -- see that module for the exact shape: `geometry.deltas.{nodes,surfs,leaves,verts,points,
    vectors}`, `content.{nodes,surfs,leaves}.{compared,indices_differ,exact,native_len,golden_len}`,
    `lighting.{identical_pct,shadow_bit_pct}`, `full_parity`)."""
    deltas = report["geometry"]["deltas"]
    matches = {k: deltas[k] == 0 for k in ("nodes", "surfs", "leaves", "verts", "points", "vectors")}
    content = report["content"]

    def _array_note(name: str) -> str:
        r = content[name]
        return "exact" if r["exact"] else f"{r['indices_differ']} idx differ"

    notes = (f"content: nodes {_array_note('nodes')}, surfs {_array_note('surfs')}, "
             f"leaves {_array_note('leaves')}")
    if content_length_mismatch(content):
        notes += " -- LENGTH MISMATCH on at least one array (never byte-identical regardless of prefix)"
    return LevelResult(
        level=level, dx_path=dx_path, status="OK", elapsed_s=elapsed_s,
        golden_cache_hit=report["cache_hit"],
        nodes_match=matches["nodes"], surfs_match=matches["surfs"], leaves_match=matches["leaves"],
        verts_match=matches["verts"], points_match=matches["points"], vectors_match=matches["vectors"],
        geometry_match_count=sum(matches.values()),
        content_exact_fraction=content_exact_fraction(content),
        content_length_mismatch=content_length_mismatch(content),
        lighting_byte_identical_pct=report["lighting"]["identical_pct"],
        lighting_shadow_bit_pct=report["lighting"]["shadow_bit_pct"],
        full_parity=report["full_parity"], notes=notes)


@dataclass(frozen=True, kw_only=True)
class SweepRun:
    started_at: str
    concurrency: int
    rebuild_timeout: float
    hang_timeout: float
    results: tuple[LevelResult, ...] = field(default_factory=tuple)


def write_sweep_json(run: SweepRun, out_path: Path) -> None:
    d = asdict(run)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(d, indent=2, sort_keys=True))


def read_sweep_json(path: Path) -> SweepRun:
    d = json.loads(path.read_text())
    results = tuple(LevelResult(**r) for r in d["results"])
    return SweepRun(started_at=d["started_at"], concurrency=d["concurrency"],
                    rebuild_timeout=d["rebuild_timeout"], hang_timeout=d["hang_timeout"],
                    results=results)
