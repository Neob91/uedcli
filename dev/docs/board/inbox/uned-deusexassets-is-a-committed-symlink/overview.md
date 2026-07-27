+++
priority = "p2"
kind = "owner-question"
summary = "`uned/DeusExAssets` is a COMMITTED symlink to a machine-specific absolute path, and it breaks the asset setup on any other machine"
+++

# `uned/DeusExAssets` is a COMMITTED symlink to a machine-specific absolute path, and it breaks the asset setup on any other machine

`git ls-files -s uned/DeusExAssets`
reports mode `120000` — it is tracked, not gitignored — pointing at
`/home/neob91/Games/LutrisDX/drive_c/DX`. On a checkout where that path does not exist the symlink
dangles, so the whole substrate tree silently looks *absent*: every corpus-dependent test skips and
`install-deusex-assets.sh` used to die with a bare `mkdir: File exists`. Cost a real session's
confusion on 2026-07-27 — the retail maps were reported missing when in truth only the symlink
target was.
Two things are wrong independently: (a) `deusex-assets-setup.md` states `uned/DeusExAssets/` is
"gitignored and never committed", which the symlink itself contradicts; (b) a personal absolute path
is baked into shared history. **Your call which way:** gitignore the symlink so each machine makes
its own (and drop it from the index), or keep the real directory and let the script populate it.
Mitigated but not fixed: the script now names a dangling target instead of failing obscurely.
*(2026-07-27.)*
