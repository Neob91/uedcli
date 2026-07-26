# Spec: `paths` as a TOML list (as well as a colon-string)

**Status:** specced, awaiting plan → build.
**Requested by:** Andrzej (2026-07-19) — "Can `~/.uedcli/config.toml` define `paths` as a **TOML
list** instead of a single string with `:` as separator? Spec now if needed." Andrzej has **decided
he wants the list form supported**; this spec designs *how* and flags the sub-choices with
recommendations.
**Ephemeral:** per the uedcli `CLAUDE.md`, this spec is scratch. The load-bearing decision + rejected
alternatives go in the durable append-only `dev/docs/decisions.md` (add an entry when this is
accepted); on build, fold the outcome into `direction.md` / `architecture.md` / `docs/usage.md` and
delete or stale-mark this file.

---

## Open sub-choices (recommendations — don't block; these are my defaults)

| # | Question | Options | **Recommendation** |
|---|---|---|---|
| A | Accept BOTH forms, or migrate to list-only? | (a) accept string OR list; (b) list-only, drop string | **(a) accept both.** Zero migration cost; every existing `config.toml`/`uedcli.toml` in the wild keeps working. The colon-string stays a valid, documented form. |
| B | Apply the list form to the project `uedcli.toml` `paths` too, or only `~/.uedcli/config.toml`? | (a) both loaders; (b) per-user only | **(a) both.** Consistency — one rule for "a `paths` value" everywhere. Andrzej asked specifically about `config.toml`; note that the per-user loader is the must-have and the project loader is the consistency add-on. |
| C | Should the single-dir keys `catalog`/`prefabs`/`maps` also accept a list? | (a) leave as plain single-dir strings; (b) make them lists | **(a) leave them.** They are semantically ONE directory each (`project_catalog_dir` etc. return a single path); a list is meaningless there. Out of scope. |
| D | What is the headline benefit — expressing a directory whose path contains a `:`? | (a) frame it as **any colon-containing POSIX dir** (works today on the Linux host); (b) frame it as **Windows drive-letter paths** | **(a) colon-containing POSIX dir.** This is the reachable benefit on uedcli's actual (host-native Linux) runtime. A Windows drive letter (`C:\…`) is NOT `os.path.isabs`-absolute on POSIX and is rejected/dropped by the unchanged absolute-dir + existence checks — genuine Windows-host support is a **separate, out-of-scope** concern (§Out of scope). Do NOT claim the drive-letter case as "accepted." |
| E | Should a list element itself still be allowed to contain a `:` separator (i.e. one element = several dirs)? | (a) NO — each element is exactly one dir, `:` in an element is a literal path char; (b) still split each element on `:` | **(a) no inner split.** The whole point of the list is to escape the `:`-as-separator overload. In list form, one element = one directory, verbatim; a `:` in it is part of the path (that is what lets a colon-containing dir through). |

---

## Motivation (the load-bearing "why")

`paths` today is a single **colon-separated** string of directories, split on `:` by
`resolve_dirs` (`config.py:140-173`). Because `:` is the element separator, a genuine value that
*contains* a colon is impossible to express. `resolve_dirs` even has an explicit guard,
`_WIN_DRIVE` (`config.py:57`, checked at `config.py:155-158`), that **rejects** any element looking
like a Windows drive path (`C:\Textures`, `Z:/System`) with:

> `path element contains a ':' (Windows-style drive?) — values are POSIX and ':' is the list separator`

Worse, the guard is **narrow**: its regex `(?:^|:)[A-Za-z]:[\\/]` only matches a *drive-letter*
shape (`X:\` / `X:/`). A perfectly ordinary **POSIX absolute directory whose name contains a colon**
— e.g. `/games/od:d/Textures` — is NOT caught by the guard and is instead **silently mis-split** on
its inner colon into two bogus fragments (`/games/od` and `d/Textures`), each existence-filtered
away. So the colon-string form cannot represent such a dir at all, and fails *silently* rather than
with an error.

**A TOML array sidesteps the collision entirely.** In a list, each element is a distinct string and
there is no separator to collide with — so `paths = ["/games/od:d/Textures", "/games/System"]` is
unambiguous and needs no `:`-splitting and no `_WIN_DRIVE` guard.

**Headline benefit (sub-choice D):** the list form is the supported, unambiguous way to express a
directory **whose path contains a colon** on uedcli's actual host-native (Linux) runtime — an
absolute POSIX dir like `/games/od:d/Textures`, which the colon-string form structurally cannot
represent (and today mis-splits silently). The colon-string remains the terse form for ordinary
colon-free POSIX dirs.

**What the list form does NOT unlock here — a Windows drive letter.** `paths = ["C:\\Textures"]`
looks like it should now work, but on the Linux host uedcli runs on, `os.path.isabs("C:\\Textures")`
is **False** (a drive letter is not POSIX-absolute) and `os.path.abspath` turns it into
`<cwd>/C:\Textures`. So such an element is *rejected* by the unchanged `require_absolute` check in
the per-user loader, and *dropped* by the unchanged existence filter everywhere else. The list form
removes the *separator* collision, not the *POSIX-path-semantics* barrier. Genuine Windows-host
support (drive-letter-aware `isabs`/normalization) is a **separate concern, explicitly out of
scope** (§Out of scope). This is why sub-choice D is anchored on the colon-in-POSIX-name case, which
genuinely works, not on drive letters, which do not.

---

## The change

`paths` accepts **EITHER**:
1. a colon-separated **string** — unchanged, back-compat (`"Textures:System"`), OR
2. a TOML **array of directory strings** — new (`["Textures", "System"]`, or a colon-containing dir
   like `["/games/od:d/Textures"]`).

Applies to the per-user `[games.<name>].paths` (the must-have) **and** the project `uedcli.toml`
`paths` (the consistency add-on) — sub-choice B(a).

The single-dir keys `catalog`/`prefabs`/`maps` are **unchanged** (plain single-dir strings) —
sub-choice C(a), out of scope.

### Data-model types

- `Substrate.paths: str` → **`str | list[str]`** (`config.py:71`).
- `Project.paths: str | None` → **`str | list[str] | None`** (`config.py:84`).

Both value objects simply carry whichever form the loader validated; the *normalization to a dir
list* happens in `resolve_dirs`, which every **production** consumer already funnels through
(`_composed_dirs_with_provenance`, `config.py:408-411`) — those need no change.

**One consumer bypasses `resolve_dirs` and MUST be fixed** (reviewer finding): the integration test
`uedcli/tests/test_uprops_defaults.py:37` reads the loaded Substrate directly with
`paths = [d for d in sub.paths.split(":") if d]`. Once a real `~/.uedcli/config.toml` migrates to the
list form, `sub.paths` is a `list` and `.split(":")` raises `AttributeError`. It is
`@pytest.mark.integration` (deselected by default, so `bin/test` stays green and would *hide* the
break), which makes it doubly important to fix as part of this change: replace line 37 with
`paths = config.resolve_dirs(sub.paths, "/", require_absolute=True)` (the canonical normalization).
This is the ONLY non-`resolve_dirs` reader of `.paths` in the tree (verified: the other `.paths`
hits — `editor.py`, `preview_game.py` — are unrelated `.paths.ini` filenames / help strings).

### `resolve_dirs` — accept `str | list[str]`

`resolve_dirs(paths, base, *, require_absolute=False)` (`config.py:140`) signature becomes
`paths: str | list[str]`. New behaviour:

- **`None` or empty (`""`, `[]`)** → `[]` (unchanged for the string case; `[]` is the empty-list
  analogue — clean no-op, not an error).
- **`str`** → EXACTLY today's path: `_WIN_DRIVE` guard, then `split(":")`, per-element strip / skip
  blanks / `*`-glob rejection / `require_absolute` check / existence filter. **Unchanged.**
- **`list`** → iterate elements directly. For each element:
  - It **must be a `str`** — a non-string element (`paths = ["A", 3]`) is a `ConfigError` naming the
    offending value and its position. (TOML also allows nested arrays / tables as elements; those hit
    the same not-a-string error.)
  - `strip()` it; a blank/whitespace-only element is **skipped** (mirrors the string form's
    skip-blank-between-colons behaviour — `config.py:161-163`). *(Design note: skip, not error —
    keeps parity with `"::A: :"` → `["A"]`. See sub-choice-adjacent note below if Andrzej would
    rather a blank list element be a hard error; I recommend skip for parity.)*
  - **NO `_WIN_DRIVE` guard and NO `:`-split** — the element is one directory, verbatim. This is what
    lets a `C:\...` path through (sub-choice E(a)).
  - A leftover glob `*` is **still rejected** (the dirs-not-globs migration invariant applies to both
    forms): `paths are directories now, not globs: drop the /*.ext from …`.
  - `require_absolute` still applies (per-user games dirs must be absolute).
  - Resolve against `base` (relative → join `base`; absolute → verbatim), abspath-normalize, include
    **only if it is an existing directory** (a non-existent dir is silently skipped — offline-safe,
    unchanged rule).
  - Order preserved; no dedup here (composers dedup).

**Invariant to preserve and test:** for any colon-string with no colon-in-value hazard, the string
form and the equivalent list form (`"A:B:C"` vs `["A","B","C"]`) resolve to the **identical** dir
list.

### Loader validation

**Per-user `load_user_config` (`config.py:274-280`)** — replace the `isinstance(paths, str)` gate.
New shape:

```
paths = tbl.get("paths")
if isinstance(paths, str):
    if not paths.strip():
        raise ConfigError(f"{where}: 'paths' string is empty")
    elements = [p.strip() for p in paths.split(":") if p.strip()]
elif isinstance(paths, list):
    elements = _normalize_paths_list(paths, where)      # str-checks, strips, drops blanks
else:
    raise ConfigError(
        f"{where}: required key 'paths' must be a colon-separated string OR a list of dir "
        f"strings, got {type(paths).__name__ if paths is not None else 'nothing'}")
if not elements:
    raise ConfigError(f"{where}: 'paths' resolves to no directories")
for pat in elements:
    if not os.path.isabs(pat):
        raise ConfigError(f"{where}: dir must be absolute: {pat!r}")
games[name] = Substrate(name=name, paths=paths)   # store the ORIGINAL form; resolve_dirs re-parses
```

Note the per-user loader keeps its own **pre-validation** (absolute-dir check) — it must run the same
str-checks the list branch of `resolve_dirs` will later run, so the error surfaces at load with the
`[games.<name>]` context, not later at compose time. Factor **only** the list
str-check/strip/skip-blank into one shared helper
`_normalize_paths_list(value, where) -> list[str]` used by both the loader pre-validation and
`resolve_dirs`. The helper raises `ConfigError` naming the offending element + index on a non-string.

**Scope of the helper (reviewer finding — don't overstate it):** `_normalize_paths_list` owns only
"is each element a non-blank string." The other two element rules — **glob `*` rejection** and
**`require_absolute`** — deliberately stay *outside* it (they already live in `resolve_dirs`, and the
per-user loader re-runs the absolute check for early context). This means a per-user *absolute glob*
element (`["/abs/*/x"]`) passes the loader and only errors later in `resolve_dirs` at compose — but
that exactly mirrors the **string** form's existing deferral (a colon-string glob also isn't
glob-checked until `resolve_dirs`), so the two forms stay consistent. Do not claim the helper is the
"single source of truth" for a valid element; it is the single source for the *string-shape* rule
only.

**Project `load_project` (`config.py:315-321`)** — the current loop rejects any non-string `paths`
(`v must be a non-empty string`). Split `paths` out of that shared string-only loop so it accepts
`str | list`:

```
# catalog / prefabs / maps stay single-dir strings (unchanged loop)
for key in ("catalog", "prefabs", "maps"):
    v = raw.get(key)
    if v is not None and (not isinstance(v, str) or not v.strip()):
        raise ConfigError(f"{toml_path}: key {key!r} must be a non-empty string, got {v!r}")
# paths accepts a colon-string OR a list of dir strings
paths = raw.get("paths")
if paths is not None:
    if isinstance(paths, str):
        if not paths.strip():
            raise ConfigError(f"{toml_path}: key 'paths' must be a non-empty string, got {paths!r}")
    elif isinstance(paths, list):
        _normalize_paths_list(paths, f"{toml_path} 'paths'")   # validate; may be [] → treated as unset
    else:
        raise ConfigError(f"{toml_path}: key 'paths' must be a string or a list of strings, "
                          f"got {type(paths).__name__}")
```

Project `paths` is **not** required-absolute (it anchors to the project root), and an empty/absent
`paths` is already a legal "base-only" project (`test_it_composes_base_only_when_the_project_has_no_paths`,
`test_config.py:356`), so a project `paths = []` should behave like "no overlay dirs" (legal).
**Two distinct mechanisms reach that result (be precise — reviewer finding):** a literal `paths = []`
is stored as `[]`, which is *falsy*, so `_composed_dirs_with_provenance`'s `if project.paths:` guard
(`config.py:408`) skips it. But an **all-blank** `paths = ["  "]` is stored as `["  "]`, which is
*truthy*, so the guard does NOT skip it — instead it calls `resolve_dirs(["  "], root)`, which
strips/skips the blank and returns `[]`. Same end result (base-only), different path; both are legal.
(The loader stores `raw.get("paths")` verbatim — it does not collapse an all-blank list to `[]`.)

### Error catalogue (all `ConfigError`, exit 2 — never a traceback)

| Input | Result |
|---|---|
| `paths = ["A", 3]` (non-string element) | `ConfigError`: names key/context, the element `3`, its index |
| `paths = ["A", ["B"]]` (nested list element) | same not-a-string error |
| `paths = 42` (scalar non-string, non-list) | `ConfigError`: "must be a colon-separated string OR a list of dir strings, got int" |
| `paths = []` (per-user) | `ConfigError`: "'paths' resolves to no directories" (a game MUST have ≥1 dir) |
| `paths = []` (project) | **legal** — treated as no overlay dirs (base-only project) |
| `paths = ["  ", ""]` (per-user, all-blank) | blanks skipped → empty → same "resolves to no directories" error |
| `paths = ["  "]` (project, all-blank) | blanks skipped → `[]` → legal base-only project |
| `paths = ["../*/Textures"]` (glob) | `ConfigError`: dirs-not-globs message |
| `paths = ["relative/dir"]` (per-user, `require_absolute`) | `ConfigError`: "dir must be absolute" |
| `paths = ["/games/od:d/Textures"]` (colon-in-POSIX-dir, list) | **accepted** — the whole point (no `_WIN_DRIVE` guard, no inner split in the list branch); resolves verbatim, existence-filtered like any dir |
| `paths = "/games/od:d/Textures"` (colon-in-POSIX-dir, string) | **silently mis-split** into `/games/od` + `d/Textures` (the `_WIN_DRIVE` regex does not match this shape) → both dropped by the existence filter. This is the bug the list form fixes; it is *not* an error, which is exactly why it's dangerous. |
| `paths = ["C:\\Textures"]` (Windows drive, list, per-user) | **rejected** — `require_absolute` fails (`os.path.isabs("C:\\Textures")` is False on POSIX). NOT the "whole point"; see §Motivation. |
| `paths = ["C:\\Textures"]` (Windows drive, list, project) | not required-absolute, so it passes validation but `os.path.abspath` → `<root>/C:\Textures` → existence-filtered away (no such dir). Effectively a no-op, not a working drive path. |
| `paths = "Z:\\Textures"` (drive-letter shape, string) | still **rejected** by `_WIN_DRIVE` (unchanged) — but see the reachability caveat below |

**`_WIN_DRIVE` string-form error message + its reachability.** Improve the `_WIN_DRIVE` message in
`resolve_dirs` to hint at the fix (append e.g. `— use the list form (paths = ["…"]) for a directory
whose path contains ':'`). **Caveat (reviewer finding):** in the **per-user** loader the string is
`split(":")` and absolute-checked *before* `resolve_dirs` ever runs, so a per-user
`paths = "Z:\\Textures"` string actually errors earlier with `dir must be absolute: 'Z'` — the
improved `_WIN_DRIVE` hint is only reached via a direct `resolve_dirs` call or the **project** loader
(which stores the string unsplit and defers to `resolve_dirs`). To make the hint reachable for the
per-user user too, **also broaden the per-user "dir must be absolute" error** to add the same "…for a
path containing ':' use the list form" hint when the offending fragment looks drive-letter-ish (a
lone `[A-Za-z]` fragment). This is a message-only nicety, not load-bearing — note it in the plan but
don't over-engineer.

---

## Backward compatibility

- Every existing colon-string `config.toml` / `uedcli.toml` is **byte-for-byte unchanged in
  behaviour** — the `str` branch is the old code path verbatim.
- Value objects store the original form; the only readers of `paths` are `resolve_dirs` (via the
  composers) and the one integration test called out above (fixed to use `resolve_dirs`).
- **`resolve_dirs`'s positional param renames** `paths_str` → `paths` (`config.py:140`). Verified
  safe: both call sites (`config.py:409,411`) pass it positionally; no `paths_str=` keyword caller
  exists. Note it in the plan so it isn't missed.
- **Migration footgun to document (reviewer finding):** because a list element is one dir verbatim
  (sub-choice E), a user "converting" a colon-string by wrapping the WHOLE thing in one element —
  `paths = ["System:Textures"]` — gets a single directory literally named `System:Textures`, which
  won't exist and is existence-filtered away. For a **project** this composes **base-only silently**
  (no error); for the **per-user** loader it errors ("resolves to no directories"). The `usage.md`
  example must show the CORRECT split-into-elements migration (`["System", "Textures"]`) to steer
  users away from this.
- **One existing test intentionally reverses.** `test_project_non_string_or_empty_keys_are_named_errors`
  (`test_config.py:605-617`) currently asserts `paths = ["Textures"]` in a project `uedcli.toml`
  **raises** a `ConfigError` matching `"paths"`. That case must be **removed from that test** (it now
  becomes *legal*) and re-expressed as a positive test that a project list `paths` parses. This is a
  deliberate, documented behaviour change, not a regression. The other cases in that test
  (`maps = 3`, `prefabs = ""`, `catalog = "  "`, `game = ""`) are unaffected and stay.

---

## Test strategy (offline; extend `uedcli/tests/test_config.py`)

The suite runs via `bin/test` (host-native venv). Add:

**`resolve_dirs` list form:**
- List form parses to the **same dir set** as the equivalent colon-string:
  `resolve_dirs(["A","B"], base) == resolve_dirs("A:B", base)` (using real existing tmp dirs so the
  existence filter passes). This is the parity invariant.
- Empty list → `[]` (analogue of `test_it_returns_empty_for_an_empty_paths_string`, `test_config.py:261`).
- Blank/whitespace elements in a list are skipped (`["A","  ",""]` → `[A]`), mirroring the
  string-form `"::A: :"` skip test (`test_config.py:257`).
- A **colon-containing POSIX dir works via the list but is silently mis-split via the string** (the
  headline benefit — a STRONG positive test, since POSIX hosts allow `:` in filenames):
  - Create a real tmp dir whose name contains a colon (`tmp_path / "od:d"`). Assert
    `resolve_dirs([str(that_dir)], "/")` returns `[that_dir]` (accepted, no `_WIN_DRIVE` error, no
    inner split).
  - Assert the STRING form fails to find it: `resolve_dirs(str(that_dir), "/")` mis-splits on the
    inner `:` and returns `[]` (the dir is not found) — demonstrating exactly what the list form
    fixes. (Use an inner-colon path shape like `/…/od:d` that the `_WIN_DRIVE` regex does NOT match,
    so this exercises the silent-mis-split bug, not the guard.)
  - Drive-letter guard still fires on the string form: `resolve_dirs("Z:\\Textures", base)`
    **raises** `ConfigError` (unchanged — extend `test_it_rejects_a_colon_inside_a_dir_element`,
    `test_config.py:250`, and assert the improved message hints at the list form).
  - **Negative expectation to pin (so no one "fixes" it into a false promise):** a drive-letter
    *element* is NOT magically accepted by the list form either —
    `load_user_config` with `paths = ["C:\\Textures"]` **raises** "dir must be absolute" on the POSIX
    test host (documents that Windows-host support is out of scope, and guards against someone later
    claiming the drive-letter case works).
- A **non-string list element** errors cleanly: `resolve_dirs(["A", 3], base)` → `ConfigError`
  naming `3`.
- A **glob element** in a list still errors: `resolve_dirs(["*/x"], base)` → dirs-not-globs error.
- `require_absolute` on a relative list element errors.

**Per-user loader (`load_user_config`):**
- `[games.deusex] paths = ["/g/System", "/g/Textures"]` loads; `cfg.games["deusex"].paths` is the
  list; composing yields the same dirs as the colon-string equivalent
  `"/g/System:/g/Textures"`. (Extend around `test_config.py:70-92`.)
- `paths = []` (per-user) → `ConfigError` (a game needs ≥1 dir).
- `paths = ["relative"]` (per-user) → absolute-required `ConfigError`.
- `paths = 42` → the string-or-list type error.

**Project loader (`load_project`):**
- `game = "deusex"\npaths = ["Maps", "LUM"]` loads; `proj.paths == ["Maps","LUM"]`; composes against
  the project root the same as `"Maps:LUM"` (extend `test_config.py:130-134`).
- `paths = []` (project) → legal base-only (no overlay), composes base-only.
- **Update** `test_project_non_string_or_empty_keys_are_named_errors` (`test_config.py:605`): drop
  the `paths = ["Textures"]` error case; add a positive parse case elsewhere.

**End-to-end parity (compose):** a project + per-user config both using the **list** form produce the
identical `composed_search_dirs` / `composed_search_files` as the colon-string equivalents (extend the
`test_config.py:290-320` compose tests).

**Consumer fix:** update `uedcli/tests/test_uprops_defaults.py:37` from `sub.paths.split(":")` to
`config.resolve_dirs(sub.paths, "/", require_absolute=True)` so the integration resolver survives a
real config migrated to the list form (see §Backward compatibility). It's integration-marked, so it
won't run under the default `bin/test`, but it must not silently `AttributeError` when it does run.

---

## Docs to update on build

- **`docs/usage.md`** — the `uedcli.toml` schema block (`docs/usage.md:33-39`): show `paths` accepts a
  colon-string **or** a list; use a CORRECT list example (`paths = ["Textures", "System"]`, one dir
  per element — NOT `["Textures:System"]`, per the migration footgun) and note the list form is the
  way to express a dir whose path contains a colon. Also note the per-user `config.toml`
  `[games.*].paths` accepts both forms. Do NOT present a `C:\…` drive-letter example as working (it
  isn't, on the Linux host — §Motivation).
- **`dev/docs/direction.md`** — "Layered packages" section: change "colon-separated" wording to
  "colon-separated **string** OR a **TOML list** of dirs" where it describes `paths`.
- **`dev/docs/architecture.md`** — the config-module description: note `paths` (both loaders) accepts
  `str | list[str]` and that `resolve_dirs` dispatches on the form; the list branch skips the
  `_WIN_DRIVE` guard and the inner `:`-split, which is what unlocks a colon-containing POSIX
  directory (with the caveat that a Windows drive letter is still not POSIX-absolute — out of scope).
- **`config.py` module docstring** (`config.py:1-34`) + `resolve_dirs`/`Substrate`/`Project`
  docstrings: reflect the `str | list[str]` shape and the drive-letter rationale.
- **`dev/docs/decisions.md`** — add a timestamped entry recording the decision (accept both forms,
  both loaders, single-dir keys stay strings) and the rejected alternatives (list-only migration;
  per-user-only). The spec is ephemeral; this is the durable record.

---

## Out of scope

- Making `catalog`/`prefabs`/`maps` lists (they are one dir each — sub-choice C).
- Any change to how dirs are composed/deduped/scanned (`composed_search_*` untouched).
- Cross-platform path handling beyond "let a colon-containing POSIX element through in list form" —
  uedcli still normalizes with `os.path.abspath` and gates on POSIX `os.path.isabs`. **Genuine
  Windows-host support** (making `C:\…` drive-letter paths `isabs`-absolute and existence-checkable)
  is explicitly a separate concern; the list form does NOT deliver it, and this spec must not be read
  as claiming it does (see §Motivation, sub-choice D, and the negative test above).
