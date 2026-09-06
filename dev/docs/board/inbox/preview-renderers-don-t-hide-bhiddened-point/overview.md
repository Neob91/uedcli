+++
priority = "p1"
kind = "implement"
summary = "Preview renderers don't hide bHiddenEd point actors"
+++

# Preview renderers don't hide bHiddenEd point actors

`_preview_point_data` (`uedcli/cli/rendering.py:944`) selects every actor with `a.brush is None` as
a point actor and draws it unconditionally:

```python
point_actors = [a for a in actors if a.brush is None]
```

No `bHiddenEd` check anywhere in the point-actor path (`_resolve_point_render`, `PointRender`
drawing in `preview.py`). Real UnrealEd hides `bHiddenEd=True` actors in editor viewports; our
previewers should match.

`dev/docs/unrealed/rendering.md` and `quirks.md` have zero mentions of "hidden" — no documented
UnrealEd ground truth for this yet, so the fix needs an RE finding (or an editor probe) confirming
exactly which actors real UnrealEd hides, before folding the rule into `rendering.md`.

`LevelInfo`'s class default IS `bHiddenEd=True`, confirmed from a decompiled `Engine.LevelInfo`
(`uned/spikes/levelinfo/LevelInfo.UC:281`) — so a correct filter must exclude `LevelInfo`, not just
apply the property blindly. Confirm whether real UnrealEd's viewport actually hides `LevelInfo` (its
special-cased singleton status may exempt it) before implementing, since a filter that also hides
`LevelInfo` from every preview would be a regression, not a fix.
