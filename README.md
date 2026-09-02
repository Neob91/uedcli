# uedcli

A control layer that turns the live UnrealEd-2.2-under-wine editor (in the `dx-lum-uned`
container, driven by `Tools/uedcli/uned/wine_ctl.py`) into a **queryable, scriptable, auditable**
level-design surface an LLM can drive entirely as text — no GUI. You issue semantic
by-name commands; T3D is internal plumbing. The level **model is the source of truth**;
the `.dx` is a build artifact; UnrealEd is the compiler/renderer/validator.

## Quickstart

uedcli is **pure Python 3.12** (one dep, `Pillow`). It runs **host-native** through the `bin/uedcli`
launcher, which self-creates and reuses a dev venv (`bin/_venv.sh`, `.venv/`) — the host needs
`python3.12` on `PATH`, nothing else. Only the editor/build containers uedcli *drives* use Docker.
(Releases will be standalone Nuitka binaries; see [`dev/docs/dev-runtime.md`](dev/docs/dev-runtime.md).)

```bash
# put the launcher on PATH (self-creates the dev venv on first run)
export PATH="$PWD/Tools/uedcli/bin:$PATH"   # or: ln -s "$PWD/Tools/uedcli/bin/uedcli" ~/.local/bin/

uedcli level status
uedcli actor find --exact-class Brush
uedcli brush poly list Brush41
uedcli actor diagram Brush41 --out /tmp/b41.png   # color quad wireframe PNG, poly-index labels
# brush clip is a T3D filter (stdin→stdout); clip a placed brush in place with show→clip→replace
uedcli actor show Brush41 | uedcli brush clip - --axis z --offset 128 --keep below | uedcli brush replace Brush41 -

# offline unit tests (committed fixtures, no editor container) — same venv, host-native
bin/test          # path-qualified: `test` alone is a shell builtin
```

Prefer a native interpreter? Everything above also works as `python3 -m uedcli …` /
`python -m pytest uedcli -q` from a Python **3.12** environment with `Pillow>=11`.

## In-game photo setup (`level photo --game`)

`level photo --game` (the default photo backend) renders truly-lit in-game frames by booting the
real game engine headless in a container. It needs Docker and the game's own files (copyrighted,
user-supplied). One script provisions everything from a Deus Ex copy — a local install or
ACE-installer directory, a download `--url`, or, with no argument at all, a built-in default
download (the archive.org GOTY installer, checksum-pinned):

```bash
dev/scripts/setup-game-preview.sh                     # fully autonomous: the built-in default
dev/scripts/setup-game-preview.sh /path/to/DeusEx     # or: --url https://…/DeusEx-installer.exe
```

It builds the `dx-lum-uned` base image, installs the game files (`install-deusex-assets.sh
--with-maps`), writes `~/.uedcli/config.toml` `[games.deusex]` and a project `uedcli.toml`, then
renders one frame to prove it works (`--no-verify` skips that; `--dry-run` shows the plan). The
`uedcli-game` image and the preview package compile automatically on first use — no UnrealEd/UCC
toolchain to install. Where to get a Deus Ex copy:
[`dev/docs/deusex-assets-setup.md`](dev/docs/deusex-assets-setup.md).

Once set up (from a project — the repo root is one):

```bash
uedcli level photo --game 'at:0,0,64;rot:0,0' --out-dir /tmp/shots   # a lit still of the trunk level
# or point at a prebuilt map instead of the trunk:
uedcli level photo --game --map dev/games/deusex/Maps/00_Training.dx 'at:0,0,64;rot:0,0' --out-dir /tmp/shots
```

The pose grammar and both backends (`--game`, offline `--native`) are in
[`docs/reference/level/photo.md`](docs/reference/level/photo.md).

## Documentation — see [`docs/`](docs/)

- [`docs/reference/`](docs/reference/actor/README.md) — the CLI: query/mutate verbs, the `actor
  diagram` viewer, `brush poly list`, brush clip, `stash`/`prefab`, the texture catalog
  (`list`/`search`/`tags`/`classify`). [`docs/usage/`](docs/usage/README.md) has task-oriented
  guides.
- [`dev/docs/architecture.md`](dev/docs/architecture.md) — layers/modules, the write
  pattern, invariants, the git-tracked T3D trunk, how to add a verb, testing, the substrate.
- [`dev/docs/unrealed/`](dev/docs/unrealed/README.md) — the verified UnrealEd-2-under-wine
  knowledge base: `commands.md` (exec verbs), `quirks.md` (gotchas), `rendering.md`
  (screenshots), `extracting-from-dll.md`. **Read before touching the driver.**
- Issues — the roadmap and backlog — live in [beads](https://github.com/steveyegge/beads) (`bd`);
  data syncs via `refs/dolt/data` on origin. The former `dev/docs/board/` was migrated 2026-09-02
  (slug map: `dev/docs/board/bd-id-map.tsv`); the directory remains only for one in-flight item
  cluster.
- Original design spec: `docs/superpowers/specs/2026-06-16-uedcli-design.md` (repo root).
