+++
priority = "p2"
kind = "docs"
summary = "Backward-compat: class-discovery ingest/generator validation changes exit status of previously-green no-config runs"
+++

# Backward-compat: class-discovery ingest/generator validation changes exit status of previously-green no-config runs

Once the class-discovery spec builds, `actor build` / `brush
build --texture` / `actor add` run WITHOUT a games config (or against a class/texture whose package
isn't on the composed path) will **exit 2** where they silently passed. Intended (no-fallback, same
honest cost `actor prop` pays) and Andrzej-chosen (generators-AND-boundaries), but it IS a visible
behavior change — flagged so it's a deliberate break, not a surprise. Also: the generators
(`actor build`/`brush build`) stop being stateless context-free producers (they now resolve a
project to validate the class) — a documented contract change to `direction/generators.md`'s "Generator
pattern: stateless T3D producers".
