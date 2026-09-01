# Documentation — the detail

`CLAUDE.md` "Documentation" carries the core: write for a stranger, be as succinct as the meaning
allows, keep user-facing docs current in the same change, and never point a user doc at a developer
doc. This doc holds the rest. The whole-tree "which doc is for what" table lives in
[`dev/docs/README.md`](../README.md); the lane model lives in
[`dev/docs/direction/process.md`](../direction/process.md).

## Markdown tables — align for a plain-text editor (vim)

Pad every column to its widest cell so interior pipes line up vertically, except the final column:
leave its content unpadded so a long prose column doesn't spawn huge trailing-whitespace runs or
200+ char lines. Separator dashes fill each padded column's width; the final column's separator
stays a short `---`. Applies to all docs, not just `dev/docs`.

## User-facing docs vs the developer tree

`docs/` is all user-facing, written for uedcli users — the LLM level-designer driving the CLI.
Developer docs are a separate tree (`dev/docs/`): architecture, direction, rationale, spikes, board,
the `dev/docs/unrealed/` engine notes, and the knowledge base at `dev/docs/unrealed/leveldesign/kb/`,
for a different audience.

The user-facing surface is `docs/reference/` (per-command CLI reference), `docs/usage/` (task
guides), and `docs/leveldesign/` (level-design craft mapped onto the verbs). Add a doc or section when a verb or
feature is substantial enough that a user would look for it and not find it; err toward documenting.
New level-design knowledge — best practices, recipes, craft or engine claims, human-scale numbers —
needs the owner's approval before it lands (`CLAUDE.md` "Documentation"); rephrasing and tool-behavior
docs do not.

User-facing docs must never reference the developer docs — no links or paths to spikes, the board,
architecture, etc.: a user cannot open them. State the fact plainly in the user doc (with a
confidence marker if it's an engine claim), and put the evidence pointer in the developer doc.
Developer docs freely cite spikes and each other.

## The developer docs split by role — keep each in its lane, and current

- **`dev/docs/architecture.md` + `dev/docs/unrealed/*.md`** — what IS (current implementation +
  verified engine facts). Updated to match whenever the implementation changes — no doc may describe
  code that no longer exists or behavior that changed.
- **`dev/docs/direction/<topic>.md`** — what the owner decided: product intent and process rulings.
  Revised in place, no supersession, no dated history (git keeps that). A gap between it and
  `dev/docs/architecture.md` is expected — work not yet done. Never write this tree without their
  explicit yes (`CLAUDE.md` "Working with the owner").
- **`dev/docs/rationale/<topic>.md`** — why the code is the way it is: engineering decisions an agent
  made (a tolerance, a scope limit, a format choice), keyed by module or subsystem. Revised in place;
  agents maintain it freely. Every entry states Why it is this way, Rejected (alternatives killed, so
  nobody re-proposes them), and Refs (spike/code pointers). Point a durable doc here for rationale —
  never at an ephemeral spec.
- **an item's `spec.md` + `plan.md`** — ephemeral per-feature scratch (below).
  **`dev/docs/spikes/`** — durable evidence.

There is no decisions ledger. Nothing is append-only or superseded — a doc is edited to say the
current answer, and git holds what it used to say.

## Specs and plans are ephemeral; the knowledge must outlive them

A spec or plan lives inside its board item — `dev/docs/board/<stage>/<slug>/spec.md` and `plan.md`,
alongside that item's `overview.md`. There is no separate specs or plans tree. A few items carry a
second spec, from work specced twice or split in two, named `spec-<topic>.md`.

All are ephemeral: scratch for designing and sequencing one piece of work, expected to go stale or be
deleted once the work lands, and deleted with the item when it is pruned from `done/`. They are never
the durable record. Once something is implemented, fold what was built, any design decision made
along the way, and the resulting direction into the global docs (`dev/docs/architecture.md`,
`dev/docs/unrealed/*.md`, or another `dev/docs/*.md`) so the knowledge survives the spec/plan's
removal. (`dev/docs/spikes/` is different: durable evidence, cited from
`dev/docs/architecture.md`/`dev/docs/unrealed/quirks.md`.)

When speccing, record every decision the owner makes — the choice, the alternatives rejected, the
reason — as they make it. A spec must capture what they decided, not just your proposal; their
answers are load-bearing and must not be lost or silently overridden. Because specs are ephemeral,
the decision must land in a durable doc before the spec is deleted:

- A decision the owner made → `dev/docs/direction/<topic>.md`, revised in place. Propose the exact
  wording and wait for their yes. While it waits, park it with
  `bin/board new inbox '[OWNER — confirm] …'`, carrying the proposed text verbatim, so it survives
  the session ending.
- A decision you made (an implementation choice) → `dev/docs/rationale/<topic>.md`, revised in place,
  with its `Rejected` alternatives and `Refs`.

Never point a durable doc at a spec for "the rationale and rejected alternatives"; point it at the
owning `direction/` or `rationale/` topic.

Being ephemeral is why the link checker skips them — an item's `spec.md` and `plan.md` are not
checked for dead links or citations, except under `to-build/`, where someone is about to act on them.
A second spec named `spec-<topic>.md` does not match that carve-out, so it is checked in every stage.
(`uedcli/tests/test_doc_links.py`.)

## UnrealEd knowledge

Document new learnings about how UnrealEd functions, our goals, or architectural choices in
`dev/docs`. The public documentation is very lacking and discovering this knowledge is expensive. New
findings go in `dev/docs/unrealed/`, back-referenced from code comments.

Every claim about UnrealEd behavior carries its evidence. Cite the `dev/docs/spikes/` file it came
from, and date any live finding (`confirmed live 2026-06-20`) — the editor is undocumented and
crash-prone, so an undated, uncited assertion can't be trusted or re-verified later.

Tag UnrealEd facts in `dev/docs/unrealed/*.md` with a confidence marker: ✅ = uedcli-used /
live-verified, 🔬 = live-probed, 📖 = extracted from the binary string table (vocabulary real,
semantics inferred). Don't state an extracted fact with the certainty of a verified one.
