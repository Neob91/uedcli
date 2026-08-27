"""Read wide (UTF-16LE) or ascii strings at VAs in a DLL."""
import sys, re, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pe, rdis

path = rdis.resolve(sys.argv[1])
for a in sys.argv[2:]:
    va = int(a, 16)
    b = pe.read_at_va(path, va, 256)
    m = re.match(rb'(?:[\x20-\x7e]\x00)+', b)
    w = m.group().decode('utf-16le') if m else None
    ma = re.match(rb'[\x20-\x7e]+', b)
    print(hex(va), 'w=%r' % w, 'a=%r' % (ma.group().decode('latin1') if ma else None))
