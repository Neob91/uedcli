# Designing a tool surface an LLM agent drives well

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** what does current published evidence say about shaping a tool surface for LLM agents, and where do uedcli's CLI conventions agree or disagree with it?

## Summary

- The core premise holds. Anthropic's Claude Code guidance states plainly: "CLI tools are the most
  context-efficient way to interact with external services," and "Claude is also effective at
  learning CLI tools it doesn't already know. Try prompts like `Use 'foo-cli-tool --help' to learn
  about foo tool, then use it to solve A, B, C.`" uedcli's whole bet — a strict CLI plus good
  `--help` — is the pattern that writing recommends.
- The thing that breaks at uedcli's size is not the CLI, it is a *tool-call* surface over it. Tool
  selection accuracy "degrades once you exceed 30–50 available tools"; uedcli has **124 leaf verbs**.
  A naive one-tool-per-verb MCP server is squarely in the degraded regime, and the measured remedy
  (tool search + `defer_loading`) is a reimplementation of what `--help` already does for free.
- Token numbers are now public and concrete: a 5-server MCP setup costs "~55k tokens in definitions
  before Claude does any work"; tool search cuts that "by over 85 percent"; selection accuracy on
  one internal benchmark moved 79.5% → 88.1% (Opus 4.5) and 49% → 74% (Opus 4). uedcli's full
  `--help` tree is **272,448 chars ≈ 68k tokens** — the same order as that 55k figure, except
  uedcli's is already lazily loadable one page at a time.
- Progressive disclosure is the explicitly recommended shape, and uedcli's help tree already has it:
  root `--help` is 3,609 chars (~900 tokens); root + all 17 family index pages is 28,390 chars
  (~7.1k); a realistic three-level path (root → `brush` → `brush build` → `brush build cube`) is
  **13,193 chars ≈ 3.3k tokens**. An agent never pays the 68k.
- `docs list|show|search` over the 125-page / ~984 KB (~246k token) `old/docs/` corpus is the same
  pattern again, and it matches the published "just in time" retrieval principle — keep "lightweight
  identifiers" in context, fetch the page on demand. The specific *tool-serves-its-own-docs* shape is
  not named in any source I found; the underlying principle is well supported. Mark as analogous, not
  directly validated.
- uedcli exposes **no MCP server** today. `mcp` appears exactly once in `old/`, in
  `old/dev/evals/EVAL-PROCEDURE.md`, and not as an implementation. `uedcli serve`
  (`old/uedcli/serve/`, ~190 KB) is a **read-only FastAPI/WS backend for the human browser GUI** —
  scene, wireframe, textures, lightmap atlas, sessions, snapshots. It is not an agent surface and
  "never writes the trunk."
- `old/dev/docs/superpowers/` is **not** agent-facing design material: it is the output dump of the
  `superpowers` plugin's spec/plan skills — 6 `specs/` + 6 `plans/` dated files for past work items.
  It bears on *how* uedcli is built, not on how its surface is shaped.
- `actor survey` and `actor diagram` are the project's clearest statement of agent ergonomics:
  survey turns geometry into a flat `<src> --relation--> <dst>` fact list (eyes replaced by a
  vocabulary); diagram renders labelled images and also emits `--json` identity so the picture is
  readable as text. Published 3D work (SceneCraft, Holodeck) converges on the same answer — LLMs
  author 3D through a **scene graph / relational constraints**, not pixels. Evidence is thin and all
  from asset-placement research, none from BSP/CSG level design.
- Two conventions have no external backing either way and are worth raising: **no `--json` on
  producers that lack a consumer** (YAGNI) and **no dry-run anywhere**. The first collides with
  "agents parse JSON lines more reliably than prose"; the second collides with "give Claude a check
  it can run."

## What we have today

Measured by introspecting `uedcli.cli.main.build_parser()` directly (stdlib only):

| | count |
|---|---|
| parser nodes | 154 |
| leaf (invocable) verbs | 124 |
| optional flags (total / on leaves) | 662 / 630 |
| top-level families | 17 |
| flags with no `help=` | **0** |
| full `--help` tree | 272,448 chars ≈ 68k tokens |
| root `--help` | 3,609 chars |
| largest single page (`actor diagram`) | 14,178 chars |

| family | verbs | flags | help chars | family index page |
|---|---|---|---|---|
| `brush` | 29 | 215 | 98,772 | 2,841 |
| `actor` | 27 | 133 | 65,626 | 4,846 |
| `level` | 9 | 41 | 16,644 | 3,446 |
| `class` | 9 | 42 | 15,592 | 3,412 |
| `texture` | 9 | 47 | 12,556 | 2,389 |
| `stash` | 7 | 36 | 17,393 | 644 |
| `prefab` | 5 | 27 | 15,691 | 749 |
| `sound` | 7 | 22 | 6,063 | 1,458 |
| `music` | 7 | 22 | 6,134 | 1,514 |
| `mover` | 5 | 19 | 6,510 | 198 |
| `docs` | 3 | 5 | 1,762 | 526 |
| `cache` | 2 | 4 | 1,533 | 899 |
| `event` | 1 | 4 | 1,422 | 577 |
| `uscript` | 1 | 5 | 1,530 | 344 |
| `substrate` | 1 | 3 | 627 | 227 |
| `project` | 1 | 2 | 595 | 322 |
| `serve` | 1 | 3 | 389 | 389 |

Other surfaces: `old/uedcli/userdocs.py` (412 lines) serves `old/docs/` — 125 markdown pages,
983,877 chars (~246k tokens) — through `docs list|show|search`. `old/uedcli/serve/` (~190 KB, 16
modules) is the GUI's read-only HTTP/WS backend. No MCP server, no tool-call schema, no SDK binding.

## Findings

### 1. uedcli's conventions, as an explicit rule list

Every citation is `old/CLAUDE.md` "Code & CLI conventions" (C) or
`old/dev/docs/direction/conventions.md` (D).

| # | Rule | Cite |
|---|---|---|
| R1 | Producer/query verbs print the result to stdout, **one item per line**; human summaries and counts go to stderr | C, D "Verbs compose" |
| R2 | `--json` is added **where a caller needs structure** — not speculatively | C, D |
| R3 | Mutating verbs read their target set from stdin via `-`, the **sole** names source, mutually exclusive with CLI args; empty stdin is a clean no-op (exit 0) | C, D |
| R4 | Exactly **two** stdin conventions, disambiguated by verb: a newline name list (`find → mutate -`) and a T3D snippet (`build → add -`). One calibrated exception: `classify set -` reads JSONL | C, D |
| R5 | A verb over a set **takes the set, and that is the operation** — no flag restating it (`actor bbox` has no `--union`) | C, D |
| R6 | Prefer one stateless `find`/query verb feeding the others over per-verb `--only-*` filter flags | C, D; `--only-groups`/`--only-actors` listed under *Rejected* |
| R7 | `find` vs `search` never merged: `find` is deterministic over concrete T3D state and yields a pipeable name set; `search` is ranked/fuzzy over a catalog or corpus | C, D |
| R8 | **No fallbacks, no silent half-answers.** A verb that cannot fully satisfy a request **exits 2 naming the offending value** — never a partial result plus a stderr note | C, D |
| R9 | No `--force` / `--allow-partial` for partial answers: "a flag to opt into a wrong answer is still a wrong answer" | D |
| R10 | Never branch on environment (arch, OS, env var, tool presence) — same code path, same output, every host | C, D |
| R11 | A batch is all-or-nothing: collect all misses and report the full set | D |
| R12 | An exact name matching nothing is an error; an **empty glob/set result is not** (empty stdout, exit 0) — empty selection is legitimate pipeline data | D |
| R13 | No Python exception ever reaches the user; a bad name exits non-zero naming it, with a regression test | C, D |
| R14 | Every command, flag and argument carries a real `help=` saying what it does | C, D |
| R15 | **YAGNI on output surface** — a new verb ships only what its use case needs | C |
| R16 | No back-compat cruft: a removed flag/verb/format is deleted in the commit that replaces it | C, D |
| R17 | Model-side by default — the editor is touched only to build or photo | D |
| R18 | Never write over an existing destination silently; refuse (exit 2) plus one explicit opt-in (`--overwrite`, `--force`); git is the only recovery route | `old/dev/docs/direction/safety.md` |

### 2. The `--json` split

43 of 124 leaf verbs carry `--json`; 81 do not. The split largely tracks R1/R2/R15:

- Verbs **with** it are query/report verbs whose output is not a bare name list — `actor bbox`,
  `actor rank`, `actor prop get`, `actor folder get`, `actor label get`, `brush vertex list`,
  `mover key list`, `level doctor`, `level status`, every `* classify status|tags` and
  `* search|list|show` in the catalog families, `docs list`, `docs search`, `event graph`,
  `uscript compile`, `actor find`, `brush poly find`, `actor relation find`, the three `diagram`
  verbs, `project show`, `class preview`.
- Verbs **without** it are mutators (`actor move`, `brush clip`, `brush poly pan`, …) and T3D
  producers whose stdout *is* the pipe payload (`actor show`, the eight `brush build *`) — both
  correct under R3/R4: a mutator has no result set to serialize, and a T3D snippet is already the
  agreed interchange format.

Three places where the split looks like drift rather than rule:

- `stash list` and `prefab list` have no `--json`, while `level list`, `class list`,
  `texture list`, `sound list` and `music list` do. Same noun shape, different surface.
- `actor survey` — a two-tier structured report — has only prose lines. Its sibling
  `actor relation find` has `--json`.
- Per the sibling note `dev/research/rust-cli-surface-and-argparse-parity.md`, `--json` already has
  **three incompatible output shapes** across those 43 verbs (compact JSONL rows, a pretty object, a
  pretty array) and 33 distinct help texts. R2/R15 kept the surface small but not uniform.

### 3. MCP: what exists today

Nothing. `grep -rniE 'model context protocol|\bmcp\b' old/` returns one hit,
`old/dev/evals/EVAL-PROCEDURE.md:47`, describing Claude Code's own plugin/MCP support in the eval
harness context — not a uedcli server.

`uedcli serve` is unrelated to agents. Its own docstring: "read-only HTTP/WS GUI backend… Wraps the
model-side library over FastAPI+uvicorn; never writes the trunk." Routes serve scene and wireframe
payloads, a texture atlas, a lightmap atlas, levels, sessions, staged snapshots and edit staging for
a localhost browser client. Treating it as an agent API would be a repurposing, not a doc fix.

### 4. `old/dev/docs/superpowers/`

Twelve files: `specs/` (6) and `plans/` (6), dated 2026-08-29 → 2026-09-19, covering level reimport,
brush measure/relation, `level graph`, the standalone binary build, PF FakeBackdrop, and a
`usage.md` split. These are artifacts the `superpowers` plugin's spec/plan skills wrote during past
work items — the directory is named after the plugin, not a subject (`old/uedcli/actorgraph.py`
cites one as its design doc). It bears on agent-driven *development process*, not on uedcli's
agent-facing surface.

### 5. `actor survey` and `actor diagram` — spatial awareness without eyes

`actor survey NAME` prints "every spatial fact uedcli can compute about one actor," in two tiers
with disjoint relation vocabularies. Lines read subject–relation–object, bare:

```
<src> [Package.Class[ Kind]] --<relation>--> <dst> [Package.Class[ Kind]]
```

Raw facts are authored geometry (`encloses`, `overlaps`, `meets`, `touches`, `coincides`); csg facts
are the post-solve world (`crosses`, `occupies`, `carves`, `connects`). The tiers are told apart by
fixed print order and by relation names being unique per tier — no prefix. Scope is deliberately one
actor, "never a set," because both tiers run over a bounded neighborhood, which keeps cost flat.

This is R1 applied to geometry: a spatial question answered as a line-per-fact stream an agent can
grep, diff and pipe, with no image and no magnitudes. `level graph` is the whole-level cheap
counterpart; `actor relation find` is the ranked pairwise query (and the one with `--json`).

`actor diagram` is the complement — it renders, but it also hands back the mapping. Its stated
purpose is to "see geometry and map **poly index ↔ face**," `--annotate` numbers faces, and
`--layout breakdown` walks the scene actor by actor with captioned panes. So the image is an index
into the text model rather than the model itself.

### 6. External: CLI vs MCP for agent tool use

**For the CLI.** Claude Code's best-practices page is the strongest direct statement: CLI tools are
"the most context-efficient way to interact with external services," and an agent can be told to
learn an unknown one from its own `--help`. Separately, Anthropic's agent-design guidance frames the
choice as *breadth vs. hooks*: "A **bash tool** gives Claude broad programmatic leverage… But it
gives the harness only an opaque command string… Promoting an action to a **dedicated tool** gives
the harness an action-specific hook with typed arguments it can intercept, gate, render, or audit."
Its rule of thumb: "**Start with bash for breadth. Promote to dedicated tools when you need to gate,
render, audit, or parallelize the action.**"

**For MCP / dedicated tools.** The named wins are exactly those four: gating hard-to-reverse actions
behind confirmation ("A `send_email` tool is easy to gate; `bash -c \"curl -X POST ...\"` is not"),
staleness checks a bash call cannot enforce, custom rendering, and parallel-safety scheduling ("the
harness can't tell a parallel-safe `grep` from a parallel-unsafe `git push`, so it must serialize").
Claude Code's own feature matrix puts MCP at "Connect to external services… Query your database,
post to Slack, control a browser" — not "wrap a local CLI."

**The hybrid.** Anthropic's code-execution-with-MCP post is the canonical "the CLI is the tool"
argument in MCP's own frame: present tools as files in a directory an agent explores, let it "load
only the tools they need," and keep intermediate results "in the execution environment by default"
so the agent "only see[s] what you explicitly log or return." One worked case goes from "150,000
tokens to 2,000 tokens… a 98.7% time and cost saving." A shell pipeline is that pattern natively:
`actor find … | actor bbox -` never puts the intermediate name list in context unless asked.

### 7. Token economy of a tool surface

| claim | source |
|---|---|
| A 5-server MCP setup (GitHub, Slack, Sentry, Grafana, Splunk) "can consume ~55k tokens in definitions before Claude does any work" | tool-search-tool docs |
| Tool search "typically reduces this by over 85 percent, loading only the 3–5 tools Claude needs" | same |
| "Claude's ability to pick the right tool degrades once you exceed 30–50 available tools" | same |
| Use tool search at "10 or more tools" or ">10k tokens" of definitions; standard calling is better "when you have fewer than 10 tools" | same |
| Tool search accuracy: 49% → 74% (Opus 4), 79.5% → 88.1% (Opus 4.5) | advanced-tool-use post |
| Programmatic tool calling: 43,588 → 27,297 tokens average, "a 37% reduction on complex research tasks" | same |
| Tool-use examples: accuracy 72% → 90% "on complex parameter handling" | same |
| Claude Code caps tool responses at 25,000 tokens by default; a `ResponseFormat` enum let one case use "⅓ of the tokens with `concise` tool responses" | writing-tools-for-agents |
| "context rot": models have an "attention budget" with diminishing returns as context grows | effective-context-engineering |
| Prefer "just in time" retrieval holding "lightweight identifiers (file paths, stored queries, web links)" over pre-loading | same |
| Aim for the "smallest possible set of high-signal tokens"; overlapping tools are a known failure — "if a human engineer can't definitively say which tool should be used," the agent can't either | same |

Relating that to the measured 68k help tree: the number is only alarming if something loads it all.
Nothing does. Root is ~900 tokens, the 17 family index pages add ~6.2k, and a working path to a leaf
is ~3.3k. That is *below* the 10k threshold the tool-search docs give for needing deferred loading.
Conversely, a one-tool-per-verb MCP server would put 124 schemas in the "degrades past 30–50" band
and would need tool search to claw back what `--help` gives for nothing.

The "overlapping tools" failure is the one real risk at 124 verbs, and R6/R7 are the mitigations:
one `find` instead of per-verb filters, and a hard `find`/`search` split so an agent choosing
between two name-producing verbs is never a coin flip.

### 8. Output design for agents

- **Lines vs JSON vs JSONL.** No source I found ranks them. The explicit position is
  writing-tools-for-agents: "there is no one-size-fits-all solution" across XML, JSON and Markdown;
  "LLMs perform better with formats matching their training data, so evaluation-driven selection is
  essential." So R1 (one item per line) is defensible, and so is R2 (`--json` on demand) — but
  **neither is externally validated as better**, and the house rule's own cost is the three
  incompatible `--json` shapes noted above. Claude Code's non-interactive mode offers
  `--output-format stream-json`, which "prints one JSON object per line" — JSONL as the structured
  stream format is at least Anthropic's own choice for a CLI, which is some support for uedcli's
  `classify set -` exception.
- **Tables.** No evidence either way on agents parsing tables reliably. Unverified. Note that
  uedcli's own `--json` help texts flag the pain point (`actor folder get --json` exists so scripts
  "would otherwise choke on the sentinel" `(none)`) — a real signal that sentinel-bearing text output
  is fragile, independent of tables.
- **Errors as self-correction.** Directly supported. "Rather than opaque error codes, craft error
  responses that clearly communicate specific and actionable improvements," with truncation messages
  that "steer agents toward more efficient strategies like targeted filtering." R8 (exit 2 naming the
  offending value) and R13 (never a traceback) are exactly this, and R11 (report the full miss set)
  is stronger than the published advice.
- **Idempotency / dry-run / making a destructive verb safe.** The strongest applicable statement is
  Claude Code's: "Give Claude a check it can run… Claude stops when the work looks done. Without a
  check it can run, 'looks done' is the only signal available." Plus reversibility as the gating
  criterion in the agent-design guidance. uedcli has **no `--dry-run` flag anywhere** (grep over
  `old/uedcli/cli/` finds none). What it has instead: git as the sole recovery route, default-refuse
  on an existing destination with a single explicit opt-in, delta writes, per-level `flock`,
  same-actor conflict detection that "exits 2 naming the conflicting actors and writes nothing," and
  atomic per-actor replace. For an autonomous agent inside a git worktree that is arguably stronger
  than a dry-run — but it means the pre-flight check an agent can run is `git diff`, which the CLI
  does not offer and does not document as the pattern.

### 9. Discovery, `--help` quality, and a tool serving its own docs

- `--help` as the agent's discovery channel is explicitly endorsed (the "learn `foo-cli-tool --help`"
  prompt). R14 (zero flags without real `help=`, measured and upheld) is the load-bearing convention
  for that, and the one that makes the 68k tree an asset rather than noise.
- Self-describing schemas: Claude Code's context-cost table says MCP loads "tool names and server
  instructions" at session start with "full JSON schemas… deferred until Claude needs a specific
  tool." That is a subcommand tree with lazy `--help` by another name.
- Bundled docs served by the tool: `docs list|show|search` matches the published just-in-time and
  progressive-disclosure principle well — "lightweight identifiers" are the topic keys, and
  `docs search`'s ranking is the retrieval step over ~246k tokens of prose. The adjacent validated
  pattern is Skills: "Each skill is a folder with a `SKILL.md`. The skill's description sits in
  context by default; Claude reads the full file when the task calls for it." uedcli's ruling that a
  shipped skill "**queries the tool** and ships **zero** copies of the docs"
  (`old/dev/docs/direction/documentation.md`) is one step further than any source I found states —
  the board item `skills-plugin-distribution-via-repo-as-its-own` is where it gets tested. Mark the
  specific pattern **analogous, not validated**.

### 10. LLM agents doing 3D / spatial authoring

Thin, and all of it adjacent rather than on-point. What exists converges on one answer:

| work | representation | relevance |
|---|---|---|
| SceneCraft (arXiv 2403.01248, Hu et al.) — LLM agent writing Blender Python for scenes of up to ~100 assets | a **scene graph** of "spatial relationships among assets," compiled to numerical placement constraints; a learned reusable function library; VLM-in-the-loop refinement on renders | strongest match to `actor survey`'s relation vocabulary + `actor diagram` as the visual check |
| Holodeck (CVPR 2024, arXiv 2312.09067, Yang et al.) — language-guided 3D embodied environments | GPT-4 emits "spatial relational constraints between objects," then a solver optimizes positions | same shape: the LLM produces *relations*, a deterministic solver produces *coordinates* |

Caveats, plainly: both are **asset-placement** systems over an asset library, not constructive solid
geometry; neither addresses brush CSG, BSP, or editing an existing level; both predate current
models; I found no published work on LLMs authoring UE1-style subtractive geometry. The one
transferable finding: where measured, LLMs do better emitting *relations* than coordinates, and
images serve as a verification channel rather than the representation. That is the architecture
uedcli already has — `actor survey` / `level graph` for relations, authored `Location` taken as-is
(`old/dev/docs/direction/conventions.md`), `actor diagram` for the check. Convergent design, not
validation.

### 11. Conventions × external evidence

| Rule | Evidence for | Evidence against / gap |
|---|---|---|
| R1 one item per line, summaries to stderr | "no one-size-fits-all" format guidance leaves it open; keeps the pipe payload at the "smallest set of high-signal tokens" | nothing says lines beat JSONL; sentinel values in line output are a known fragility (`--json` on `actor folder get` exists because of one) |
| R2 + R15 `--json` only where a caller needs it | "smallest possible set of high-signal tokens"; Claude Code's own `--output-format` is opt-in | three incompatible `--json` shapes and 33 help texts is the cost of per-verb judgement; `stash list`/`prefab list`/`actor survey` read as gaps |
| R3 stdin `-` as the sole names source | composition keeps intermediates out of context — the same win code-execution-with-MCP measures at 150k → 2k tokens | none found |
| R4 exactly two stdin conventions | "if a human engineer can't definitively say which tool should be used," neither can the agent — a bounded convention set is that principle applied to argument shape | the `classify set -` JSONL exception is the thin end; a third convention is where the rule would start costing |
| R5 the set *is* the operation | fewer, non-overlapping parameters; tool-use-examples finding (72% → 90%) shows parameter handling is where agents fail | none found |
| R6 one `find`, no `--only-*` | directly matches tool consolidation ("combine related operations") and the overlapping-tools failure mode | consolidation guidance also warns the *opposite* way — a single tool doing multiple steps internally is preferred over three the agent must sequence; R6 pushes work onto the pipeline instead |
| R7 `find` vs `search` split | disambiguation is the stated cure for selection failure; namespacing by prefix is explicitly recommended | the names are not self-evident to a cold agent; discoverability rests entirely on R14 |
| R8 + R9 no fallbacks, exit 2 naming the value | "craft error responses that clearly communicate specific and actionable improvements" | an agent that cannot proceed burns a turn per refusal; no source measures refuse-vs-degrade for agents |
| R11 batch all-or-nothing, full miss set | self-correction in one round trip instead of N | none found |
| R12 empty result is data, not an error | matches treating an empty tool result as legitimate | none found |
| R13 no traceback ever | error-as-guidance | none found |
| R14 every flag has real help | "learn `foo-cli-tool --help`"; MCP's own model defers full schemas to on-demand `--help`-equivalents | help quality is unmeasured — 0 missing `help=` is a floor, not a quality metric |
| R16 no back-compat cruft | smaller surface, no stale-help bug class | agents are trained on *historical* spellings; a deleted flag spelling an agent recalls fails hard. R8 makes that a clean exit 2, which is the right failure, but it is a real cost of R16 |
| R17 model-side by default | deterministic, no external state to desync | none found |
| R18 refuse-then-opt-in, git as recovery | reversibility is the published gating criterion for a destructive action | no dry-run and no `--check`; "give Claude a check it can run" is satisfied only by `git diff`, which uedcli neither offers nor documents as the pattern |

## Options

The CLI/MCP question, framed as what uedcli could expose to an agent.

| Option | Pros | Cons |
|---|---|---|
| **A. CLI only (status quo)** | Matches "CLI tools are the most context-efficient way"; progressive disclosure already works (~3.3k tokens per working path); zero new surface to keep true (R16); composition keeps intermediates out of context; one implementation for humans and agents | No typed schemas, so no harness-side gating, staleness check, or parallel-safety marking; every agent rediscovers the verb tree from `--help`; a mis-spelled flag is a turn burned |
| **B. MCP server, one tool per verb** | Typed args reduce the parameter errors the tool-use-examples finding measures (72% → 90%); harness can gate the destructive verbs; discovery without `--help` | 124 tools is deep in the "degrades past 30–50" band; definitions would rival the ~55k-token 5-server figure; needs tool search to be usable at all; a second surface to keep true, which R16 exists to prevent; duplicates `--help` |
| **C. MCP server, a handful of coarse tools** (e.g. `uedcli_run`, `uedcli_help`, `uedcli_docs`) | Under the 10-tool threshold where standard calling is recommended; gives the harness a hook to gate mutating runs; the CLI stays the single implementation (the "code execution" pattern in MCP's frame) | A command string is "opaque… the same shape for every action" — most of the gating benefit evaporates unless the wrapper parses the verb; near-duplicate of a plain bash allowlist; new surface to maintain |
| **D. CLI + a Claude Code skills plugin** (the shape already decided on the board) | Thin per-task skills (~15 lines) load on description and pull full guidance on demand — the validated Skills pattern; `docs search` keeps one source of truth, zero doc copies; no tool-call surface at all | Skill descriptions cost context every session; distribution is blocked on the standalone-repo extraction; teaches verb *selection* but not flag spelling, which stays a `--help` round trip |
| **E. CLI + a narrow query/report hardening pass** (no new protocol): fill the `--json` gaps, unify the three JSON shapes, add a cheap pre-flight an agent can run | Addresses the two concrete gaps evidence points at (structured output uniformity, a runnable check) without adding a surface; stays inside existing conventions | Collides with R15 (YAGNI) and R2 — "a caller needs it" would have to mean "an agent needs it," which is an owner ruling, not a reading |

## Proposal (owner's call — not decided)

Keep **A**, pursue **D** as already planned, and raise **E** as three narrow questions rather than a
change. The evidence does not support building an MCP server: at 124 verbs option B lands in the
measured degradation band, and option C's gating benefit is largely illusory for a command-string
wrapper. The CLI-plus-`--help`-plus-served-docs shape uedcli already has is the pattern Anthropic's
own guidance recommends, and its token profile (~3.3k per working path) is comfortably under the
threshold at which deferred loading becomes necessary.

## Open questions / what to verify next

1. **Does "a caller needs structure" (R2) include an LLM agent?** If yes, `stash list`,
   `prefab list` and `actor survey` are gaps; if no, they are correct and the other 43 are the
   anomaly. Owner ruling either way.
2. **Should the three `--json` shapes be unified?** Agents parsing one verb's output do not care;
   agents writing a pipeline across several do. Unifying is an R16-clean change (delete the old
   spelling) but touches 43 verbs.
3. **Is "give Claude a check it can run" satisfied by git alone?** R18 deliberately has no dry-run.
   Options short of a `--dry-run` flag: document `git diff` as the pre-flight in `docs/usage/`, or
   treat `level doctor` as the post-mutation check. Both are documentation, not code.
4. **Does R16 have an agent-specific cost worth measuring?** An agent may recall a deleted flag
   spelling; R8 turns that into a clean exit 2 — measurable as turns-wasted-per-task if wanted.
5. **Unverified:** whether agents parse markdown tables reliably — no source found. Relevant to
   `level doctor` / `actor rank` text output.
6. **Unverified:** whether a tool serving its own docs (`docs search`) beats bundled skill
   references. A before/after on `old/dev/evals/` would settle it.
7. **Thin evidence:** nothing published covers LLMs authoring CSG/BSP geometry. uedcli's own eval
   harness is the only instrument that will answer it.

## Sources

- https://www.anthropic.com/engineering/writing-tools-for-agents — tool consolidation, namespacing,
  semantic identifiers, pagination/truncation, `ResponseFormat` concise vs detailed (~⅓ the tokens),
  Claude Code's 25,000-token response cap, "no one-size-fits-all" on output format, errors as
  actionable guidance.
- https://www.anthropic.com/engineering/code-execution-with-mcp — definitions "overload the context
  window"; filesystem-as-API; progressive disclosure; intermediate results staying out of context;
  the 150,000 → 2,000 token / 98.7% case.
- https://www.anthropic.com/engineering/advanced-tool-use — tool search 85% context saving and
  49%→74% / 79.5%→88.1% accuracy; programmatic tool calling 43,588→27,297 tokens (37%); tool-use
  examples 72%→90%.
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents — context rot
  and the attention budget; just-in-time retrieval with lightweight identifiers; smallest set of
  high-signal tokens; the overlapping-tools failure test.
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool — the ~55k-token
  5-server figure, >85% reduction, the 30–50 tool accuracy cliff, `defer_loading` mechanics, and the
  "when to use / when not to" thresholds (≥10 tools or >10k tokens; standard calling under 10).
- https://code.claude.com/docs/en/best-practices — "CLI tools are the most context-efficient way to
  interact with external services"; learning an unknown CLI from `--help`; "Give Claude a way to
  verify its work"; `--output-format stream-json` as one JSON object per line; subagents for keeping
  exploration out of context.
- https://code.claude.com/docs/en/features-overview — per-feature context-cost table (MCP loads
  names at start, schemas deferred; skills load descriptions then full content); MCP-vs-skill split.
- Anthropic `claude-api` skill, `shared/agent-design.md` (bundled, version 2.1.261) — bash vs
  dedicated tools and the four promotion criteria (gate, render, audit, parallelize); tool search
  appending rather than swapping definitions to preserve cache.
- https://arxiv.org/abs/2403.01248 — SceneCraft: scene graph → numerical constraints → Blender
  Python; VLM-in-the-loop refinement; library learning. **Asset placement, not CSG.**
- https://arxiv.org/abs/2312.09067 — Holodeck: GPT-4 emits spatial relational constraints, a solver
  places objects; human annotators prefer it to procedural baselines in residential scenes.
  **Asset placement, not CSG.**
- Internal: `old/CLAUDE.md`; `old/dev/docs/direction/` (`conventions.md`, `documentation.md`,
  `safety.md`, `README.md`); `old/README.md`; `old/uedcli/userdocs.py`; `old/uedcli/serve/`
  (`__init__.py`, `app.py`); `old/uedcli/actor_survey.py`; `old/uedcli/cli/parsers/docs.py`;
  `old/docs/reference/actor/` (`survey.md`, `diagram.md`); the two board items named in the task;
  `dev/research/rust-cli-surface-and-argparse-parity.md`.
