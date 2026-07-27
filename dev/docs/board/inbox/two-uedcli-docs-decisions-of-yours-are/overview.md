+++
priority = "p2"
kind = "owner-question"
summary = "Two `uedcli docs` decisions of yours are currently recorded only in the agent-owned `rationale/` tree, where a future session may revise them freely"
+++

# Two `uedcli docs` decisions of yours are currently recorded only in the agent-owned `rationale/` tree, where a future session may revise them freely

The `docs`
command shipped 2026-07-26; its spec (`specs/2026-07-24-docs-command.md`, ephemeral) attributes
these two to you, so they need a `direction/` home. Both are implemented and live — this is
about where the *ruling* is filed, not about changing behaviour. Proposed text, verbatim,
awaiting a yes:

**(A) Suggested home: a NEW topic in the `direction/` tree, suggested name **documentation**
(nothing covers documentation today; fold it into the existing `scope` topic instead if you
prefer fewer topics). Only you can create it, so it does not exist yet:**

> **The docs are an asset of the TOOL, and the tool serves them.** uedcli's user-facing
> documentation ships inside uedcli and is readable through it (`uedcli docs list|show|search`),
> the way `git help <topic>` and `rustc --explain` work. A consumer that needs to point a user at
> a page — including a shipped Claude skill or plugin — **queries the tool** and ships **zero**
> copies of the docs. There is one source of truth, and a user always reads the pages that match
> the binary they are running: version-locked, offline, cross-platform.
>
> **Rejected:** *bundling the documentation under the skill's own `references/`* — it duplicates
> the corpus, inverts ownership (the skill would own uedcli's docs), and needs a bake/sync step
> that is one more thing to keep true. *Referencing hosted docs by URL* — needs a network and
> drifts from the installed version.

**(B) Suggested home: `direction/conventions.md`, under "No silent half-answers and no
fallbacks"** (it is an instance of that rule):

> **An ambiguous served set is an error, not a precedence rule.** Where two inputs claim one
> name — two documentation files deriving the same topic key, say — the tool refuses and names
> both, rather than picking one silently. Where such a conflict can only be created by an author
> (not by a user of a shipped binary), the refusal fires during enumeration so it breaks the test
> suite and every invocation at authoring time, and can never reach a user.

**What I judged NOT yours, and left in `rationale/userdocs.md`:** the resolver's
source-tree-before-packaged-`_docs` order. The spec marks it a review finding (`[R:H2-B]`), not
a ruling of yours, and it is an implementation trade about dev iteration. Say the word if you
read it as yours and it moves too. *(2026-07-26.)*
