+++
priority = "p2"
kind = "implement"
summary = "Split CLI parsing and command orchestration out of the two composition hotspots"
+++

# Reorganize the command layer

Split `cli.py` and `dispatch.py` by command family without changing the CLI or moving the stable
model, package, editor, or native cores.
