import re, sys

path = sys.argv[1]
pat = sys.argv[2] if len(sys.argv) > 2 else None
data = open(path, "rb").read()

# ASCII strings (C++ symbol/RTTI/debug)
ascii_runs = [m.group().decode("latin1") for m in re.finditer(rb"[\x20-\x7e]{4,}", data)]
if pat:
    rx = re.compile(pat, re.I)
    for s in ascii_runs:
        if rx.search(s):
            print(s)
else:
    for s in ascii_runs:
        print(s)
