#!/usr/bin/env python3
"""Spike harness — the stored property on a UE1 `Texture` export that records import-time masking.

Background: `unrealed/quirks.md` (2026-07-26) says `Masked` is a property of the TEXTURE, set at
import, and that a texture's flags are OR'ed into every surface using it — but recorded the property
as "not yet probed to the stored property name/offset on the export". `--faces textured`
(board item `four-actor-preview-faces-rulings-need-a-durable`) cannot gate cut-outs without it.

Answer: the property is **`bMasked`** (a UE1 bool, stored PRESENCE-ONLY — see findings.md).

Modes:
    probe_masked.py --known            props for the ground-truth set + property frequency
    probe_masked.py --sweep            corpus-wide bMasked vs index-0 usage (the blast radius)
    probe_masked.py <pkg.utx> ...      props for arbitrary packages

Point it at a texture dir with $UEDCLI_SPIKE_TEXTURES if the default paths do not apply.
"""
import glob
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path.insert(0, ROOT)

from uedcli import utexture  # noqa: E402

TEX_DIRS = [
    os.environ.get("UEDCLI_SPIKE_TEXTURES", ""),
    os.path.expanduser("~/Games/LutrisDX/drive_c/DX/Textures"),
    os.path.expanduser("~/Games/LutrisDX/drive_c/DX/LUM/Textures"),
    os.path.join(ROOT, "uedcli", "tests", "fixtures"),
]

# Ground truth from spikes/levelbuild-friction/agent-reports.md — textures the level-building
# agents OBSERVED rendering see-through (or solid) in a --game render. Two of these labels turned
# out to be wrong; findings.md §3 explains which, and why the texture data is the better evidence.
GROUND_TRUTH = {
    ("CoreTexMetal", "ladder_a"): "reported see-through on a SOLID wall (ContainerYard + DiveBar)",
    ("CoreTexMetal", "ClenChainlink_B"): "reported as chain-link cut-out",
    ("CoreTexMisc", "DangDoNoEnter_A"): "reported as a cut-out sign",
    ("MolePeople", "WirePanel"): "reported fixed by --add-flag Masked",
    ("Paris", "pa_gate_a"): "reported: flagging it was a NO-OP, 'gaps are painted, not index 0'",
    ("CoreTexMetal", "ShipGrayMetal_A"): "reported masked on 12 polys by a blanket --add-flag",
    ("CoreTexWater", "dirtywater"): "reserved magenta at index 0",
    ("LUM_InfoPortraits", "ArthurCallaway"): "index 0 is REAL BLACK",
}


def find_pkg(stem):
    for d in TEX_DIRS:
        if not d:
            continue
        p = os.path.join(d, stem + ".utx")
        if os.path.exists(p):
            return p
    return None


def texture_props(pkg, i):
    e = pkg.exports[i]
    props, _ = utexture._read_props(pkg.buf, e["soff"], e["soff"] + e["ssize"], pkg.names)
    return props


def index0_fraction(pkg, i):
    """Fraction of mip-0 texels that are palette index 0, or None if undecodable."""
    try:
        t = utexture.decode_texture(pkg, i)
    except Exception:                                    # noqa: BLE001 - probe tool
        return None, None
    if not t.mips or not t.mips[0].data:
        return None, None
    m = t.mips[0]
    pal0 = None
    try:
        # NOTE: palette_ref is an object REF, not an export index — it must go through
        # export_index_of_ref. Doing it directly raises "palette body not at EOF".
        idx = utexture.export_index_of_ref(pkg, t.palette_ref)
        if idx is not None:
            pal0 = utexture.decode_palette(pkg, idx)[0]
    except Exception:                                    # noqa: BLE001
        pal0 = None
    return m.data.count(0) / len(m.data), pal0


def mode_known():
    key_counter = Counter()
    per_key_values = defaultdict(Counter)
    rows = []
    for (stem, name), note in GROUND_TRUTH.items():
        path = find_pkg(stem)
        if path is None:
            print(f"!! package not on disk: {stem}", file=sys.stderr)
            continue
        pkg = utexture.load_package(path)
        for i in utexture.textures(pkg):
            for k, v in texture_props(pkg, i).items():
                key_counter[k] += 1
                per_key_values[k][repr(v[1])[:24]] += 1
            if pkg.names[pkg.exports[i]["nm"]].casefold() != name.casefold():
                continue
            props = texture_props(pkg, i)
            frac, pal0 = index0_fraction(pkg, i)
            rows.append((f"{stem}.{name}", "bMasked" in props, frac, pal0, note))

    print("PROPERTY FREQUENCY (all Texture exports in the packages touched)")
    for k, n in key_counter.most_common():
        print(f"  {n:6d}  {k:<20} {', '.join(f'{v}×{c}' for v, c in per_key_values[k].most_common(4))}")
    print()
    print(f"{'texture':<38} {'bMasked':<8} {'idx0':>7}  {'pal[0]':<16} note")
    print("-" * 110)
    for name, bm, frac, pal0, note in sorted(rows):
        fs = f"{100*frac:6.2f}%" if frac is not None else "    n/a"
        print(f"{name:<38} {str(bm):<8} {fs}  {str(pal0):<16} {note}")


def mode_sweep():
    seen = set()
    tot = masked = m_idx0 = u_idx0 = 0
    worst = []
    for d in TEX_DIRS:
        if not d or not os.path.isdir(d):
            continue
        for p in sorted(glob.glob(os.path.join(d, "*.utx"))):
            stem = os.path.basename(p)[:-4].casefold()
            if stem in seen:
                continue
            seen.add(stem)
            try:
                pkg = utexture.load_package(p)
            except Exception:                            # noqa: BLE001
                continue
            for i in utexture.textures(pkg):
                bm = "bMasked" in texture_props(pkg, i)
                frac, _ = index0_fraction(pkg, i)
                if frac is None:
                    continue
                tot += 1
                masked += bm
                if frac > 0:
                    if bm:
                        m_idx0 += 1
                    else:
                        u_idx0 += 1
                        worst.append((frac, stem, pkg.names[pkg.exports[i]["nm"]]))
    print(f"textures scanned                : {tot}")
    print(f"  bMasked present               : {masked}  ({100*masked/tot:.1f}%)")
    print(f"  index-0 users, bMasked        : {m_idx0}   <- genuine cut-outs")
    print(f"  index-0 users, NOT bMasked    : {u_idx0}   <- FALSE HOLES if masking is ungated")
    print("\nworst ungated index-0 users:")
    for frac, pk, n in sorted(worst, reverse=True)[:12]:
        print(f"  {100*frac:6.2f}%  {pk}.{n}")


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--known":
        mode_known()
    elif argv[0] == "--sweep":
        mode_sweep()
    else:
        for path in argv:
            pkg = utexture.load_package(path)
            for i in utexture.textures(pkg):
                props = texture_props(pkg, i)
                print(f"{pkg.names[pkg.exports[i]['nm']]:<28} "
                      f"bMasked={'bMasked' in props} {sorted(props)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
