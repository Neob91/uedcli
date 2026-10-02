# SPIKE 40 — Nuitka bundles a PyO3 `.so` end-to-end (the ship-story gate)

**Date:** 2026-07-15. **Method:** throwaway end-to-end build. Built a trivial PyO3 extension
(`abi3-py312`, via maturin), imported it from a tiny `app.py`, and froze that app with Nuitka
`--standalone` and `--onefile`; ran each frozen binary from a neutral cwd with an **empty environment**
(`env -i`) to prove it needs no venv. **Harness:** `harness/nuitka_pyo3/` (`spikemod/` crate + `app.py`
+ `run.sh` one-shot reproducer).

---

## VERDICT ✅

**PROVEN. Nuitka bundles a PyO3 `.so` end-to-end — the spec's "Nuitka bundles the `.so` like Pillow"
assertion (§8.3) holds.** Both `--standalone` and `--onefile` produced a self-contained binary that
loads the Rust extension and runs correctly (`spikemod.add(2,3) = 5`) from an empty environment. The
`.so` is even **auto-detected** on `import spikemod` — `--include-module` is a belt-and-suspenders
extra, not a requirement (exactly the Pillow mechanism). **§8's ship story is de-risked; the PyO3-first
decision can be ratified.**

---

## What was built and run

- **`spikemod`** — a PyO3 0.23 crate, `crate-type = ["cdylib"]`, features `extension-module` +
  **`abi3-py312`**. One `#[pyfunction] fn add(a,b)` in a `#[pymodule]`.
- **`maturin develop --release`** → built `spikemod.abi3.so` into the venv (wheel tag
  `spikemod-0.1.0-cp312-abi3-linux_x86_64.whl`). Note the `.so` is named `spikemod.abi3.so` — the
  **stable-ABI** name, decoupled from the CPython patch/minor.
- **`app.py`**: `import spikemod; print(spikemod.add(2,3))` → prints `5` in the venv. ✅

### Results matrix

| Build | Command | Ran from `env -i` neutral cwd | Output | `.so` bundled at |
|---|---|---|---|---|
| venv import | `python app.py` | (in venv) | `5` | `venv/.../spikemod/spikemod.abi3.so` |
| **standalone** | `nuitka --standalone --include-module=spikemod app.py` | ✅ `5` | `app.dist/spikemod/spikemod.so` |
| **standalone (auto-detect)** | `nuitka --standalone app.py` *(NO include flag)* | ✅ `5` | `app.dist/spikemod/spikemod.so` |
| **onefile** | `nuitka --onefile app.py` | ✅ `5` | inside the 22 MB self-extracting `app.bin` |

All three frozen runs printed `5` with an **empty environment** — no venv, no `PYTHONPATH`, proving the
extension is genuinely bundled and loaded, not picked up from the build tree.

---

## Toolchain, flags, and gotchas (for M0 / `_venv.sh` wiring)

- **Versions used (host):** Python 3.12.9, Rust 1.97.0, PyO3 0.23.5, maturin 1.14.1, Nuitka 4.1.3,
  Nuitka backend C compiler gcc 11.
- **`--include-module=uedcli_native` is OPTIONAL** — Nuitka's import-follower auto-includes the
  extension on `import`. Keep it as a belt-and-suspenders flag (spec §8.3) since uedcli imports
  `uedcli_native` behind a `try/except`-guarded path; an explicit include guarantees it survives even
  if the import is conditional.
- **`patchelf` is REQUIRED on Linux for `--standalone`/`--onefile`.** Nuitka hard-fails without it
  (`FATAL: ... requires 'patchelf'`). It is **pip-installable** (`pip install patchelf` ships a
  `patchelf` binary into the venv `bin/`) — no system/root package needed; just ensure the venv `bin/`
  is on `PATH` when invoking Nuitka. Add `patchelf` to the dev/CI deps alongside `nuitka`.
- **maturin gotchas hit during the spike (fixed in the committed harness):** `maturin develop` needs a
  virtualenv it can find — either activate it or export `VIRTUAL_ENV=<venv>`; and `pyproject.toml`
  **must** carry `project.version` (or `project.dynamic=["version"]`) or maturin aborts. Both are baked
  into the harness so `run.sh` works clean.

## The three gotchas the spec flagged — measured

1. **Python-ABI coupling → solved by `abi3`.** With `abi3-py312` the built artifact is `spikemod.abi3.so`
   (stable ABI), loadable on CPython **3.12 and any later 3.x** — it will not break on a 3.12→3.13
   interpreter bump the way a `cp312`-tagged `.so` would. Ratify the spec's `abi3-py312` choice.
2. **glibc floor — MEASURED.** The `.so`'s dynamic deps are only `libgcc_s.so.1` + `libc.so.6`
   (`ldd`); its highest versioned glibc symbol is **`GLIBC_2.34`** (`objdump -T`). Build host glibc is
   **2.35** (Ubuntu 22.04). So a binary built here needs **glibc ≥ 2.34** on the target — fine for any
   distro from ~2021 on, but per the spec, **build the release on the OLDEST supported glibc** (e.g. a
   manylinux_2_28 / Rust `x86_64-unknown-linux-gnu` container) to lower that floor. The 2.34 symbols come
   from the Rust/glibc side (e.g. `__libc_start_main@2.34`), not from anything uedcli controls, so the
   only lever is the build host.
3. **Per-platform Rust toolchain — unchanged, still real.** This spike only proves the **Linux/x86_64**
   path. The "one binary, many platforms" direction still means each target (Windows, macOS, other
   arches) needs its own Rust toolchain + Nuitka build; cross-compiling a PyO3 extension remains
   materially harder than shipping pure Python. Not a blocker for the Linux-first ship, but keep it on
   the packaging board item.

## Consequence for the spec

- **§8.3 / §9 "Nuitka bundles the `.so` like Pillow" — RATIFIABLE.** The load-bearing, previously-`⚠
  UNPROVEN` claim is now demonstrated end-to-end (standalone + onefile, auto-detected, empty-env run).
  The M0 "Nuitka-bundling spike" prerequisite (§7) is satisfied by this doc; M0 can proceed to wire the
  real crate.
- **PyO3-first (over the sidecar) stands.** The one risk that argued *for* a sidecar — untested
  Nuitka+PyO3+ABI packaging — is now tested and works, so the in-process choice keeps its advantages
  (no runtime sidecar location, one coherent app) without the untested-packaging cost. The pure-core
  crate shape still keeps the sidecar reversible if a *cross-platform* build later proves painful.
- **M0 `_venv.sh`/`bin/test` wiring to add:** `maturin`, `nuitka`, `patchelf` in the dev/CI deps;
  `maturin develop` gated on a Rust-source hash (a `.rs` edit must trigger rebuild — the pip marker
  won't); export `VIRTUAL_ENV`; `project.version` in the crate's `pyproject.toml`.

**Confidence:** ✅ (executed end-to-end on this host; both freeze modes verified with empty-env runs).
**Scope caveat:** Linux/x86_64, glibc 2.35 host only — cross-platform matrix unproven (and out of scope
for this gate).

## Reproduce
```
harness/nuitka_pyo3/run.sh /tmp/spike40    # needs python3.12 + rustup/cargo + internet
```
Prints `5` from the venv, then `5` from the standalone `app.bin`, then `5` from the onefile `app.bin`,
then `SPIKE 40 OK`.
