+++
priority = "p2"
kind = "owner-question"
summary = "Warm editor now; the native and commandlet BUILD backends are later, separate work"
+++

# Warm editor now; the native and commandlet BUILD backends are later, separate work

Decided 2026-07-26 ("just build a warm container for now"), taken against
`spikes/headless-materialize/findings.md`, which ranks `level materialize --native` first overall
and calls the GUI editor a dead end. Recorded so the ranking is not silently re-litigated, and so
the warm work is understood as a bridge rather than a foundation. Proposed wording, verbatim, as a
closing note to `direction/materialize.md` § "The editor container":

> The warm editor is a **bridge, not a destination.** The editor-free native build already
> produces a complete map — geometry, lighting, movers, actor names and paths — in a fraction of
> the time and with no Wine, container or display at all; what it still lacks is byte-parity with
> UnrealEd on large maps. When that lands as a materialize backend, the warm editor becomes the
> `--editor` fallback it was always going to be. Nothing should be built on top of the warm
> container that would be expensive to retire with it.

*(Rejected: re-scoping the warm-editor work to `materialize --native` now — a bigger, different
change with an open byte-parity front; promoting the headless commandlet to a build backend — it
cannot produce a lit map, and nine workarounds for that failed.)*
