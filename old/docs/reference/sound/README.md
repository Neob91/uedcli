# Sound

`sound` catalogs the substrate's audio the way `class` catalogs its actor classes — enumerate,
inspect, search, and record a classification — offline, reading the game's own `.uax`/`.u`
packages, no editor or level. This is **phase (a)**: no sample decoding yet, so there is no `sound
preview` (spectrogram), duration, or export.

| Command | What it does |
|---|---|
| [`sound list`](list.md) | enumerate every sound object, one full dotted ref per line |
| [`sound show`](show.md) | a sound object's facts (package, group, identity) + stored classification |
| [`sound search`](search.md) | ranked discovery: objects whose name / stored tags / description match the terms, best first |
| [`sound classify`](classify.md) | record / inspect what a sound object IS — `set`/`unset`/`status`/`tags` |

See also: [`music`](../music/README.md) (same catalog shape, plus title/format),
[`class`](../class/README.md).
