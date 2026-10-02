"""Decode a ULevel export's serial body from a real .dx to settle on-disk layout.

Walks: UObject tagged-property list (terminated by 'None') -> Actors array
(count encoding?) -> FURL -> ULevel tail (Model ref, ReachSpecs, ...).

Usage: decode_level.py <path.dx>
"""
import struct, sys

MAGIC = 0x9E2A83C1

def ci(buf, pos):
    b = buf[pos]; pos += 1
    neg = b & 0x80; val = b & 0x3F
    if b & 0x40:
        shift = 6
        while True:
            b = buf[pos]; pos += 1
            val |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
    return (-val if neg else val), pos

def u32(buf, pos): return struct.unpack_from('<I', buf, pos)[0], pos+4
def i32(buf, pos): return struct.unpack_from('<i', buf, pos)[0], pos+4

def parse_header(buf):
    tag, verl, flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
        struct.unpack_from('<9I', buf, 0)
    assert tag == MAGIC, hex(tag)
    return dict(ver=verl & 0xFFFF, lic=verl>>16, namecnt=namecnt, nameoff=nameoff,
                expcnt=expcnt, expoff=expoff, impcnt=impcnt, impoff=impoff)

def read_name(buf, p, ver):
    # UE1: v>=64 uses length-prefixed (ci) string; older uses NUL-terminated.
    if ver >= 64:
        length, p = ci(buf, p)
        if length < 0:
            nb = (-length)*2
            s = buf[p:p+nb].decode('utf-16-le','replace').split('\x00',1)[0]
        else:
            nb = length
            s = buf[p:p+nb].split(b'\x00',1)[0].decode('latin-1')
        p += nb
    else:
        e = buf.index(b'\x00', p)
        s = buf[p:e].decode('latin-1'); p = e+1
    flags, p = u32(buf, p)
    return s, p

def parse_names(buf, h):
    names=[]; p=h['nameoff']
    for _ in range(h['namecnt']):
        s,p = read_name(buf,p,h['ver'])
        names.append(s)
    return names

def parse_imports(buf, h, names):
    imps=[]; p=h['impoff']
    for _ in range(h['impcnt']):
        cls_pkg, p = ci(buf,p)     # ClassPackage (name idx)
        cls_name, p = ci(buf,p)    # ClassName (name idx)
        pkg_idx, p = i32(buf,p)    # PackageIndex (obj ref)
        obj_name, p = ci(buf,p)    # ObjectName (name idx)
        imps.append((cls_pkg, cls_name, pkg_idx, obj_name,
                     names[obj_name] if obj_name<len(names) else '?',
                     names[cls_name] if cls_name<len(names) else '?'))
    return imps

def parse_exports(buf, h, names):
    exps=[]; p=h['expoff']
    for _ in range(h['expcnt']):
        cls_idx, p = ci(buf,p)
        super_idx, p = ci(buf,p)
        pkg_idx, p = i32(buf,p)
        name_idx, p = ci(buf,p)
        flags, p = u32(buf,p)
        size, p = ci(buf,p)
        off = 0
        if size>0:
            off, p = ci(buf,p)
        exps.append(dict(cls=cls_idx, sup=super_idx, pkg=pkg_idx, name_idx=name_idx,
                         name=names[name_idx] if name_idx<len(names) else '?',
                         flags=flags, size=size, off=off))
    return exps

def objref_name(idx, exps, imps, names):
    if idx>0:
        e=exps[idx-1]; return f"exp#{idx}:{e['name']}({classname(e,exps,imps,names)})"
    if idx<0:
        im=imps[-idx-1]; return f"imp#{-idx}:{im[4]}({im[5]})"
    return "None(0)"

def classname(e, exps, imps, names):
    ci_=e['cls']
    if ci_==0: return "Class"
    if ci_<0: return imps[-ci_-1][4]
    return exps[ci_-1]['name']

def main(path):
    buf=open(path,'rb').read()
    h=parse_header(buf)
    print(f"ver={h['ver']} lic={h['lic']} names={h['namecnt']} imps={h['impcnt']} exps={h['expcnt']}")
    names=parse_names(buf,h)
    imps=parse_imports(buf,h,names)
    exps=parse_exports(buf,h,names)
    none_idx = names.index('None') if 'None' in names else -1
    print(f"'None' name idx = {none_idx}")
    # find Level export (class name == 'Level')
    levels=[i for i,e in enumerate(exps) if classname(e,exps,imps,names)=='Level']
    print("Level exports:", [(i+1, exps[i]['name'], exps[i]['size'], hex(exps[i]['off'])) for i in levels])
    if not levels:
        return
    li=levels[0]; e=exps[li]
    off=e['off']; size=e['size']
    body=buf[off:off+size]
    print(f"\n=== Level exp#{li+1} '{e['name']}' off={off:#x} size={size} ===")
    print("first 64 bytes:", body[:64].hex())
    pos=0
    # UObject::Serialize tagged property list: expect immediate 'None' terminator
    tag, pos = ci(body,pos)
    print(f"[+0] first tag name idx (ci) = {tag} -> name='{names[tag] if 0<=tag<len(names) else '?'}'  (None={none_idx})")
    if tag != none_idx:
        print("  NOTE: level has tagged properties before None; not walking props here")
        return
    print(f"  property list terminated by None at body offset {pos}")

    # ULevelBase: Actors TTransArray. Non-trans path: try both encodings.
    p_ci = pos
    cnt_ci, after_ci = ci(body, p_ci)
    cnt_i32, after_i32 = i32(body, pos)
    print(f"\n[Actors count] as compact-index = {cnt_ci} (consumes {after_ci-pos}B)")
    print(f"[Actors count] as raw int32     = {cnt_i32} (consumes 4B); next int32 = {struct.unpack_from('<i',body,pos+4)[0]}")

    # Heuristic: decode assuming raw int32 count, then N object refs (compact index each).
    for label, count, start in [("int32", cnt_i32, pos+4), ("int32x2", cnt_i32, pos+8), ("ci", cnt_ci, after_ci)]:
        try:
            q=start; ok=True; refs=[]
            for k in range(min(count, 6)):
                r,q = ci(body,q); refs.append(r)
            print(f"\n  assuming count-enc={label}: count={count}, first refs={refs}")
            print(f"    -> {[objref_name(r,exps,imps,names) for r in refs]}")
        except Exception as ex:
            print(f"  {label}: ERR {ex}")

if __name__=='__main__':
    main(sys.argv[1])
