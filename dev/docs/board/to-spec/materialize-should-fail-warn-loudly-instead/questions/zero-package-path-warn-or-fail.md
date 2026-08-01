# When the composed search path resolves to 0 packages, warn or fail?

## Context

The referenced-package fail-fast (spec §Design (ii)) already makes materialize exit 2, naming every
package, whenever the level references a package the load set can't resolve. That is the load-bearing
guarantee and needs no ruling.

The residual case is a level that references **no** packages (bare classes, no textures) while the
composed path resolves to **0** packages — usually a mis-typed `paths` config dir. The level would
build correctly (nothing to load), so this is a smell, not a correctness failure.

- **Option A (recommended):** advisory stderr line, build continues (rc 0). Correctness rests on (ii);
  a valid reference-free greybox still materializes. Softest, but a non-blocking warning is the exact
  "scrolls away" shape `conventions.md` dislikes — tolerable here only because nothing is being
  silently dropped (there is nothing to drop).
- **Option B:** hard exit 2 on any empty composed path. Conventions-pure, but rejects the legitimate
  no-texture build — a correct input refused.
- **Option C:** make a *dangling configured dir* a `ConfigError` at `config.composed_search_files`
  (stop swallowing `OSError` for a dir that doesn't exist). Catches the typo at its source for every
  verb, not just materialize. Broader than this item; would be its own board item.

Recommendation: A for this item, and file C separately if the config-dir-typo class is worth catching
tool-wide.

## Answer

<!-- Empty = open. -->
