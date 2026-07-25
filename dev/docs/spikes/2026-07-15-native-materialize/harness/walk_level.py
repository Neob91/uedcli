"""Full ULevel serial-body walker: validates the reverse-engineered on-disk layout
by walking a real Level export to EOF.

Layout (from Engine.dll disasm, ver 68 path):
  UObject props: 'None' terminator (ci name-idx)
  ULevelBase:
    Actors: INT32 Num, INT32 Max, Num x ci(objref)
    URL: FString Protocol, Host, Map, Portal; TArray<FString> Op; INT32 Port; INT32 Valid
  ULevel tail:
    obj-ref  Model            (this+0x98)
    ReachSpecs: ci count, N x { INT32 Dist, ci Start, ci End, INT32 CollR, INT32 CollH, INT32 Flags, BYTE bPruned }
    INT32/float  (this+0xdc-derived; 4 bytes)
    obj-ref  (this+0x100)
    16 x obj-ref (this+0x9c..)
    [ver>=63] TravelInfo: ci count, N x { FString, FString }
Usage: walk_level.py <path.dx> [--verbose]
"""
import struct, sys
import decode_level as D

def ci(b,p): return D.ci(b,p)
def i32(b,p): return D.i32(b,p)
def u32(b,p): return D.u32(b,p)

def fstring(b,p):
    ln, p = ci(b,p)
    if ln==0: return "", p
    if ln>0:
        s=b[p:p+ln]; p+=ln
        return s.split(b'\x00',1)[0].decode('latin1'), p
    n=-ln; s=b[p:p+2*n]; p+=2*n
    return s.decode('utf-16-le','replace').split('\x00',1)[0], p

def walk(path, verbose=False):
    buf=open(path,'rb').read()
    h=D.parse_header(buf)
    names=D.parse_names(buf,h); imps=D.parse_imports(buf,h,names); exps=D.parse_exports(buf,h,names)
    none_idx=names.index('None')
    levels=[i for i,e in enumerate(exps) if D.classname(e,exps,imps,names)=='Level']
    li=levels[0]; e=exps[li]; off=e['off']; size=e['size']; body=buf[off:off+size]
    def nm(idx): return D.objref_name(idx,exps,imps,names)
    p=0
    tag,p=ci(body,p)
    assert tag==none_idx, f"expected None prop terminator, got {tag}"
    # Actors
    num,p=i32(body,p); mx,p=i32(body,p)
    refs=[]
    for _ in range(num):
        r,p=ci(body,p); refs.append(r)
    log=[]
    log.append(f"ver={h['ver']} level='{e['name']}' size={size}")
    log.append(f"Actors: Num={num} Max={mx}; [0]={nm(refs[0]) if refs else '-'} [1]={nm(refs[1]) if len(refs)>1 else '-'} [last]={nm(refs[-1]) if refs else '-'}")
    zero_refs=sum(1 for r in refs if r==0)
    log.append(f"  (Actors: {zero_refs} null slots / {num})")
    # URL
    proto,p=fstring(body,p); host,p=fstring(body,p); mapn,p=fstring(body,p); portal,p=fstring(body,p)
    opn,p=ci(body,p); ops=[]
    for _ in range(opn):
        s,p=fstring(body,p); ops.append(s)
    port,p=i32(body,p); valid,p=i32(body,p)
    log.append(f"URL: proto={proto!r} host={host!r} map={mapn!r} portal={portal!r} Op={ops} Port={port} Valid={valid}")
    # ULevel tail
    model,p=ci(body,p)
    log.append(f"Model objref = {nm(model)}")
    # ReachSpecs
    rc,p=ci(body,p)
    p_before=p
    specs=[]
    for _ in range(rc):
        dist,p=i32(body,p); start,p=ci(body,p); end,p=ci(body,p)
        cr,p=i32(body,p); ch,p=i32(body,p); fl,p=ci(body,p) if False else i32(body,p)
        pr=body[p]; p+=1
        specs.append((dist,start,end,cr,ch,fl,pr))
    log.append(f"ReachSpecs: count={rc}; first={specs[0] if specs else '-'}")
    if specs:
        avg=(p-p_before)/rc
        log.append(f"  reachspec bytes total={p-p_before} avg/elem={avg:.2f}")
    # 4-byte field (float/int derived)
    fld,p=i32(body,p)
    ffloat=struct.unpack('<f',struct.pack('<i',fld))[0]
    log.append(f"post-ReachSpecs 4byte field = {fld} (asfloat={ffloat!r})")
    # obj-ref this+0x100
    ref100,p=ci(body,p)
    log.append(f"objref(this+0x100) = {nm(ref100)}")
    # 16 obj-refs
    r16=[]
    for _ in range(16):
        r,p=ci(body,p); r16.append(r)
    log.append(f"16 obj-refs (this+0x9c): {[nm(x) for x in r16[:4]]} ... nonzero={sum(1 for x in r16 if x)}")
    # TravelInfo (ver>=63)
    if h['ver']>=63:
        tc,p=ci(body,p)
        pairs=[]
        for _ in range(tc):
            a,p=fstring(body,p); b2,p=fstring(body,p); pairs.append((a,b2))
        log.append(f"TravelInfo pairs: count={tc}; {pairs[:3]}")
    log.append(f"FINAL pos={p} / size={size}  -> {'EOF-EXACT' if p==size else f'DELTA={size-p}'}")
    if p!=size:
        log.append(f"  tail bytes: {body[p:p+32].hex()}")
    if verbose:
        for r in specs[:5]:
            log.append(f"    spec {r}")
    return '\n'.join(log), (p==size)

if __name__=='__main__':
    verbose='--verbose' in sys.argv
    paths=[a for a in sys.argv[1:] if not a.startswith('--')]
    for path in paths:
        try:
            out,ok=walk(path, verbose)
            print("="*70); print(out)
        except Exception as ex:
            import traceback
            print("="*70); print(f"{path}: ERROR {ex}"); traceback.print_exc()
