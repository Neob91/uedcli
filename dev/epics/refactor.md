# The Rust rewrite

uedcli (Python, vibe-coded across many changes of direction, violating YAGNI/DRY throughout) is
being rewritten in Rust, one PR at a time, every PR reviewed by the owner before merge.

## End state

- Python is eliminated entirely — no interpreter, no venv, no PyO3 boundary. The CLI, its argument
  parsing, and the GUI's HTTP backend are all Rust.
- `web/` (the TypeScript/React GUI frontend) stays TypeScript — no Rust rewrite of it — but its
  code is in scope for a refactor too: it's built against the backend this rewrite replaces, and
  was vibe-coded same as the rest. It keeps calling the same `/api/...` surface, served by the new
  Rust backend instead of the old Python one. (Where that refactor happens relative to `old/`'s
  freeze is still open — see `old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/questions/`.)
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

Considered and rejected: embedding a CPython interpreter in the new binary instead (single binary
throughout the migration, but needs `libpython` present, complicates cross-compilation, and needs
the Rust side to manage the GIL) — shelling out is simpler to build and reason about.

Also considered and rejected: a Nuitka-compiled standalone binary for `old/` (verified working —
zero Python/pip/node on the host), in favor of shelling out to `old/bin/uedcli` directly. The
standalone compile is ~20-30 min and its cache doesn't survive across worktrees, so every fresh
worktree needing it would pay that cost from scratch. Trade-off: the dev/migration toolchain now
needs Python+venv+Docker on whoever's host runs it, not just at release time — acceptable, since
`old/` and the whole strangler setup disappear before anything actually ships.

No name is decided yet for the new GUI-backend component — whether it's a separate binary or a
subcommand of `uedcli` is still open, same category as the `web/`-sequencing question above.

## `old/` stays frozen — behavior, not every byte

Every verb's *behavior* is never patched once `old/` lands, for the whole migration — no
exceptions, even for a confirmed real bug. A bug found in `old/` gets a `TODO` in the new Rust
code instead, fixed for real once that verb is properly ported. This is what keeps `old/` a
trustworthy, unchanging oracle for differential testing.

Tooling/dev-infra additions that don't change any verb's behavior (a build script, venv
provisioning) are fine to add directly to `old/` — they don't touch what the oracle relies on.
`old/bin/build` is the current example: provisions the venv, native extension, and web frontend,
with Docker as the only host dependency.

## Testing strategy

- **Differential testing (primary).** For each verb being ported, run both `old/bin/uedcli` and
  the new Rust implementation against identical inputs, diff stdout/exit code/output bytes. Retire
  the `old/` implementation from the dispatch table once a verb passes consistently.
- **Fixture extraction (complementary).** Extract existing golden test cases into data fixtures
  once, so `cargo test` can check them without needing `old/` at all — this is what preserves
  coverage once `old/` is eventually retired.

## Rejected: a shared CLI/GUI registry

Considered for avoiding duplicated brush-builder definitions between the CLI and the GUI — a
generic schema driving both the CLI's flags and GUI form fields. Dropped as more machinery than
the actual ask needed; plain code reuse (both call the same core function) solves it. Revisit only
if the same duplication shows up across enough features to justify a generic mechanism.

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

The complete spec, including the open questions, lives at
`old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/spec.md` (frozen alongside the rest of `old/`,
but still the authoritative record of every decision behind this plan).
