#!/usr/bin/env python3
"""Mouseless perspective-camera rotation set, self-locating (no hardcoded address).
Usage: setcam.py PITCH YAW ROLL   (Unreal rotation units, 65536 = 360 deg)
Pipeline:
  1. MAP SAVE; parse Camera8's ViewRotation FRotator from the .dx (the read oracle).
  2. Scan the editor heap for that 12-byte FRotator where the *next* 12 bytes are a
     plausible Location FVector (finite, non-zero, |comp|<1e5). Unique => the live
     derived ViewRotation copy.
  3. authoritative = derived + 0x1F4 (the render-source field). Write FRotator to both.
  4. RMB press+release (NO move) in the perspective pane -> recompute + repaint."""
import sys, struct, subprocess, time, re, math
sys.path.insert(0,"/tmp")
import memscan as M
from dxparse import parse

PID=int(open("/run/uned.pid").read())
W=["python3","/repo/Tools/uedcli/uned/wine_ctl.py"]
DELTA=0x1F4

def ri(d,o):
    b=d[o];o+=1;neg=b&0x80;val=b&0x3f
    if b&0x40:
        sh=6
        while True:
            b=d[o];o+=1;val|=(b&0x7f)<<sh;sh+=7
            if not(b&0x80):break
    return(-val if neg else val),o

def read_oracle(dxpath):
    subprocess.run(W+["exec",f"MAP SAVE FILE={dxpath}"]); time.sleep(1.2)
    d,names,(eoff,ec),_,_=parse(dxpath)
    o=eoff; exps=[]
    for i in range(ec):
        cls,o=ri(d,o);sup,o=ri(d,o);pkg,=struct.unpack_from("<i",d,o);o+=4
        nme,o=ri(d,o);flg,=struct.unpack_from("<I",d,o);o+=4;ssz,o=ri(d,o)
        soff=0
        if ssz>0:soff,o=ri(d,o)
        exps.append((names[nme] if 0<=nme<len(names) else nme,soff,ssz))
    cands=[]
    for nm,soff,ssz in exps:
        if not nm.startswith("Camera"): continue
        seg=d[soff:soff+ssz]
        for m in range(len(seg)-12):
            p,y,r=struct.unpack_from("<iii",seg,m)
            if r==0 and -66000<p<66000 and -200000<y<200000 and (abs(p)>50 or abs(y)>50):
                cands.append((p,y,r))
    return cands

def locate(rot):
    sig=struct.pack("<iii",*rot); cands=[]
    for s,e,_ in M.maps(PID):
        off=s
        while off<e:
            n=min(4*1024*1024,e-off); d=M.rd(PID,off,n); idx=0
            while True:
                j=d.find(sig,idx)
                if j<0: break
                fv=d[j+12:j+24]
                if len(fv)==12:
                    x,y,z=struct.unpack("<fff",fv)
                    if all(math.isfinite(v) for v in (x,y,z)) and any(abs(v)>1 for v in (x,y,z)) and all(abs(v)<1e5 for v in (x,y,z)):
                        cands.append(off+j)
                idx=j+1
            off+=n
    return cands

def trigger():
    st=subprocess.run(W+["status"],capture_output=True,text=True).stdout
    win=re.search(r"window=(\d+)",st).group(1)
    geo=subprocess.run(["xdotool","getwindowgeometry","--shell",win],capture_output=True,text=True).stdout
    g={k:int(v) for k,v in re.findall(r"(\w+)=(\d+)",geo)}
    subprocess.run(W+["focus"]); time.sleep(0.2)
    px=g["X"]+g["WIDTH"]//4; py=g["Y"]+g["HEIGHT"]*3//4
    subprocess.run(["xdotool","mousemove",str(px),str(py)]); time.sleep(0.15)
    subprocess.run(["xdotool","mousedown","3"]); time.sleep(0.1)
    subprocess.run(["xdotool","mouseup","3"]); time.sleep(0.4)

def main():
    P,Y,R=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
    oracles=read_oracle("/repo/_scratch/camspike/_locate.dx")
    if not oracles: print("FAIL: no ViewRotation in .dx (camera at class default? nudge once first)"); return 1
    hit=None; usedrot=None
    for rot in oracles:
        hs=locate(rot)
        print(f"oracle {rot} -> {[hex(h) for h in hs]}")
        if len(hs)==1: hit=hs[0]; usedrot=rot; break
    if hit is None: print("FAIL: no oracle gave a unique memory hit"); return 1
    hits=[hit]
    derived=hits[0]; auth=derived+DELTA
    data=struct.pack("<iii",P,Y,R)
    M.wr(PID,derived,data); M.wr(PID,auth,data)
    trigger()
    after=[struct.unpack("<iii",M.rd(PID,a,12)) for a in (derived,auth)]
    print(f"target=({P},{Y},{R})  after={after}")
    return 0 if after[1]==(P,Y,R) else 2

sys.exit(main())
