"""Narrower follow-up to `scan_noncardinal.py`: does ANY `Brush` actor in the cached corpus have
all THREE FRotator axes simultaneously non-cardinal (Pitch, Yaw, AND Roll each not a multiple of
16384)? `check_multiaxis_noncardinal.py` found that a genuine two-axis non-cardinal compose (the
only case any real corpus brush hits) round-trips bit-identically between Python-double-compose
and a true per-step float32 compose, but a genuine THREE-axis non-cardinal compose does NOT (1 ULP
divergence on synthetic angles) -- so whether any real brush needs all three axes truly decides
whether this lever has any real-content target at all.
"""
import re
import glob

def is_cardinal(v: int) -> bool:
    return (v % 65536) % 16384 == 0

ROOTS = glob.glob("/workspace/uedcli/_scratch/geo-confirm-*")
ROT = re.compile(r"Rotation=\(([^)]*)\)")
COMP = re.compile(r"(Pitch|Yaw|Roll)=(-?\d+)")


def main():
    hits = []
    for root in ROOTS:
        for f in glob.glob(root + "/**/actors/Brush*/actor.t3d", recursive=True):
            try:
                text = open(f, errors="ignore").read()
            except OSError:
                continue
            if "Class=Brush" not in text and "Class=Mover" not in text:
                # keep it simple -- still print class line for visibility below
                pass
            for m in ROT.finditer(text):
                fields = dict(COMP.findall(m.group(1)))
                # ALL THREE fields must be present and each non-cardinal.
                if not {"Pitch", "Yaw", "Roll"} <= fields.keys():
                    continue
                if all(not is_cardinal(int(fields[k])) for k in ("Pitch", "Yaw", "Roll")):
                    hits.append((f, m.group(0)))
    print(f"scanned {len(ROOTS)} level dirs (Brush* actors only)")
    print(f"found {len(hits)} 3-axis-simultaneously-non-cardinal Brush Rotations")
    for f, rot in hits:
        print(rot, "--", f)


if __name__ == "__main__":
    main()
