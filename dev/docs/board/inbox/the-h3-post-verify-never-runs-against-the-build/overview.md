+++
priority = "p2"
kind = "owner-question"
summary = "The H3 post-verify never runs against the build editor"
+++

# The H3 post-verify never runs against the build editor

Decided
2026-07-26 (owner chose "verify in a one-shot commandlet container" over an idle barrier and over a
separate GUI verify editor). Folded into board item `resolved-2026-07-26-was-warm-editor-materialize` decision 6;
**`direction/materialize.md` is NOT edited until this is confirmed.** Proposed wording, verbatim,
for `direction/materialize.md` § "The post-build verify":

> **The verify never runs against the editor that did the build.** It runs in its own one-shot
> headless container, which starts an editor engine with no GUI or display, executes a short
> script of console verbs, prints its output and exits by itself in a few seconds. Two reasons,
> and the second is the durable one. A reused build editor intermittently loses the *next* build's
> `MAP SAVE` after a verify has run against it — around half of reused builds — so a warm editor
> and an in-editor verify cannot coexist. And the qualification dump the verify depends on is
> documented as requiring a *fresh* editor with exactly one level loaded, because loading a level
> never purges the previous one's objects; a reused editor structurally cannot offer that, and a
> one-shot container offers it by construction. The verify also stops depending on scraping a
> block-buffered log file, which is what its two poll-until-settled loops existed to defeat.

*(Rejected, for the same section: an editor-quiesce/CPU-idle barrier — it only works if the cause
is a transient race, which the spike explicitly did not discriminate; a separate cold GUI verify
editor — robust, but its boot costs about as much as warm reuse saves; making `--no-verify` the
warm default — trading build correctness for speed on the one path whose job is detecting
wrongness.)*

**This decision also touches `direction/containers.md`, in two places.** (i) Its opening sentence
enumerates the container kinds and assigns "materialize, qualify" to the editor container;
qualification moves out to a fourth kind — a **one-shot headless commandlet container**, which
starts an engine with no GUI or display, runs a short script and exits by itself. (ii) Its
lifecycle bullet reads *"a warm-mode drive **or verify** failure tears it down before releasing the
lock"* — written when the verify ran against the warm editor. **Proposed replacement, verbatim:**

> **An untrusted container is never left warm**: a warm-mode *drive* failure tears it down before
> releasing the lock, and the invocation fails with a hint rather than silently retrying. A
> *verify* failure does not — the verify runs in its own container and so implicates the build, not
> the editor, and discarding a healthy warm editor there would penalise exactly the moment the
> operator is about to rebuild.

**Until you rule on (ii), the build follows the CURRENT direction text and tears down on a verify
failure too** (board item `resolved-2026-07-26-was-warm-editor-materialize` §4.3 says so explicitly). This is the
one place the spec knowingly proposes against a direction doc.
