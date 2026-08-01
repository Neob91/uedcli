# Should `level doctor` also flag near-grid slop, pointing at `brush snap`?

## Context

`brush snap` cleans near-grid float noise on demand. Separately, `level doctor` could *detect* such
slop — a vertex within a small band of a grid line but not on it — and advise running `brush snap`,
so an author finds the problem without knowing to look. The item raised this as open.

Options:

- **Defer to a separate item (recommended).** Ship the filter first. A doctor advisory is a distinct
  feature: it needs its own grid/band definition (which grid? doctor has no `--grid`), a severity, and
  care not to flood already-off-grid retail imports. Bundling it widens this item's scope.
- **Add it here.** One change delivers both cleaning and detection. Cost: the scope and the
  open design questions above land inside a filter build.

Recommendation: defer — file a separate `level doctor` item once the filter exists and the grid/band
question can be answered against real use.

## Answer

<!-- Empty = open. -->
