+++
priority = "p2"
kind = "implement"
summary = "Bundle the user-facing docs into the wheel/Nuitka build (`uedcli/_docs/`)"
+++

# Bundle the user-facing docs into the wheel/Nuitka build (`uedcli/_docs/`)

p2.
**Deliberately not built** with the `docs` command that landed 2026-07-26 — that command is
complete and shipped, and this is the packaging half it was always specced to wait for (spec
`specs/2026-07-24-docs-command.md` §8, Andrzej 2026-07-24). Today `uedcli docs list|show|search`
serves the source checkout's `docs/` tree; `userdocs.docs_root()` already has the third branch
that reads a packaged `uedcli/_docs/`, and it is **dormant because nothing generates that
directory**. So an installed wheel or a Nuitka binary built today ships with NO docs and every
`docs` verb exits 2 with "uedcli docs unavailable (broken install)". **No command-code change is
needed** — only build wiring: (1) a build step that copies the served subset (`*.md` under
`docs/`, minus the top-level `dev/`) into `uedcli/_docs/`; (2) `.gitignore` it — it is generated,
never committed; (3) `pyproject.toml` `package-data = { uedcli = ["_docs/**"] }` (currently
explicitly empty) **plus MANIFEST**, with generation running BEFORE the sdist/wheel build, else a
clean-checkout build ships a broken install; (4) Nuitka
`--include-data-dir=uedcli/_docs=uedcli/_docs` — the ALREADY-FILTERED bundle, never
`docs=uedcli/_docs`, which would re-bundle the developer tree into a user-facing binary; (5) a CI
drift guard that `_docs` regenerates identically from source. Also verify then (untestable now)
that the resolver picks the bundled branch identically under a wheel and under Nuitka —
**and specifically this hazard**: the source-tree branch is
`importlib.resources.files("uedcli").parent / "docs"`, which in a wheel install resolves to
`site-packages/docs`. If any OTHER installed distribution ships a top-level `docs/` package
directory, it would satisfy that branch and shadow uedcli's own bundled `uedcli/_docs`, serving a
stranger's documentation. The spec assumed no `docs/` sibling exists in an install. Unverified
and speculative — packaging does not exist yet — but it is cheap to check once it does, and the
fix if real is to require a marker file inside the candidate directory. *(2026-07-26.)*
