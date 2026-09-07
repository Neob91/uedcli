+++
priority = "p2"
kind = "debug"
summary = "DONE — the two disagreeing uedcli_native builds were not two compilations of one source: cargo's mtime freshness check skipped the rebuild and shipped a stale wheel. bin/_venv.sh now refreshes the crate mtimes before maturin; the UNATCO N=116 bail it caused was never real."
spikes = ["dev/docs/spikes/2026-09-07-native-ext-build-staleness/"]
+++

# The `uedcli_native` binary IS stable across builds — the discrepant one was stale

Filed 2026-09-07 as "two builds of the identical `src/` give different `.so`s and disagree about
UNATCO N=116 leaf 9", blamed on `.cargo/config.toml`/`.gitignore`/an empty directory. Wrong on both
counts.

**Cargo decides freshness by mtime.** A crate whose sources were restored with older timestamps —
`git archive` stamps the commit's time, `tar -x`/`cp -p`/`rsync -t` preserve the stored one — is
taken as up to date, so `maturin build` repackages the PREVIOUS build's `.so`. The six N=116
packages the prior session labelled with six different commits are byte-identical modulo the package
GUID; six materially different sources cannot compile to one package, so none of them was compiled.
Rebuilt properly, those commits give different binaries and the 940-light PASS result.

Ruled out by measurement: the three non-source files (same sha256 with and without them), codegen
(`-C opt-level=1 -C codegen-units=1` and `-C target-cpu=native` leave the whole leaf-9 margin trace
byte-identical), run order (`RAYON_NUM_THREADS` 1/8/14 differ only in the GUID). Detail and the
forensics: `dev/docs/spikes/2026-09-07-native-ext-build-staleness/`.

Fixed: `ensure_native_ext` refreshes the crate's source mtimes before building, so the content hash
it already gates on is what decides; `ladder_run.py` prints the extension's sha256 and path so a
bail is attributable. Regression:
`test_native_roundtrip.py::test_native_ext_build_refreshes_crate_mtimes_before_cargo_sees_them`.

Re-gated with the verified wheel, every level holds where it was recorded: UNATCO 160-162 PASS /
163 FAIL, WanChai 43-44 / 45, NYC_Bar 151-152 / 153, Island 122 / 123, OceanLab 46-47 / 48.

Not fixed, filed separately: the build image installs `--default-toolchain stable` and an unpinned
`maturin`, so an image rebuild can silently change rustc — board `pin-the-rust-build-image-toolchain`.
