"""Parse an Unreal Engine 1 (DeusEx, ver 69) package header: Names + Imports.

Authoritative dependency extraction: the Import table's FObjectImport
records name the package that every imported object (incl. actor classes,
meshes, textures, sounds) comes from.
"""
import struct, sys

def read_compact_index(buf, pos):
    # FCompactIndex: signed, variable length. UE1 format.
    b = buf[pos]; pos += 1
    neg = b & 0x80
    val = b & 0x3f
    if b & 0x40:
        shift = 6
        while True:
            b = buf[pos]; pos += 1
            val |= (b & 0x7f) << shift
            shift += 7
            if not (b & 0x80):
                break
    if neg:
        val = -val
    return val, pos

def read_name(buf, pos):
    # ver>=64: signed compact-index length, then string incl null terminator,
    # then u32 object flags. A NEGATIVE length means a UTF-16LE (Unicode) string
    # of -length code units (DeusEx maps carry Unicode Group names, e.g.
    # 20_AireGardens.dx); a positive length is ANSI of that many bytes.
    length, pos = read_compact_index(buf, pos)
    if length < 0:
        nbytes = (-length) * 2
        s = buf[pos:pos+nbytes].decode('utf-16-le', 'replace').split('\x00', 1)[0]
    else:
        nbytes = length
        s = buf[pos:pos+nbytes].split(b'\x00', 1)[0].decode('latin-1')
    pos += nbytes
    pos += 4  # u32 object flags
    return s, pos

def parse(path):
    buf = open(path, 'rb').read()
    tag, ver_l, flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = struct.unpack_from('<9I', buf, 0)
    assert tag == 0x9e2a83c1, "bad magic %08x" % tag
    ver = ver_l & 0xffff

    # Names
    names = []
    pos = nameoff
    for _ in range(namecnt):
        s, pos = read_name(buf, pos)
        names.append(s)

    # Imports: FObjectImport = ClassPackage(FName idx), ClassName(FName idx),
    # PackageIndex(int32), ObjectName(FName idx)
    imports = []
    pos = impoff
    for _ in range(impcnt):
        cls_pkg_i, pos = read_compact_index(buf, pos)
        cls_name_i, pos = read_compact_index(buf, pos)
        pkg_idx = struct.unpack_from('<i', buf, pos)[0]; pos += 4
        obj_name_i, pos = read_compact_index(buf, pos)
        imports.append((cls_pkg_i, cls_name_i, pkg_idx, obj_name_i))
    return ver, names, imports

def name_of(names, i):
    return names[i] if 0 <= i < len(names) else '<%d>' % i

if __name__ == '__main__':
    path = sys.argv[1]
    ver, names, imports = parse(path)
    print("== %s ver=%d names=%d imports=%d ==" % (path, ver, len(names), len(imports)))
    print("--- IMPORT TABLE ---")
    for cp, cn, pi, on in imports:
        print("  ClassPkg=%-12s Class=%-16s PkgIdx=%-4d Obj=%s" % (
            name_of(names, cp), name_of(names, cn), pi, name_of(names, on)))

def resolve_packages(names, imports):
    """Top-level package of every import, by walking PackageIndex to the root.

    PackageIndex encoding (UE object refs): 0 = none/root; negative n means
    import entry (-n - 1); positive would be an export (never a package owner
    for an import's outer chain at top level). The root import (PkgIdx==0) is
    itself a top-level package (ClassName 'Package'); its ObjectName is the
    package name we must ensure-load.
    """
    pkgs = set()
    for cp, cn, pi, on in imports:
        idx = (cp, cn, pi, on)
        # Walk up the outer chain.
        cur = idx
        guard = 0
        while True:
            guard += 1
            if guard > 64:
                break
            c_cp, c_cn, c_pi, c_on = cur
            if c_pi == 0:
                # top-level: this import IS a package (or a root object); the
                # package name is its ObjectName.
                pkgs.add(name_of(names, c_on))
                break
            elif c_pi < 0:
                parent = -c_pi - 1
                if 0 <= parent < len(imports):
                    cur = imports[parent]
                else:
                    break
            else:
                # positive => export in THIS package; not an external dep.
                break
    return pkgs
