# `uedctl docs` — serve the user-facing docs from the CLI (dev + Nuitka)

**Status: SPEC v1.2** — TWO review gates passed (2026-07-24 the base design; 2026-07-24 the
README-fold refinement) — four cold reviewers total, findings folded (cross-noted `[R…]`). All design
decisions Andrzej's ([`decisions.md`](../decisions.md) 2026-07-24 21:46 + 22:28 UTC).

Ephemeral (see `CLAUDE.md`); on landing, fold what shipped into `architecture.md` + `docs/usage.md`,
keep the decision in `decisions.md`.

---

## 1. Goal

Make uedctl **self-documenting**: a `docs` verb serving the repo's **user-facing** prose docs
(`usage.md`, `leveldesign/**`, and the folder `README.md` overviews) from the CLI, so a human can read
them in-terminal and a shipped **Claude skill routes to them by querying the tool** (`uedctl docs …`)
rather than bundling a copy. Docs are an asset of the **tool**; the skill/plugin ships **zero** copies.
One source of truth (`docs/`); a user reads the docs baked into the binary they have (version-locked,
offline, cross-platform) — the `git help <topic>` / `rustc --explain` pattern. *Rejected:* bundling the
KB under the skill's `references/` (duplication + ownership inversion + a bake/sync step); URL-referencing
hosted docs (network + drift). See `decisions.md`.

## 2. CLI surface

Top-level `docs` verb, three subverbs, mirroring `texture list|search` / `class list|show`. Every
subparser/argument carries a real `help=` (>10 chars) — `tests/test_help_completeness.py`.

```
uedctl docs list   [--json]
uedctl docs show   (<topic> | -)
uedctl docs search <query> [--json]
```

**Terminology (one word, used everywhere):** a **topic key** identifies a doc (§3). `list`/`search`
print topic keys; `show` takes a topic key. The `--json` field is named `path` for brevity but **holds
the topic key**, not a filesystem path.

### 2.1 `docs list [--json]`
Print every served **topic key**, one per line to **stdout**; count to **stderr**; lexicographic by
key. `--json` → array of `{ "path": <key>, "title": … }`. Title = the doc's first `# ` heading; if it
has none, the **directory name** for a folded-README key (never the literal `"README"`) else the file
basename. `[R2:L3]`

### 2.2 `docs show <topic>` / `docs show -`
Print a topic's markdown to **stdout as bytes** (`sys.stdout.buffer.write` — the docs contain UTF-8
`°×≡…`; a locale-decoded reprint could corrupt them). `[R:L1]`

**Resolution is a case-insensitive lookup into the enumerated served-set map (§3), never a filesystem
path-join** `[R:H1]` — which structurally kills traversal (`../…`, absolute), directory hits,
non-`.md`/binary dumps, and the dev-tree leak. The lookup key is the **full topic key**; `.md` is an
optional trailing suffix on it (`leveldesign/general/lighting` ≡ `…/lighting.md` ≡ the folded
`leveldesign/deusex` from `deusex/README.md`). A **bare basename is NOT a resolver** — `docs show
human-scale` (two files: `leveldesign/deusex/human-scale`, `leveldesign/general/human-scale`) is
**not-found + a hint listing both candidates**, never an ambiguous hit. `[R2:L2/L3]` A directory is
addressable **only if it holds a `README.md`** (its overview) — a README-less directory is not a topic
(intentional; §7 hint may still redirect `<dir>/README` → `<dir>`).

**No bare sugar:** only `docs show <topic>` (no `uedctl docs <topic>`).

**`-` (stdin) is ATOMIC** `[R2:M2 — "no silent half-answers"]`: reads topic keys from stdin (one per
line), resolves **all** first; if **any** is unresolved it prints **nothing** to stdout, names the
offending key(s) on stderr, and exits 2 — no partial output, no skip-with-warning. On full success it
prints each doc separated by a `<!-- topic: <key> -->` line, so `docs search lighting | docs show -`
composes. `-` is mutually exclusive with a positional topic; empty stdin → clean no-op (exit 0).

### 2.3 `docs search <query> [--json]`
Ranked matching **topic keys** — one key per line to stdout (so the output pipes into `docs show -`),
count to stderr. `[R1:M — search emits folded keys, not relpaths.]` `<query>` = a single literal,
case-insensitive substring (no tokenization in v1). Score = `10 × (query in title ? 1 : 0)` +
`(body lines containing the query)`; ties lexicographic by key; zero-score omitted. `--json` → array of
`{ "path": <key>, "title": …, "snippet": … }` where snippet = first body line containing the query,
stripped, ≤120 chars. No hits → empty stdout, `0 matches` stderr, exit 0.

## 3. Served scope & topic keys — user-facing `.md`, `dev/` excluded

Served set = every **`*.md`** under `docs/` **except the top-level `dev/docs/` subtree** (anchored at
the top-level dir, not any segment named `dev`). The dev tree never appears in `list`/`search`/`show`
and never ships. Non-`.md` assets (none exist today) are out of v1 scope. `[R:L1/L2]`

**Topic-key derivation** (shared by `list`/`search`/`show`): a served file's key is its path relative
to the docs root with `.md` stripped, with one fold — a **`README.md` maps to its containing
directory's path** (`leveldesign/deusex/README.md` → `leveldesign/deusex`), and the root
`docs/README.md` → the reserved key **`index`**.

**Collision = hard error (general rule)** `[R:H2 — both reviewers]`: if **any two served files derive
the same topic key under the case-insensitive comparison used for lookup**, enumeration raises
`_SelectionExit` **naming both files** (exit 2). This is deliberately general — it covers a
`X/README.md` vs a sibling `X.md`, a `docs/index.md` vs the reserved root `index`, and two files whose
keys differ only in case on a case-sensitive FS. **Why hard-error, not silent precedence**
`[R2:M1]`: a served set with an ambiguous key can't be trusted, and because the collision fails
*enumeration* it trips **every `docs` invocation AND `bin/test`** — so it's caught at authoring/CI
before a release binary can ship it; a user of a shipped binary never hits it. A committed test asserts
the live served set has **no duplicate keys** (the standing authoring gate). *(decision — Andrzej,
2026-07-24 22:28 UTC.)*

**Served today (derived from the live tree — do NOT hand-maintain a count in a golden; enumerate):**
**45** `*.md` → **45** topic keys, of which **7** are folded README indexes:
`index`, `leveldesign`, `leveldesign/deusex`, `leveldesign/deusex/recipes`, `leveldesign/general`,
`leveldesign/general/recipes`, `leveldesign/general/recipes/shapes`. `[R:H1 — census corrected; the
`recipes/shapes/` subtree had been omitted.]`

## 4. Source resolution — one resolver, source-tree before packaged `_docs`

Source of truth stays **`Tools/uedctl/docs/`**. Order keeps dev iteration live even if a local build
left a stale bundle `[R:H2-B]`:

```python
def docs_root() -> Path:
    if (p := os.environ.get("UEDCTL_DOCS_DIR")):          # 1. override (tests, packaging)
        return Path(p)
    pkg = importlib.resources.files("uedctl")             # package anchor (not parents[N])
    src = Path(pkg).parent / "docs"                       # 2. source checkout → Tools/uedctl/docs
    if src.is_dir():
        return src
    bundled = pkg / "_docs"                               # 3. packaged wheel / Nuitka one-file
    if bundled.is_dir():
        return Path(bundled)
    raise _SelectionExit("uedctl docs unavailable (broken install)")
```

- Dev (`bin/uedctl`) → branch 2, always live; no build step to iterate.
- Wheel / Nuitka → branch 3 (no source `docs/` sibling exists there).
- Resolver lives in a top-level `uedctl/*.py` module and derives from `files("uedctl")`, so it can't
  break if moved. Filesystem-backed installs only; zip-import/zipapp out of scope. The
  "resolves identically in wheel & Nuitka" claim is **to verify when packaging lands** (§8). `[R:M3/M4]`
- Ships complete in v1; branch 3 dormant until packaging exists.

## 5. Enumeration
Walk `docs_root()` for `*.md`, prune the top-level `dev/` dir, derive each file's topic key (§3),
enforce the no-duplicate-key rule (§3), extract titles. **One enumeration feeds `list`, `search`, and
`show`** — so `show` shares the exact served set and no path-join exists. Tiny set ⇒ no committed
index. Symlinks pointing outside the root / into `dev/` are not added (structural).

## 6. Output & conventions
- `show` → bytes to stdout, nothing to stderr on success. `list`/`search` → keys to stdout one per
  line, count/summary to stderr, `--json` for structure.
- Read-only; no level, no editor, no game config — runs in a bare checkout/install; never trips the
  author-time ingest/config gate.

## 7. Errors (house rules; via `_SelectionExit` → stderr + exit 2, no new type) `[R:M1]`
- `docs show <unknown / dev/ path / directory / non-`.md`>` → `Doc not found: <key>`, exit 2, with a
  **nearest-match hint** when one served key is an obvious prefix/substring match (incl. redirecting an
  old `<dir>/README` address → `<dir>`; a bare stem matching several keys, e.g. `human-scale`, lists
  the candidates).
- **Topic-key collision** (§3) → enumeration raises `_SelectionExit` naming both files, exit 2, no
  traceback — so `list`/`search`/`show` and `bin/test` all fail loudly.
- `docs show -` with any unresolved stdin key → atomic fail (§2.2): nothing on stdout, offending
  key(s) on stderr, exit 2.
- `docs search` no hits → exit 0. `docs list | head` (BrokenPipe) → exit 0 (global handler).
- `docs_root()` unresolvable → `_SelectionExit`, exit 2.

## 8. Deferred to when Nuitka/wheel packaging exists (NOT built in v1) — no command-code change
- Build step generates the served subset (`.md` under `docs/` minus `dev/`) into **`uedctl/_docs/`**.
- `.gitignore` `uedctl/_docs/`; generated, never committed.
- Wheel: `package-data = { uedctl = ["_docs/**"] }` (currently `[]`); generation runs **before** the
  sdist/wheel build (+ MANIFEST), else a clean-checkout build ships a broken install. `[R:H2-A]`
- Nuitka include source is the **already-filtered** bundle: `--include-data-dir=uedctl/_docs=uedctl/_docs`
  (NOT `docs=uedctl/_docs`, which re-bundles `dev/`). `[R:H2/M2]`
- CI drift guard: `_docs` regenerates identically from source.

## 9. Testing (offline, `bin/test`)
- `docs list` prints the served keys, **excludes every `dev/` path**, count on stderr; `--json` schema
  `{path,title}`. Assert against the **enumerated** live set, not a hand-typed count.
- `docs show` a leaf both ways (`…/lighting` and `…/lighting.md`) → same bytes; title with/without a
  `# ` heading; an empty file.
- **README fold:** `docs show leveldesign/deusex` → `…/deusex/README.md`; `docs show index` →
  `docs/README.md`; **`docs show leveldesign/general/recipes/shapes`** (the 7th index) → its README;
  `list` contains those keys and **no** `…/README` key; a folded-README title falls back to the
  **directory name**, not `"README"`.
- **Bare stem:** `docs show human-scale` → not-found + a hint naming both `…/deusex/human-scale` and
  `…/general/human-scale`.
- **Security/leak:** `docs show ../../pyproject.toml`, `/etc/passwd`, `..` → not-found, exit 2; a root
  that **actually contains `dev/`** → `docs show dev/architecture` not found; a directory / non-`.md`
  → not found.
- **Collision (general):** fixtures for (a) `X/README.md` + `X.md`, (b) `docs/index.md` + root
  `README.md`, (c) `Foo/README.md` + `foo.md` (case-fold) → each makes **`docs list` itself** (not just
  a helper) error via `_SelectionExit`, exit 2, no traceback; and the no-duplicate-key test guards the
  real tree.
- **`show -`:** multi-key stdin all-valid → concatenated with separators; **any** invalid key → nothing
  on stdout, exit 2. Empty stdin → exit 0.
- **`search`** emits folded keys (a README hit prints the dir key, resolvable by `show`); title hit >
  body hit; snippet ≤120; `--json` = `{path,title,snippet}`; no-hit → exit 0.
- Resolver: `UEDCTL_DOCS_DIR` wins; source-before-`_docs` (fixture with both → source wins); broken
  root → clean `_SelectionExit`, **assert no traceback**. Bare-install smoke (no config, no level).

## 10. Docs & house-rule updates on landing
- `docs/usage.md` gains a `docs` section (the reference file the command serves). `[R:M2]`
- **The root `docs/README.md` was ALREADY trimmed to a user-facing index** `[R2:M3]` — done
  2026-07-25 when the `docs/`-is-user-facing house rule landed: the whole-tree "which doc is for
  what" table moved to `dev/docs/README.md`, and `docs/README.md` became a lean user index pointing
  only at `usage.md` + `leveldesign/`. So `index` already resolves to a valid landing page that
  `docs show` will serve — this change no longer needs to trim it; just verify the trim holds.
- Help strings on every `docs` subparser/arg. `[R:L4]`

## 11. Open questions
None. Forks resolved in chat 2026-07-24; both review gates' findings folded (v1.1, v1.2).
