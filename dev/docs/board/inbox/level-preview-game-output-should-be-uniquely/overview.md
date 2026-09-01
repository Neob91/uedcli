+++
priority = "p3"
kind = "implement"
summary = "level preview --game output should be uniquely named (content hash)"
+++

# level preview --game output should be uniquely named (content hash)

`level preview --game` writes fixed names (`shot-01.png`, `shot-02.png`, …) into `--out-dir`,
overwriting on every run. Owner would expect each render to save under a **different name each time,
ideally a hash of something** — e.g. the build/pose content hash — so:

- successive renders don't silently overwrite each other,
- you can tell two renders apart, and a same-inputs render is recognisably the same file,
- a stale/cached render is obvious (the name wouldn't change when it should, or would collide when it
  shouldn't). Pairs with [[level-preview-game-can-serve-a-stale-cached]].

Suggested: derive the filename stem from a hash of (trunk content hash + camera pose + size), so the
name encodes exactly what produced the frame. Keep an explicit `;name:STEM` override (already
supported) for callers that want a stable path.

**Why it matters:** a content-addressed output name makes renders cacheable, comparable, and
non-clobbering, and turns "did my change take?" into a filename diff.
