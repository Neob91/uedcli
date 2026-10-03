# The Rust rewrite

uedcli (Python, vibe-coded across many changes of direction, violating YAGNI/DRY throughout) is
being rewritten in Rust, one PR at a time, every PR reviewed by the owner before merge.

## End state

- Python is eliminated entirely — no interpreter, no venv, no PyO3 boundary. The CLI, its argument
  parsing, and the GUI's HTTP backend are all Rust.
- `web/` (the TypeScript/React GUI frontend) stays TypeScript — no Rust rewrite of it — but its
  code is in scope for a refactor too: it's built against the backend this rewrite replaces, and
  was vibe-coded same as the rest. It keeps calling the same `/api/...` surface, served by the new
  Rust backend instead of the old Python one. (Sequencing — when/where that refactor happens — is
  still open; see `old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/questions/`.)
- `uned/` (the Docker/Wine UnrealEd harness) stays untouched, removed later once uedcli is
  feature-complete under the new implementation.

## The `old/` move

Everything that used to be at the repo root — code, both doc trees (`docs/` and `dev/docs/`),
`CLAUDE.md`, CI config, the lot — moved into `old/` in one commit (git history keeps it all). The
new root started genuinely empty: the existing `uedcli-native` Rust extension wasn't carried over
or extended in place either — every line that lands in the new tree does so through a reviewed PR,
nothing grandfathered in.

## Migration technique: subprocess strangler

The new `uedcli` binary has a per-verb dispatch table. A ported verb calls the new Rust
implementation directly. An unported verb shells out to `old/bin/uedcli` (the existing dev-loop
launcher — it provisions its own venv/native-ext on first use). Argv, stdin, stdout, and exit code
all pass through unchanged.

The new GUI-backend component will be a subcommand of `uedcli`, not a separate binary.

## Editing `old/`

`old/` isn't frozen — it can be patched. The UX isn't fully figured out yet, and real bug/perf
fixes are expected and wanted along the way: the new architecture is one of the primary
motivators for the rewrite, so fixing what it fixes as verbs get ported is the point, not
something to avoid.

Once a verb's logic is fully ported to the new Rust implementation, its `old/` implementation
gets deleted outright — not kept around, not left as dead code (same no-back-compat-cruft rule as
the rest of the CLI).

## Testing strategy

- **Differential testing (primary).** For each verb being ported, run both `old/bin/uedcli` and
  the new Rust implementation against identical inputs, diff stdout/exit code/output bytes. Delete
  the verb's `old/` implementation once it passes consistently.
- **Fixture extraction (complementary).** Extract existing golden test cases into data fixtures
  once, so `cargo test` can check them without needing `old/` at all — this is what preserves
  coverage once `old/` is eventually retired.

## Bootstrap sequence

0. **The `old/` move + the empty root.** Done.
1. **Bootstrap.** A minimal Rust `uedcli` binary that does nothing but subprocess-strangle every
   verb to `old/bin/uedcli`. Done — proven byte-identical against `old/bin/uedcli` directly, for
   both a success and a failure case (`tests/proxy.rs`).
2. **First vertical slice.** Port one small, self-contained, low-dependency verb for real (a
   single brush builder is the current candidate), proven via differential testing. Validates the
   whole shape — arg parsing → model → emit → dispatch — before scaling to more verbs.
3. **Every PR after that**: one verb (or a tight cluster) at a time, same pattern.

## Full detail

The original, more detailed spec (including remaining open questions) lives at
`old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/spec.md`. This file has since diverged from it
on at least one point (`old/` editability) — this file wins where the two disagree.
