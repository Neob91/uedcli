+++
priority = "p3"
kind = "implement"
summary = "GUI Inspector: dynamic ArrayProperty support (format known, no real content exercises it)"
+++

# GUI Inspector: dynamic ArrayProperty support (format known, no real content exercises it)

Parked out of `dev/docs/board/to-spec/gui-inspector-effective-props-search-show-all/` (owner
ruling, 2026-09-23): skip for this round, `ArrayProperty`-kind properties are excluded from
`EffectiveProp` the same way `object`/`class` are (not shown, no placeholder row) — not because the
format is unknown, but because there is no real content anywhere to build/verify it against.

## What's already known (RE'd this session, not open work)

- **Serialization is fully understood** — just in the wrong subsystem for this feature.
  `uprops.values.decode_array_tag` + `mapimport.render_prop` already decode a dynamic array's
  compiled bytes (compact-index element count + N elements in the element's own per-kind wire
  form, resolved via `Prop.array_inner`) and render it as T3D text — one indexed line per element,
  `Foo(0)=`, `Foo(1)=`, …, textually identical to a STATIC array's own convention; an empty array
  contributes zero lines. Byte-exact tested: `uedcli/tests/test_mapimport_array.py`.
- **`propedit` (the CLI's `actor prop` engine, and everything the GUI Inspector spec reuses) never
  calls this decoder at all** — every array-handling code path in `uedcli/propedit/*.py` branches
  on `prop.array_dim > 1` (the static-array case), never `prop.kind == "ArrayProperty"`. Wiring
  this in means calling `uprops.decode_array_tag` directly, bypassing `propedit` for this one kind —
  a real (if small) departure from the "reuse propedit's engine" pattern the rest of the Inspector
  spec follows.
- **No real content exists to build this against.** Scanned every class in all 37 packages on the
  real `[games.deusex]` substrate: 13 total `ArrayProperty` declarations exist anywhere, exactly ONE
  has `CPF_Edit` set (`Editor.EditorEngine.EditPackages`) — editor/UCC config, not a level-placeable
  actor property, populated via `.ini` repeated-key syntax in practice (a DIFFERENT serialization
  from the T3D form above — doesn't even validate it). No real Deus Ex level actor, anywhere in the
  substrate, has an editable dynamic array property. (Every actor-relevant array-shaped thing that
  DOES occur in real content — `MultiSkins` etc. — is a static array, already fully supported,
  unrelated to this item.)

## When to pick this up

Only if/when real content (a mod, a custom class, a different substrate) actually needs it — this
is a completeness/robustness gap, not a blocker for any current Deus Ex level work. If picked up:
reuse `uprops.decode_array_tag`/`Prop.array_inner` directly (don't re-derive the format), and note
there's no real fixture in this repo to test against — a synthetic fixture (like
`test_mapimport_array.py`'s own approach) will be needed either way.

## Related

- `dev/docs/board/inbox/committed-uned-ued22-engine-u-vs-substrate/` — a tangential finding from the
  same investigation (an `Engine.u` version mismatch on an unrelated property), filed separately.
- Parent spec: `dev/docs/board/to-spec/gui-inspector-effective-props-search-show-all/`.
