"""Print any ASCII run around a needle inside a .u package (ScriptText is stored plain ASCII)."""
import re
import sys

data = open(sys.argv[1], 'rb').read()
needle = sys.argv[2].encode()
span = int(sys.argv[3]) if len(sys.argv) > 3 else 900
for m in re.finditer(re.escape(needle), data):
    lo = max(0, m.start() - span)
    print(f"=== hit at 0x{m.start():x} ===")
    print(data[lo:m.start() + span].decode('latin-1'))
    print()
