import struct, sys
sys.path.insert(0,"/tmp")
from dxparse import parse

PROP_TYPE={1:"Byte",2:"Int",3:"Bool",4:"Float",5:"Object",6:"Name",7:"String",8:"Class",9:"Array",10:"Struct",11:"Vector",12:"Rotator",13:"Str",14:"Map",15:"FixedArray"}
SIZECODE={0:1,1:2,2:4,3:12,4:16}

def ri(d,o):
    b=d[o];o+=1;neg=b&0x80;val=b&0x3f
    if b&0x40:
        sh=6
        while True:
            b=d[o];o+=1;val|=(b&0x7f)<<sh;sh+=7
            if not(b&0x80):break
    return (-val if neg else val),o

def try_props(d,start,limit,names):
    """Parse a UE1 property list starting at `start`. Returns list or None on misparse."""
    o=start; out=[]
    while o<limit:
        nidx,o2=ri(d,o)
        if nidx<0 or nidx>=len(names): return None
        nm=names[nidx]
        if nm=="None":
            return out
        o=o2
        info=d[o];o+=1
        ptype=info&0x0f
        sc=(info>>4)&0x07
        is_arr=info&0x80
        if sc<=4: size=SIZECODE[sc]
        elif sc==5: size=d[o];o+=1
        elif sc==6: size,=struct.unpack_from("<H",d,o);o+=2
        else: size,=struct.unpack_from("<I",d,o);o+=4
        if ptype==10:
            sidx,o=ri(d,o)
            sname=names[sidx] if 0<=sidx<len(names) else "?"
        else: sname=None
        if ptype==3:
            aidx=(info>>6)&1
        elif is_arr:
            aidx,o=ri(d,o)
        else: aidx=0
        val=d[o:o+size]; o+=size
        out.append((nm,PROP_TYPE.get(ptype,ptype),sname,size,val,aidx))
    return out

def fmt(props):
    for nm,pt,sn,sz,val,ai in props:
        extra=""
        if pt=="Rotator" and len(val)>=12:
            p,y,r=struct.unpack("<iii",val[:12]); extra=f"  Pitch={p} Yaw={y} Roll={r} (P={p*360/65536:.1f} Y={y*360/65536:.1f} R={r*360/65536:.1f} deg)"
        elif pt=="Vector" and len(val)>=12:
            x,yy,z=struct.unpack("<fff",val[:12]); extra=f"  X={x:.1f} Y={yy:.1f} Z={z:.1f}"
        elif pt=="Int" and len(val)==4: extra=f"  ={struct.unpack('<i',val)[0]}"
        sns=f"<{sn}>" if sn else ""
        print(f"    {nm:14}{sns:10}{pt:8} sz={sz:3} {val.hex()}{extra}")

def main(path):
    d,names,(eoff,ec),(ioff,icnt),_=parse(path)
    o=eoff; exports=[]
    for i in range(ec):
        cls,o=ri(d,o); sup,o=ri(d,o); pkg,=struct.unpack_from("<i",d,o);o+=4
        nme,o=ri(d,o); flg,=struct.unpack_from("<I",d,o);o+=4; ssz,o=ri(d,o)
        soff=0
        if ssz>0: soff,o=ri(d,o)
        exports.append((names[nme] if 0<=nme<len(names) else nme,soff,ssz))
    for nm,soff,ssz in exports:
        if not nm.startswith("Camera"): continue
        limit=soff+ssz
        # The export may begin with leading actor bytes; brute-force the start offset
        best=None
        for st in range(soff,soff+8):
            p=try_props(d,st,limit,names)
            if p and any(x[0] in ("ViewRotation","Rotation","Location","RendMap") for x in p):
                if best is None or len(p)>len(best[1]):
                    best=(st,p)
        print(f"=== {nm} @ {hex(soff)} sz={ssz} ===")
        if best: print(f"  (props start +{best[0]-soff})"); fmt(best[1])
        else: print("  <no clean parse>", d[soff:soff+ssz][:16].hex())

main(sys.argv[1])
