# What is the offline `level preview` tier's flag called after consolidation?

Today `level preview --native` means "the Rust-native offline tier" (vs `--game`). After
consolidation the offline tier is drawn by pure-Python `preview.py` — "native" becomes a misnomer
(and the planned Rust rasterizer is a *separate* follow-on, so it won't re-earn the name soon).
No-back-compat rule (`conventions.md`): whatever we pick is the only spelling, no alias.

Options:
- **`--offline`** (recommended) — contrasts cleanly with `--game` (the in-game tier): the two tiers
  are "offline draft" vs "in-game faithful." Says what it is to a user who doesn't know the internals.
- **`--draft`** — emphasises fidelity (fast rough vs faithful) rather than where it runs. Also fine;
  slightly less obvious against `--game`.
- **Keep `--native`** — least churn, but now inaccurate (it's Python, not the native extension's
  rasterizer). Reads as a lie once someone looks.

Whichever wins, the `--game`/offline pair stays mutually exclusive, `--game` stays the default, and
`--fov` stays gated to the offline tier.

## Answer

<!-- Empty = open. -->
