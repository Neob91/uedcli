+++
priority = "p4"
kind = "investigate"
summary = "uscript: bare function-call name treated as class reference for package discovery"
+++

# uscript: bare function-call name treated as class reference for package discovery

Found in code review of `PubliciseScore`'s cast-call class discovery fix (`compile.py`
`add_expr_class_lits`). To find a class named only via a cast call (`TeamGamePlus(Level.Game)`,
syntactically identical to an ordinary function call at the AST level), the discovery pre-pass treats
EVERY bare-name call's callee as a candidate class reference, relying on `env.resolve_class` returning
`None` for anything that isn't actually a real class to "no-op" on an ordinary function call
(`Rand(100)`).

This is a real gap, not proven wrong: a plain function call whose bare name coincidentally matches a
real class name on the search path (function and class names are different UnrealScript namespaces,
so this can legally happen) would get treated as a class reference, pulling that class's whole
transitive `package_imports` into the compile's discovery frontier — widening the loaded catalog/graph
with no signal that discovery over-fired. Whether this actually changes compiled bytes (vs. just
loading unused packages harmlessly) wasn't traced through to `load_catalog`/name-table gather.

Not fixed here — no current corpus package hits this coincidence, and disambiguating properly needs
function-name resolution info this pre-pass (which runs before functions are resolved) doesn't have.
Also noted in the same review: the `resolve_class(base) is None and import_only_class_package(base)
is None` guard is duplicated verbatim across three call sites in `compile.py` (`_func_prop_type`,
`_resolve_var_type`, `_resolve_array_type`) — a future change to the fallback condition risks being
applied to two and missing the third. And `_extra_super_packages` builds a fresh whole-search-path
`ClassGraph` on every call with no caching across a corpus run's many compiles — a real but
low-priority perf cost, not correctness.
