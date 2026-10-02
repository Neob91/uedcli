+++
priority = "p4"
kind = "investigate"
summary = "uscript: import-only class fallback could theoretically collide across packages"
+++

# uscript: import-only class fallback could theoretically collide across packages

Found in code review of the `UTServerAdmin` corpus win. `env._import_only_class_to_package`
(`env.py`) indexes, by casefolded name, the home package of any class known only via another
package's import table (no export anywhere on the search path) — `compile._add_import` falls back to
it when `resolve_class` fails. It picks the FIRST package found for a given name
(`index.setdefault`), with no ambiguity check.

In practice this should be safe: a coherent UE1 install can't have two genuinely different classes
sharing one exact name (case aside) in two different home packages, so every import row for a given
name should already agree on its true home. But this isn't proven, and the repo's own convention
(`CLAUDE.md`: no fallbacks, no substituted default for something that couldn't be resolved) argues
for at least a same-name-different-home consistency check that raises instead of silently picking one
if the assumption is ever wrong. Not chased further — no known real corpus case hits it.
