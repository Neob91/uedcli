+++
priority = "p1"
kind = "owner-question"
summary = "`POLY TEXALIGN` is MEASURED; four things in board item `the-per-surface-verb-split` §4b now need your call"
+++

# `POLY TEXALIGN` is MEASURED; four things in board item `the-per-surface-verb-split` §4b now need your call

The spike ran
(`dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/`, live 2026-07-26; durable facts in
`dev/docs/unrealed/texalign.md`; six regressions in `test_engine_facts.py`). Headlines: the editor has
**nine** mode tokens, not six — and **`ONETILE` and `WALLCOLUMN` do nothing at all** in UED22, so
there is no fit-a-tile-to-a-face operation in the editor to port. Nothing in `TEXALIGN` ever changes
texel density; the modes only choose an in-plane orientation and an anchor, at 1 texel/uu. The spec
is NOT edited — the caller instructed explicitly, when commissioning the spike, that the spec was
not to be touched and that the required changes were to be reported instead. **So note that §4b now
states three things that are FLATLY DISPROVED and will mislead whoever builds from it**, quite
apart from the four decisions: (a) "six modes against our two" — there are **nine**; (b) "we cannot
currently say what any of them does" — all nine are now measured (`dev/docs/unrealed/texalign.md`);
(c) "**`ONETILE` has no counterpart at all** — fit exactly one tile to the face" — `ONETILE` is a
**no-op** in UED22 and fits nothing. Those three are corrections of fact and do not need a ruling;
only the four below do:
1. **`align wall|floor` orientation.** The spec's `builders._tex_basis(n̂)` does not agree with the
   editor on any of the seven face directions measured (mirror / 180° / on a yawed wall a full
   90°), and `_tex_basis` lets V point UP on roughly half a room's walls where the editor always
   drives V down. **Match the editor (`WALLDIR` for wall, `FLOOR` for floor), or diverge on
   purpose?** Right now the spec reads as if `_tex_basis` were the editor's rule.
2. **Anchor.** The editor pins `FLOOR`/`WALLX`/`WALLY` to a **world axis** — which is what makes
   separately-aligned faces across a level share one grid — while the spec pins to the **seed
   face's centroid**, making the result depend on which face was listed first and on how many
   invocations you split the plane across. A world-axis anchor would make `poly align --floor`
   idempotent and set-order-independent. **Change it?**
3. **`one-tile` is a uedcli invention, not a port.** No objection from the spike; the spec should
   just stop implying an editor precedent.
4. **Two modes worth adding, both absent from uedcli:** a `WALLPAN` equivalent (re-phase a wall's
   texture to world Z=0 without touching its axes) and the `WALLX`/`WALLY` projection pair (a
   stretched-but-continuous run across walls that are not quite parallel — the only thing the
   editor has for a TURNING run, which is what `align run` is reaching for).
Also open, and deliberately not guessed at: **what `CLAMP` is FOR** (measured to be `DEFAULT` with
`PanV = VSize−1`; the rendering consequence was not observed), and whether `ONETILE`/`WALLCOLUMN`
are implemented in non-UED22 UnrealEd builds (not checked — out of scope, we ship UED22).
