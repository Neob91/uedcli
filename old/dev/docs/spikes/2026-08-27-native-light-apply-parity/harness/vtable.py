import sys, struct
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
import pe

UED = __import__("os").path.normpath(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "..", "..", "..", "..", "uned", "UED22"))
DLLS = {"Engine": f"{UED}/Engine.dll", "Editor": f"{UED}/Editor.dll", "Core": f"{UED}/core.dll"}
path = DLLS.get(sys.argv[1], sys.argv[1])
va = int(sys.argv[2], 16)
n = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x40
base = pe.image_base(path)
rev = {}
for name, rva in pe.exports(path).items():
    rev.setdefault(rva, name)
b = pe.read_at_va(path, va, n * 4)
for i in range(n):
    v = struct.unpack_from('<I', b, i * 4)[0]
    print(f"{va+i*4:#010x} [+{i*4:#x}] {v:#010x} {rev.get(v-base,'')}")
