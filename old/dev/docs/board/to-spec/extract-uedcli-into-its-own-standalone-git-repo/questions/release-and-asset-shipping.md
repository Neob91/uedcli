# What is the release model, and how do the non-wheel assets ship?

## Context

The README promises "standalone Nuitka binaries"; `pyproject.toml` builds a pure-Python wheel
(`Pillow` the only dep) and ships **no** package data. But uedcli needs assets that are not Python:

- `uned/` — the docker-compose dir + the committed UED22 editor substrate (105M).
- `umodel_win32` — the mesh extractor the stub pipeline needs. It is **gone** from the standalone
  layout: `tool_assets.umodel_dir()` resolves `tool_root().parent / "umodel_win32"`, a path that no
  longer exists. Its home must be decided.
- `uedcli-native/` — a Rust crate (native mesh decode) with its own `pyproject.toml`; how it builds
  and ships alongside the Python package.

`tool_assets.py` resolves all of these package-relative and its docstring defers "how these ship
under a pipx/Nuitka install" to this packaging work. Questions to settle:

- **Distribution channel:** pipx-from-git / PyPI wheel / Nuitka standalone binary — which is the
  primary, and is there more than one?
- **Asset location per channel:** does `uned/`+umodel travel with the install, get downloaded on
  first use, or stay developer-supplied? (The editor already runs from a Docker image + read-only
  mounts, so the substrate need not be in the wheel — but umodel and the compose dir must resolve
  somehow.)

There is a separate packaging board item; the scope here is to **confirm the boundary** between this
extraction item and that one, and to give `umodel_dir()` a real home so the broken path is fixed.

## Answer

<!-- Empty = open. -->
