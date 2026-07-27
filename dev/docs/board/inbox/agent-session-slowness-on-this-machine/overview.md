+++
priority = "p2"
kind = "chore"
summary = "Agent-session slowness on this machine is HARDWARE-bound — measured 2026-07-25"
+++

# Agent-session slowness on this machine is HARDWARE-bound — measured 2026-07-25

Diagnosis run at Andrzej's request ("code review and coding tasks are extremely slow"). The box is
an **Intel i5-2400, 4 cores, no SMT**; 7.7 GiB RAM with **167 MiB free** and **1.9 of 2.0 GiB swap
consumed**; **five concurrent `claude` processes** at 1.9 GB RSS combined (two of them idle for 9 h
and 1 h 49 m). Subagent concurrency is therefore `min(16, cores - 2)` = **2**. The gate headcount
was cut to match (decision 2026-07-25 18:42 UTC); the rest is unaddressed and needs Andrzej's call
because it is machine/repo-shape work, not tool work:
1. **Idle sessions hold RAM and reviewer slots** — closing the two long-idle ones frees ~860 MB and
   two-thirds of the concurrency. No code change; a habit.
2. **Root-level `rg` costs 3.6 s per search, vs 0.16 s excluding the binary-heavy dirs** (22×).
   Cause: ~500 MB of **tracked** blobs in the search path — `Temp/downtown_export*.t3d` (24 MB
   each), **three copies** of the 25 MB UED22 packages (`Tools/uedcli/uned/UED22/`, `Extra/UED22/`,
   `Extra/UED22_COPY/`), `Maps/20_Downtown.dx` (18 MB), `Textures/*.utx`. `.gitignore` cannot help
   (they are tracked). Fix: a repo `.ignore` (ripgrep-only, does not affect git or the build).
   Separately: is `Extra/UED22_COPY/` needed at all? Three tracked copies of the same 60 MB look
   accidental and they are a large part of the 3.2 GiB pack. **Deleting tracked files is Andrzej's
   call.**
3. **698 MB of session transcripts** for this project alone (43 sessions, largest single file
   82 MB), plus 134 MB of `~/.claude/file-history`. Pruning speeds session resume but discards
   history — **Andrzej picks what to keep.**
4. **2 GiB of swap for 7.7 GiB of RAM with five agents is undersized** — more RAM / zram / fewer
   concurrent sessions. Machine change, outside the repo.
