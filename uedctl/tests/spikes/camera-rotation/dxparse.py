import struct, sys

def read_index(d, o):
    # Unreal compact index (FCompactIndex) signed varint
    b = d[o]; o += 1
    neg = b & 0x80
    val = b & 0x3f
    if b & 0x40:
        shift = 6
        while True:
            b = d[o]; o += 1
            val |= (b & 0x7f) << shift
            shift += 7
            if not (b & 0x80):
                break
    return (-val if neg else val), o

def parse(path):
    d = open(path, "rb").read()
    sig, = struct.unpack_from("<I", d, 0)
    assert sig == 0x9E2A83C1, hex(sig)
    ver, lver = struct.unpack_from("<HH", d, 4)
    flags, = struct.unpack_from("<I", d, 8)
    name_count, name_off = struct.unpack_from("<II", d, 12)
    export_count, export_off = struct.unpack_from("<II", d, 20)
    import_count, import_off = struct.unpack_from("<II", d, 28)
    print(f"ver={ver} lver={lver} names={name_count}@{hex(name_off)} exports={export_count}@{hex(export_off)} imports={import_count}@{hex(import_off)}")
    # Names
    names = []
    o = name_off
    for _ in range(name_count):
        n, o = read_index(d, o)
        s = d[o:o+n-1].decode("latin1"); o += n
        o += 4  # object flags (DWORD)
        names.append(s)
    return d, names, (export_off, export_count), (import_off, import_count), read_index

if __name__ == "__main__":
    d, names, exp, imp, ri = parse(sys.argv[1])
    print("NAMES:", names)
