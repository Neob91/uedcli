+++
priority = "p?"
kind = "unknown"
summary = "Offline class discovery + qualify-and-validate on ingest"
+++

# Offline class discovery + qualify-and-validate on ingest

— BUILT + tested + live-verified
2026-07-17 (spec `specs/2026-07-17-class-discovery-and-author-validation.md`; decisions.md
2026-07-17 19:37 UTC). New `class list`/`class show` verbs over an offline `classindex.ClassIndex`;
bare→FQCN class qualification + existence validation + texture existence validation wired into
every ingest/emit seam (`actor add`, stash capture/apply, prefab apply, the generators, `brush poly
set --texture`); `verify.py` H3 reconciliation (`requalify_classes_to_loaded`) keeps post-verify
live-vs-live. Abstract detection via the shipped ScriptText source (`unrealed/class-schema.md`).
`class list` is a rooted depth-limited BROWSE (default now = an indented inheritance TREE rooted at
Engine.Actor, abstract nodes `*`, a collapsed frontier node's hidden direct-subclass count as `(N)`,
depth auto-fits ~60 lines; `--subclass-of` reroots, `--depth` counts from the shown root, `--flat`
gives the pipeable one-per-line list, `--all` reroots at Core.Object) — a flat 1200-class dump was
unusable (Andrzej; tree per decisions.md 2026-07-18 10:56 UTC). `class show` groups props per declaring class; default truncates ancestor sections to a
~60-line budget (`… N more hidden` note), `--all` = full chain. (DX props carry no `var(Category)`.) Post-build review (two cold reviewers) findings all resolved: foreign-`.u` index-bounds
robustness (no traceback), the untested real bodies now covered (`test_ingest_validation.py`), one
canonical no-package-path message, `TextureResolver.exists` cache, ancestry cycle-guard, and a
RELAXED `uprops` EOF gate (tolerates trailing padding — `CaroneElevatorSet.u` now parses instead of
skip-noting). Gates green: `bin/test` 1337 passed / 1 skipped / 2 xfailed, 35 cargo. Live: `class
list`/`show` on real DX; `actor add` of bare `Class=Light` stores `Engine.Light`; unknown
class/texture → exit 2. **Remnants (boarded in `inbox.md`):** the annotated class catalog (curated
placeability/guidance) + the backward-compat exit-status change note.
