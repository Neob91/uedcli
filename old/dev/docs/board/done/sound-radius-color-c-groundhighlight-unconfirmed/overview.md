+++
priority = "p3"
kind = "investigate"
summary = "sound-radius uses C_GroundHighlight, a distinct constant from collision/light -- its real RGB value is unconfirmed"
+++

# Sound radius color (`C_GroundHighlight`) unconfirmed

Owner question (2026-09-18): "Didn't radii view show blue for sound radius?"

Not fixed, not chased -- filed for the record.

## What's actually confirmed vs. not

The `radii-overlay-color-hardly-visible-disassemble` disassembly pass (done, `dev/docs/board/done/`)
confirmed sound radius uses a genuinely DIFFERENT `UEditorEngine` color member than collision/light:
`C_GroundHighlight` at `+0x1a8`, vs. `C_BrushWire`/`C_ActorArrow` for collision/light. The call site
(`Editor.dll` VA `0x1003da35`) and the member offset are both binary-confirmed (`GUI-PARITY.md`'s
"Radii overlay colors" section, cross-checked via `DrawWireBackground`'s own two uses of the same
offset).

**What was NOT confirmed: `C_GroundHighlight`'s actual RGB value.** That pass never read it out of
`uned/UED22/unrealtournament.ini` or disassembled a load of it -- it only established the member
exists and is used for sound radius, distinct from the other two. Whether it's blue, or something
else, is unknown from this campaign's own evidence.

Also note: this GUI doesn't render sound radius as an overlay at all right now (`GUI-PARITY.md`:
"Our GUI doesn't currently draw mover/sound radii at all"), so there's nothing in the live app to
check this against even if the value were known.

## What to do (if ever picked up)

Read `C_GroundHighlight`'s value straight out of `uned/UED22/unrealtournament.ini`'s
`[Editor.EditorEngine]` block, the same way `C_BrushWire`/`C_ActorArrow` were read for the landed
radii-color fix. No disassembly needed for the value itself (only the member identity, already
established) -- this is a ~5-minute lookup whenever sound-radius rendering is ever prioritized.

## Where to look

`uned/UED22/unrealtournament.ini`, `GUI-PARITY.md`'s "Radii overlay colors" Findings section.
