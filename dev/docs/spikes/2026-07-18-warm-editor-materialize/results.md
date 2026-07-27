# Spike SP-E — warm-editor materialize: reused-editor cleanliness + timing split

**Date:** 2026-07-19 (all builds live against fresh `dx-lum-uned` editor containers on this host).
**Blocks:** the warm-editor materialize build (board item `resolved-2026-07-26-was-warm-editor-materialize` §8).
**Question (spec §8):** the whole design assumes *a REUSED editor builds as cleanly as a fresh one*.
Is that true, and what are the numbers (timing, RSS, resident-package behavior)?
**Reviewed:** 2-reviewer cold gate run 2026-07-19; findings folded (an over-stated SP-E.1, a
falsified "alternation" narration, and a mis-attributed SP-E.2 signature were all corrected below).

**Answer — editor *reuse itself works, but the current H3-verify placement breaks it.* 🔬** With the
post-verify disabled (`no_verify`), one warm editor builds the castle 4/4 cleanly and its output is
**canonically identical to a fresh build even on genuinely-reused builds** (below). But with the H3
post-verify enabled — which today runs *against the warm editor* — roughly **half** of reused builds
fail: the verify leaves the editor in a state where a later reused build's `MAP SAVE` silently
produces no file. So the blocker is **not** editor reuse and **not** content contamination of a
successful build; it is that the H3 verify must not run against the warm editor between builds. The
design's §8 premise is **not met as specced** and needs a fix + a re-run before shipping. Details,
timing, and RSS below.

## How this was tested

One warm editor is booted once and driven through many `level materialize` builds the **faithful**
way: the harness monkeypatches ONLY the container-lifecycle seams (`apply.ensure_editor` → return
the one warm container; `apply.stop_editor` → no-op) and then calls the **real**
`apply.run_materialize` N times. Every build runs the true production drive (full re-import →
`MAP REBUILD` → `LIGHT APPLY` → `MAP SAVE` → H3 verify with the live qualify pass against the reused
editor). The only thing changed vs today is that the container boots once and tears down once.

Trunk: the 161-actor castle (`_scratch/castle/uedcli/maps/foobar`, packages CoreTexSky / CoreTexWater
/ LUM_CoreTex). Harnesses (committed beside this doc, re-runnable):
- [`harness/warm_editor_probe.py`](harness/warm_editor_probe.py) — main run: cold baseline, boot,
  6 warm builds, RSS/log/OBJ-LOAD instrumentation, the first SP-E.1 comparison.
- [`harness/warm_editor_diag.py`](harness/warm_editor_diag.py) — failure-mechanism diagnostic:
  `wmctrl` dialog snapshot per build, UCC-stderr + saved-`.dx`-size capture on failure, a
  dismiss+settle mitigation phase, and the cross-level (SP-E.2) build.
- [`harness/warm_editor_noverify.py`](harness/warm_editor_noverify.py) — the decisive isolation:
  `no_verify` vs a separate-container UCC export.
- [`harness/warm_editor_canoncmp.py`](harness/warm_editor_canoncmp.py) — SP-E.1 completion:
  canonical-compares the genuinely-reused successes (builds 4 & 6) vs cold.
- [`harness/warm_editor_qualify_probe.py`](harness/warm_editor_qualify_probe.py) — a follow-up that
  turned out confounded (see SP-E.4); kept for the record.

Raw JSON for every run is under `_scratch/warm-spike/` (gitignored); numbers below are quoted from it.

---

## THE BLOCKER — reused builds fail intermittently at the H3 verify boundary 🔬

**Symptom (`warm_spike_results.json`).** Six consecutive warm builds of the same trunk in one editor:
`1 ✓(59.6s) · 2 ✗(17.5s) · 3 ✗(17.5s) · 4 ✓(57.9s) · 5 ✗(17.4s) · 6 ✓(57.2s)` — **3 of 6 failed**.
The 4-build diagnostic runs reproduced ~50% (`baseline 2/4`, `mitigated 2/4`). The exact per-build
propagation is **not cleanly deterministic**: the 6-build run failed builds 2 **and** 3
back-to-back, while the 4-build runs happened to alternate `✓✗✓✗`. What is firm is the **rate and the
correlation** (below), not a tidy one-build-on/one-build-off rule.

**It is NOT the GC "Cleaning up…" xmessage dialog.** `wmctrl -l` before each failing build showed
**no** `xmessage` window, and a defensive `dismiss_blocking_dialog()` + 1.5 s settle before every
build did **not** change the failure rate (still 2/4). Spec §4.3's leading-dismissal is fine to keep
but does not address this.

**The failure is a silently-missing `MAP SAVE`.** A failing build's drive finishes in ~17 s (vs
~58 s for a full build) and the H3 verify's UCC export aborts with
`Failed loading package: Can't find file '/work/<uuid>.dx'` — the saved temp does not exist
(in-container `stat` returned empty). The drive ran but `MAP SAVE` wrote nothing.

**It is caused by running the H3 verify against the warm editor — decisive within-one-editor
isolation (`warm_noverify.py`, phase A then phase B in the SAME warm container):**

| Variant | Verify against warm editor? | Result |
|---|---|---|
| **`no_verify=True`** | none | **0/4 failed** — every reused build succeeds in ~16 s and writes a ~449 KB artifact |
| full verify (UCC + qualify on warm) | yes | 2/4 failed |
| **UCC export isolated to a separate container**, qualify still on warm | partial | **2/4 failed** — isolating the second `wine` process does NOT fix it |

So the drive + `MAP SAVE` themselves are **reliable** on a reused editor (`no_verify` is 0/4). The
disruptor is the **H3 verify's interaction with the warm editor**. Isolating *only* the UCC
batchexport to a separate container still fails 2/4 — and those failures surface one step earlier (a
`docker cp` of the already-missing `/work` file), confirming the `MAP SAVE` was lost **before**
UCC runs, independent of where UCC runs. The remaining warm-editor interaction inside verify is the
live `OBJ DEPENDENCIES` qualify dump (`qualify_driver=ed`) and the editor simply being mid-verify.
A discriminator that drops *only* the qualify dump (`qualify_driver=None`) is **confounded** — verify
then mis-compares bare-vs-qualified names and fails 4/4 with `post-verify mismatch` on *every* build
including the first — so it cannot isolate the dump. **What is firm: verify-against-warm breaks
reuse; no-verify does not.** (This is the same class as the §89 board finding that `wine_ctl exec`
is fire-and-forget with no wait-for-completion — the editor is driven with no robust completion
barrier — surfaced here because warm reuse is the first path to drive a *second* build after a
verify.)

### Design implication (for the spec author — an open decision, flagged in `board/inbox/`)
The current §4.4 "H3 verify against the same live editor" (D-Q3, inherited from the ephemeral path)
is exactly what must change. Two candidate fixes — but **the evidence does not yet distinguish a
transient timing race from a durable bad state** left by a completed verify (the 1.5 s settle not
helping leans slightly *against* a short race). A cheap discriminator should gate the choice:

1. **Run the whole H3 verify (export AND qualify) against a SEPARATE throwaway editor** — the
   `qualify.export_and_qualify` pattern (it already boots its own ephemeral editor precisely because
   a reused editor is untrustworthy). This works whether the cause is a race or durable state.
   Isolating only the UCC export was tried and is insufficient (the qualify dump must move too).
   **Caveat:** verify costs ~42 s and needs an editor; a separate *cold* verify editor per build
   reintroduces a ~15 s boot ≈ the entire warm saving (below) — so the verify editor would itself
   need warm-pooling, or verify made cheaper, for warm reuse to net ahead.
2. **A robust editor-quiesce / CPU-idle barrier** after each build's verify — poll the container
   until the editor process drops to idle CPU before starting the next build (the §89 golden harness
   uses exactly such a `--quiet-reads`/CPU-idle barrier to keep a headless rebuild from racing;
   `harness/build_ued_golden.py` in the native-materialize spike). Keeps verify in the warm editor →
   preserves the full ~16 s saving. **Only works if the cause is a transient race** — so gate it
   behind a quick discriminator first (e.g. a long fixed sleep before build N: if failures vanish,
   it's a race and the barrier suffices; if they persist, the state is durable and only fix 1 works).

Either way **re-run SP-E to confirm 0/N before shipping**; the build is not green-lit as specced.

---

## SP-E question-by-question

**SP-E.1 — same-trunk double build (✅ answered, strengthened after review).** The genuinely-reused
successful builds — builds **4 and 6**, which ran *after* prior builds populated the object pool —
are `canonical_level_hash`-**identical** to a fresh cold build: `cold == warm1 == warm4 == warm6 ==`
`ad9ba84e…361ac` (`warm_canoncmp.py`, `warm_canoncmp_results.json`). (Their *raw* bytes differ by
~350 KB purely from object-table renumbering, §82/§83 — canonical export is the correct oracle.) So
the object pool surviving `MAP NEW` does **not** corrupt the *content* of a build that succeeds. The
original run only compared `cold == warm1`, but warm1 is the first drive after boot (empty pool) and
cannot exhibit reuse contamination — builds 4/6 are the real test, and they pass. ✅ live-verified.
(The reliability of *whether* a reused build succeeds is the separate blocker above.)

**SP-E.2 — cross-level, disjoint packages (🔬 a possible POSITIVE signal — inconclusive, must
re-test).** Built the 7-actor `anchor` trunk (refs `UNATCO`, disjoint from the castle's
`CoreTex*`/`LUM_CoreTex`) after castle builds in one warm editor. It failed with a **`post-verify
mismatch` on actor `Bounce_…`** at 30.9 s (`fail_detail` empty — so `MAP SAVE` *succeeded* and UCC
exported a file; this is a **content** mismatch, a *different* signature from the missing-file
blocker). **`Bounce_…` is a CASTLE actor** (`Bounce_3p0d6q` et al.), NOT an anchor actor — so a
castle actor appears in the anchor build's verify. **That is exactly the stale-pool cross-level
contamination SP-E.2 exists to detect.** BUT it ran in a flaky editor (it followed the *failed*
build `mit-4`), so it is not trustworthy in isolation, and it could alternatively be the same
bare-vs-qualified qualify artifact as SP-E.4's confound, or `MAP NEW` not fully clearing the prior
level. **Inconclusive but NOT nothing** — re-test cleanly once the reliability blocker is fixed, and
this is direct motivation to check whether §4.4.2's scoped-dump (and/or a stronger per-build reset)
is needed. (A castle build immediately after anchor succeeded.)

**SP-E.3 — `OBJ LOAD FILE=` on an already-resident package (✅ live).** Every warm build's
`ensure_load` re-issues `OBJ LOAD FILE=` for the 3 resident packages; across **21 such calls, zero
errors**, each ~1.3 s regardless of residency. Editor.log growth per repeat varied 0–24 KB —
**sometimes zero (indistinguishable from a silent skip), sometimes tens of KB** — so it is not a
hard error and not reliably a reload; either way harmless. **`ensure_load` runs unchanged and safely
on the warm path.** A resident-set skip is a valid *optimization* (~4 s/build for 3 packages; more
for a package-heavier level), not a correctness requirement. Lands in `quirks.md`.

**SP-E.4 — repeated `MAP NEW` stability (✅ the negative).** `MAP NEW`/GC-dialog is stable and NOT
the instability source (dialog rarely up; dismissing it changed nothing). The instability is the
verify boundary. So spec §4.4's "dialog dismissal at `MAP NEW`" is harmless-and-fine but is not what
makes reuse reliable.

**SP-E.5 — timing split.** On this host, castle trunk:

| Phase | Seconds | Source |
|---|---|---|
| Cold ephemeral end-to-end | **79.2** | ✅ measured (boot + drive + verify + teardown + `docker compose run` overhead) |
| Warm boot (container→ready) | **15.4** | ✅ measured |
| Drive alone (import→rebuild→light→save) | **~16** | ✅ measured (the `no_verify` builds) |
| H3 verify (UCC export + qualify dump) | **~42** | ⚠ **derived** = full-success (~58) − drive (~16); not directly timed |
| Teardown | **0.4** | ✅ measured |
| Warm build end-to-end (successful) | **~57–60** | ✅ measured (drive + verify, no boot/teardown) |

**Warm reuse saves ≈ boot + teardown ≈ 16 s/build (~20 % off the 79 s cold).** The ~58 s drive+verify
dominates and is per-build regardless (matches §1). The parts sum to ~73.8 s vs the 79.2 s cold
end-to-end; the ~5 s gap is the `docker compose run` + prefix-seed overhead that sits *outside* the
"container→ready" boot measure. **Sharpest new number:** the derived verify (~42 s) is *larger than
boot* (~15 s) — so fix-candidate 1 (separate cold verify editor) would cost about as much as the
warm saving itself. Worst single editor op is well under the 10-min idle deadline — §4.5 is safe.

**SP-E.6 — RSS + log growth (✅ measured, with a soak caveat).** Editor RSS: **85 MB → 181 MB on
build 1** (the package `OBJ LOAD`s), then **flat ~181–184 MB across builds 2–6** — no unbounded RSS
growth. **No RSS-driven §4.6 reboot cap needed** within this run. **Caveat:** builds 2/3/5 were
failures (~17 s, no full rebuild/light), so the soak is really only ~**3 full builds** (1/4/6) — the
"no growth" claim is weaker than the 6-build count suggests and a longer *successful* soak (post-fix)
should confirm it. `Editor.log` grows ~360 KB per full build (monotonic; minor housekeeping).

**SP-E.7 — colliding-bare-name qualification (deferred).** Not reached — needs the reliability
blocker fixed first (trustworthy successive builds) and a two-package colliding-name fixture that
does not exist yet. Re-scope with the SP-E.2 cross-level re-test (both exercise the same
live-qualify-dump-across-builds seam that SP-E.2 already flagged a possible positive on).

---

## What to pin / carry back

- **quirks.md** (done): the standing engine fact — *a reused editor driven for a second materialize
  after an H3 verify intermittently loses the next `MAP SAVE`; `no_verify` reuse is clean and
  content-identical* (dated, 🔬).
- **The spec** (board item `resolved-2026-07-26-was-warm-editor-materialize`) §8 (done): SP-E.1/3/5/6 folded; the
  blocker + candidate fixes recorded as an open design decision; SP-E.2's possible-positive and
  SP-E.7 deferred behind the fix.
- **board/inbox/** (done): the open design decision flagged for Andrzej (which fix; then re-run).
- **Regression:** the full "N reused builds all succeed" assertion waits for the fix (pinning a
  currently-failing behavior as a green test would assert the bug). But the **positive** facts here
  are pinnable now as integration-marked tests when the warm path lands: `no_verify` reused builds
  succeed 0-fail, and a genuinely-reused successful build is canonically == a fresh build
  (`warm_canoncmp.py` is the ready-made oracle).
