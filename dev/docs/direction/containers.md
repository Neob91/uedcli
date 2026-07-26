# Containers — isolation, and the code/content substrate split

## What we want

A **container** here means a Docker container uedcli starts, drives and throws away in order to run
a Windows program under wine: the **UnrealEd 2.2 editor** (materialize, qualify), the no-GUI **UCC
build container** (stub building, texture batchexport), and the **game container**
(`level preview --game`). uedcli itself never runs in one — that is a separate ruling
([`process.md`](process.md)); this topic is about the containers it *drives*.

### No container writes into the repo tree

Repo pollution is made **structurally impossible, not a convention to remember**. There is no broad
read-write `/repo` bind mount; a container's filesystem is three disjoint domains:

- **Substrate — BAKED into the image**, at its final runtime location. The editor runs straight
  from the baked dir with no boot-time assembly; its own writes (logs, `Running.ini`, `make`
  output) land on the per-container copy-on-write overlay and die with the container.
- **Assets — READ-ONLY bind mounts**, composed per command.
- **Mutable exchange — ONE container-local `/work` dir**, on the writable overlay, crossed only by
  `docker cp`. It dies with the container, so nothing it holds can leak into the tree.

Earlier we repeatedly point-fixed individual seams to write elsewhere; the *capability* remained,
so the next forgotten seam re-polluted the tree. Removing the capability is the whole point.

### One image, one mount scheme, one `Paths` generator

- **One shared UED22 image is the editor for every game.** Nothing about the editor is
  game-specific: a game's content arrives through its configured paths and a game's own code
  arrives as stubs. There is no per-game image key and no user-configurable container name —
  container instances are ephemeral and derived.
- **Every composed config dir is mounted the SAME way** — read-only at `/resources/<n>` — for
  **every** container. `.u`/`.utx`/`.uax`/`.umx`/`.dx` are one package format and the extension is
  convention, not role (a `.u` can hold textures), so there is **no code-vs-content *directory*
  split** and no second, bespoke mount root for code.
- **Being on disk is not enough: a package must be on the engine's search path.** The
  `[Core.System] Paths` list is therefore **regenerated wholesale** by ONE generator over the
  ordered container dirs — including the editor's own substrate, generated like everything else
  rather than preserved by hand. Each line is `<dir>/*.<ext>`, one per directory × extension
  actually present: UE1's `Paths` format requires the extension (a bare `<dir>/*` wedges the editor
  at boot).
- **Safety rests on Paths ORDER, not on a directory split.** The v69 stub cache and the baked
  substrate come first, so a stub **shadows** the same-named game package that a mounted dir puts
  on the path. A v68 package the level references that has **no** stub would demand-load and crash
  the editor, so it is refused up front with a named error before any load.
- **The explicit preload is O(level), not O(install)** ([`materialize.md`](materialize.md)).

### Editor CODE is substrate-authoritative; a game's own code is STUBBED

The editor loads only the UED22 substrate's own version-69 `.u` code. A game whose code the editor
cannot load gets **stubs**: mesh-preserving stand-in packages built on demand from the game's real
`.u` and cached per-user.

- **Why stubs exist: mesh layout and `Engine`/`Core` divergence — NOT the package version.** UED22's
  UCC reads the older packages fine. What it cannot do is *run* code compiled against a different
  `Engine`/`Core` class graph with a different mesh vertex layout. The version numbers are a
  symptom, so "convert v68 → v69" describes the mechanism, not the reason.
- **A stub is EDITOR-facing only, and is never an authority on anything else.** Anything model-side
  — the class-property schema above all — reads the game's **real** packages
  ([`packages.md`](packages.md)).
- **Stubbing is automatic and lazy**, triggered at package resolution rather than by a verb the
  user must remember, and it **fails loudly**: a stub that cannot be built is a named error, never
  a silently broken stub.
- **The stub cache is derived, per-user and never committed** — generated from copyrighted game
  code, it lives with the other per-user caches.
- **Game CONTENT is user-supplied and never committed.** Texture/sound/music packages come from the
  user's own install; uedcli builds, and its offline test suite runs, without them.

### Per-command ephemeral is the concurrency story; warm containers are a fast path

- **Every editor-driving invocation owns its own container by default** — spun up, driven, torn
  down within the one command. Parallelism is then free by construction and no cross-command lock
  exists.
- **The two hot loops get a warm per-user container** in front of that — the game-preview container
  and the editor for `level materialize` — because a cold boot dominates an interactive edit→look
  loop. Reuse is gated on a fingerprint (image + mounts + the mutable packages' stat tuples),
  guarded by a **nonblocking** lock, and **self-terminates when idle**. Any staleness reboots: the
  editor never purges a prior build's loaded objects, so a reused container that quietly built
  against yesterday's package is exactly the failure a fingerprint exists to prevent.
- **Contention falls back; it never queues.**
- **An untrusted container is never left warm**: a warm-mode drive or verify failure tears it down
  before releasing the lock, and the invocation fails with a hint rather than silently retrying.
- **The host talks to a container in as few round-trips as possible** — a batch script run in one
  exec, not a chatty sequence of per-operation calls, and not a long-lived server.

## Rejected

**Isolation**

- **Keeping the `/repo` mount and redirecting writes elsewhere** — leaves the write *capability*
  intact, so the next forgotten seam silently re-pollutes the tree.
- **A tmpfs `/work`** — `docker cp` writes the file *under* the tmpfs mountpoint, on the overlay,
  where it is shadowed and invisible to a live `exec` (verified live).
- **Copying content packages in per-package to a `/work` sub-tree** — read-only mounts reuse the
  existing path remap with near-zero change and cost no per-boot copy.
- **Keeping the boot-time symlink-farm assembly** — pure overhead once there is no `/repo` mount.

**Images, mounts and search paths**

- **A per-game editor image**, or a built-in default image per game — implies each game needs its
  own editor build; it does not.
- **A configured container name** — with one image and derived instances there is nothing to select.
- **Mounting the assets without editing the ini** — insufficient: a qualified reference is not found
  merely by existing on disk.
- **Classifying each configured dir as "code" or "content" and mounting them differently** —
  complexity that buys nothing once stubs shadow by path order; and the premise is false, since a
  `.u` can hold textures.
- **A separate mount root for the code a stub is built from** — the source is read by explicit
  path, so it needs no scheme of its own.
- **Filtering package discovery to "content" extensions** — wrong for the same reason.
- **Keeping the old static compose mounts as a fallback** — a second path nothing verifies.
- **A separate editor-only `paths` config key** — the editor's view is *derived* from the analysis
  paths, not separately authored.
- **Putting the game's own raw code on the editor's `Paths`** — the editor cannot load it; that is
  the entire reason stubs exist.
- **Config-driving the editor substrate or the stub cache** — they are editor code, baked or
  derived, not user content.
- **Editing the ini surgically** — a naive strip deletes the editor's own search path.
- **A bare `<dir>/*` search-path entry** — measured to stall the editor at boot.
- **Bind-mounting arbitrary host roots into a container so it can reach assets** (with or without an
  allowlist, at identity paths or a translated prefix) — mounting user paths over a container's own
  dirs is a clobber risk, and the translated variant reintroduces the host-vs-container path branch.

**Stubbing**

- **Using the game's own toolchain as the decompiler** — that toolset ships no export commandlet at
  all.
- **Compiling a stub under its real package name** — it can collide with a resident package of that
  name and bind to the wrong one.
- **A deep transitive stub engine** — over-built for a closure that bottoms out on the committed
  substrate one hop down.
- **Making stubbing an explicit verb, or a separate pre-flight step** — every build would carry a
  step the user has to remember.
- **Writing stubs into the committed substrate tree** — mixes generated with committed and risks
  committing derived copyrighted material.
- **Reading a stub for the class schema.**
- **Treating native mesh decoding as blocking** — reading a mesh natively is worth having on its
  own merits, not as a dependency of this.
- **Deleting the editor image outright** once the native build path exists — it has to survive as
  the differential-verification oracle the native build is judged against.

**Container identity and lifecycle**

- **One shared editor container behind a global lock** — serializes every build on the machine.
- **A per-level, per-project, or pooled container** — still shared, still keyed, still needs a lock.
- **Blocking on the warm container's lock.**
- **Fingerprinting only the configuration** — a regenerated stub would silently build stale.
- **Rebooting the editor process every time anyway** — forfeits the boot saving.
- **Automatically retrying a failed warm build on a fresh container** — masks whether warm reuse is
  flaky and doubles the cost of a genuinely bad build.
- **A long-lived container daemon on a published port** — buys about one process spawn over one
  batched exec, at the cost of a hand-rolled protocol, a collision-prone fixed port, and a
  testability regression.
- **Falling back to the image's own packages when no games config exists** — an implicit,
  image-defined load set is surprising and cannot express a project's overlay.

## Refs

`../architecture.md` "Substrate" · `../unrealed/quirks.md` · `../unrealed/package-format.md` ·
`../parallel-editors.md` · `../dev-runtime.md` · `../deusex-assets-setup.md` ·
`../spikes/2026-06-21-deusex-package-stubbing-roundtrip.md` ·
`../spikes/2026-06-27-decontainerize-uedcli/` · `../spikes/2026-07-18-warm-editor-materialize/`
