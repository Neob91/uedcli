+++
priority = "p2"
kind = "implement"
summary = "Catch build-emergent BSP problems the static level doctor structurally cannot; PARKED mid-spike."
spikes = ["dev/docs/spikes/2026-06-25-umodel-serialize-format.md"]
+++

# BSP-issue detector (D0 + the P0 spike + `level doctor --rebuilt` + D0-b)

**Status:** Step 1 (P0 spike) DONE — verdict **GO** (2026-08-03). Steps 2–4 remain. Spec reviewed
(6 rounds), plan reviewed (3 rounds).

**Step 1 P0 verdict — GO.** All six arrays (Vectors/Points/Nodes/Surfs incl. `PolyFlags`/Verts/Leaves)
parse from a built `.dx`; node polys reconstruct planar-exact from `iVertPool→Verts→Points`. P0-b1
(located T-junction) confirmed negative as expected — HoM stays a D0 `T-points` count, not a D1
located row. Viable `--built` rows: invisible walls (near-zero-area nodes) + fall-through
(`PF_NotSolid`/`PF_SemiSolid`/`PF_Portal` surfs). So steps 2–3 (incl. the `--built` arm) are
unblocked; the D1-b located analyses are their own plan. Evidence + verdict:
[`../../../spikes/2026-06-25-umodel-serialize-format.md`](../../../spikes/2026-06-25-umodel-serialize-format.md)
(P0 section), pinned by `spikes/bspspike/test_umodel_p0_gate.py`.
**Plan (full detail):** [`plan.md`](plan.md)
**Spec:** board item `bsp-issue-ground-truth-detector-d0-d1` ·
**Decision:** `rationale/MIGRATION.md` (2026-06-24 12:40 UTC)

**What it is.** Catch the *build-emergent* BSP problems (slivers, hall-of-mirrors, invisible walls,
fall-through) that the already-shipped static `level doctor` structurally can't.

**Build order (the near-term scope — D1-b and all D2 engine slices are OUT/deferred):**

1. **`UModel`-parser feasibility spike (first, alone)** — the value gate: decides whether the
   located-issue tier (`--built`) is even buildable. One session, on a *built* `.dx`.
2. **Promote D0** — the validated drop-warning parser → a new `uedcli/bsp/editorlog.py` + helpers +
   offline golden tests. (Offline, pure, touches no shared code.)
3. **`level doctor --rebuilt`** — the MVP: rebuild the level in an ephemeral editor, read the
   drop-warnings, report (a CI tripwire). Self-contained — wraps the injected `rebuild` callable, so
   it does **not** modify the shared `materialize()`/`level apply` path. `--built` added only if
   step 1 is go.
4. **D0-b measurement** — run over real maps to decide whether D1 is worth building (needs the
   gitignored install content; content-blocked → tracked TODO).

**Footprint (mostly additive):** a new `uedcli/bsp/` module + an opt-in `level doctor --rebuilt`
flag. The static `level doctor` and `level apply` are left as-is; `doctor.py` gets only a cosmetic
stale-string fix. The one change that would touch a load-bearing feature (surfacing build-health on
`level apply`, step 3b) is **deferred, optional, warn-only, and never alters `apply`/`materialize`
behavior**.

**Spike outcome:** The parser is complete and validated — it reads the `Model` body byte-exact to
EOF and re-serializes byte-exact across the whole retail corpus (`spikes/2026-06-25-…` and
`spikes/2026-06-28-…`). The `0xa8` blocker is long resolved. The committed harness lives in
`dev/docs/spikes/bspspike/` (not `_scratch/`). The P0 gate is **GO** — see the status block above.

**Done when:** step 1 go/no-go recorded; step 2 landed (suite green); step 3 shipped per the spike
answer (docs current); step 4 measurement recorded or content-blocked TODO. D1-b proceeds only on a
green spike, as its own plan.
