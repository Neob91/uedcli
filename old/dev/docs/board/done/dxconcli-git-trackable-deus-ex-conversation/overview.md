+++
priority = "p?"
kind = "unknown"
summary = "`dxconcli` — git-trackable Deus Ex conversation source ↔ `.con`"
+++

# `dxconcli` — git-trackable Deus Ex conversation source ↔ `.con`

— v1 BUILT 2026-07-05/06
(standalone `Tools/dxconcli/`, own `.venv-dxconcli`; 116 offline tests + a corpus-gated full
round-trip; the CLI decompiles/validates/recompiles real game files e.g. Mission1.con's 71
conversations). Byte-exact Layer-1 codec (`con_codec`, cmp-clean over 25 real `.con`); two-way
Layer-2 (`con_source`): all verbs, `if`/`choice`/`random`, fragments (Tarjan SCC/tail-position),
a total deterministic decompile. All 6 verbs (`new`/`compile`/`decompile`/`validate`/`search`/
`voices`) with a no-traceback error boundary. Plan:
`plans/2026-07-05-dxconcli-implementation-plan.md`; spec:
`specs/2026-06-26-uedcli-deusex-con-tool-design.md`. A live spike corrected the
`Jump.conversationID` model (`spikes/2026-07-05-deusex-con-jump-conid-live/`).
Inline-collapse pass DONE 2026-07-06 (single-use fragments inlined; Mission1 −77% fragments);
multi-error `validate` DONE 2026-07-06 (reports every broken conversation in one pass, each
located).
**Deferred remnants:** choice `skill:` gates (refused — no corpus data for the
wire encoding). Phase-4 golden fixtures folded into the per-verb tests + corpus round-trip.
