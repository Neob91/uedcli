import sys, struct
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
import pe

UED = __import__("os").path.normpath(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "..", "..", "..", "..", "uned", "UED22"))
DLLS = {"Engine": f"{UED}/Engine.dll", "Editor": f"{UED}/Editor.dll", "Core": f"{UED}/core.dll"}
path = DLLS.get(sys.argv[1], sys.argv[1])
target = int(sys.argv[2], 16)
p = pe.load(path)
base = p.OPTIONAL_HEADER.ImageBase
if target < base:
    target += base
data = p.__data__
# direct E8/E9 rel32 calls in .text
for sec in p.sections:
    name = sec.Name.rstrip(b'\0').decode()
    off, size = sec.PointerToRawData, sec.SizeOfRawData
    va0 = base + sec.VirtualAddress
    blob = bytes(data[off:off + size])
    for i in range(len(blob) - 5):
        if blob[i] in (0xE8, 0xE9):
            rel = struct.unpack_from('<i', blob, i + 1)[0]
            if va0 + i + 5 + rel == target:
                print(f"{name} call/jmp at {va0+i:#010x}")
    # absolute dword refs
    for i in range(0, len(blob) - 4):
        if struct.unpack_from('<I', blob, i)[0] == target:
            print(f"{name} dword ref at {va0+i:#010x}")
