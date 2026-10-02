"""render.dll-aware wrapper around adis_iat: PE info, export lookup, disasm.

Usage:
  python3 rdis.py info <dll>
  python3 rdis.py exports <dll> [substr]
  python3 rdis.py dis <dll> <va-or-rva> [len]
  python3 rdis.py vt <dll> <va> [count]
"""
import sys, struct, os, datetime, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pe, adis_iat

UED = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "..", "..", "..", "..", "uned", "UED22"))
DLLS = {"Engine": f"{UED}/Engine.dll", "Editor": f"{UED}/Editor.dll",
        "Core": f"{UED}/core.dll", "Render": f"{UED}/render.dll"}


def resolve(name):
    return DLLS.get(name, name)


def main():
    cmd = sys.argv[1]
    path = resolve(sys.argv[2])
    if cmd == "info":
        o = pe.load(path)
        print("path", path)
        print("stamp", datetime.datetime.utcfromtimestamp(o.FILE_HEADER.TimeDateStamp))
        print("linker", o.OPTIONAL_HEADER.MajorLinkerVersion, o.OPTIONAL_HEADER.MinorLinkerVersion)
        print("base", hex(o.OPTIONAL_HEADER.ImageBase))
        for s in o.sections:
            print(" sec", s.Name.rstrip(b"\0").decode(), hex(s.VirtualAddress), hex(s.Misc_VirtualSize))
    elif cmd == "exports":
        sub = sys.argv[3] if len(sys.argv) > 3 else ""
        for n, r in sorted(pe.exports(path).items(), key=lambda kv: kv[1]):
            if sub in n:
                print(hex(r), hex(r + pe.image_base(path)), n)
    elif cmd == "dis":
        rva = int(sys.argv[3], 16)
        base = pe.image_base(path)
        if rva >= base:
            rva -= base
        n = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x400
        adis_iat.disone(path, rva, n)
    elif cmd == "vt":
        va = int(sys.argv[3], 16)
        cnt = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x40
        base = pe.image_base(path)
        rev = {}
        for name, rva in pe.exports(path).items():
            rev.setdefault(rva, name)
        b = pe.read_at_va(path, va, cnt * 4)
        for i in range(cnt):
            v = struct.unpack_from("<I", b, i * 4)[0]
            print(f"{va+i*4:#010x} [+{i*4:#x}] {v:#010x} {rev.get(v-base,'')}")


if __name__ == "__main__":
    main()
