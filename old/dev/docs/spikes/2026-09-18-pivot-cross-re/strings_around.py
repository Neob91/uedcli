import sys, re
P = sys.argv[1]
off = int(sys.argv[2], 16)
n = int(sys.argv[3]) if len(sys.argv) > 3 else 25
data = open(P, "rb").read()
runs = [(m.start(), m.group().decode("utf-16le"))
        for m in re.finditer(rb'(?:[\x20-\x7e]\x00){2,}', data)]
idx = min(range(len(runs)), key=lambda i: abs(runs[i][0] - off))
for o, s in runs[max(0, idx - n): idx + n]:
    mark = " <<<" if o == runs[idx][0] else ""
    print(f"{o:#x}  {s!r}{mark}")
