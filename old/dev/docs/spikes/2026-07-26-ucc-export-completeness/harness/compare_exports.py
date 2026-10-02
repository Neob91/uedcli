#!/usr/bin/env python3
"""Is UCC's offline `.dx` -> T3D export CONTENT-COMPLETE, measured against UnrealEd's own export,
on the retail Deus Ex maps?

WHY THIS EXISTS. uedcli's post-build verify re-reads the map it just built and compares it to the
trunk it was built from. The re-read is done by `UCC.exe batchexport` — a plain command-line tool,
no editor, no GUI. If that export silently omits anything, the verify compares an incomplete picture
and reports a clean build that is not clean.

The claim that UCC's export is equivalent to the editor's rests on `2026-06-18-ucc-level-export.md`,
which verified it on ONE synthetic level: four actors, 8693 bytes, hand-built for that probe. That
is far too small a sample to carry a build-correctness check for real maps. The owner's ruling
(2026-07-26) was to adopt the no-editor route only after comparing against UnrealEd on the shipped
Deus Ex levels — maps with thousands of actors, movers, conversations, scripted pawns and
special classes that a four-actor fixture cannot represent.

METHOD. For each map, produce two T3D texts of the SAME on-disk `.dx`:

  UCC     `wine /opt/UED22/UCC.exe batchexport <map>.dx Level T3D <outdir>`   (no editor)
  EDITOR  `MAP LOAD FILE=<map>.dx` then `MAP EXPORT FILE=<out>.t3d`           (live UnrealEd)

Both are parsed and normalized through uedcli's OWN seam (`parse_t3d` -> `level_order` ->
`normalize_level`), i.e. exactly what the verify would see, so a difference this reports is a
difference the verify would actually act on — not a formatting artifact the pipeline already folds.
Two known-contextual differences are folded before comparing, both already handled in production:
the self-referential package prefix (in memory the level lives in package `MyLevel`; on disk it is
the file stem) and the editor-computed props in `normalize.COMPUTED_PROPS`.

Differences are then BUCKETED rather than merely counted, because the verdict depends entirely on
which kind they are: a missing ACTOR is fatal to the design, a property that only ever appears on
one side is a normalization gap, and a differing VALUE needs reading.

    compare_exports.py <outdir> [MAP.dx ...]      (default: the sample below)
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(_REPO))

from uedcli import container_assets, editor, xfer                        # noqa: E402
from uedcli.driver import Driver, to_z_path                              # noqa: E402
from uedcli.model import parse_t3d                                       # noqa: E402
from uedcli.normalize import level_order, normalize_level                # noqa: E402

EDITOR_ID = "uccexport-probe"

DX = Path("/home/neob91/Games/LutrisDX/drive_c/DX")
ASSET_DIRS = [str(DX / d) for d in ("System", "Textures", "Sounds", "Music", "Maps")]

# A deliberately DIVERSE sample rather than the first N alphabetically: the point is to cover the
# shapes a four-actor fixture could not. Sizes are the on-disk `.dx` bytes.
SAMPLE = [
    "00_Training.dx",          # small, simple
    "00_Intro.dx",             # ~1837 actors — the largest actor count in the corpus
    "01_NYC_UNATCOHQ.dx",      # conversations, scripted pawns
    "02_NYC_BatteryPark.dx",   # outdoor, terrain-ish
    "04_NYC_Hotel.dx",         # movers (the SavedPos/SavedRot engine-stamped class)
    "06_HONGKONG_WanChai_Street.dx",   # large city map
]

_PKG_PREFIX = re.compile(r"(\w+)'([A-Za-z0-9_]+)\.")


def _canon_prefix(text: str) -> str:
    """Fold the self-referential package prefix. `MAP EXPORT` writes the IN-MEMORY package name
    (`MyLevel`); UCC writes the ON-DISK file stem. Both name the same object. Production already
    folds this (`2026-06-18-ucc-level-export.md` action item), so it is not a finding."""
    return _PKG_PREFIX.sub(r"\1'PKG.", text)


def _to_level(text: str):
    lvl = parse_t3d(_canon_prefix(text))
    lvl.order = level_order(lvl)
    normalize_level(lvl)
    return lvl


def _ucc_export(driver: Driver, container_map: str) -> tuple[str | None, str]:
    """(t3d_text, diagnostic). `None` text means UCC could not export this map at all — which is a
    finding in its own right, NOT a reason to abort the sweep, so the caller keeps going."""
    outdir = xfer.work_dir("ucc")
    subprocess.run(["docker", "exec", driver.container, "mkdir", "-p", outdir],
                   check=True, capture_output=True, text=True)
    r = subprocess.run(
        ["docker", "exec", driver.container, "wine", "/opt/UED22/UCC.exe", "batchexport",
         container_map, "Level", "T3D", to_z_path(outdir)],
        capture_output=True, text=True)
    out = subprocess.run(["docker", "exec", driver.container, "cat",
                          f"{outdir}/MyLevel.T3D"], capture_output=True, text=True)
    if out.returncode != 0:
        why = ""
        for line in r.stdout.splitlines():
            if "Failed" in line or "Error" in line or "Can't find" in line:
                why = line.strip()
                break
        xfer.remove(driver.container, outdir)
        return None, why or (r.stdout.strip().splitlines() or ["(no output)"])[-1]
    xfer.remove(driver.container, outdir)
    return out.stdout, "ok"


def _editor_export(driver: Driver, container_map: str, tag: str, outdir: Path,
                   timeout: float = 420.0) -> str | None:
    """`MAP LOAD` then `MAP EXPORT`, as ONE `EXEC` script whose last line is the export that
    doubles as the completion marker (driving is fire-and-forget; a marker is the only honest
    completion signal, and a script rides through the GC dialog).

    Returns `None` if UnrealEd could not load this map. That is the control the whole comparison
    needs: a map UCC cannot read is only damning if the EDITOR can read it.

    ⚠ `MAP NEW` FIRST — it is load-bearing, not tidiness. `EXEC` does NOT abort on a failing line
    (`dev/docs/unrealed/commands.md`), so when `MAP LOAD` fails the editor simply keeps whatever
    level it already had and the very next `MAP EXPORT` writes THAT — a full, healthy-looking export
    of the wrong map. This probe hit exactly that: three maps UCC had rejected each came back as a
    perfect 1304-actor export, which was the PREVIOUS map still resident. Emptying the level first
    turns a failed load into an unmistakably tiny export instead of a silently wrong one.
    """
    marker = f"/work/{tag}-ued.t3d"
    subprocess.run(["docker", "exec", driver.container, "rm", "-f", marker],
                   capture_output=True, text=True)          # never read a stale marker
    script = outdir / f"{tag}.cmd"
    script.write_text(f"MAP NEW\n"
                      f"MAP LOAD FILE={to_z_path(container_map)}\n"
                      f"MAP EXPORT FILE={to_z_path(marker)}\n")
    cpath = xfer.cp_in(driver.container, str(script), ext="txt")
    driver.exec(f"EXEC {to_z_path(cpath)}")

    deadline = time.time() + timeout    # bounded: the editor wedges silently
    last, stable = None, 0
    while time.time() < deadline:
        st = driver.container_stat(marker)
        if st is not None and st[0] > 0:
            if st[0] == last:
                stable += 1
                if stable >= 3:
                    host = outdir / f"{tag}-ued.t3d"
                    xfer.cp_out(driver.container, marker, str(host))
                    txt = host.read_text()
                    # A `MAP NEW` level exports as LevelInfo + the builder brush and nothing else,
                    # so a handful of actors means the LOAD failed and this is the EMPTY level.
                    return None if len(parse_t3d(txt).actors) <= 3 else txt
            else:
                stable = 0
            last = st[0]
        time.sleep(2.0)
    return None


def _props(actor) -> dict:
    """Property name -> value text. Later duplicates win, matching the importer."""
    return {k: v for k, v in actor.props}


def compare(ucc, ued) -> dict:
    """Bucket every difference. `ucc` is the no-editor export; `ued` is UnrealEd's own."""
    a, b = ucc.actors, ued.actors
    missing = sorted(set(b) - set(a))          # in UnrealEd's export, ABSENT from UCC's -> fatal
    extra = sorted(set(a) - set(b))            # only UCC has it
    cls_diff, only_ued, only_ucc, val_diff, brush_diff = [], [], [], [], []

    for n in sorted(set(a) & set(b)):
        x, y = a[n], b[n]
        if getattr(x, "cls", None) != getattr(y, "cls", None):
            cls_diff.append((n, getattr(x, "cls", None), getattr(y, "cls", None)))
        px, py = _props(x), _props(y)
        for k in sorted(set(py) - set(px)):
            only_ued.append((n, k, py[k]))
        for k in sorted(set(px) - set(py)):
            only_ucc.append((n, k, px[k]))
        for k in sorted(set(px) & set(py)):
            if px[k] != py[k]:
                val_diff.append((n, k, px[k], py[k]))
        bx, by = getattr(x, "brush", None), getattr(y, "brush", None)
        if (bx is None) != (by is None):
            brush_diff.append((n, "brush presence", bx is None, by is None))
        elif bx is not None and len(bx.polys) != len(by.polys):
            brush_diff.append((n, "poly count", len(bx.polys), len(by.polys)))

    return {"n_ucc": len(a), "n_ued": len(b),
            "missing_from_ucc": missing, "only_in_ucc": extra,
            "class_diff": cls_diff, "prop_only_in_ued": only_ued,
            "prop_only_in_ucc": only_ucc, "value_diff": val_diff, "brush_diff": brush_diff}


def _summary(d: dict) -> str:
    def hist(rows, idx=1):
        c = collections.Counter(r[idx] for r in rows)
        return ", ".join(f"{k}×{v}" for k, v in c.most_common(8)) or "-"
    return (f"    actors: UCC {d['n_ucc']} / UnrealEd {d['n_ued']}\n"
            f"    MISSING from UCC: {len(d['missing_from_ucc'])} {d['missing_from_ucc'][:5]}\n"
            f"    only in UCC:      {len(d['only_in_ucc'])} {d['only_in_ucc'][:5]}\n"
            f"    class differs:    {len(d['class_diff'])} {d['class_diff'][:3]}\n"
            f"    prop only in UED: {len(d['prop_only_in_ued'])} [{hist(d['prop_only_in_ued'])}]\n"
            f"    prop only in UCC: {len(d['prop_only_in_ucc'])} [{hist(d['prop_only_in_ucc'])}]\n"
            f"    value differs:    {len(d['value_diff'])} [{hist(d['value_diff'])}]\n"
            f"    brush differs:    {len(d['brush_diff'])} {d['brush_diff'][:3]}")


def main() -> int:
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    explicit = sys.argv[2:]

    state = _REPO / "_scratch" / "uccexport" / "state"
    state.mkdir(parents=True, exist_ok=True)
    mounts = container_assets.resource_mounts(ASSET_DIRS)
    maps_mount = next(m.container_dir for m in mounts if Path(m.host_dir).name == "Maps")
    container = editor.ensure_editor(EDITOR_ID, state_dir=state, mounts=mounts)
    print(f"editor ready: {container}   (Maps at {maps_mount})", flush=True)
    driver = Driver(container)

    all_maps = explicit or sorted(p.name for p in (DX / "Maps").glob("*.dx"))
    report: dict = {"phase1": {}, "phase2": {}}

    # ---- PHASE 1: can UCC read every shipped map at all? (cheap; no editor involved)
    print(f"\n=== PHASE 1 — UCC batchexport over {len(all_maps)} maps", flush=True)
    for name in all_maps:
        tag = name[:-3]
        t0 = time.time()
        txt, why = _ucc_export(driver, f"{maps_mount}/{name}")
        dt = round(time.time() - t0, 1)
        if txt is None:
            report["phase1"][name] = {"ok": False, "why": why, "secs": dt}
            print(f"  FAIL {name:<34} {dt:>5.1f}s  {why[:90]}", flush=True)
        else:
            (outdir / f"{tag}-ucc.t3d").write_text(txt)
            n = len(_to_level(txt).actors)
            report["phase1"][name] = {"ok": True, "secs": dt, "bytes": len(txt), "actors": n}
            print(f"  ok   {name:<34} {dt:>5.1f}s  {len(txt):>9}B  {n:>5} actors", flush=True)
        (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str))

    ok = [m for m, d in report["phase1"].items() if d["ok"]]
    bad = [m for m, d in report["phase1"].items() if not d["ok"]]
    print(f"\n  UCC read {len(ok)}/{len(all_maps)} maps; {len(bad)} failed", flush=True)

    # ---- PHASE 2: for a diverse sample, does UnrealEd's OWN export differ from UCC's?
    # Sample = the largest maps UCC read (most actors = most chances to lose something), plus the
    # named diversity picks that survived phase 1, plus up to 3 maps UCC could NOT read — those
    # last ones are the control: a map UCC cannot read only matters if the EDITOR can read it.
    by_actors = sorted(ok, key=lambda m: -report["phase1"][m]["actors"])
    sample = list(dict.fromkeys(by_actors[:4] + [m for m in SAMPLE if m in ok]))
    controls = bad if explicit else bad[:3]
    print(f"\n=== PHASE 2 — UnrealEd export vs UCC on {len(sample)} maps "
          f"(+{len(controls)} UCC-unreadable controls)", flush=True)

    for name in sample + controls:
        tag = name[:-3]
        cmap = f"{maps_mount}/{name}"
        is_control = name in controls
        print(f"--- {name}{'   [control: UCC could not read it]' if is_control else ''}",
              flush=True)
        t0 = time.time()
        ued_txt = _editor_export(driver, cmap, tag, outdir)
        t_ued = round(time.time() - t0, 1)

        if ued_txt is None:
            report["phase2"][name] = {"editor_ok": False, "ucc_ok": not is_control,
                                      "secs_ued": t_ued}
            print(f"    UnrealEd ALSO could not export it ({t_ued}s)", flush=True)
            (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str))
            continue
        if is_control:
            report["phase2"][name] = {"editor_ok": True, "ucc_ok": False, "secs_ued": t_ued,
                                      "bytes_ued": len(ued_txt)}
            print(f"    UnrealEd READ IT ({t_ued}s, {len(ued_txt)}B) but UCC could not "
                  f"— UCC IS WEAKER HERE", flush=True)
            (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str))
            continue

        ucc_txt = (outdir / f"{tag}-ucc.t3d").read_text()
        d = compare(_to_level(ucc_txt), _to_level(ued_txt))
        d.update(editor_ok=True, ucc_ok=True, secs_ued=t_ued,
                 secs_ucc=report["phase1"][name]["secs"],
                 bytes_ucc=len(ucc_txt), bytes_ued=len(ued_txt))
        report["phase2"][name] = d
        print(f"    UCC {d['secs_ucc']}s / {len(ucc_txt)}B   "
              f"UnrealEd {t_ued}s / {len(ued_txt)}B", flush=True)
        print(_summary(d), flush=True)
        (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str))

    print("\n== VERDICT ==", flush=True)
    print(f"  phase 1: UCC read {len(ok)}/{len(all_maps)} shipped maps", flush=True)
    compared = {m: d for m, d in report["phase2"].items() if d.get("ucc_ok")
                and d.get("editor_ok")}
    lost = [m for m, d in compared.items()
            if d["missing_from_ucc"] or d["class_diff"] or d["brush_diff"]
            or d["prop_only_in_ued"] or d["value_diff"]]
    print(f"  phase 2: {len(compared)} maps compared against UnrealEd's own export", flush=True)
    print(f"           UCC lost content on: {len(lost)} {lost}", flush=True)
    weaker = [m for m, d in report["phase2"].items()
              if d.get("editor_ok") and not d.get("ucc_ok")]
    print(f"           maps UnrealEd could read but UCC could NOT: {len(weaker)} {weaker}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
