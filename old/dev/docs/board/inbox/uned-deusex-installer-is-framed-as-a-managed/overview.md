+++
priority = "p3"
kind = "docs"
summary = "`uned/deusex-installer/` is framed as a managed setup home in `architecture.md` (~1496-1503) but the SOURCE-arg script never uses it"
+++

# `uned/deusex-installer/` is framed as a managed setup home in `architecture.md` (~1496-1503) but the SOURCE-arg script never uses it

Cold review (2026-07-21): `install-deusex-assets.sh` takes
any `SOURCE` path and (for ACE) extracts into `dev/games/<game>/`; it never reads/writes
`uned/deusex-installer/`. Main setup doc caveat already softened (2026-07-21); `architecture.md`'s
"raw installer lives at uned/deusex-installer/" framing is the remaining vestige. Also re-check the
"Verify it worked" expected package counts (System ~17 / Textures ~57 / Sounds ~2 / Music ~35)
against a real install when one is available.
