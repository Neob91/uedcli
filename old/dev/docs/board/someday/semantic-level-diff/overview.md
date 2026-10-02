+++
priority = "p?"
kind = "unknown"
summary = "Semantic `level diff` (worktree or `--git A..B`)"
+++

# Semantic `level diff` (worktree or `--git A..B`)

Instead of raw per-file T3D diffs:
"3 actors added, Keep_a3 moved +128Y, 12 faces retextured, light L_4 brightness 40→120, brush
Wall_x2 geometry changed". Reads two trunk states (git refs or dirs) and classifies per-actor
changes — the review surface for level PRs, and the digest an LLM wants before merging. Optional:
emit a before/after preview shot pair. (AI brainstorm 2026-07-16.)
