+++
priority = "p3"
kind = "docs"
summary = "architecture.md --tree rider list still names `brush clip` (now a filter)"
+++

# architecture.md --tree rider list still names `brush clip` (now a filter)

`brush clip` became a stateless T3D-stdin filter (item `brush-clip-should-be-a-t3d-stdin-filter`,
owner 2026-08-02) and no longer carries `--tree`. `dev/docs/architecture.md` still lists it in the
`--tree` rider enumeration ("The flag rides the content verbs … `brush clip/replace/vertex …`" in
the `LevelSource` seam section). Drop `clip` from that list.

The GeometryError producer list in the same doc still naming `brush clip` is fine — the filter still
raises `GeometryError` on a degenerate result.

Editing `architecture.md` needs the owner's yes (CLAUDE.md dev/docs rule), so this is filed rather
than fixed in the build.
