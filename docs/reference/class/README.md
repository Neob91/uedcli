# Class

Actor-class discovery, offline, reading the game `.u` packages: browse the inheritance tree,
inspect a class's props/facts, render its default mesh, rank by relevance, warm the schema cache,
and record a classification (tags + description).

| Command | What it does |
|---|---|
| [`class list`](list.md) | browse actor classes as an indented inheritance tree (rooted at `Engine.Actor`) |
| [`class show`](show.md) | a class's own editable props by category + super chain, a Facts block, and any stored classification |
| [`class preview`](preview.md) | render the class's default Mesh as an orthographic PNG thumbnail |
| [`class search`](search.md) | ranked discovery: classes whose name / stored tags / description match the terms, best first |
| [`class prewarm`](prewarm.md) | eagerly warm the package schema cache so a later offline `list`/`search`/`show` starts warm |
| [`class classify`](classify.md) | record / inspect what a class IS — `set`/`unset`/`status`/`tags` |

See also: [`sound`](../sound.md) and [`music`](../music.md) (the same catalog shape over audio),
[`texture`](../texture.md) (the same shape over textures),
[classes.md](../../leveldesign/deusex/classes.md) (the Deus Ex class families in level-design terms).
