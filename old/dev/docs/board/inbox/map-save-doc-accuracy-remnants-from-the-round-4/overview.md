+++
priority = "p3"
kind = "chore"
summary = "`MAP SAVE` doc-accuracy remnants from the round-4 review — five small corrections, all in dev docs, none affecting behaviour"
+++

# `MAP SAVE` doc-accuracy remnants from the round-4 review — five small corrections, all in dev docs, none affecting behaviour

Logged rather than fixed under the two-round gate
ceiling. (a) `unrealed/commands.md` and `spikes/2026-07-25-map-save-mechanism/README.md` say the
`SavePackage` literals sit at "**consecutive** offsets"; they don't — 14 other phase literals
(`Untag`, `TagExports`, `CheckExportCompat`, `TagImports`, `ExportNames`, `SaveSummary`,
`BuildNameMap`, `SortNames`, `SaveNames`, `BuildImportMap`, `SortImports`, `BuildExports`,
`SortExports`, `SetLinkerMappings`) sit between `UObject::SavePackage` and `SaveExports`, and four
more between `Save.tmp` and `Moving '%s' to '%s'`. Say "ascending offset order" and quote the full
run — the intervening names (esp. `SaveSummary` early vs `RewriteSummary` last) are STRONGER
evidence for the inferred sequence than what was published. (b) Both docs call the summary "the
36-byte header"; the engine's summary is **64 bytes** (measured `nameoff=64` on `00_Intro.dx`,
`00_Training.dx`, `00_TrainingCombat.dx` — bytes 36-63 hold the GUID + generation records). 36 is
uedcli's READ WINDOW, not what `RewriteSummary` patches. (c) `measure_header_window.py` bare-asserts
every package passes; it should collect outliers instead, since legitimate zero-count packages exist
(`uned/UED22/WinDrv.u`, `Window.u`) and a search path containing one would die with an unexplained
`AssertionError`. (d) That harness needs the retail install AND the tool dir as cwd (run from the
repo root it dies with a confusing `ImportError` because the repo's `uedcli/` maps dir shadows the
package); document both and fail with a named error. (e) `architecture.md` says
"`qualify.export_and_qualify` … never called either" — that function no longer exists (removed in
`607dc430f`); say it was deleted with the store. (2026-07-25, round-4 cold reviews.)
