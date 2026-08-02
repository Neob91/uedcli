+++
priority = "p3"
kind = "implement"
summary = "`stash capture -` (stdin)"
+++

# `stash capture -` (stdin)

Done: `stash capture -` reads a stdin T3D snippet as the source (remaining names subset it);
`--from-t3d` is files-only, the `--from-t3d -` spelling dropped. Empty stdin exits 2; `-` is mutually
exclusive with `--from-t3d`/`--tree`.
