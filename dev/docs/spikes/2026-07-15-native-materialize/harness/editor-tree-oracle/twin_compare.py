#!/usr/bin/env python3
"""Index-for-index twin comparison: native STRUCT log vs editor ND log (plane bits)."""
import sys, re
nat_path, ed_path = sys.argv[1], sys.argv[2]
def parse_native(p):
    d={}
    for ln in open(p):
        m=re.match(r'^STRUCT node=(\d+) .*pbits=((?:0x)?[0-9a-f]+),((?:0x)?[0-9a-f]+),((?:0x)?[0-9a-f]+),((?:0x)?[0-9a-f]+)',ln)
        if m: d[int(m.group(1))]=tuple(int(m.group(i),16) for i in range(2,6))
    return d
def parse_editor(p):
    d={}
    for ln in open(p):
        m=re.match(r'^ND (\d+) .*pbits=((?:0x)?[0-9a-f]+),((?:0x)?[0-9a-f]+),((?:0x)?[0-9a-f]+),((?:0x)?[0-9a-f]+)',ln)
        if m: d[int(m.group(1))]=tuple(int(m.group(i),16) for i in range(2,6))
    return d
nat=parse_native(nat_path); ed=parse_editor(ed_path)
common=sorted(set(nat)&set(ed))
print(f'native nodes={len(nat)} editor nodes={len(ed)} common={len(common)}')
twins=[]; wonly=0; first=None
for i in common:
    if nat[i]!=ed[i]:
        twins.append(i)
        if first is None: first=i
        # is it w-only?
        if nat[i][:3]==ed[i][:3] and nat[i][3]!=ed[i][3]: wonly+=1
print(f'TWINS={len(twins)}  w-only={wonly}  first-divergence-node={first}')
for i in twins[:12]:
    dn=[c for c in range(4) if nat[i][c]!=ed[i][c]]
    print(f'  node {i} diff-comp={dn} nat={[hex(x) for x in nat[i]]} ed={[hex(x) for x in ed[i]]}')
