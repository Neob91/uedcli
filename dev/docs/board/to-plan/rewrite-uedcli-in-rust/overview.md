+++
priority = "p?"
kind = "implement"
summary = "Full rewrite of uedcli (CLI + GUI backend) in Rust, strangler-fig migration from a frozen old/"
+++

# Rewrite uedcli in Rust

The current codebase (Python `uedcli/`, TS `web/`, partial Rust `uedcli-native/`) is vibe-coded
across many changes of direction and violates YAGNI/DRY throughout. Owner wants a full rewrite in
Rust, with every PR into the new tree reviewed personally — not a mechanical port done unsupervised.

See `spec.md` for the agreed approach.
