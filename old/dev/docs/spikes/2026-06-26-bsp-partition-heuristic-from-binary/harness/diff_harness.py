"""Differential harness: compare the asm-faithful candidate-loop simulator against
the rewritten Python port's candidate sequence, over many random configs."""
import os
import random
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sim_candidate_loop import chosen_candidates_asm
import find_best_split as fbs

PF_STRUCTURAL = fbs.PF_STRUCTURAL          # 0x28
PF_PORTAL = fbs.PF_PORTAL                  # 0x04000000


def port_candidates(num: int, inc: int, flags: list[int]) -> list[int]:
    """Re-run JUST the candidate-selection slot loop from the port, returning the
    sequence of chosen candidate indices (mirrors find_best_split's structure)."""
    all_structural = all((f & PF_STRUCTURAL) for f in flags)
    chosen: list[int] = []
    slot_start = 0
    while slot_start < num:
        window_end = slot_start + inc
        cand_i = None
        for k in range(slot_start, min(window_end, num)):
            f = flags[k]
            is_structural = bool(f & PF_STRUCTURAL)
            is_portal = bool(f & PF_PORTAL)
            if is_structural and not is_portal and not all_structural:
                continue
            cand_i = k
            break
        slot_start = window_end
        if cand_i is None:
            continue
        chosen.append(cand_i)
    return chosen


def random_flags(num: int, rng: random.Random) -> list[int]:
    out = []
    for _ in range(num):
        f = 0
        r = rng.random()
        if r < 0.45:
            f |= PF_STRUCTURAL              # structural (semisolid/notsolid bits)
        elif r < 0.55:
            f |= (rng.choice([0x08, 0x20, 0x28]))  # individual structural-ish bits
        if rng.random() < 0.2:
            f |= PF_PORTAL                  # portal (overrides skip)
        if rng.random() < 0.15:
            f |= 0x04                       # an unrelated flag bit (transparent)
        out.append(f)
    return out


def main():
    rng = random.Random(1337)
    mismatches = []
    total = 0
    # exhaustive-ish over small num for several inc, plus random fuzz.
    for trial in range(200000):
        num = rng.randint(1, 40)
        inc = rng.randint(1, max(1, num + 3))   # include inc>num edge
        flags = random_flags(num, rng)
        a = chosen_candidates_asm(num, inc, flags)
        p = port_candidates(num, inc, flags)
        total += 1
        if a != p:
            mismatches.append((num, inc, flags, a, p))
            if len(mismatches) <= 5:
                print(f"MISMATCH num={num} inc={inc}")
                print(f"  flags={[hex(x) for x in flags]}")
                print(f"  asm ={a}")
                print(f"  port={p}")
    print(f"\nran {total} configs; {len(mismatches)} mismatches")
    return len(mismatches)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
