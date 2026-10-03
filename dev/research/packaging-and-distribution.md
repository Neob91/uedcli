# Packaging, distribution and the cross-platform story for the Rust uedcli

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** How should the shipped artifact be built and distributed, and what platform matrix is
actually required?

## Summary

- **~91 of 124 verbs need nothing but stdin/stdout.** Only **3** touch Docker
  (`level materialize`, `level photo --game`, `substrate stub`); ~33 read the game install off disk.
- **Today's release artifact is one Linux x86_64 tarball from Nuitka**, 127 MB / ~592 linked files,
  built inside a Docker image. A Rust binary replaces it with single-digit MB.
- **One CI workflow exists and it does not run tests.** `old/.github/workflows/build-standalone.yml`
  builds + smoke-tests the standalone on a `v*` tag only; nothing runs `old/bin/test` on a push or
  PR, and the Rust tree has no `.github/`. That gap matters more than the release workflow, since
  the rewrite's correctness argument *is* differential testing against `old/`.
- **The strangler binary is Unix-only by construction** — `src/main.rs` uses
  `std::os::unix::process::CommandExt` for `exec`. Windows is uncompilable until that changes.
- **The no-env-branching rule bites packaging hard**: no feature gate that changes a verb's output,
  no per-target verb set, no "lite/offline" artifact, no install-time host sniffing.
- **musl static linking is safe here.** The glibc-vs-musl breakage is all name resolution and
  `dlopen`; uedcli does neither, and needs no TLS stack. The one real cost is musl's allocator.
- **`dist` (cargo-dist) is alive** (v0.33.0, 2026-09-11) but `uv`, its biggest user, now maintains
  the generated workflow by hand. Four of five comparables are hand-rolled; `jj` is the closest fit.
- **A Claude Code plugin can ship a native binary** — a top-level `bin/` is prepended to the Bash
  tool's PATH. But there is **no post-install script** and **no per-arch asset selection**.
- **`old/uned/` (105 MB committed) and `umodel_win32` do not survive as "ships with the binary".**
  `umodel_win32` **does not exist anywhere in the repo today**; `substrate stub` depends on it.
- **Reproducibility gap:** Cargo's `trim-paths` is still unstable (rust-lang/cargo#12137 open), so
  `--remap-path-prefix` via `CARGO_BUILD_RUSTFLAGS` is the portable lever — and the rewrite is
  validated by byte-for-byte diffs, so this is load-bearing.

## What we have today

Two paths, both Linux x86_64 only.

**Dev path.** `old/bin/build` provisions, `old/bin/uedcli` and `old/bin/test` consume. `old/bin/_venv.sh`
splits them explicitly: `ensure_*` provisions (needs Docker), `check_*` only verifies and fails with
"run old/bin/build first".

| Step | Needs | Produces |
|---|---|---|
| `old/bin/build` | **Docker only** — no host `python3.12` | `.venv/`, the `uedcli_native` wheel pip-installed, `web/src/wasm/`, `web/dist` |
| `old/bin/uedcli` | nothing beyond what is on disk | the CLI host-native via `.venv/bin/python -m uedcli` |
| `old/bin/test` | nothing on disk; Docker for `run_cargo_test` | pytest (4 xdist workers, `--dist=loadfile`) + the Rust goldens |
| `old/bin/ensure_wasm.sh` | Docker | `web/src/wasm/resolve_wasm_bg.wasm` for `web/`'s npm scripts |

The venv's interpreter is `uv`'s managed `python-build-standalone`, fetched inside
`ghcr.io/astral-sh/uv:bookworm-slim`, statically linked with no `libpython.so` dependency; created
with the project bind-mounted at `/io`, so `ensure_venv` rewrites every symlink and shebang back to
the real host path afterward. **`old/dev/docs/dev-runtime.md` is stale here** — it still says "Host
needs only `python3.12` on PATH + Docker"; Docker became the only host tool in commit `162f3505`.

**Release path.** `old/bin/build-standalone` → Nuitka `--mode=standalone --python-flag=-m`
`--static-libpython=yes`, compiled inside `old/dev-container/Dockerfile.nuitka` (which builds a
Python from source without `--enable-shared`, because an arbitrary host 3.12 cannot guarantee
static-libpython capability). Output `dist/standalone/uedcli.dist/` plus a copied `web/dist`, tarred
to `dist/uedcli-<version>-linux-x86_64.tar.gz`. `old/bin/test-standalone` runs it under
`env -i PATH=/usr/bin:/bin` and asserts startup is not >10% slower than the venv launcher.

`old/dist/` **does not exist in a checkout** — gitignored (`/dist/`, leading-slash-anchored), a build
output dir only. The rewrite spec records the rejected use of it: the Rust binary was to shell out to
`old/dist/standalone/uedcli.dist/uedcli`, dropped because the compile takes 20-30 min and ccache keys
on absolute paths so it misses in every worktree.

Two measured facts to carry forward: **127 MB / ~592 linked files**, because Nuitka follows the
static import graph from `main()`, so `PIL`, `fastapi` and `websockets` all land in the binary
despite lazy imports (argparse's dispatch-by-string makes every handler equally reachable at compile
time); and **a locale bug the rewrite deletes** — under `env -i` the compiled binary raised
`UnicodeEncodeError` on the help text's em-dashes, because CPython coerces UTF-8 under a `C` locale
(PEP 538/540) and Nuitka's runtime does not. Rust writes UTF-8 bytes unconditionally.

**The new tree.** `Cargo.toml` is 4 lines; `src/main.rs` 16; `tests/proxy.rs` asserts byte-identity
with `old/bin/uedcli` for `--help` and a failing `class list --flat`. No `rust-toolchain.toml` (the
old Dockerfile installs a floating `stable`), no `.cargo/config.toml`, no `[profile.release]`, no CI.

## Findings

### External runtime dependencies — what is not the binary

| Dependency | Where | How located | Under Wine? | Survives rewrite? | Deleted by |
|---|---|---|---|---|---|
| UnrealEd 2.2 substrate | `old/uned/UED22/`, 105 MB **committed** | `tool_assets.uned_dir()` → `tool_root()/uned`, package-relative via `__file__` | yes — baked into the image, run by `wine`/`FEXBash` | yes, untouched during the rewrite; "removed in a separate, later change" | de-containerizing materialize |
| `docker` + `docker compose` on PATH | host | bare `subprocess.run(["docker", …])` in `old/uedcli/xfer.py`, `preview_game.py`, `editor.py` | n/a | yes — the Rust binary still shells out | same |
| Editor image `ued-x86-runtime:latest` | built locally from `old/uned/docker-compose.yml` `build: context: .` | compose service `uned`, `container_name: dx-lum-uned` | yes | yes | same |
| Game image `uedcli-game` | built locally; `GAME_IMAGE` in `old/uedcli/preview_game.py` | `docker image inspect` | yes | yes | de-containerizing `level photo --game` |
| Deus Ex game assets | `old/uned/DeusExAssets/` (empty, gitignored), `dev/games/` (gitignored) | `~/.uedcli/config.toml` `[games.*]` absolute colon-glob `paths=` | read natively; mounted `:ro` at `/resources/<n>` | **yes, permanently** — copyrighted, never shippable | never; a config contract, not a packaging problem |
| `umodel_win32` | **nowhere — does not exist** | `tool_assets.umodel_dir()` → `tool_root().parent / "umodel_win32"` | yes (x86 Windows exe) | only if given a home | extraction item; `questions/release-and-asset-shipping.md` open |
| v69 stub cache | `~/.uedcli/cache/stubs`, mounted `:ro` at `/stubs` | `config.stub_cache_root()` | consumed by the editor | yes | same as the editor |
| `web/dist` bundle | `old/web/dist` (`web/` source is 1.6 MB) | `old/uedcli/serve/app.py:134` — `parents[2] / "web" / "dist"` | no | yes, as TypeScript | never; becomes an embedded asset |

The `umodel_win32` row is the only one breaking a real code path today.
`old/uedcli/tool_assets.py`'s docstring defers the whole question: "how these assets ship under a
pipx/Nuitka install is the (to-be-respecced) global-CLI packaging item's problem — including the
known `__file__`-inside-a-onefile caveat". In Rust the `__file__` caveat vanishes
(`std::env::current_exe` is reliable); the *question* is untouched and open in two board items.

### "Platform-transparent x86 Windows" — what the item says

From `old/dev/docs/board/to-plan/generic-platform-transparent-x86-windows/spec.md`: one multi-arch
container tag running an x86 Windows program (`DeusEx.exe` or `unrealed.exe`) under wine, choosing
the x86-execution engine by host arch — **FEX + wine-10 on arm64, native wine on amd64**. The motive
is concrete: on arm64 the `linux/amd64` editor runs under qemu-i386, which deterministically GPFs in
`SyntaxHighlighting::AddQuote` during startup, so `level materialize` fails on every arm host.
Spiked: the same `unrealed.exe` under FEX + wine-10 completed engine init and materialized a real
79 KB level to a valid `.dx`.

The load-bearing ruling, quoted in the item: "substrate adaptation under identical logic is not a
fallback and does not violate no-env-switching." The only arch-aware line — a `run_x86` shim,
`FEXBash -c "wine …"` vs `wine …` — lives **inside the image**, never in uedcli.
`old/uned/docker-compose.yml` already carries the `ued-x86-runtime:latest` tag and notes the arm64
variant is built out-of-band. Packaging implications:

1. The binary's arch matrix must cover **`linux-x86_64` + `linux-aarch64`** — the item exists
   because arm64 Linux hosts are real today. macOS/Windows are a separate question it does not touch.
2. Arch dispatch is **not** the binary's job. A `cfg!(target_arch)` in uedcli picking an image tag
   is the violation the ruling carves an exception *around*, not *for*.
3. It makes a container registry an open dependency. The arm64 FEX image is ~35 GB in the spike;
   neither a tarball nor a plugin bundle can carry that. Either images are published (and the binary
   pulls a pinned digest) or every user builds them — and the global-CLI spec names this open: "a
   `pipx`-installed uedcli has no repo, yet the single UED22 image is currently *built* from
   `Tools/uedcli/uned/`. How the installed tool obtains it … is **open**."

### The house rule, and what it forbids in a packaging design

`old/CLAUDE.md` and `old/dev/docs/direction/conventions.md` carry the same rule; the fuller text:

> **Never switch behaviour on the environment.** A verb does the same thing on every host — same code
> path, same engine, same output — or it exits 2 naming what's wrong. Never branch on CPU arch, OS,
> an env var, or the presence/absence of a tool to pick a different implementation. When an approach
> is specified (e.g. a dockerized setup), it is the only path: a missing host tool is a broken host
> to fix, surfaced as a clear error, never a reason to silently keep a host path "in case docker
> isn't there". *(Owner ruling, 2026-08-06.)*

The forbidden-list entry naming it directly: "A second host code path taken when a required tool or
container is absent." `old/bin/build-standalone`'s header already applies it to a build script — the
Nuitka compile is dockerized with "no `--no` fallback (owner ruling, 2026-09-19 … a build that
silently shipped a differently-linked binary depending on host toolchain capability was flagged by
two independent reviews and is not an approved exception)."

In a packaging design this forbids:

- **Cargo features that change verb behaviour or availability** — no build dropping `serve` or the
  renderer. A feature is allowed only where it cannot change output; a musl-allocator swap is the
  boundary case, defensible because it is unobservable.
- **Per-target verb sets** — no "Windows build without `level materialize`"; the verb ships
  everywhere and exits 2 naming the missing thing. Likewise no "lite"/"offline" artifact: the 91
  no-deps verbs and the 3 Docker verbs ship together.
- **Install-time host probing** — a script picking musl vs gnu by sniffing, or falling back to a
  source build when no asset matches, is a second code path. One asset per declared target.
- **Host-dependent linkage** — the Nuitka ruling is precedent; linkage is fixed at build time. And
  no degraded binary when an embedded asset is missing: `web/dist` compiles in or the build fails.

It does *not* forbid the image's internal `run_x86` shim (explicitly ruled an exception), nor
target-specific *build* configuration producing identical behaviour.

### How much of the surface needs nothing

The surface is **124 leaf verbs / 154 parser nodes / 662 flags** over 17 families
(`dev/research/port-order-and-cost-model.md`).

**Docker: 3 verbs.** `level materialize` (`apply.run_materialize` → `editor.ensure_editor` →
`docker compose run`); `level photo` on its default `--game` backend (`docker run` the `uedcli-game`
image); `substrate stub` (`stub.ephemeral_build_container`). `level photo --native` is container-free
by its own help text ("no editor, no container, no game"); `uscript compile`'s module docstring says
"no editor and no docker".

**Game install assets on disk: ~33 verbs**, counted from `resources.class_index` / `mover_index` /
`composed_dirs` / `composed_load_set` / `schema_resolver_for` call sites in `old/uedcli/cli/commands/`:

| Set | Count | Note |
|---|---|---|
| `class` family | 9 | `classes.py:556` builds the index unconditionally in `run()` |
| `texture` family | 9 | `texture.py:24` `_resolver_and_index` likewise |
| `mover_index` sites | 11 | `mover key`, `stash capture`, `event graph`, `level doctor`, `level graph`, `level photo --native`, `brush intersect`, `brush deintersect`, `brush scale`, `brush apply-transform`, `actor survey` |
| `class_index` in `level` | 2 | `level import`, `level reimport` |
| the 3 Docker verbs | 3 | also need the composed paths |
| **distinct total** | **~33** | `level photo` counted once |

**So ~91 of 124 verbs are pure text transforms** — T3D in, T3D out, needing at most a `uedcli.toml`:
the `brush` builder/edit set (29 minus 4), most of `actor` (27 minus 1), all of `sound`, `music`,
`prefab`, `docs`, `cache`, `uscript`, `project`.

One correction: the board item `why-do-seven-verbs-now-require-the-games-config` is **stale on its
own count**. It names seven verbs plus `*preview`; the tree today has 11 `mover_index` labels —
`level graph`, `actor survey` and `level photo --native` were added since. Both its `questions/`
files are open, so the scoping decision is unmade and the number grew meanwhile.

### Rust release tooling

| Tool | Cross-compiles to | Static | Notes |
|---|---|---|---|
| `dist` (cargo-dist) | via its generated native-runner matrix | target-dependent | v0.33.0 (2026-09-11), repo active, not archived. Generates its own `release.yml` plus shell/powershell/npm/homebrew/msi installers, `dist-manifest.json`, per-archive `.sha256` **and** a unified `sha256.sum`, optional `github-attestations`, per-triple `min-glibc-version`, a linkage report. `targets` defaults to none — you list them; 8 supported triples |
| `cross` | 60+ incl. arm, riscv, s390x, android, BSD | yes for musl | needs Docker ≥20.10 or Podman ≥3.4. **No Apple Darwin images** — README says they cannot ship prebuilt macOS images |
| `cargo-zigbuild` | Linux + macOS only | yes | zig as linker; glibc floor via target suffix (`aarch64-unknown-linux-gnu.2.17`); macOS cross needs an `SDKROOT` macOS SDK |
| GH Actions native matrix | n/a | n/a | Free for public repos on standard runners. `ubuntu-24.04`/`-arm`, `macos-15`/`-intel`, `windows-2022`/`-2025`, `windows-11-arm`. Linux arm64 free in public repos since 2025-01-16 (fails in private) |
| `cargo-binstall` | n/a | n/a | Resolves crates.io metadata → GitHub release assets over ~10 filename patterns × 2 path shapes. **Zero config if asset names match the defaults — `dist`'s naming does.** `[package.metadata.binstall]` to override |

Provenance: `actions/attest-build-provenance` binds artifact digest → SLSA v1 in-toto provenance,
Sigstore-signed, verified with `gh attestation verify`; free on public repos, GHEC for private (v4 is
now a thin wrapper over `actions/attest`). GH-hosted runners plus attest lands around SLSA Build L2;
cosign/keyless is redundant with it.

### Static linking: musl is safe for this CLI

The glibc-vs-musl gotcha list is almost entirely name resolution — musl has its own resolver, no NSS
modules, no `nsswitch.conf`, no IDN, ≤3 nameservers, TCP only since 1.2.4
(<https://wiki.musl-libc.org/functional-differences-from-glibc.html>). **uedcli opens no sockets and
resolves no names**, so none of it applies; it never `dlopen`s host plugins either. No TLS stack at
all, so openssl-vs-rustls does not arise (and rustls would avoid the musl+OpenSSL tax if network I/O
is ever added).

- **The allocator is the real cost.** ripgrep's `crates/core/main.rs` says it verbatim: "when
  ripgrep is built with musl, this means ripgrep will use musl's allocator, which appears to be
  substantially worse… Therefore, when building with musl, we use jemalloc", gated
  `#[cfg(all(target_env = "musl", target_pointer_width = "64"))]`. Cost ~200 KB. `oxc` sidesteps the
  `cfg` by using mimalloc on *all* targets — cleaner against the no-env-branching rule.
  **Unverified:** no citable hard musl-vs-glibc malloc multiplier was found; treat "2-10×" as folklore.
- **Prefer musl over `+crt-static` on gnu.** Static glibc is exactly where `getaddrinfo`/NSS
  genuinely breaks (it needs `dlopen`). musl targets are static by default
  (<https://doc.rust-lang.org/reference/linkage.html>); targets that cannot honour `crt-static`
  silently ignore the flag.
- Proc macros and build scripts build for the **host**, so target choice does not affect them; the
  failure mode is a build script compiling C for the target, and uedcli has no C deps today.

### Binary size

min-sized-rust (<https://github.com/johnthagen/min-sized-rust>) has no stable-only measured table —
its 51 KB → 30 KB → 8 KB figures are nightly, macOS, `build-std` + `-Z` flags, on a hello-world, so
not transferable. The stable knobs and their costs:

| Knob | Effect | Cost |
|---|---|---|
| `strip = true` | drops symbols | no backtrace symbols — the main debugging signal for a panic in a shipped verb |
| `opt-level = "z"` / `"s"` | smaller codegen | slower; `"s"` is sometimes *smaller* than `"z"` — measure |
| `lto = "fat"` | cross-crate inlining | long links, worse stack traces |
| `codegen-units = 1` | better optimization | serial codegen, slow builds |
| `panic = "abort"` | no landing pads | **behaviour change**: no `catch_unwind`, `#[should_panic]` tests cannot run in that profile |

ripgrep keeps a custom `release-lto` profile; `jj` ships `strip = "debuginfo", codegen-units = 1`;
ruff uses `lto = "fat"` with `codegen-units = 16` globally and `1` on three hot crates plus a
separate `[profile.minimal-size]`. **Nobody ships `opt-level = "z"` as their main profile.** Against
a 127 MB Nuitka baseline, size is not the constraint — a plain `--release` clap CLI is single-digit MB.

### Reproducible builds

- **`trim-paths` is not stable** — still in the Cargo unstable book
  (<https://doc.rust-lang.org/cargo/reference/unstable.html#profile-trim-paths-option>), tracking
  issue rust-lang/cargo#12137 open. Values `none`, `"macro"`, `"diagnostics"`, `"object"`, `"all"`.
- The portable lever is
  `CARGO_BUILD_RUSTFLAGS="--remap-path-prefix=$PWD=/src --remap-path-prefix=$CARGO_HOME=/cargo"`.
  `RUSTFLAGS` does not apply to host build-script/proc-macro units the same way.
- **Cargo has no `SOURCE_DATE_EPOCH` support** — absent from the reference. *(Unverified as an
  explicit "not supported" statement; it is simply not mentioned.)*
- Pin the toolchain with `rust-toolchain.toml` (the new tree has none), build `--locked`, set
  `CARGO_INCREMENTAL=0` in CI as `jj` does.

Precedent that this bites: the old native-extension build produced a real staleness bug from
mtime-based freshness — `old/bin/_venv.sh` documents a false UNATCO N=116 ladder bail where "six
'different revision' builds all emitted one byte-identical package".

### How comparable tools ship

| Tool | Tooling | Targets | Linux libc | Channels |
|---|---|---|---|---|
| ripgrep | hand-rolled; `cross` for Linux, native for mac/win; `cargo-deb` | 14 | both | brew, choco, scoop, winget, nixpkgs, apt, binstall |
| `jj` | hand-rolled, **native runners only, zero cross** | 6 (`ubuntu-24.04`, `-arm`, `macos-15`, `windows-2022`, `windows-11-arm`) | **musl only** | binstall, brew, winget, scoop, nixpkgs |
| `uv` | `dist` 0.32.0 config, but `release.yml` header says "now maintained manually"; maturin + PGO | 18 incl. riscv64, ppc64le, s390x | both | install script, PyPI wheels, brew |
| `ruff` | hand-rolled maturin matrix, PGO, `manylinux: 2_17` | ~15 | both | PyPI wheels, npm, brew |
| `oxc` | hand-rolled; `cross` + `cargo-zigbuild`; napi-rs | ~18 incl. android, FreeBSD | both | npm, GH release zips |

Only `uv` adopted `dist`, and it has since taken the workflow over by hand.

### Shipping as a Claude Code plugin alongside the binary

Verified against <https://code.claude.com/docs/en/plugins> (the `docs.claude.com` path 301s there)
and its `manifest-reference`, `marketplace-reference`, `components`, `loading`, `skills` pages:

- **A plugin can ship a native binary.** A top-level `bin/` in the plugin root is added to the Bash
  tool's PATH while the plugin is enabled, after the user's own entries so it cannot shadow `git`.
  Must be `chmod +x`. Caveat: claude.ai/Cowork refuse a plugin with a top-level `bin/`.
- **No post-install script.** The `Setup` hook event fires only on `claude --init-only` /
  `-p --init` / `-p --maintenance`, and the docs say a plugin "cannot rely on Setup alone". The
  documented pattern is a `SessionStart` hook or a first-use check in a skill, installing into
  `${CLAUDE_PLUGIN_DATA}` (survives updates). Dependency auto-install exists **only for Node**.
- **No per-arch asset selection** — one `source` per marketplace entry. Multi-arch means a fat
  bundle, a wrapper in `bin/` that picks the binary, or a `command` source that runs a command on the
  user's machine printing an absolute plugin dir (re-running on install/update and once per session;
  admins can disable it via `disableCommandPluginSources`).
- **No mechanism to declare a required external binary** — no `requires`/`engines`/`binaries` field;
  `dependencies` covers other plugins only.
- Layout matches what the skills-plugin board item recorded as owner-decided:
  `.claude-plugin/plugin.json` in the plugin dir, `.claude-plugin/marketplace.json` at the repo root,
  `skills/<name>/SKILL.md`; its note that an installed plugin "runs from a cache and cannot read
  `../` outside the plugin dir" matches the docs' path rules.
- **Versioning:** `version` in `plugin.json` wins over the marketplace entry; if set and unchanged,
  users stay pinned however many commits you push. `claude plugin update` refetches the marketplace,
  not a `git pull`. Auto-update is off by default for third-party marketplaces.

That item's rejected option — "bundling the plugin into the pipx/Nuitka binary (onefile temp-unpack
can't be pointed at)" — is about the reverse direction and moot in Rust. It is `p3`, hard-blocked on
the extraction item.

## Options

| Option | Pros | Cons |
|---|---|---|
| **A. Hand-rolled `release.yml`, native runners only** (`jj` model) | ~80 lines of YAML; no Docker, no `cross`, no cross-compile sysroots; `ubuntu-24.04-arm` and `windows-11-arm` free on public repos; binstall-compatible for free with conventional asset names; full control of profile/flags | you own the YAML; a new target means a new runner; no installer script unless you write one |
| **B. `dist init`** | installers (shell, powershell, brew, msi), checksums + unified `sha256.sum`, attestations, `min-glibc-version`, linkage report, binstall-ready naming — all generated | another tool's lifecycle to track; `uv` took its generated workflow over manually; `targets` must be listed anyway; its workflow is what you'd debug |
| **C. `cross` for everything** | 60+ targets from one Linux runner | needs Docker in CI; **no macOS images**; a second container toolchain to pin on top of `old/uned/`'s |
| **D. `cargo-zigbuild`** | one runner covers Linux + macOS; explicit glibc floor | macOS needs a vendored SDK; no Windows; zig version coupling |
| **E. Tarball only, no installer** | smallest surface; matches the current workflow's shape | no update path; users hand-place a binary |
| **F. Plugin-with-`bin/` as primary channel** | one install gesture for the agent-facing use case | Claude Code only; no per-arch selection; no install hook to check Docker; blocked behind the extraction item |

## Proposal (owner's call — not decided)

**Option A, two targets first, and a PR test gate before any of it.**

1. **The PR CI gate is the prerequisite, not the release workflow.** `cargo test` + `clippy` on
   `ubuntu-24.04`, plus `old/bin/build` + `old/bin/test` so the differential oracle is exercised on a
   runner. Add `rust-toolchain.toml` and `--locked` in the same change so the oracle is pinned.
2. **Matrix: `x86_64-unknown-linux-musl` + `aarch64-unknown-linux-musl`, native runners.** arm64
   Linux is required by the platform-transparent item's own motivation and is free on public repos.
   musl for the reasons above, with mimalloc as the global allocator on **every** target — `oxc`'s
   shape, not ripgrep's `cfg`, so there is no per-target branch to defend against the house rule.
3. **Defer macOS and Windows until the strangler is gone.** `std::os::unix::process::CommandExt`
   makes Windows uncompilable today, and every Docker verb assumes a Linux-ish `docker` CLI. Adding
   those targets now ships a binary where 3 verbs cannot work — fine under the house rule only once
   that error is deliberate and tested.
4. **Checksums + `actions/attest` from the first release** — a few lines, free on a public repo.
5. **Embed `web/dist` in the binary**, which removes the `parents[2] / "web" / "dist"` guessing in
   `old/uedcli/serve/app.py` and makes the artifact a single file.
6. **Keep the plugin channel out of scope** until the extraction item answers its questions.

## Open questions / what to verify next

- Does `old/uned/` ship, download, or stay developer-supplied? Open in two board items'
  `questions/` dirs. The artifact's size and the arm64 FEX image both depend on it.
- Where does `umodel_win32` live? It resolves nowhere today and `substrate stub` depends on it.
- Are `ued-x86-runtime` and `uedcli-game` published to a registry or built by every user? If
  published, the house rule argues for a pinned digest per version, not a drifting tag.
- Is `aarch64` Linux a target host or only a dev machine? The arm64 case rests on a `p2` item.
- Measure, don't assume: build `src/main.rs` `--release` and record the size, then re-measure once
  `clap` and the first ported verbs land. 127 MB is the only measured number in this repo.
- Is a `cfg`-free global allocator (mimalloc everywhere) acceptable, or does the owner read *any*
  target-conditional dependency as an env branch?

## Sources

Internal: `old/bin/{_venv.sh,build,uedcli,test,build-standalone,test-standalone,ensure_wasm.sh}`; `old/.github/workflows/build-standalone.yml`; `old/dev/docs/dev-runtime.md` (stale on `python3.12`-on-PATH); `old/dev/docs/parallel-editors.md`; `old/CLAUDE.md` + `old/dev/docs/direction/conventions.md` (the rule); `old/uedcli/tool_assets.py`, `old/uedcli/serve/app.py`, `old/uned/docker-compose.yml`, `old/pyproject.toml` (empty `package-data`); `old/dev/docs/spikes/2026-09-19-nuitka-standalone-native-ext/spike.md` (127 MB, the locale crash); `dev/research/port-order-and-cost-model.md`; `dev/research/rust-cli-surface-and-argparse-parity.md`. Board items under `old/dev/docs/board/`: `to-plan/rewrite-uedcli-in-rust`, `to-plan/generic-platform-transparent-x86-windows`, `to-plan/uedcli-as-a-global-cli-over-multiple-projects`, `to-spec/extract-uedcli-into-its-own-standalone-git-repo`, `to-spec/skills-plugin-distribution-via-repo-as-its-own`, `to-spec/why-do-seven-verbs-now-require-the-games-config`.

External: <https://github.com/axodotdev/cargo-dist> + <https://axodotdev.github.io/cargo-dist/book/> (status, targets, checksums, attestations, installers, linkage report); <https://github.com/cross-rs/cross> (no Darwin images); <https://github.com/rust-cross/cargo-zigbuild>; <https://github.com/actions/runner-images> (labels); <https://docs.github.com/en/billing/concepts/product-billing/github-actions> (free for public repos); <https://github.blog/changelog/2025-01-16-linux-arm64-hosted-runners-now-available-for-free-in-public-repositories-public-preview/>; <https://github.com/cargo-bins/cargo-binstall/blob/main/SUPPORT.md>; <https://github.com/actions/attest-build-provenance>; <https://slsa.dev/spec/v1.0/levels>; <https://wiki.musl-libc.org/functional-differences-from-glibc.html>; <https://doc.rust-lang.org/reference/linkage.html>; <https://github.com/BurntSushi/ripgrep/blob/master/crates/core/main.rs> (the musl/jemalloc comment); <https://github.com/oxc-project/oxc/blob/main/.github/workflows/release_apps.yml> (mimalloc everywhere); <https://github.com/johnthagen/min-sized-rust>; <https://doc.rust-lang.org/cargo/reference/unstable.html#profile-trim-paths-option>; <https://code.claude.com/docs/en/plugins> + its manifest/marketplace/components/loading/skills pages. Release workflows read directly: ripgrep, `jj`, `uv` (`dist-workspace.toml` + its header), `ruff`, `oxc`.

**Unverified:** any hard musl-vs-glibc malloc multiplier; an explicit Cargo statement that
`SOURCE_DATE_EPOCH` is unsupported (it is simply absent); that a doc page names a compiled binary
bundled in a plugin for MCP `command` specifically (it follows from `${CLAUDE_PLUGIN_ROOT}`
substitution plus the LSP page calling `command` "the language server binary").
