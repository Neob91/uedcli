import sys, re
P = sys.argv[1]
pat = sys.argv[2]
data = open(P, "rb").read()
runs = [(m.start(), m.group().decode("utf-16le"))
        for m in re.finditer(rb'(?:[\x20-\x7e]\x00){2,}', data)]
rx = re.compile(pat, re.I)
for i, (off, s) in enumerate(runs):
    if rx.search(s):
        ctx = " | ".join(t for _, t in runs[max(0, i - 2): i + 3])
        print(f"{off:#x}  {s!r}\n        ctx: {ctx}")
