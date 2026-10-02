+++
priority = "p2"
kind = "debug"
summary = "`level photo --native` checkerboards an unresolvable texture ref and warns — a `conventions.md`-Rejected warn-and-continue"
+++

# `level photo --native` checkerboards an unresolvable texture ref and warns — a `conventions.md`-Rejected warn-and-continue

`preview_native._TextureTable` renders a
checkerboard for any ref it cannot resolve and prints one stderr warning, then exits 0 with an
image that looks like an answer. `direction/conventions.md` lists exactly that under **Rejected**
("a half-answer that looks like a full one is worse than a refusal; the note scrolls away").
Surfaced while speccing `--faces textured`, which now **exits 2** on an unresolvable ref per that
rule — so the two renderers are deliberately inconsistent until this one is brought in line.
Changing an existing verb was out of scope for that spec; it is not out of scope forever.
*(2026-07-26.)*
