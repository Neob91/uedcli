# Plan — split the god modules

Five slices, each leaving the suite no worse than the recorded baseline
(`spec.md` "Verification" — five tests are already red on master for unrelated reasons). Slice 0 first; slices 1-3 are
independent of each other and ordered by ascending risk; slice 4 needs 2 and 3 landed (it ran without slice 1).

## Slice 0 — the layering test, before any code moves

Add `uedcli/tests/test_module_layering.py`: for `uedcli/uprops/` and `uedcli/propedit/`, assert no
module imports one ranked later in its layer order.

Rank **every** module including the package root:

| Package | Order |
|-------------|---
| `uprops` | `base` < `ufield` < `uclass` < `values` < `__init__` |
| `propedit` | `base` < `tokens` < `paths` < `structtext` < `fields` < `edit` < `__init__` |

`__init__` ranks LAST in both — it is pure re-export, so it imports from every sibling, and any
order that ranks it lower turns correct code red. Both packages end in a top layer (`values.py`, `edit.py`) with the
root holding no logic; the test enforces that shape as much as the direction.

Two things the test must do, or it measures nothing:

- **Walk function bodies, not just module scope** (`ast.walk`, not `tree.body`). The spec forbids
  lazy in-function imports as a cycle escape hatch, which is exactly the reflex an executor reaches
  for — and a top-level-only scan cannot see it. `uedcli/tests/test_import_boundary.py:65` already
  does this and its docstring says why; copy that approach.
- **Resolve each import to an absolute module name, then test it against the package** — do not
  pattern-match spellings. `.values`, `uedcli.uprops.values`, `..uprops.values` and
  `import uedcli.uprops.values` are one module, and an import of the package ROOT is an edge to
  `__init__` (the partially-initialised-package cycle). `..upackage` resolves outside and is legal.

The test skips while the packages do not exist, so at slice 0 it is green-by-skip and proves nothing.
**Commit a negative control** rather than proving it once by hand: a fixture package with a
deliberate upward edge, named in the rank table, asserted to be reported. `test_doc_links.py` already
does exactly this (`test_link_check_fails_on_a_missing_file:264`,
`test_anchor_check_fails_on_a_missing_anchor:276`) — copy that shape. A throwaway proves the gate
once and never again; and a package the rank table does not name is not checked AT ALL, so a later
rename of `schema.py` would silently drop it from the check with the suite still green.

## Slice 1 — `utexture_decode.py` — BUILT, MEASURED, REVERTED (blocked)

Slices 0, 2, 3 and 4 landed in `25a9325`. Slice 1 did not: the filename below shadows a committed
spike harness module and flips two tests from skip to fail. It was built, verified byte-identical,
and reverted rather than improvised around. The ruling that unblocks it is
`questions/utexture-decode-name-collision.md`; the steps below are correct once a name is settled.


1. Enumerate `utexture.py`'s current public surface FIRST, `_`-prefixed names included — the module
   has no `__all__`, and the tests read `utexture._CODE_TO_CLASS`, `_fitting_classes`, `_bc2_alpha`
   and friends directly.
2. Move the fourteen decoder/layout symbols **and the five constants** (`_LINEAR_BPP`,
   `_BLOCK_BYTES`, `_CODE_TO_CLASS`, `_CODE_TO_LAYOUT`, `_CLASS_TO_LAYOUT`) into
   `uedcli/utexture_decode.py`. Import `Mip` under `if TYPE_CHECKING:`.
3. `utexture.py` imports back what it calls and re-exports the list from step 1.
4. Gate: **the full suite against the baseline**, not `-k texture`. `mip0_to_rgb` and `decode_palette` are used by
   `test_engine_facts.py` and `meshrender.py` decodes mesh skins through `utexture`, so a `-k
   texture` filter misses the consumers most likely to break.

## Slice 2 — `uedcli/uprops/`

**Start by renaming the module into the package**, or the intermediate states do not run at all:

```
mkdir uedcli/uprops
git mv uedcli/uprops.py uedcli/uprops/__init__.py
```

`git mv` does not create the destination directory — without the `mkdir` it exits 128. And a package
directory shadows a same-named module: with both `uedcli/uprops.py` and `uedcli/uprops/__init__.py`
present, `import uedcli.uprops` resolves to the package and every symbol still in the flat file
becomes unreachable. So peel symbols OUT of `__init__.py` into siblings; never create the package
alongside the module and move symbols in.

1. Capture the before-set of importable names from `uedcli/uprops.py` BEFORE touching it.
2. `mkdir` + `git mv` as above, **and in the same step fix the module-scope relative imports**:
   `uprops.py:27`'s `from .upackage import (…)` becomes `from ..upackage import (…)`, keeping the
   `read_compact_index as _read_compact_index` / `read_fstring as _read_fstring` aliases. Inside
   `uedcli/uprops/__init__.py`, `.` anchors on `uedcli.uprops`, so the unfixed line resolves to
   `uedcli.uprops.upackage` and the whole suite errors at collection. The rename is NOT a no-op step.
3. Peel out in layer order — `base.py`, `ufield.py`, `uclass.py`, `values.py` — fixing each file's
   import depth AS it is peeled, not in a later pass, and running `bin/test` after each so a break is
   attributable to one move. Point the `upackage` names at `..upackage` in every file that uses them.
4. Fix the function-local imports listed in `spec.md` as their owning symbol moves —
   `uprops.py:359`'s lazy `from . import schema_cache` is the one here.
5. Gate: `bin/test` against the baseline, the layering test, and the before-set is a subset of the
   after-set. Two exclusions on that comparison, or it can never pass: a package also binds its
   submodules and `__path__` (so do not compare `dir()` equality), and the flat module's `dir()`
   includes its own imports — `re`, `struct`, `functools`, `dataclass`, `replace`, `annotations` for
   `uprops` — which a re-export-only root does not bind. Exclude imported modules and aliases, or
   compare against an explicit list.

## Slice 3 — `uedcli/propedit/`

Same shape: `mkdir uedcli/propedit && git mv uedcli/propedit.py uedcli/propedit/__init__.py` first,
then peel out `base.py`, `tokens.py`, `paths.py`, `structtext.py`, `fields.py`, `edit.py`, with the same
import-depth fix and subset gate. `propedit.py` has THREE module-scope relative imports to fix in the
rename step (`:28` `from . import typedprops`, `:29` `from .normalize import is_computed_key`, `:30`
`from .uprops import Prop, SchemaError`) plus the four function-local ones. Its `dir()` exclusion list
is longer: `re`, `dataclass`, `field`, `Decimal`, `InvalidOperation`, `Callable`, `typedprops`,
`is_computed_key`, `Prop`, `SchemaError`, `annotations`.

Gate: the full suite against the baseline, the layering test, and `actor prop get`/`set`/`unset` on a real
trunk — `propedit` is a write path and a golden-free regression there is a silent data bug.

`ScaleField` is load-bearing for `MainScale`/`PostScale` round-tripping (`architecture.md` "STORE" —
`emit_actor` re-emits solely from the typed field). Riskiest step in the plan; run the scale
round-trip tests specifically, not just the suite total.

## Slice 4 — packaging and docs

1. **`pyproject.toml`**: add `"uedcli.uprops"` and `"uedcli.propedit"` to the static `packages` list.
   Nothing in the suite catches this — `bin/test` and `bin/uedcli` both run from the source tree via
   `PYTHONPATH` and never install the wheel, so the omission surfaces only as `ModuleNotFoundError`
   for whoever first installs a built wheel. (`uedcli.bsp` and `uedcli.native` are missing from the
   same line already; that is `include-existing-runtime-subpackages-in-wheels`, not this item — but
   both edit this line, so do not run the two concurrently.)
2. **Agent-owned docs (`rationale/` only), fixed here**: `dev/docs/rationale/propedit.md` and
   `rationale/mapimport.md`. Check each citation before rewriting it — most do NOT go stale.
   `rationale/texture-decode.md` needs NO edit: its `utexture.py` citations name symbols that stay
   there (`TextureObj`, `_read_mip_array`, `TextureResolver._decode_export`, `_DECODERS`,
   `TextureError`, `DecodedTexture`, `load_package`, the `MAX_MIP*` bounds), and its two
   `detect_layout` mentions (`:24`, `:69`) stay accurate because `utexture.py` imports that name back.
   Rewriting the file wholesale would point correct refs at a module that does not contain those
   symbols.
   **Leave `dev/docs/spikes/` alone entirely** — agents may not edit it without the owner's yes
   (`CLAUDE.md` "dev/docs — never edit without the owner's approval, except the board"), and nothing
   there needs editing anyway. Two spikes mention `utexture.py`
   (`2026-07-25-native-mesh-decode/README.md:177`,
   `2026-06-27-decontainerize-uedcli/01-native-texture-decode.md:113`) and both stay true —
   `utexture.py` still exists. `2026-07-15-native-materialize/PARITY-STATUS.md:109` names `uprops.py`
   (not `utexture.py`) inside a historical sentence about which files another session was editing;
   retargeting it would falsify a record.
   Nothing reddens on any of this: `test_doc_links.py` strips inline code before matching, and its
   prose-path check covers only `direction/`, `rationale/`, `rules/`.
3. **Owner-gated docs, proposed not edited**: `dev/docs/architecture.md` and
   `dev/docs/unrealed/class-schema.md` (which cites `uprops.py`'s `class_is_abstract` /
   `_class_script_source`). Write the exact find→replace rows into this item's
   `questions/architecture-module-map-after-the-split.md` and wait — `CLAUDE.md` puts an owner
   decision in the owning item's `questions/`, and files it standalone only when no item owns it.
   This item owns it: its own change is what makes the map stale. That question blocks the item from
   reaching `done/`, which is the intended behaviour — the doc should not go stale unnoticed.
   No `docs/` user-facing file and no `direction/` topic references these modules, so the owner-gated
   set is exactly those two.

## Not doing

- No renames, no signature changes, no dead-code deletion — each is its own proposal.
- No `preview.py` work, and no `utexture.py` package-layer work; both are owned elsewhere
  (`spec.md` "Scope").
