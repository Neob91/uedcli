+++
priority = "p2"
kind = "implement"
summary = "Spike whether .u prop flags (transient/const/editconst/native) can replace the hand-maintained COMPUTED_PROPS blacklist."
+++

# derive computed-props from class-schema flags to replace COMPUTED_PROPS

The post-verify compare ignores engine-computed props via a hand-maintained blacklist
(`normalize.COMPUTED_PROPS`) — every entry a manual, per-name audit. Inverting to a whitelist of
authored props is larger to maintain and doesn't escape the core problem: telling a harmless
engine-stamp (`Base`, `Region`) apart from a real divergence (a light the trunk meant to leave default
that came back non-default).

Idea (owner, 2026-08): derive "don't compare" from the class schema's own UE1 prop flags —
`transient` (never saved), `const`, `editconst`, `native` — package-class scoped (e.g.
`Engine.Mover.KeyPos` kept, its computed siblings not). uedcli already decodes the schema, so this
would be self-maintaining rather than a hand list.

Spike: do the engine-stamped fields (`Base`, `Region`, `NavigationPointList`, mover `SavedPos`) carry a
schema flag that authored fields don't? If yes, the flag rule replaces the blacklist. If the flags
don't cleanly separate them, the idea fails and we keep the list. Verify against the decoded `.u`, not
memory.

Immediate `Base` fix is decoupled: [[materialize-post-verify-excludes-engine-stamped]].
