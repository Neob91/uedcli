# Should a stub build warn when it drops a cross-package asset ref, or stay silent?

## Context

`assemble_stub_source` collects `CrossPackageRef`s — an asset (mesh/texture) a stubbed class
references in *another* package — into `AssembledStub.cross_package_refs` (`stub.py:73,99-113`),
"flagged (deferred), build proceeds". But **nothing reads that field**: the flags are discarded and
the build completes silently. A stub whose ref crosses a package boundary may then render or behave
wrong with no notice, which sits against the no-silent-halfanswer convention.

Full cross-package asset *resolution* is genuinely deferred (a separate future item). The question is
only what to do with the flags **now**:

- **Warn (recommended).** Emit each flag (package, ref, where) to stderr at build time; the stub
  still builds and caches. Cheap, honest, matches "human summaries go to stderr". Full resolution
  stays a later item.
- **Stay silent.** Accept that a cross-package ref is a known limitation and say nothing per build.
  Simpler output, but the failure is invisible exactly when it matters.

Recommendation: **warn** to stderr, and file a separate board item for real cross-package resolution.

## Answer

<!-- Empty = open. -->
