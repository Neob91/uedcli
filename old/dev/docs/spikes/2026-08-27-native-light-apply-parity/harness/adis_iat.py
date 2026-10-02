"""Annotated disassembler: exports + IAT import names + float/string consts."""
import sys, struct, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
import pe, pefile

UED = __import__("os").path.normpath(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "..", "..", "..", "..", "uned", "UED22"))
DLLS = {"Engine": f"{UED}/Engine.dll", "Editor": f"{UED}/Editor.dll", "Core": f"{UED}/core.dll"}

_rev, _iat = {}, {}


def revmap(path):
    if path not in _rev:
        m = {}
        for n, rva in pe.exports(path).items():
            m.setdefault(rva, n)
        _rev[path] = m
    return _rev[path]


def iatmap(path):
    if path not in _iat:
        m = {}
        p = pe.load(path)
        if hasattr(p, "DIRECTORY_ENTRY_IMPORT"):
            for mod in p.DIRECTORY_ENTRY_IMPORT:
                dll = mod.dll.decode('latin1')
                for imp in mod.imports:
                    if imp.name:
                        m[imp.address] = f"{dll}!{imp.name.decode('latin1')}"
        _iat[path] = m
    return _iat[path]


def read(path, va, n):
    try:
        return pe.read_at_va(path, va, n)
    except Exception:
        return None


def ann_mem(path, va):
    base = pe.image_base(path)
    if not (base <= va < base + 0x800000):
        return ""
    im = iatmap(path)
    if va in im:
        return "  ; IAT-> " + im[va]
    b = read(path, va, 16)
    if not b:
        return ""
    out = []
    f = struct.unpack("<f", b[:4])[0]
    if abs(f) < 1e9 and (abs(f) > 1e-9 or f == 0.0):
        out.append(f"f32={f:g}")
    m = re.match(rb'(?:[\x20-\x7e]\x00){3,}', b + (read(path, va + 16, 96) or b""))
    if m:
        out.append('w"%s"' % m.group().decode("utf-16le"))
    ma = re.match(rb'[\x20-\x7e]{4,}', b + (read(path, va + 16, 96) or b""))
    if ma:
        out.append('a"%s"' % ma.group().decode("latin1"))
    return ("  ; " + " ".join(out)) if out else ""


def disone(path, rva, length):
    base = pe.image_base(path)
    rv = revmap(path)
    for ins in pe.disasm(path, rva, length):
        line = f"{ins.address:#010x}  {ins.mnemonic:<8}{ins.op_str}"
        ann = ""
        if ins.mnemonic in ("call", "jmp"):
            for op in ins.operands:
                if op.type == 1:
                    tr = op.imm - base
                    if tr in rv:
                        ann = f"   ; -> {rv[tr]}"
        for op in ins.operands:
            if op.type == 3:
                m = op.mem
                if m.base == 0 and m.index == 0 and m.disp:
                    a = ann_mem(path, m.disp & 0xffffffff)
                    if a:
                        ann += a
        print(line + ann)


if __name__ == "__main__":
    path = DLLS.get(sys.argv[1], sys.argv[1])
    rva = int(sys.argv[2], 16)
    b = pe.image_base(path)
    if rva >= b:
        rva -= b
    length = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x600
    disone(path, rva, length)
