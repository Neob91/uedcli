"""Scan the cached corpus trunks (`_scratch/geo-confirm-*`) for a brush `Rotation=` whose
FRotator has TWO OR MORE simultaneously non-cardinal axes -- the one gap `uedcli/rotation.py`'s
own module header flags as unverified against the real editor ("a genuine NON-CARDINAL
multi-axis FRotator ... DX content has NONE, so it is unexercised and UNMEASURED"). A single
non-cardinal axis, or several axes where at most one is non-cardinal, stays inside the
already-verified bit-exact envelope (composing with a cardinal {-1,0,1} signed-permutation
matrix introduces no floating-point rounding -- see this spike's write-up).
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
        for f in glob.glob(root + "/**/actor.t3d", recursive=True):
            try:
                text = open(f, errors="ignore").read()
            except OSError:
                continue
            for m in ROT.finditer(text):
                fields = dict(COMP.findall(m.group(1)))
                noncard = [k for k, v in fields.items() if not is_cardinal(int(v))]
                if len(noncard) >= 2:
                    hits.append((f, m.group(0)))
    print(f"scanned {len(ROOTS)} level dirs")
    print(f"found {len(hits)} multi-axis-non-cardinal Rotation instances")
    for f, rot in hits[:60]:
        print(rot, "--", f)


if __name__ == "__main__":
    main()
