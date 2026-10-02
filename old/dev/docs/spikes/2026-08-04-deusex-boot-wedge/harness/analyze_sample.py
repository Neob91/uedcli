#!/usr/bin/env python3
"""analyze_sample.py <sample.log> — summarize an instrument_boot.sh sample log to decide
OOM vs deadlock. Reports: peak memory.current vs cap, oom_kill/max event counts, pgmajfault
rate, and whether threads sit blocked (0 cpu-tick delta) in a wait wchan at the end (deadlock)
vs one thread burning cpu with rising major faults (OOM thrash)."""
import re, sys

blocks = open(sys.argv[1]).read().split("=== t=")
samples = []
for b in blocks[1:]:
    t = int(b.split("s", 1)[0])
    cur = int(m.group(1)) if (m := re.search(r"mem\.current=(\d+)", b)) else 0
    cap = int(m.group(1)) if (m := re.search(r"mem\.max=(\d+)", b)) else 0
    ev = dict(re.findall(r"(\w+) (\d+)", re.search(r"mem\.events:(.*)", b).group(1))) if "mem.events:" in b else {}
    pmf = int(m.group(1)) if (m := re.search(r"pgmajfault=(\d+)", b)) else 0
    ll = int(m.group(1)) if (m := re.search(r"loglines=(\d+)", b)) else 0
    threads = re.findall(r"pid=(\d+) tid=(\d+) name=(\S+) state=(\S+) wchan=(\S+) cputicks=(\d+)", b)
    samples.append(dict(t=t, cur=cur, cap=cap, ev=ev, pmf=pmf, ll=ll,
                        threads=[(tid, name, state, wch, int(ct)) for _, tid, name, state, wch, ct in threads]))

if not samples:
    print("no samples"); sys.exit(1)

cap = max(s["cap"] for s in samples)
peak = max(s["cur"] for s in samples)
last = samples[-1]
oom = max(int(s["ev"].get("oom_kill", 0)) for s in samples)
oomgroup = max(int(s["ev"].get("oom", 0)) for s in samples)
maxev = max(int(s["ev"].get("max", 0)) for s in samples)
print(f"samples={len(samples)} window={last['t']}s")
print(f"mem cap        = {cap/2**30:.2f} GiB")
print(f"mem peak       = {peak/2**30:.2f} GiB  ({100*peak/cap:.0f}% of cap)")
print(f"mem final      = {last['cur']/2**30:.2f} GiB")
print(f"events: oom_kill={oom} oom={oomgroup} max(hit-limit)={maxev}")
print(f"loglines final = {last['ll']} (banner wedge if ~21-22)")

# pgmajfault rate over the window
pmf0, pmft = samples[0]["pmf"], last["pmf"]
dur = max(1, last["t"] - samples[0]["t"])
print(f"pgmajfault     = {pmf0} -> {pmft}  (+{pmft-pmf0}, {(pmft-pmf0)/dur:.0f}/s)")

# CPU activity: per-thread tick delta between last two samples
if len(samples) >= 2:
    prev = {tid: ct for tid, _, _, _, ct in samples[-2]["threads"]}
    print(f"\n--- final tick: threads (delta cputicks over last {last['t']-samples[-2]['t']}s) ---")
    active = 0
    for tid, name, state, wch, ct in last["threads"]:
        d = ct - prev.get(tid, ct)
        active += d
        print(f"  tid={tid:<8} {name:<16} state={state:<3} wchan={wch:<24} dticks={d}")
    print(f"\nTotal active cputicks last interval = {active}")

print("\n--- VERDICT HINTS ---")
if oom or oomgroup:
    print("OOM: oom_kill/oom event fired.")
elif peak > 0.97 * cap:
    print(f"MEMORY-BOUND: peak reached {100*peak/cap:.0f}% of cap.")
if last["ll"] <= 23 and last["t"] > 40:
    print("WEDGED at boot banner (log frozen).")
