# Extract camera ViewRotation/Rotation FRotators from a saved .dx by locating them
# within each Camera* export region.
import struct, sys
sys.path.insert(0,"/tmp")
from dxparse import parse
def ri(d,o):
    b=d[o];o+=1;neg=b&0x80;val=b&0x3f
    if b&0x40:
        sh=6
        while True:
            b=d[o];o+=1;val|=(b&0x7f)<<sh;sh+=7
            if not(b&0x80):break
    return(-val if neg else val),o
def main(path):
    d,names,(eoff,ec),_,_=parse(path)
    o=eoff; exps=[]
    for i in range(ec):
        cls,o=ri(d,o);sup,o=ri(d,o);pkg,=struct.unpack_from("<i",d,o);o+=4
        nme,o=ri(d,o);flg,=struct.unpack_from("<I",d,o);o+=4;ssz,o=ri(d,o)
        soff=0
        if ssz>0:soff,o=ri(d,o)
        exps.append((names[nme] if 0<=nme<len(names) else nme,soff,ssz))
    for nm,soff,ssz in exps:
        if not nm.startswith("Camera"):continue
        seg=d[soff:soff+ssz]
        rots=[]
        for m in range(len(seg)-12):
            p,y,r=struct.unpack_from("<iii",seg,m)
            if r==0 and -65537<=p<=131072 and -200000<=y<=200000 and (abs(p)>200 or abs(y)>200) and (-66000<p<66000):
                rots.append((m,p,y,r))
        if rots:
            print(f"{nm}: "+", ".join(f"@+{m} (P={p} Y={y} R={r} | P={p*360/65536:.1f} Y={y*360/65536:.1f}deg)" for m,p,y,r in rots))
main(sys.argv[1])
