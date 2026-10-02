import re,sys
def pn(p):
    d={}
    for ln in open(p):
        m=re.match(r'^STRUCT node=(\d+) .*iF=(-?\d+) iB=(-?\d+) iP=(-?\d+) isurf=(-?\d+) nf=\S+ nv=(\d+)',ln)
        if m: d[int(m.group(1))]=tuple(int(m.group(i)) for i in range(2,7))
    return d
def pe(p):
    d={}
    for ln in open(p):
        m=re.match(r'^ND (\d+) .*iF=(-?\d+) iB=(-?\d+) iP=(-?\d+) isurf=(-?\d+) nv=(\d+)',ln)
        if m: d[int(m.group(1))]=tuple(int(m.group(i)) for i in range(2,7))
    return d
nat=pn(sys.argv[1]); ed=pe(sys.argv[2])
common=sorted(set(nat)&set(ed))
diff=[i for i in common if nat[i]!=ed[i]]
print(f"native={len(nat)} editor={len(ed)} common={len(common)} struct(iF,iB,iP,isurf,nv)-mismatches={len(diff)}")
for i in diff[:10]:
    print(f"  node {i} nat={nat[i]} ed={ed[i]}")
