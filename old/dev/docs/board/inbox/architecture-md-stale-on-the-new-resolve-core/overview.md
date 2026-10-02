+++
priority = "p3"
kind = "docs"
summary = "architecture.md stale on the new resolve-core/resolve-wasm workspace split"
+++

# architecture.md stale on the new resolve-core/resolve-wasm workspace split

`dev/docs/architecture.md`'s "Native CSG core" section (`:1618-1651`) describes `uedcli-native/`
as a single PyO3 crate. As of `shared-rust-core-for-class-schema-resolution`
(dev/docs/board/done/), the Rust workspace has three members — the original `uedcli-native`,
a new pure-compute `resolve-core` crate, and a new `resolve-wasm` crate exposing the same core to
a browser consumer via wasm-bindgen. The doc doesn't mention any of this.

Found by the final whole-branch review for that board item. `dev/docs/` edits need the owner's
explicit yes (not the board's own agent-operated exception), so this is filed here rather than
edited directly — flagging it for the owner to review, not proposing exact replacement text yet.
