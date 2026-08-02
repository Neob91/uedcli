# reviewer-brief.md — the context pack handed to every review subagent

This is what a review subagent is given **instead of the whole `CLAUDE.md`**. A
reviewer needs to tell a deliberate convention from a defect; it does not need the
worktree procedure, the commit-hunk rules, or the board taxonomy, because it is not
committing anything. Hand over the full `CLAUDE.md` only when the artifact under
review is itself a process rule.

Keep this file in step with `CLAUDE.md` "Code & CLI conventions" and
"Documentation" — if those change and this does not, reviewers start flagging
current conventions as defects.

---

## What uedcli is

A command-line tool for authoring Unreal Engine 1 levels — Deus Ex is the first
substrate, but the tool is meant to be generic. The **source of truth is a T3D
tree** (a text level format) that uedcli reads and writes directly; the actual
editor (UnrealEd) is driven only as a *build tool*, to bake lighting and BSP. So
most changes are ordinary Python that manipulates a parsed text tree — not editor
automation.

It is **unreleased**: no external users, no scripts in the wild.

## Conventions a reviewer must not mistake for defects

**No back-compat cruft.** Because uedcli is unreleased, a removed or renamed flag,
verb, option value, output format or code path is **deleted outright** in the same
change that adds the replacement. Deprecated aliases, no-op compatibility flags,
migration-error shims, dual-format support and "old way" branches are all
forbidden. **Do not file "this breaks existing callers" as a finding** — there are
no existing callers, and the missing shim is the rule being followed.

**No silent half-answers.** A command that cannot fully satisfy a request **exits 2
naming the offending value**. It must not emit a partial result plus a stderr
warning — stderr scrolls away and the caller takes the partial answer for a
complete one. A hard failure where you might expect a warning is deliberate.

**Never let a Python exception reach the user.** A bad actor/entity name raises a
clear error naming the offending value (`Actor not found: Foo`) and exits non-zero
— never a bare `KeyError`/`IndexError` traceback. Each such path should have a
regression test; a missing one **is** a finding.

**Every command and argument needs a `help=` string** that explains what it
actually does — never a restatement of the flag name.

**Verbs compose — this is the core CLI philosophy.** Small, single-purpose verbs
that pipe together, never big verbs with many bespoke flags:

- **Producer/query verbs print to stdout, one item per line.** Human
  summaries and counts go to **stderr** so they never pollute the pipe. `--json`
  is added where a script needs structure rather than lines.
- **Mutating verbs read their target set from stdin via `-`.** `-` is the *sole*
  names source, mutually exclusive with names as CLI args. **Empty stdin is a
  clean no-op, exit 0** — not an error.
- **Two stdin conventions, disambiguated by verb:** a **name list**
  (`find → mutate -`) versus a **T3D snippet** (`build → add -`). They stay
  distinct.
- **A verb over a SET takes the set, and that IS the operation.** `actor bbox
  <names…>` returns the box enclosing all of them, so there is deliberately **no
  `--union` flag**. A flag that merely restates "operate on this set" is the
  defect; its absence is not.
- **Prefer a stateless `find`/query verb** over per-command
  `--only-groups`/`--only-actors` filter flags sprinkled on every verb.
- **`find` vs `search` are different words on purpose.** `find` = a deterministic
  query over concrete T3D-tree state that exists in the trunk (`actor find`,
  `brush poly find`). `search` = ranked/fuzzy discovery over a catalog or corpus
  (`texture search`). Never propose merging them.

## Documentation rules a reviewer should check

- **`docs/` is ALL user-facing; `dev/docs/` is the developer tree.** A user-facing
  doc that links to a spike, the board, `architecture.md` or any `dev/docs` path is
  a **leak and a real finding** — the user cannot open it. The fact goes in the
  user doc; the evidence pointer goes in the developer doc.
- **Behaviour changes must land in the user docs in the same change** —
  `docs/usage.md` (CLI reference) and `docs/leveldesign/`. A new verb or changed
  flag with no doc update is a finding.
- **Every claim about how UnrealEd behaves carries its evidence** — a `spikes/`
  citation, and a date on any live finding. An undated, uncited engine assertion is
  a finding. Facts in `dev/docs/unrealed/*.md` carry a confidence marker: ✅
  live-verified, 🔬 live-probed, 📖 extracted from the binary string table.
- **A board item's `spec.md` and `plan.md` are ephemeral** — per-feature scratch
  under `dev/docs/board/<stage>/<slug>/`, expected to go stale. `direction/`,
  `rationale/`, `architecture.md`, `unrealed/` and `spikes/` are durable. A durable
  doc pointing at a spec for its rationale is a finding — it should point at the
  owning `direction/` or `rationale/` topic.
- **`dev/docs/direction/` is owner-owned.** Agents may not write it without an
  explicit yes. Do not file "this direction doc is stale" as something the author
  should have fixed — the correct action there is to ask the owner, not to edit.
- **Markdown tables** pad every column to its widest cell *except the final one*,
  which stays unpadded.

## Tests

Run via **`bin/test`**, never bare `pytest`. uedcli and its suite are
**host-native, not containerised** — only the editor/build containers uedcli
*drives* run under Docker. A permanently-red test is repaired or skipped, never
left red. Full rules: `dev/docs/rules/tests.md`.

## Read these before reviewing, by path

You do **not** inherit the dispatching agent's reading. Read what your artifact
touches, before you judge it:

| Read it when the artifact touches | Doc |
|-----------------------------------|---
| any uedcli code or design question | `dev/docs/architecture.md` |
| game-runtime / DLL behaviour, or RE workflow | `dev/docs/engine-internals/gotchas.md` |
| T3D authoring/parsing, surfaces, geometry | `dev/docs/unrealed/t3d.md` |
| driving UnrealEd, or debugging its behaviour | `dev/docs/unrealed/quirks.md` |
| the editor console | `dev/docs/unrealed/commands.md` |
| screenshots or rendering | `dev/docs/unrealed/rendering.md` |
| tests | `dev/docs/rules/tests.md` |
| a spike | `dev/docs/rules/spikes.md` |
| background jobs or long waits | `dev/docs/rules/background-work.md` |

Never answer a question about UnrealEd behaviour, the T3D format or uedcli
internals from memory — the editor is undocumented, and these docs are the only
ground truth.

## What counts as a finding

There is no severity scale. The test is **observability**:

> A finding may be left standing only if fixing it would change nothing anyone
> would ever observe — pure wording, formatting, or naming taste.

Report everything above that line. Rank most severe first. For each finding give
the file, the line, one sentence stating the defect, and a concrete failure
scenario — inputs or state, and the wrong output or crash that results. A finding
you cannot state a failure scenario for is probably taste; say so rather than
inflating it.

Be adversarial about your own findings before reporting them: check the code
actually does what you think it does. A confident, wrong finding costs more than a
missed one, because it gets acted on.

## What you are not told, on purpose

You are **not** shown what any previous round found, and you are not told what to
look for. That is deliberate — a reviewer told what was already found stops
looking for what wasn't. If you are given a diff alongside the full artifact, the
diff is orientation, not scope: **a finding anywhere in the artifact counts**, not
only inside the diff.
