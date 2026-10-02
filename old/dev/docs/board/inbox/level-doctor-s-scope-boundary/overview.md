+++
priority = "p1"
kind = "owner-question"
summary = "`level doctor`'s scope boundary — proposed `direction/trunk-and-editor.md` addition"
+++

# `level doctor`'s scope boundary — proposed `direction/trunk-and-editor.md` addition

Ruled 2026-07-26 and already written into `docs/usage.md`, `architecture.md` and
`cli.py`'s `help=`; needs a durable home in the owner's own tree. That topic already says the
"is this trunk well-formed?" lint *"folds into `level doctor`"*, which is where the bound belongs.
Proposed text (verbatim, awaiting a yes):

> **`level doctor` is bounded by INTENT-INDEPENDENCE.** It reports only defects that are wrong
> *regardless of what the author intended*: the math and geometry that breaks or burdens the BSP,
> zoning of the same kind, and objectively-wrong footguns — an `Event` matching no `Tag` fires into
> the void, a light buried in solid geometry lights nothing. It does **not** judge gameplay or style.
> **Passage/occlusion checking is rejected, not deferred:** doctor can measure the free gap between
> two brushes but cannot tell a deliberately sealed wall from an accidentally blocked doorway,
> because the two are identical geometry and differ only in intent. Whether a space is comfortable,
> whether a decoration is well seated, whether the level is detailed or good — all need eyes on
> renders, from a human or an independent reviewing agent. A clean `doctor` report is not a quality
> report, and no better heuristic changes that.
