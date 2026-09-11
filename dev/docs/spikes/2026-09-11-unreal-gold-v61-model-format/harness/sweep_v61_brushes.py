"""Corpus-wide check: every `Engine.Brush` actor across a set of real, retail v61 (original
1998/Gold Unreal) `.unr` maps decodes through the PRODUCTION `uedcli.mapimport.brush_of` — the
same fix `decode_v61_model.py` (same dir) traced out by hand on one brush.

Confirms the v61 top-level object-ref layout (module docstring, `uedcli/native/umodel.py`) holds
for every brush sampled, not just the one hand-decoded example, and that every one of those
brushes' `Polys` ref resolves and decodes cleanly through the unmodified, production
`decode_upolys` (proving `FPoly`'s own on-disk layout needs no v61 branch).

Usage: `python3 sweep_v61_brushes.py <maps-dir>` (defaults to `dev/games/unreal/MAPS` under the
repo root — the full working copy `dev/scripts/install-unreal-assets.sh` assembles, gitignored/
user-supplied). Run 2026-09-11 over the 8 maps below (6173 brushes total): zero failures.
"""
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli.mapimport import SchemaError, _skip_state_frame, brush_of
from uedcli.upackage import PT_OBJECT, load_package, read_compact_index, read_property_tags

DEFAULT_MAPS_DIR = Path(__file__).resolve().parents[5] / "dev" / "games" / "unreal" / "MAPS"

# A spread of maps this session confirmed present, from 53 KB to 9.8 MB — not exhaustive over the
# whole retail set (that took several minutes per full run; see the module docstring).
SAMPLE_MAPS = [
    "Bluff.unr", "DmDeck16.unr", "DmCurse.unr", "DmMorbias.unr",
    "DmTundra.unr", "Dig.unr", "Dark.unr", "DasaPass.unr",
]


def brush_refs(pkg):
    out = {}
    for e in pkg.exports:
        if pkg.object_path(e["cls"]) != "Engine.Brush":
            continue
        start = _skip_state_frame(pkg, e)
        tags, _pos = read_property_tags(pkg, start, e["soff"] + e["ssize"])
        for tag in tags:
            if tag.name == "Brush" and tag.ptype == PT_OBJECT:
                ref, _ = read_compact_index(tag.raw, 0)
                out[pkg.names[e["nm"]]] = ref
    return out


def sweep_map(path: Path) -> None:
    pkg = load_package(str(path))
    refs = brush_refs(pkg)
    n_ok, n_fail, n_polys = 0, 0, 0
    fails = []
    for name, ref in refs.items():
        try:
            n_polys += len(brush_of(pkg, ref).polys)
            n_ok += 1
        except SchemaError as ex:
            n_fail += 1
            fails.append((name, str(ex)))
    print(f"{path.name}: version={pkg.version} brushes={len(refs)} ok={n_ok} fail={n_fail} "
          f"total_polys={n_polys}")
    for name, err in fails[:5]:
        print("   FAIL", name, err)


def main(maps_dir: Path) -> None:
    for name in SAMPLE_MAPS:
        p = maps_dir / name
        if p.exists():
            sweep_map(p)
        else:
            print(f"{name}: not present under {maps_dir} — skipped")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MAPS_DIR)
