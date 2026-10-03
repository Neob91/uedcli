# The Rust CLI surface — argparse parity, clap, and help/UX fidelity

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** what Rust CLI machinery reproduces `old/`'s argparse surface exactly, and where will it fight us?

## Summary

- The surface is 154 parsers / 124 invocable verbs / 507 flag actions / 104 positionals / 150
  distinct option spellings, max depth 4 (`brush poly align wall`). Two families carry half of it:
  `brush` (29 verbs, 186 flags) and `actor` (27 verbs, 106 flags).
- Help text is the bulk of the work, not parsing: 766 `help=` strings, 133 KB of prose, rendering to
  272 KB / 4,577 lines across 154 screens. The largest single screen (`actor diagram`) is 202 lines.
- A parity oracle already exists and is git-tracked: `old/uedcli/tests/fixtures/parser_baseline/`
  holds `help.json` (all 154 screens, pinned at `COLUMNS=80`, 272,448 chars — matches a fresh
  measurement exactly), `action_tree.json` (611 KB normalized parser tree) and `argv_corpus.json`
  (22 accept/reject cases). It is data, so it survives `old/`'s retirement.
- Byte-identical `--help` is a *reimplementation of `argparse.HelpFormatter`*, not a clap
  configuration: width is `terminal_columns - 2`, the help column is `min(24, max(width-20, 4))`,
  and wrapping uses `textwrap.wrap` defaults — breaking *inside* words and *on hyphens*. All three
  are observable in `old/`'s output today, so byte identity is pinned to one width, locale and
  CPython version.
- Nothing in the rewrite spec commits to help parity after a verb is ported. The one
  "byte-identical" sentence is scoped to PR #1's plumbing, and `tests/proxy.rs` asserting it is
  tautological: `src/main.rs` `exec`s `old/bin/uedcli`, so the test compares that binary to itself.
  Open owner question, not a settled constraint.
- Exit codes are **0, 2, and 1**. The 1 is a single site — `level doctor` returns 1 when findings
  reach `Severity.ERROR` (`old/uedcli/cli/commands/level.py:788`), documented in that verb's own
  help. Everything else is 0 (incl. `BrokenPipeError`) or 2. `_SelectionExit` does not exist in code
  — it survives only in `old/dev/docs/` prose; the live types are
  `CommandError`/`ProjectError`/`LevelSelectionError`.
- Two argparse behaviors are load-bearing and clap does not reproduce: **prefix abbreviation**
  (`--jso` → `--json`; `allow_abbrev=False` is set on exactly 3 parsers *because* abbreviation is
  otherwise on and would resurrect a retired flag spelling) and the **`_CoordArgumentParser`
  `_parse_optional` override**, which makes `-32,-32,32` and `-128` parse as values.
- Shared `Args` fragments buy less than it looks: of 72 options on more than one verb, only 28 have
  one identical signature everywhere. `--json` is on 43 verbs with 33 distinct help texts; `--by` on
  11 verbs with 11 distinct signatures. And `--json` already has three incompatible output shapes
  (compact JSONL rows, a pretty object, a pretty array).
- `clap` 4.6 handles the *parsing* side cleanly — runtime-built subcommands, `ArgGroup` for the 35
  mutex groups, `num_args` for `nargs`, `ValueEnum` for the 17 choice sets, bare `-` as a positional
  value unconfigured, `ErrorFormatter` for exact stderr text, and `USAGE_CODE = 2` already matching
  argparse. It is the only credible crate at this size; `bpaf` is the one real alternative,
  everything smaller (`argh`/`gumdrop`/`xflags`/`pico-args`/`lexopt`) generates no help or is
  unmaintained.
- `clap` cannot reproduce argparse's help *through its renderer*: different alignment algorithm (no
  24-column cap, no per-entry overflow line), hardcoded `Usage:`/`Arguments:`/`Options:` headings,
  mandatory `<NAME>`/`[NAME]` metavar brackets, `[OPTIONS]`-collapsed usage. Exact bytes need either
  `override_help` on all 154 nodes (a maintenance trap) or our own formatter over clap's reflection
  API — one implementation, with `help.json` as its fixture.
- `clap_complete` / `clap_mangen` are near-worthless for an agent caller. What would help is a
  `--schema` JSON dump built from clap's reflection getters: no crate is mature enough to depend on
  (`clap_schema` self-deprecates, OpenCLI is alpha), but the getters suffice to hand-roll it.

## What we have today

The CLI lives in `old/uedcli/cli/`: `main.py` (70 lines) builds the root parser and calls 17
`register(sub)` functions in `old/uedcli/cli/parsers/` (2,819 lines total; `brush.py` 656,
`actor.py` 506, `_arguments.py` 377). `old/uedcli/cli/dispatch.py` (195 lines) routes on
`args.cmd`/`args.sub` with function-local imports and wraps everything in one ordered
exception guard. Handlers are in `old/uedcli/cli/commands/` (3,331 lines in the top-level modules,
plus the `actor/` and `brush/` subpackages).

The new root is `src/main.rs` (18 lines): it `exec`s `old/bin/uedcli` with argv passed through.
`Cargo.toml` has **no dependencies** — no clap, no CLI crate anywhere in the repo (`old/uedcli-native`
uses `pyo3`/`rayon`/`serde_json` only).

### Measured surface

Walked from `uedcli.cli.main.build_parser()` on Python 3.12.13.

| family | leaf verbs | parser nodes | flag actions | max depth |
|---|---|---|---|---|
| `brush` | 29 | 34 | 186 | 4 |
| `actor` | 27 | 32 | 106 | 3 |
| `level` | 9 | 10 | 32 | 2 |
| `class` | 9 | 11 | 33 | 3 |
| `texture` | 9 | 11 | 38 | 3 |
| `sound` | 7 | 9 | 15 | 3 |
| `music` | 7 | 9 | 15 | 3 |
| `stash` | 7 | 8 | 29 | 2 |
| `mover` | 5 | 7 | 14 | 3 |
| `prefab` | 5 | 6 | 23 | 2 |
| `docs` | 3 | 4 | 2 | 2 |
| `cache` | 2 | 3 | 2 | 2 |
| `event`, `project`, `substrate`, `uscript`, `serve` | 1 each | 2,2,2,2,1 | 3,1,2,4,2 | 2 (`serve` 1) |
| **total** | **124** | **153** (+ root = 154) | **507** | **4** |

`sound` and `music` are the same registrar invoked twice (`old/uedcli/cli/parsers/music.py` is 12
lines) with `set_defaults(kind=noun)` — one code path, two nouns.

Group (non-leaf) nodes below a family: `actor folder|label|prop|relation`, `brush build|vertex|poly`,
`brush poly align`, `mover key`, `class|sound|music|texture classify`.

Fattest verbs by flag count: `actor diagram` (18), `stash diagram` / `prefab diagram` (17),
`actor find` (15), `brush build cylinder|cone|spiral` (15).

### argparse features in use

| feature | count | notes |
|---|---|---|
| `store` actions | 442 | |
| `store_true` | 118 | |
| `append` (repeatable flag) | 51 | |
| `store_false` | 1 | `brush apply-transform --no-lock-textures` |
| `required=True` subparsers | 12 families + nested | every group node |
| mutually exclusive groups | 35 | 4 of them `required=True` |
| `choices=` | 47 args | 17 distinct value sets |
| custom `type=` callables | 15 distinct | see below |
| `nargs` | `'+'` 27, `'*'` 27, `'?'` 11, `2` 1 | the `nargs=2` is `brush clip --plane`, tuple metavar `("PX,PY,PZ","NX,NY,NZ")` |
| `metavar=` | 308 sites | 59 distinct; `KIND/NAME` x50, `N` x24, `PATH` x21, `X,Y,Z` x20 |
| `help=argparse.SUPPRESS` | 2 | hidden `--all` on `class list` / `class show` (`dest="legacy_all"`) |
| `formatter_class=RawDescriptionHelpFormatter` + `epilog` | 2 | `actor relation` verbs |
| `allow_abbrev=False` | 3 | `actor diagram`, `stash diagram`, `prefab diagram` |
| subparser `aliases=`, `argparse.REMAINDER`, `parse_known_args` | **0** | no verb has an alias — consistent with the no-back-compat rule |

Custom `type=` callables, all in `old/uedcli/cli/parsers/_arguments.py` unless noted:
`parse_coord` (44 sites), `float` (32), `int` (27), `_nonempty` (19), `_csv` (9, defined three
times — `classes.py`, `sound.py`, `texture.py`), `_nonempty_class` (4), `parse_decimal` (3),
`str.lower` (3, paired with `choices` for case-insensitive enums), `parse_bbox` (2), `parse_pan` (2),
`parse_factor_pair` (2), `depth_value` (2, returns `int | math.inf` for `--depth all`), plus
`_top_arg`, `_hops_arg`, `_parse_footprint_list`.

Value DSLs are **not** argparse's problem: `--facing` (`flat|wall|ramp`, `nz:-1,1`, `wall;ny:0.7..1`)
has no `type=` and is parsed in `old/uedcli/facing_spec.py`; poly selectors (`BRUSH:IDX`) in
`old/uedcli/surface.py`. A Rust port can keep that split.

### The `-` stdin convention

Two readers, both in the CLI tier:

- `old/uedcli/cli/targets.py::resolve_target_names` — the newline name list (`find → mutate -`).
  37 call sites across 14 modules. `-` is the sole source (mixing it with names is a `CommandError`),
  blank lines dropped, a leading UTF-8 BOM stripped, empty stdin → `[]` → clean exit 0.
- `old/uedcli/cli/ingest.py::read_t3d_input` / `read_t3d_files` — the T3D snippet (`build → add -`),
  11 call sites. `--from-t3d <FILE…|->`, `-` again the sole value.

58 argument help strings across 56 of the 124 verbs mention stdin. `old/dev/docs/direction/conventions.md`
names one calibrated third convention: `classify set -` reads JSONL.

argparse accepts `-` as a positional value out of the box; `-12` and `-32,-32,32` are accepted only
because of the `_CoordArgumentParser._parse_optional` override — and all 154 parsers are
`_CoordArgumentParser` (`add_parser` inherits `parser_class` from the parser that owns the
subparsers action; confirmed in `action_tree.json`).

### Flag reuse across verbs

150 distinct option spellings; 72 appear on more than one verb; of those, only **28** have one
identical signature everywhere and **44** diverge.

Genuinely shareable: `--csg` (10 verbs), `--mover-class` (10), `--catalog-dir` (9), and the
`_preview_opts` block — 17 flags shared verbatim by `actor diagram` / `stash diagram` /
`prefab diagram` (`--layout`, `--view`, `--iso-angle`, `--mode`, `--brush-colors`, `--annotate`,
`--frame`, `--frame-tightness`, `--highlight`, `--focus`, `--show`, `--size`, `--locator-cells`,
`--no-locator-cells`, `--grid-size`, `--json`, `--out`); `actor diagram` adds only `--from-t3d`.

Not shareable: `--tree` (53 sites, 3 signatures — 49 `KIND/NAME`, 3 `level/NAME` from
`_tree_flag(level_only=True)`, 1 `level import` destination form), `--json` (43 verbs, **33**
distinct help texts), `--at` (15 verbs, 6 signatures), `--by` (11/11), `--to` (9/9),
`--force` (9/8).

### The existing parity oracle

`old/uedcli/tests/parser_baseline.py` + `old/uedcli/tests/fixtures/parser_baseline/`, added for an
earlier command-layer reorg and git-tracked since the `old/` move (`efa92961`):

| fixture | size | content |
|---|---|---|
| `help.json` | 282 KB | `{path → format_help()}` for all 154 parsers, `COLUMNS=80` pinned |
| `action_tree.json` | 612 KB | per-action class, option strings, dest, nargs, const, default, required, choices, metavar, converter name, mutex-group membership; recursive |
| `argv_corpus.json` | 17 KB | 22 argv cases with outcome, exit code, stdout, stderr, normalized namespace |
| `import_closure.json` | 218 B | the parser's non-CLI module closure |

`old/uedcli/tests/test_parser_baseline.py` replays and compares; regeneration is explicit
(`python -m uedcli.tests.parser_baseline`). The corpus deliberately covers negative coordinates,
`--facing` grammar, **prefix abbreviation**, required and non-required mutex violations, and multiple
simultaneous mistakes.

`old/uedcli/tests/test_help_completeness.py` enforces the `help=` rule structurally: non-blank, not
an echo of the flag name, ≥10 chars after strip.

## Findings

### What "byte-identical `--help`" actually requires

Help volume: 154 screens, 272,448 bytes, 4,577 lines at `COLUMNS=80`; mean 1,769 bytes/screen.
919 help strings (766 argument-level + 153 subcommand-level) totalling 157,740 chars; the
argument-level ones alone are 133,080 chars, median 113, max 1,281, 76 of them over 400 chars.
None contains a newline — every one is a single paragraph, so argparse's rewrapping is the only
thing that introduces line breaks. 275 contain non-ASCII (`—` ×286, `…` ×50, `°` ×28, `→` ×18,
`·` ×12, `⇒` ×5, `×` ×3, `±` ×2), 166 contain backticked examples, and 32 contain `{`/`}`.

Reproducing that byte-for-byte means reimplementing `argparse.HelpFormatter`, because the output is
not a fixed string — it is a function of five things:

1. **Terminal width.** `width = shutil.get_terminal_size().columns - 2` (`argparse.py:173`);
   `get_terminal_size()` honours `$COLUMNS`, then the tty, then falls back to 80. Verified:
   `actor bbox --help` gives a 4-line usage block at `COLUMNS=60`, 3 at 80, 1 at 120; piped with no
   `$COLUMNS` it is 80. `old/`'s own fixture pins 80 for exactly this reason.
2. **The help column.** `max_help_position = min(24, max(width - 20, indent_increment * 2))`
   (`argparse.py:178`). An invocation wider than 21 chars pushes its help onto the next line at
   indent 24 — visible on `--field {min,max,size,center}`.
3. **`textwrap` defaults.** `textwrap.wrap(text, width)` with `break_long_words=True` and
   `break_on_hyphens=True` (`argparse.py:657`). Both fire in real output: `newline-\nseparated`
   (hyphen break) and `mat\nerialize` (mid-word break of
   `create/import/…/doctor/graph` in the top-level `level` entry). A wrapper that does neither
   produces different bytes for a large share of the 766 strings.
4. **Section headers through gettext.** `self._optionals = add_group(_('options'))`
   (`argparse.py:1808`) — so `options:` / `positional arguments:` are locale-sensitive, and the
   `options:` spelling is itself CPython-version-coupled (it was `optional arguments:` in older
   releases — UNVERIFIED against a changelog here).
5. **Metavar and usage rendering.** `nargs='+'` → `names [names ...]`; `choices` →
   `{min,max,size,center}`; a non-required mutex group inside one bracket pair with `|`
   (`[--field {min,max,size,center} | --json]`), a required one in parens
   (`(--to X,Y,Z | --by DX,DY,DZ)`). The subparsers metavar is the full brace list
   (`{actor,brush,mover,…}`, 108 chars) and is **not** wrapped — it overflows 80 columns unchanged.
   Option and subcommand order is registration order throughout.

**What the spec commits to.** `old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/spec.md` says
"byte-identical" exactly once, at line 132, about PR #1: *"Proven against a couple of real verbs that
proxying is byte-identical to running `old/bin/uedcli` directly — a sanity check on the plumbing
itself, distinct from the differential-testing methodology above."* Its testing section diffs
"stdout/exit code/produced T3D bytes" per ported verb; `--help` writes to stdout, so help parity
*would* follow if `--help` were in the per-verb diff corpus, but the spec never says it is. **It does
not say help must stay byte-identical, and it does not say help may change.** Unstated.

The two forces: `old/CLAUDE.md`'s no-back-compat rule ("uedcli is unreleased… no scripts in the
wild") is the stated reason nothing else is preserved — but help text is the agent-facing contract,
how the LLM driving this CLI learns a verb, and 133 KB of hand-tuned prose is the most expensive
single asset in the surface. Only the owner can settle that.

### Behaviors a Rust port has to decide about, not just reproduce

| `old/` behavior | evidence | why it matters |
|---|---|---|
| prefix abbreviation on (`allow_abbrev=True` default) | `uedcli actor bbox --jso Foo` parses and runs | clap v4 has no long-flag inference by default; three parsers set `allow_abbrev=False` *specifically* because abbreviation would resurrect retired `--grid` as a unique prefix of `--grid-size` (`old/uedcli/cli/parsers/actor.py:488`, `stash.py:36`, `prefab.py:22`) |
| `-32,-32,32` / `-128` as values | `_CoordArgumentParser._parse_optional` override, all 154 parsers | the reason `--at=-32,-32,32` is not needed; a port needs `allow_hyphen_values`-style handling or its own equivalent |
| option after a `nargs='+'` positional is a hard error | `actor bbox A --json B` → exit 2 `unrecognized arguments: B` | argparse's single-pass greedy positional consumption. The error even comes from the **root** prog (`uedcli: error:`), not `uedcli actor bbox:`. Most Rust parsers accept this input |
| `--` separator and `-` positional | `actor bbox -- -A` → `names=['-A']`; `actor move - --to 1,2,3` → `names=['-']` | the stdin convention depends on it |
| hidden flags | `help=argparse.SUPPRESS` on `--all` (`class list`, `class show`) → `dest="legacy_all"`, still handled in `old/uedcli/cli/commands/classes.py:568,629` | undocumented-but-live flags; note these are back-compat shims surviving in a codebase whose rule forbids them |
| locale/width/Python coupling | see above | any byte-parity test must pin all three |

### The error and exit-code contract

Exit codes in the whole CLI are **0, 1, 2** — nothing else (`grep` over `old/uedcli/cli/` returns
only `return 0` ×155, `return 2` ×107, one `return 1`).

- **2** — every expected failure. Produced two ways: argparse's own
  `<prog>: error: <message>` preceded by the usage block, and `old/uedcli/cli/dispatch.py`'s guard
  printing a bare message to stderr with no usage block.
- **1** — exactly one site: `old/uedcli/cli/commands/level.py:788`,
  `return 1 if exit_severity is doctor.Severity.ERROR else 0`. `level doctor`'s help documents it
  ("does NOT affect the exit code, which always reflects all findings").
- **0** — success, and `BrokenPipeError` (`uedcli … | head`): `dispatch` reassigns
  `sys.stdout = open(os.devnull, "w")` and returns 0.

`_SelectionExit` **does not exist** in `old/uedcli/` — only in `old/dev/docs/` prose
(`architecture.md:76,747,1384` plus three `board/inbox/` items) as a historical name. The live types,
all in `old/uedcli/cli/errors.py`: `CommandError(Exception)` with `.message` (the base clean exit-2
failure, 268 `raise` sites — densest in `commands/classes.py` 31, `commands/level.py` 20,
`commands/texture.py` 19), and its subclasses `ProjectError` and `LevelSelectionError`.

`dispatch.dispatch()` catches an **ordered** chain, every arm printing to stderr and returning 2.
Order is load-bearing where subclassing exists:

| arm (in order) | rendered message prefix |
|---|---|
| `CommandError` (incl. `ProjectError`, `LevelSelectionError`) | bare `.message` |
| `ConfigError` | bare `str(exc)` |
| `CoordinateError` (`model`) | `invalid coordinate: ` |
| `GeometryError` (`geometry`) | `invalid brush geometry: ` |
| `DriverError`, `TimeoutError` (incl. `EditorNotReadyError`) | `editor error: ` |
| `ClassRefError` (`classindex`) | bare `str(exc)` |
| `SchemaError` (`uprops`) | `schema error: ` |
| `CacheWriteError`, `PkgCacheWriteError` | bare `str(exc)` |
| `BrokenPipeError` | silent, exit **0** |
| `OSError` backstop (after `TimeoutError`) | `filesystem error: ` |

The prefixes live in `old/uedcli/serve/errors.py::error_to_status`, not `dispatch.py` — shared so the
CLI's stderr text and `serve`'s HTTP bodies cannot drift. It returns `(http_status, message)` and
raises `TypeError` for anything outside the closed set, so an unclassified exception is a bug rather
than a guessed status. It carries three arms the CLI never reaches (`json.JSONDecodeError`,
`PackageRawError`, `NativePreviewError`). A Rust port that keeps a GUI backend needs the same single
classifier.

Named-value message shapes a port must reproduce (the "exit 2 naming the offending value" rule):
`Actor not found: <name>` (`old/uedcli/query.py:293`, `old/uedcli/actor_survey.py:33`; swept by
`old/uedcli/tests/test_name_not_found_sweep.py`); argparse's own
`argument --field: invalid choice: 'nope' (choose from min, max, size, center)` (value `repr`'d,
choices bare — `argparse.py:2572`, 3.12 formatting), `the following arguments are required: names`,
`argument --field: not allowed with argument --json`, `argument --plane: expected 2 arguments`,
`unrecognized arguments: --nope`; and custom-validator text routed through `ArgumentTypeError` into
the same envelope, e.g. `argument --to: coordinate must be X,Y,Z (3 comma-separated numbers), got
'abc'`.

Batch semantics from `old/dev/docs/direction/conventions.md`: all-or-nothing — collect every miss
and report the full set, never act on the good ones, never die on the first. An exact name matching
nothing is exit 2; an empty glob or empty stdin is exit 0 with empty stdout. One calibrated
exception: a set member a verb structurally cannot act on (a point actor handed to a poly verb) is
named on stderr and skipped.

### `--json` today

43 verbs carry `--json`, with **three** output shapes and no naming distinction between them:

| shape | where | example |
|---|---|---|
| JSONL — one compact object per line | catalog producers (`class list`, `texture list/search/show`, `sound`/`music` equivalents), ~19 `json.dumps` sites with no `indent` | help text says "emit one JSON object per line (JSONL)" |
| one pretty-printed object, `indent=2` | aggregate verbs (`event graph`, `mover key list`, `actor bbox`, `brush vertex list`, `project show`, the diagram verbs) | `old/uedcli/cli/rendering.py:613` etc. |
| a pretty-printed array | `docs list`, `docs search`, `level doctor` | `json.dumps([{…}], indent=2)` |

`level list --json` is compact (no `indent`) and prints `{"selected": null}` explicitly so a script
can detect "no level". `classify set -` reads JSONL on stdin — the documented third stdin convention.

### clap v4: what it gives us and what it will not

`clap` 4.6.7 (released 2026-09-14); `clap_complete` 4.6.11; `clap_mangen` 0.3.3. A 5.0 exists only
behind an `unstable-v5` feature.

**Fits this surface well:**

| need | clap mechanism |
|---|---|
| 154 parsers built from a table | builder API: `Command::subcommand(…)` / `subcommands(…)` take runtime values; `mut_arg`/`mut_args`/`mut_subcommand` rewrite after the fact |
| mixing a table-driven spine with per-verb structs | officially supported: `CommandFactory::command()`, `Args::augment_args(cmd) -> Command`, `Subcommand::augment_subcommands`, `FromArgMatches` |
| 154 parsers' construction cost | `Command::defer(fn(Command) -> Command)`, documented for "large applications to delay definitions of subcommands until they are being invoked"; `#[command(defer)]` landed in 4.6.7 |
| 47 `choices=` args / 17 value sets | `ValueEnum` derive; renders possible values into help **and** error messages |
| 15 custom `type=` callables | `value_parser!`, closures, or `TypedValueParser::parse_ref` returning `clap::Error` |
| 35 mutex groups (4 required) | `ArgGroup`, `multiple` defaults false; `multiple(false)` + `required(true)` = exactly one. Violation → `ErrorKind::ArgumentConflict` |
| `nargs` | `num_args`: `N`→`num_args(N)`, `'?'`→`0..=1`, `'*'`→`0..`, `'+'`→`1..` |
| bare `-` as a value | works unconfigured. `clap_lex`'s `is_stdio()` is `inner == "-"`, and `is_short()` excludes it, so `-` is never lexed as a flag (source-read, not compile-verified) |
| exit 2 on usage error | `USAGE_CODE: i32 = 2` is a hardcoded constant; `Error::exit_code()` returns 2 whenever the error goes to stderr. Matches argparse for free |
| custom stderr text | `ErrorFormatter` is a public trait (`fn format_error(&Error<Self>) -> StyledStr`); `RichFormatter` / `KindFormatter` ship, `err.apply::<MyFormatter>()` swaps in yours. Read context with `ContextKind::InvalidValue` etc. |
| custom exit code (for `level doctor`'s 1) | no setter — use `try_get_matches_from()`, print the error yourself, `std::process::exit(n)` |

**Will fight us:**

- **Help layout is a different algorithm, not different parameters.** clap aligns the help column to
  `longest_invocation + 4` with **no cap**, and offers only all-or-nothing `next_line_help`.
  argparse caps at `min(action_max_length + 2, 24)` and pushes a too-long invocation onto its own
  line. There is no setting that converts one into the other.
- **Hardcoded strings.** `{usage-heading}` expands to literally `Usage:`; `Arguments:` and
  `Options:` are string literals. Only `Commands:` is configurable (`subcommand_help_heading`), and
  section order is Commands → Arguments → Options with custom `help_heading` groups *after* all
  three — argparse's positionals-then-options order is unreachable.
- **Metavar brackets are mandatory.** `Arg::render_arg_val` emits `<NAME>` / `[NAME]` (+ `...` for
  multi-value); `value_name` sets only the inner text. argparse's bare `--out PATH` and
  `--field {min,max,size,center}` spellings cannot be produced.
- **Usage differs structurally**: options collapse to `[OPTIONS]`, and subcommands render as a
  `Commands:` block rather than a `{a,b,c} ...` positional.
- **No long-flag abbreviation** — no clap equivalent of `--jso` → `--json`.
- **Defaults that change bytes:** `color` (ANSI on a tty) and `suggestions` ("did you mean" in
  stderr) are both default features; an auto `help` subcommand is added unless disabled; `string`
  (needed for owned names/helps from a runtime table) is **not** default. Without the non-default
  `wrap_help`, clap wraps at a deterministic 100 columns — better for snapshots than reading
  `$COLUMNS`.

Two escape hatches give exact bytes: `Command::override_help(StyledStr)`, which its own docs warn
"only replaces the help message for the current command" (so: all 154 nodes), or
`disable_help_flag(true)` plus our own `-h/--help` and our own formatter walking
`get_subcommands()` / `get_arguments()` / `get_num_args()` / `get_value_names()` /
`possible_values()` — one formatter instead of 154 strings.

Compile/size cost at *this* scale is **unverified** — no published numbers for a 60-verb clap CLI.
The only measured data is `argparse-rosetta-rs`'s toy CLI (rustc 1.94.0): clap_derive +596 KiB
release / 4 s clean debug, clap builder +574 KiB / 3 s, bpaf +256 KiB / 831 ms, lexopt +37 KiB /
329 ms. clap issue #5657 notes `clap_derive` pulls `syn/full`, feature-unified across the workspace
(4.6.4 moved to syn v3). Mitigations if it bites: builder for the bulk plus `defer`.

### Alternatives

| crate | version / last release | help control | release overhead | clean debug build | derive ergonomics | error-message control | runtime/dynamic subcommands | 2026 status |
|---|---|---|---|---|---|---|---|---|
| `clap` | 4.6.7, 2026-09-14 | templating + `override_help` (exact bytes, per command); renderer itself rigid | 574–596 KiB | 3–4 s | best available | `ErrorFormatter` trait + `ContextKind` map | yes — builder is runtime data; `defer`, `mut_*`, `string` | very active |
| `bpaf` | 0.9.28, 2026-09-17 | `custom_usage`, `group_help`, `hide`; `docgen` emits md/html/manpage | ~256 KiB | 831 ms (combinator) / 4 s (derive) | good, but combinator style is awkward | `ParseFailure` + `exit_code()` | partial — combinators are typed/static | active, much smaller ecosystem |
| `argh` | 0.1.19, 2026-03-16 | limited (description/examples) | 38 KiB | 4 s | derive-only | minimal | no | maintained (Google), but follows the Fuchsia CLI spec, not Unix; no invalid-UTF-8 support |
| `gumdrop` | 0.8.1, **2022-03-09** | minimal | 28 KiB | 2 s | simple | minimal | no | effectively unmaintained |
| `xflags` | 0.3.2, **2023-12-18** | limited, from its own DSL | 23 KiB | 539 ms | custom-DSL macro | minimal | no | stalled |
| `pico-args` | 0.5.0, **2022-06-04** | none | 24 KiB | 300 ms | n/a (imperative) | you write it | n/a | stale but widely used |
| `lexopt` | 0.3.2, 2026-02-28 | none by design | 37 KiB | 329 ms | n/a (imperative) | you write it | n/a | healthy, single file, zero deps |
| hand-rolled | — | total | ~0 | ~0 | n/a | total | total | 124 verbs × 507 flags × 35 groups = reimplementing clap worse |

Only `clap` and `bpaf` are credible at 124 verbs. `bpaf` buys ~320 KiB and faster non-derive builds;
it costs ecosystem size and a combinator model that suits a table-driven verb set less well than
clap's runtime `Command`. Caveat on the comparison data: `argparse-rosetta-rs` is maintained by a
clap maintainer, so read its tradeoffs doc with that in mind.

Note what `lexopt`/`pico-args` would actually mean here: no help generation at all, so the
argparse-identical formatter becomes mandatory rather than optional — which, if we are writing that
formatter anyway, is less absurd than it first looks. It still means hand-rolling 35 mutex groups,
`num_args` semantics, and 150 option spellings' conflict logic.

### Completions and man pages

`clap_complete` 4.6.11 ships AOT generators for bash, elvish, fish, PowerShell and zsh (nushell is a
separate crate); its **dynamic** engine (`CompleteEnv`, `ArgValueCompleter`, `PathCompleter`) is
still behind `unstable-dynamic` after ~2 years, so do not build a contract on it. `clap_mangen` 0.3.3
renders ROFF from a `Command` (`generate_to` covers subcommands; its docs recommend a `cargo xtask`
over `build.rs`).

For an agent-driven CLI both are close to worthless — an agent neither tab-completes nor reads man
pages. Two secondary arguments: humans debugging the agent's invocations do, and `clap_complete`'s
dynamic engine plus `TypedValueParser::possible_values()` are the same reflection hooks a `--schema`
dump would use. If scope is being cut, cut the generators and keep the reflection.

### Machine-readable output, 2026 practice

- **JSON Lines** (jsonlines.org): UTF-8 required, BOM must **not** be included, `\n` terminator,
  extension `.jsonl`, MIME `application/jsonl` explicitly *not yet standardized*. It is a direct
  upgrade of `old/`'s "one item per line to stdout" rule, not a second output mode — and `old/`'s
  JSONL verbs already do it.
- **`cargo --message-format=json`** is the closest in-ecosystem precedent: one object per line, a
  `reason` field discriminating record kinds, and a **terminal record** (`build-finished`
  "lets a tool know that Cargo will not produce additional JSON messages"). Worth stealing for
  mutators. Cargo also documents the escape hatch "only interpret a line as JSON if it starts with
  `{`", i.e. it does not promise a pure stream; `old/`'s stdout/stderr split already does better.
- **`gh`** requires an explicit field list (`--json name,bucket`) rather than dumping everything,
  plus `--jq` and `--template`. Required projection keeps payloads small — relevant when the
  consumer pays per token.
- **Exit codes.** GNU's standards prescribe nothing beyond "do not use a count of errors as the exit
  status" and the 0–255 range; there is no GNU table. `sysexits.h` runs `EX_USAGE`=64 …
  `EX_CONFIG`=78. Real tools diverge — `grep` is 0/1/2 (match/no-match/error), `gh` is 0/1/**2 =
  user cancellation**/4/8 with *usage* errors at 1. So 2 is not a universal "usage error", but it is
  argparse's and clap's, which is what matters here.
- **Self-describing schemas.** clap has no built-in JSON dump (the request has been open since the
  pre-4.x repo), but its reflection API suffices: `Command::get_subcommands`, `get_arguments`,
  `get_positionals`, `get_opts`, `get_groups`, `get_about`/`get_long_about`, `get_aliases`,
  `get_arg_conflicts_with`, `get_display_order`, plus `Arg::get_num_args`, `get_value_names`,
  `get_help`, `get_action`, and `TypedValueParser::possible_values()` — call `Command::build()`
  first. Third-party crates are all too weak: `clap_schema` 0.2.1 (99 downloads, self-described as
  deprecated in favour of `argx`), `argx` 0.3.0 (first released 2026-08-29), `clap_describe` 0.1.1
  (unvetted side-product), `clap-markdown` (docs, not a schema), `clap-serde` (reverse direction,
  stale).
- **Specs, both immature:** OpenCLI (opencli.dev, v1.0.0-alpha.16, "OpenAPI for CLIs", explicitly
  marketed at LLM consumers) and The CLI Spec (clispec.dev, v0.3, single maintainer) whose Rust/clap
  guide prescribes nearly the shape under discussion here — error-enum→exit-code mapping, per-command
  read-only/non-idempotent declarations, a schema generated by walking clap's tree at runtime,
  bounded output. Useful as checklists; negligible adoption.
- **"CLI as tool definition for LLM agents"** is emerging with no standard. The clearest real
  instance is `sanity-io/cli` PR #1924, deriving MCP tool definitions from its own command
  definitions so it keeps no second copy of the surface; `bhouston/clidoc` issue #96 is an
  OpenCLI→MCP bridge. Tool-use APIs take JSON-Schema-shaped inputs, so a JSON Schema per verb is the
  portable target.

## Options

### Parser crate

| Option | Pros | Cons |
|---|---|---|
| `clap` builder, table-driven | 124 verbs from data; `defer` keeps startup cheap; one place to attach the shared `--tree` / `_preview_opts` fragments; mixes with derive per verb; reflection gives `--schema` for free | needs the non-default `string` feature for owned names; more boilerplate per flag than derive; help renderer still wrong (see below) |
| `clap` derive, per-verb structs | best ergonomics; `ValueEnum` covers all 17 choice sets; `#[command(defer)]` since 4.6.7 | 124 structs for a surface where only 28 of 72 repeated flags share a signature — `--json` alone needs 33 distinct doc comments; `clap_derive` pulls `syn/full`, feature-unified across the workspace |
| `clap` hybrid — builder spine, `Args` fragments for the shared blocks | matches the measured reuse exactly: `_preview_opts` (17 flags × 3 verbs), `--csg`/`--mover-class`/`--catalog-dir` (~10 verbs each), `--tree` (49 of 53 sites) | two idioms in one codebase |
| `bpaf` | ~320 KiB smaller, faster non-derive builds, `docgen` | smaller ecosystem; combinators fit a table-driven verb set poorly; dynamic subcommands only partially |
| `lexopt` / hand-rolled | total control of help and errors; near-zero build cost; argparse's abbreviation and `-32,-32,32` quirks become trivially reproducible | we re-implement 35 mutex groups, `num_args`, conflict logic and suggestion-free error text; `rust-cli-recommendations` explicitly discourages it |

### Help fidelity

| Option | Pros | Cons |
|---|---|---|
| **A — our own formatter** over clap's reflection, with `disable_help_flag(true)` | exact argparse bytes achievable; one implementation covers all 154 screens; `old/`'s `help.json` becomes the test fixture directly; the proxy test then tests *our* code | must port argparse's width rule, the `min(len+2, 24)` help column, and `textwrap`'s break-on-hyphens / break-long-words; pinned to one Python version + locale + width |
| **B — `override_help` per command** | exact bytes with no formatter | 154 `StyledStr`s, hand-maintained, drifting from the actual flags; clap's own docs call it per-command-only; a maintenance trap |
| **C — clap's renderer, accept new help** | zero help work; idiomatic Rust CLI; 157 KB of prose ports as `about`/`help` strings unchanged | every one of the 154 screens changes shape; `help.json` stops being an oracle; the agent's learned surface changes |
| **D — C plus `uedcli --schema`** (JSON from clap reflection) | gives the agent a *better* contract than prose: per-verb args, `num_args`, possible values, conflicts, groups; snapshot-testable; aligns with where tool-definition practice is heading | a new output surface to maintain; `old/dev/docs/direction/conventions.md`'s YAGNI rule argues against adding it speculatively |

## Proposal (owner's call — not decided)

Ask the owner to settle help parity *before* PR #2 ports a verb, because it determines whether the
first ported verb needs a formatter or not.

If the answer is "help may change": `clap` 4.6 hybrid — builder spine driven by a verb table,
`#[derive(Args)]` fragments for the four genuinely shared blocks, `ValueEnum` for the 17 choice
sets, `TypedValueParser` for the 15 validators, a custom `ErrorFormatter` reproducing the
`invalid coordinate: ` / `invalid brush geometry: ` / `editor error: ` prefixes from
`old/uedcli/serve/errors.py`, and `try_get_matches_from` + explicit `process::exit` so
`level doctor`'s 1 is reachable. Turn off `color` and `suggestions`, leave `wrap_help` off (100-column
deterministic help), and retire `tests/proxy.rs::help_is_identical` in favour of snapshotting the new
help — it is tautological today anyway.

If the answer is "help must stay byte-identical": the same clap setup plus option A, with
`old/uedcli/tests/fixtures/parser_baseline/help.json` wired directly into `cargo test` as the
fixture. Budget the formatter as its own PR before any verb lands, and pin width (80), locale (C) and
the fact that the fixture was generated on CPython 3.12.

Either way, port `action_tree.json` and `argv_corpus.json` into the Rust test suite early — they are
data, they already encode the abbreviation and negative-coordinate cases, and they outlive `old/`.

## Open questions / what to verify next

- **Owner:** must a ported verb's `--help` stay byte-identical, or is help explicitly allowed to
  change? The spec is silent; `tests/proxy.rs` does not answer it.
- **Owner:** keep prefix abbreviation (`--jso` → `--json`)? Dropping it would also retire the three
  `allow_abbrev=False` workarounds. Note that `old/CLAUDE.md`'s no-back-compat rule cuts *against*
  keeping it.
- **Owner:** the two hidden `--all` flags (`help=argparse.SUPPRESS`, `dest="legacy_all"`) are
  back-compat shims in a codebase that forbids them. Port, or drop at port time?
- **Owner:** `--json`'s three shapes — normalize to JSONL plus a `cargo`-style terminal record, or
  reproduce all three? Normalizing is a behavior change and so needs a ruling, not a judgment call.
- **Owner:** add `uedcli --schema` / `uedcli schema`? It is the strongest lever for the actual
  consumer, and it is also exactly the kind of speculative output surface the YAGNI rule names.
- **Verify by building:** clap's compile time and binary size at 154 nodes / 507 flags, builder vs
  derive, with and without `defer`. No published number exists at this scale.
- **Verify by building:** that clap accepts `-` as a positional value and `-32,-32,32` as an option
  value with `allow_hyphen_values`. The `clap_lex` behavior above was read from source, not compiled.
- **Verify:** whether the `options:` / `optional arguments:` header and the `invalid choice:
  (choose from min, max, …)` formatting differ across CPython versions, and which version
  `help.json` was generated on. Both affect what "byte-identical" even names.
- **Verify:** how clap treats `{`/`}` inside a `help` string — 32 of `old/`'s help strings contain
  braces, and clap's templating uses them (likely only in `help_template`, unconfirmed).
- **Not researched:** `serve` is a blocking long-running verb inside the same binary; whether the
  Rust GUI backend stays a subcommand is marked undecided in the spec.

## Sources

Internal: `old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/spec.md` (line 132 is the only
"byte-identical" sentence) · `old/CLAUDE.md` "Code & CLI conventions" + `old/dev/docs/direction/conventions.md`
· `old/uedcli/cli/{main,dispatch,targets,ingest,errors}.py`, `old/uedcli/cli/parsers/*`,
`old/uedcli/cli/commands/*` · `old/uedcli/cli/parsers/_arguments.py` (`_CoordArgumentParser`,
validators, `_preview_opts`, `_tree_flag`) · `old/uedcli/serve/errors.py` (the shared classifier) ·
`old/uedcli/cli/commands/level.py:788` (the only exit-1 site) ·
`old/uedcli/tests/parser_baseline.py` + `old/uedcli/tests/fixtures/parser_baseline/*.json` ·
`old/uedcli/tests/test_help_completeness.py` · `src/main.rs`, `tests/proxy.rs`, `Cargo.toml` ·
`/opt/pyenv/versions/3.12.13/lib/python3.12/argparse.py:173,178,657,1808,2572` (width, help-column
cap, `textwrap` call, gettext'd `options`, invalid-choice text).

External, fetched 2026-10-03:

- clap version/API: https://crates.io/crates/clap (4.6.7, 2026-09-14) ·
  https://docs.rs/clap/latest/clap/struct.Command.html (`subcommand(s)`, `mut_*`, `defer`,
  `override_help`, `disable_help_flag`, reflection getters) ·
  https://docs.rs/clap/latest/clap/_derive/index.html (mixing derive + builder) ·
  `struct.ArgGroup.html`, `struct.Arg.html`, `trait.ValueEnum.html`,
  `builder/trait.TypedValueParser.html`, `error/enum.ErrorKind.html`, `error/enum.ContextKind.html`
  on the same host.
- clap source (github.com/clap-rs/clap/blob/master/…): `clap_builder/src/builder/command.rs`
  (template placeholders), `clap_builder/src/output/help_template.rs` (hardcoded `Usage:` /
  `Arguments:` / `Options:`, `longest + 4` help column, 100-column fallback),
  `clap_builder/src/error/mod.rs` (`USAGE_CODE = 2`), `clap_builder/src/error/format.rs`
  (`ErrorFormatter`), `clap_lex/src/lib.rs` (`is_stdio()`/`is_short()` — bare `-` never a flag;
  source-read, not compiled).
- clap issues: /5657 (`clap_derive`'s `syn/full` compile cost) · /5109 (dynamic subcommands, open) ·
  kbknapp/clap-rs/issues/918 (JSON export, never implemented).
- Companions: https://docs.rs/clap_complete/ + `clap_complete/Cargo.toml` (`unstable-dynamic` still
  non-default) · https://docs.rs/clap_mangen/.
- Alternatives: https://github.com/rosetta-rs/argparse-rosetta-rs + its `docs/tradeoffs.md` (the
  size/build table — a toy CLI, and maintained by a clap maintainer) ·
  https://rust-cli-recommendations.sunshowers.io/cli-parser.html ·
  https://usage.jdx.dev/rust/performance (one 3.1 MB-vs-2.5 MB clap/bpaf data point) ·
  https://docs.rs/bpaf/ · https://github.com/google/argh · https://github.com/blyxxyz/lexopt.
- Output and exit codes: https://jsonlines.org/ ·
  https://doc.rust-lang.org/cargo/reference/external-tools.html (`reason` discriminator,
  `build-finished` terminal record) · https://cli.github.com/manual/gh_help_formatting +
  https://github.com/cli/cli/blob/trunk/internal/ghcmd/cmd.go (`gh`'s codes; its usage errors are 1)
  · https://www.gnu.org/prep/standards/standards.txt (no GNU exit-code table) ·
  https://man.freebsd.org/cgi/man.cgi?query=sysexits&sektion=3 ·
  https://docs.python.org/3/library/argparse.html.
- Schemas: https://opencli.dev/ + https://github.com/bcdxn/opencli (v1.0.0-alpha.16) ·
  https://clispec.dev/guide/rust/ (v0.3, single maintainer) ·
  https://github.com/sanity-io/cli/pull/1924 (CLI definitions → MCP tool definitions) ·
  https://github.com/bhouston/clidoc/issues/96 · https://crates.io/crates/clap_describe ·
  https://github.com/selemis-com/clap_schema · https://lib.rs/crates/clap-serde.

**Unverified:** clap's compile time and binary size at this surface size; which CPython version
produced `help.json`; whether `options:` replaced `optional arguments:` in 3.10 specifically (the
string is clearly version-coupled, but no changelog was fetched); `kubectl`/`docker` JSON specifics;
clap's treatment of literal braces in `help` strings; clap issue #918's current label state.
