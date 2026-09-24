+++
priority = "p3"
kind = "chore"
summary = "One #10 commit (`6c3df18bd`) leaves the tree red"
+++

# One #10 commit (`6c3df18bd`) leaves the tree red

It landed the `--png` deletion in
`cli.py`/`dispatch.py`/`preview.py` without the test updates, which came in the next commit
(`631617888`), so `bin/test` fails at that commit and `git bisect` across the range is broken. It
was split that way only because a stream watchdog fired mid-task and the in-flight work had to be
committed immediately to avoid losing it. Not repaired because that would mean rewriting published
history, which is forbidden; the branch is squash-merged, so the red intermediate does not reach
`uedcli-impl`. Recorded so the "each commit lands green" rule is not silently eroded.
