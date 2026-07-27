# Documentation — the detail

`CLAUDE.md` "Documentation" carries the core: write for a stranger, be as succinct as the meaning
allows, keep the user-facing docs current in the same change, and never point a user doc at a
developer doc. This doc holds the rest. The whole-tree "which doc is for what" table lives in
[`../README.md`](../README.md); the lane model and why it is split that way lives in
[`../direction/process.md`](../direction/process.md).

## Markdown tables — align for a plain-text editor (vim)

Pad every column to its widest cell so the interior pipes line up vertically, **except the final
column**: leave its content unpadded so a long prose column doesn't spawn huge trailing-whitespace
runs or 200+ char lines. Separator dashes fill each padded column's width; the final column's
separator stays a short `---`. Applies to all docs, not just `dev/docs`.

## User-facing docs vs the developer tree

**`docs/` is ALL user-facing; developer docs are a SEPARATE tree** (`dev/docs/`). Everything under
`docs/` is written for uedcli *users* — the LLM level-designer driving the CLI. The developer docs
(architecture, direction, rationale, spikes, board, the `../unrealed/` engine notes, the dev
knowledge base at `../unrealed/leveldesign/kb/`) are for uedcli *developers*, a different audience.

The user-facing surface is `docs/usage.md` (the CLI reference: verbs, flags, output) and
`docs/leveldesign/` (level-design craft mapped onto the verbs). Add a new doc — or a new section —
when a verb or feature is substantial enough that a user would look for it and not find it; err
toward documenting.

**User-facing docs must NEVER reference the developer docs** — no links or paths to spikes, the
board, architecture, etc.: a user cannot open them and must not be sent there. State the fact
plainly in the user doc instead (with a confidence marker if it's an engine claim), and put the
evidence pointer in the *developer* doc. Symmetrically, developer docs freely cite spikes and each
other.

## The developer docs split by role — keep each in its lane, and current

- **`../architecture.md` + `../unrealed/*.md`** — *what IS* (current implementation + verified engine
  facts). **MUST be updated to match whenever the implementation changes** — no doc may be left
  describing code that no longer exists or behavior that changed.
- **`../direction/<topic>.md`** — *what the OWNER decided*: product intent AND process rulings.
  **Revised in place** to state the current answer — no supersession, no dated-entry history (git
  keeps that). A gap between `../direction/` and `../architecture.md` is expected — it's work not yet
  done. **You may NEVER write this tree without their explicit yes** (`CLAUDE.md` "Working with the
  owner").
- **`../rationale/<topic>.md`** — *why the CODE is the way it is*: the engineering decisions an agent
  made (a tolerance, a scope limit, a format choice), keyed by module or subsystem. Also **revised in
  place**; agents maintain it freely. Every entry states **Why it is this way**, **Rejected**
  (alternatives killed, so nobody re-proposes them) and **Refs** (spike/code pointers). Point a
  durable doc here for rationale — never at an ephemeral spec.
- **an item's `spec.md` + `plan.md`** — ephemeral per-feature scratch (below). **`../spikes/`** —
  durable evidence.

**There is NO decisions ledger.** Nothing is append-only and nothing is superseded — a doc is
*edited* to say the current answer, and git holds what it used to say.

## Specs and plans are ephemeral; the knowledge must outlive them

**A spec or plan lives INSIDE the board item it belongs to** — `../board/<stage>/<slug>/spec.md` and
`plan.md`, alongside that item's `overview.md`. There is no separate specs or plans tree. A few items
carry a **second** spec, from work that was specced twice or split in two; it is named
`spec-<topic>.md`.

**All of them are ephemeral**: scratch for designing and sequencing one piece of work, expected to go
stale or get deleted once that work lands, and deleted with the item when it is pruned from `done/`.
They are NEVER the durable record. Once something is implemented, fold what was actually built, any
design decision made along the way, and the resulting general direction into the global docs
(`../architecture.md`, `../unrealed/*.md`, or another `dev/docs/*.md` as fits) — so the knowledge
survives even if the originating spec/plan is later removed. (`../spikes/` is different: it's kept as
durable evidence, cited from `../architecture.md`/`../unrealed/quirks.md`.)

**When speccing, record every decision the owner makes** — the choice, the alternatives rejected, and
the reason — as they make it. A spec must capture what *they* decided, not just your proposal; their
answers to the design questions are the load-bearing part and must not be lost or silently
overridden. Because specs are ephemeral, the decision must land in a **durable** doc before the spec
is deleted:

- **A decision the owner made** → `../direction/<topic>.md`, **revised in place** to state the new
  current answer. Propose the exact wording and wait for their yes. While it waits, park it with
  `bin/board new inbox '[OWNER — confirm] …'`, carrying the proposed text verbatim, so it survives
  the session ending.
- **A decision you made** (an implementation choice) → `../rationale/<topic>.md`, revised in place,
  with its `Rejected` alternatives and its `Refs`.

Never point a durable doc at a spec for "the rationale and rejected alternatives"; point it at the
owning `direction/` or `rationale/` topic.

**Being ephemeral is why the link checker skips them** — an item's `spec.md` and `plan.md` are not
checked for dead links or dead citations, *except* under `to-build/`, where someone is about to act
on them. A second spec named `spec-<topic>.md` does not match that carve-out, so it is checked in
every stage. (`uedcli/tests/test_doc_links.py`.)

## UnrealEd knowledge

**Always document new learnings about how UnrealEd functions, what our goals are, or architectural
choices/changes in `dev/docs`.** UnrealEd knowledge is ESPECIALLY important, because the public
documentation is very lacking and discovering the knowledge is expensive. New findings go in
`../unrealed/` (and back-reference them from code comments).

**Every claim about how UnrealEd behaves carries its evidence.** Cite the `../spikes/` file it came
from, and date any live finding (`confirmed live 2026-06-20`) — the editor is undocumented and
crash-prone, so an undated, uncited assertion can't be trusted or re-verified later.

**Tag UnrealEd facts in `../unrealed/*.md` with a confidence marker:** ✅ = uedcli-used /
live-verified, 🔬 = live-probed, 📖 = extracted from the binary string table (vocabulary real,
semantics inferred). Don't state an extracted fact with the certainty of a verified one.
