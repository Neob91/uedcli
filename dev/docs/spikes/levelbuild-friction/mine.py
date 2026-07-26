"""Mine subagent transcripts for uedcli friction: failed commands, argparse rejections,
tool errors. Writes a deduped, counted report; prints only a compact summary."""
import json, re, sys, collections, pathlib

SUB = pathlib.Path("/home/neob91/.claude/projects/-home-neob91-Documents-Dev-uedcli/"
                   "33a3c366-0f96-4715-90e3-8a541592d60e/subagents")
OUT = pathlib.Path("/home/neob91/Documents/Dev/uedcli/dev/docs/spikes/levelbuild-friction/raw-mined.txt")

NAMES = {
    "a02dd34e3ce71f9bb": "dive-bar (1st)",
    "aca66d58cb691fa8a": "container-yard (1st)",
    "a3cda8c4927df8578": "tube-platform (1st)",
    "aced3ec150bf3253a": "tube-platform (2nd)",
    "adbbdfc89c1a6eecf": "dive-bar (2nd)",
    "a1867987c3fd8c3bd": "container-yard (2nd)",
    "ac0d18c19b9e183e5": "spike-headless",
}

# Signatures of a uedcli/CLI problem, not general shell noise.
SIG = re.compile(
    r"(unrecognized arguments|invalid choice|error: argument|usage: uedcli|"
    r"Traceback \(most recent call last\)|"
    r"materialize failed|post-verify mismatch|did not complete within|"
    r"is not built|not found:|No such file|refuses to overwrite|"
    r"unknown color|exit code 2|EditorNotReady|EditorBusy|"
    r"did NOT match|nothing written|wedged|SchemaError|"
    r"requires|must be|cannot |Cannot |failed:)", re.I)

# Lines that are pure environment noise, or DOC TEXT the agent merely read
# (Read returns `<lineno>\t<content>`, and docs quote all our error vocabulary).
NOISE = re.compile(r"XGetWindowProperty|^\s*$|Shell cwd was reset|"
                   r"warning: .*deprecat|^\s*at:|^\s*File \"", re.I)
DOCLINE = re.compile(r"^\s*\d+\t")          # a Read() numbered line = documentation, not an error
MARKDOWN = re.compile(r"^\s*[-*>#|]|\*\*")  # prose/bullets/tables from docs or the agent's own writing


def norm(s):
    s = re.sub(r"[0-9a-f]{8}-?[0-9a-f-]{4,}", "<ID>", s)
    s = re.sub(r"_[a-z0-9]{6}\b", "_<RND>", s)
    s = re.sub(r"/[\w./-]{20,}", "<PATH>", s)
    s = re.sub(r"\d+", "N", s)
    return s.strip()[:240]


def texts(msg):
    """Yield all string content out of a transcript message."""
    c = msg.get("message", {}).get("content")
    if isinstance(c, str):
        yield c
    elif isinstance(c, list):
        for b in c:
            if not isinstance(b, dict):
                continue
            if isinstance(b.get("text"), str):
                yield b["text"]
            r = b.get("content")
            if isinstance(r, str):
                yield r
            elif isinstance(r, list):
                for rb in r:
                    if isinstance(rb, dict) and isinstance(rb.get("text"), str):
                        yield rb["text"]


buckets = collections.defaultdict(lambda: collections.Counter())
per_agent = collections.Counter()

for f in sorted(SUB.glob("agent-*.jsonl")):
    aid = f.stem.replace("agent-", "")
    who = NAMES.get(aid, aid)
    with f.open(errors="replace") as fh:
        for line in fh:
            try:
                msg = json.loads(line)
            except Exception:
                continue
            for t in texts(msg):
                for ln in t.splitlines():
                    if (len(ln) > 400 or NOISE.search(ln) or DOCLINE.match(ln)
                            or MARKDOWN.match(ln) or not SIG.search(ln)):
                        continue
                    buckets[norm(ln)][who] += 1
                    per_agent[who] += 1

with OUT.open("w") as out:
    out.write("# Raw mined uedcli friction from subagent transcripts\n")
    out.write("# (deduped + normalised; <ID>/<RND>/<PATH>/N are placeholders)\n\n")
    for sig, who in sorted(buckets.items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(who.values())
        out.write(f"[{tot:4d}x] {sig}\n         agents: {dict(who)}\n")

print("hits per agent:", dict(per_agent))
print("unique signatures:", len(buckets))
print("wrote", OUT)
print("\n--- TOP 45 ---")
for sig, who in sorted(buckets.items(), key=lambda kv: -sum(kv[1].values()))[:45]:
    print(f"{sum(who.values()):4d}x | {sig[:150]}")
