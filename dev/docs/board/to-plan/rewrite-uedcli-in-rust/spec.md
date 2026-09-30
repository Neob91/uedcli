# Spec: rewrite uedcli in Rust

## Goal

Replace the current Python `uedcli/` + TS `web/` + partial Rust `uedcli-native/` codebase with a
single Rust implementation, built up PR by PR, every PR reviewed by the owner before merge. Not a
mechanical port — a from-scratch rebuild that the owner controls line by line.

## End state

- Python is eliminated entirely: no interpreter, no venv, no PyO3 boundary. The CLI, its argument
  parsing, and the GUI's HTTP backend are all Rust.
- `web/` (the TypeScript/React GUI frontend) is unaffected in **language** — it stays TypeScript, no
  Rust rewrite of it. Its code is still in scope for a refactor as part of this effort, and it keeps
  calling the same `/api/...` surface, served by the new Rust backend instead of `uedcli/serve/`.
  What that refactor covers and why: see `questions/web-refactor-scope.md`.
- `uned/` (the Docker/Wine UnrealEd harness) is untouched. It stays until uedcli is feature-complete
  under the new implementation, then gets removed in a separate, later change.

## Scope

In scope: everything under the current `uedcli/` package (CLI, dispatch, T3D/model logic, the
editor driver, the offline package/schema decoders), including `uedcli/serve/` (the GUI's HTTP
backend). Also in scope: a refactor of `web/`'s own code — but as a TypeScript refactor, not a
language rewrite; see `questions/web-refactor-scope.md` for what that covers.

Out of scope for this rewrite: `uned/` (infra, untouched until later removal).

## Repo restructure

Everything currently at the repo root — `uedcli/`, `uedcli-native/`, `web/`, `uned/`, `docs/`,
`dev/docs/` (board, direction, rationale, rules, spikes, unrealed — all of it), `CLAUDE.md`,
`README.md`, `.github/`, all of it — moves into `old/` in one commit. Nothing is deleted; git
history keeps it all, and `old/dev/docs/...` stays readable forever for reference.

The new root starts genuinely empty. `uedcli-native` (the existing Rust CSG/BSP/lighting/paths
code) is **not** carried over or extended in place — it goes into `old/` with everything else. Any
of its logic that's worth keeping gets reintroduced deliberately, as its own reviewed PR, same as
everything else. Nothing lands in the new tree without a PR the owner has reviewed.

The new Rust binary is named `uedcli` (the name is free once the Python package moves out of the
way), matching what people already type.

## Migration technique: subprocess strangler

The new `uedcli` binary has a per-verb dispatch table. A ported verb calls the new Rust
implementation directly. An unported verb shells out to `old/`'s compiled binary
(`old/dist/standalone/uedcli.dist/uedcli`, produced by the existing `bin/build-standalone` —
already a single command that builds the Rust native extension, the web frontend, and a Nuitka
standalone Python compile into one binary with no system Python/pip/node dependency; verified
working end to end: moved to `/tmp`, run with a stripped `PATH`, booted the real GUI and served a
legitimately-imported real level). Argv, stdin, stdout, and exit code pass through unchanged. This
means the new tool never needs Python, a venv, or npm on the host — only the prebuilt `old/`
artifact.

Same idea on the GUI side: the new backend's unported API routes proxy to `old/`'s HTTP server. (No
name is set yet for the new GUI-backend component — whether it's a separate binary or a subcommand
of `uedcli` is undecided.)

## Review discipline

Every PR that lands code in the new tree is reviewed by the owner before merge. This applies
uniformly — a freshly written verb and a verb ported near-verbatim from `old/` both go through
review as their own PR. Nothing is grandfathered in.

## `old/` stays frozen

`old/` is never patched once PR #0 lands it, for the whole migration — no exceptions, even for a
confirmed real bug found in its behavior. If a real bug turns up in `old/` during the migration, it
is not fixed there; instead, a `TODO` comment describing the bug is added at the relevant point in
the new Rust codebase, so it's tracked rather than silently inherited or forgotten, and gets fixed
for real once that verb is properly ported (not papered over in the code being phased out).

## Rejected: a shared CLI/GUI registry

Considered and dropped. The original ask was narrower than it first sounded: avoid duplicating
brush-builder definitions between the CLI surface and the GUI. A generic schema-driven registry
(auto-deriving both the CLI's flags and GUI form fields from one declarative definition) was scoped
out as more machinery than a single feature needs — plain code reuse (the CLI handler and the GUI
handler both call the same core function) solves the actual problem. Revisit only if the same
duplication concern recurs across enough features to justify the fixed cost of a generic mechanism.

## Testing strategy

Two complementary methods, confirmed. Neither requires shipping Python in the final binary
(test-time and runtime dependencies are separate):

- **Differential testing (primary).** For each verb being ported, run both `old/`'s compiled binary
  and the new Rust implementation against identical inputs and diff stdout/exit code/produced T3D
  bytes. As a verb passes consistently, retire its `old/` implementation from the dispatch table.
  Catches drift on arbitrary new inputs, not just recorded ones. Depends on `old/` staying a
  trustworthy, unchanging oracle — see "`old/` stays frozen" above.
- **Fixture extraction (complementary).** Extract the existing golden test input/expected-output
  pairs (T3D golden files, byte-parity captures) into data fixtures once, then point `cargo test` at
  the same fixtures — no live `old/` binary needed at test time, but only covers cases someone
  already thought to test. This is what preserves coverage once `old/` is eventually retired and
  there's nothing left to differential-test against.

## Bootstrap sequence (walking skeleton)

1. **PR #0 — the `old/` move.** Move everything to `old/`. Run `bin/build-standalone` inside
   `old/` to produce the compiled binary the new skeleton will shell out to.
2. **PR #1 — bootstrap.** A minimal Rust `uedcli` binary that does nothing but subprocess-strangle:
   every verb proxies to `old/`'s compiled binary. Proven against a couple of real verbs that
   proxying is byte-identical to running `old/` directly — a sanity check on the plumbing itself,
   distinct from the differential-testing methodology above, which applies once real porting starts.
3. **PR #2 — first vertical slice.** Pick one small, self-contained, low-dependency verb — a single
   brush builder is a good candidate (pure function, no editor, no git-trunk I/O) — and port it end
   to end for real, proven via differential testing against `old/`. This validates the whole shape
   (arg parsing → model → emit → dispatch) before scaling to more verbs.
4. **Every PR after that**: one verb (or a tight cluster) at a time, same pattern — port,
   differential-test against `old/`, retire that verb from `old/`'s dispatch table once proven.
