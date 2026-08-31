# project

`project show [--json]` prints the resolved root, game, managed dirs, and composed package search
path (each entry tagged `project`/`base`); `--json` emits
`{root, game, maps, prefabs, catalog, search_path:[{path, provenance}]}`.

See also: [`docs/README.md`](../README.md#projects-uedclitoml) for the `uedcli.toml` schema and
package-layering rules.
