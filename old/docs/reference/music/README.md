# Music

`music` catalogs the substrate's music modules the way `class` catalogs its actor classes —
enumerate, inspect, search, and record a classification — offline, reading the game's own
`.umx`/`.u` packages, no editor or level. `music` additionally reports each module's **embedded
title** and **format**. Sample decoding isn't implemented yet, so there is no `music preview`
(spectrogram), duration, or export.

| Command | What it does |
|---|---|
| [`music list`](list.md) | enumerate every music module, one full dotted ref per line |
| [`music show`](show.md) | a module's facts (package, group, identity, title, format) + stored classification |
| [`music search`](search.md) | ranked discovery: modules whose name / stored tags / description match the terms, best first |
| [`music classify`](classify.md) | record / inspect what a module IS — `set`/`unset`/`status`/`tags` |

See also: [`sound`](../sound/README.md) (same catalog shape, no title/format),
[`class`](../class/README.md).
