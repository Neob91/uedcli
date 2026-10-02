import json

d = json.load(open('/tmp/corpus_measure_out.json'))

def delta(pair):
    native, golden = pair
    return native - golden

CONFIGS = ["OFF", "RING_NEAR", "MERGE_NEIGHBOR_SAME", "BOTH"]
FIELDS = ["nodes", "surfs", "leaves", "verts"]

rows = []
for level in sorted(d.keys()):
    cell = {}
    for cfg in CONFIGS:
        r = d[level][cfg]
        if isinstance(r, str):
            cell[cfg] = None
            continue
        cell[cfg] = {f: delta(r[f]) for f in FIELDS}
    rows.append((level, cell))

# Strict-improvement / regression analysis vs OFF baseline
def strictly_better_or_equal(base, cand):
    # all |delta| <= |base delta|, at least one strictly smaller, none flips to worse magnitude
    improved = False
    for f in FIELDS:
        b, c = abs(base[f]), abs(cand[f])
        if c > b:
            return False
        if c < b:
            improved = True
    return improved

def any_regression(base, cand):
    return any(abs(cand[f]) > abs(base[f]) for f in FIELDS)

print(f"{'level':28} {'cfg':22} {'nodes':>8} {'surfs':>7} {'leaves':>8} {'verts':>8}")
for level, cell in rows:
    off = cell["OFF"]
    for cfg in CONFIGS:
        c = cell[cfg]
        if c is None:
            print(f"{level:28} {cfg:22} FAILED")
            continue
        marker = ""
        if cfg != "OFF" and off is not None:
            if strictly_better_or_equal(off, c):
                marker = "  <== STRICT IMPROVEMENT"
            elif any_regression(off, c):
                marker = "  (regression on >=1 count)"
        print(f"{level:28} {cfg:22} {c['nodes']:+8} {c['surfs']:+7} {c['leaves']:+8} {c['verts']:+8}{marker}")
    print()

print("=== Levels currently EXACT under OFF (nodes=surfs=leaves=0) and their status under each config ===")
for level, cell in rows:
    off = cell["OFF"]
    if off is None:
        continue
    if off["nodes"] == 0 and off["surfs"] == 0 and off["leaves"] == 0:
        print(f"{level}: OFF exact (nodes/surfs/leaves=0, verts={off['verts']:+d})")
        for cfg in CONFIGS[1:]:
            c = cell[cfg]
            if c is None:
                continue
            broke = c["nodes"] != 0 or c["surfs"] != 0 or c["leaves"] != 0
            print(f"    {cfg}: nodes={c['nodes']:+d} surfs={c['surfs']:+d} leaves={c['leaves']:+d} verts={c['verts']:+d}"
                  + ("  <<< BREAKS EXACT" if broke else "  (structure still exact)"))
