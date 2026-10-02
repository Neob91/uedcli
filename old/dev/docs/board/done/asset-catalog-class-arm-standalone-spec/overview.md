+++
priority = "p2"
kind = "implement"
summary = "Standalone spec for the asset-catalog CLASS arm, split from the 4-kind engine; built C1-C4."
depends-on = ["unified-asset-catalog"]
+++

# asset-catalog class arm — standalone spec

Done (C1–C4, merged). The `class` noun now has `show` (mesh facts: signed local extents, collision,
prepivot, drawtype, parent, + stored classification; `--json`), `preview` (mesh thumbnail, `--rotate`
pose, azimuth), `classify set/unset/status/tags` (git-tracked shards `{kind,ref,tags,description}`,
JSONL batch, `mount:`/`faces:` shape-check), `list --classified/--unclassified --json`, `search`
(ranked), and `prewarm` (schema cache). Owner §8 rulings folded; the `conventions.md` JSONL carve-out
landed.

Owner-gated tails still parked: the `direction/asset-catalog.md` no-override wording fix
(`direction-asset-catalog-md-reword-the-class`) and the C5 `docs/leveldesign` craft line
(`class-arm-c5-one-docs-leveldesign-line-tying`). Deferred with their own board items: C0 defaults
cache, the C2 preview-cache pool, the shard-index roll-up, `classify prune`/`list-outdated`. Owed on
real content: extents' RotOrigin/world-facing probe, and a fill-cost measurement.
