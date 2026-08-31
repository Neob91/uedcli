# class search

`class list` **enumerates** the class tree deterministically; `class search` **ranks** it by
relevance. Give it one or more terms and it prints the matching classes best-first, matching each
term against the class's leaf name, its stored classification tags, and its description.

```bash
uedcli class search chair                              # anything named/tagged/described "chair"
uedcli class search crate --tag storage --drawtype DT_Mesh
uedcli class search lamp --subclass-of Engine.Light --json
```

- **Terms are required.** A term-less `class search` **exits 2** pointing at `class list` (the
  enumerator). A class must match **every** term (AND); a term matching nothing drops the class.
- **Ranking** is a fixed tier order per term, summed across terms: exact leaf class name (5) > exact
  tag (4) > substring of the `Package.Class` ref (3) > substring of a tag (2) > substring of the
  description (1). Ties break by ref ascending, so output is deterministic.
- **Corpus** is every placeable Actor subclass. `--subclass-of Package.Class` restricts it to that
  base's descendants (an unknown base **exits 2** naming it); `--include-abstract` also searches
  abstract / non-placeable classes.
- **`--tag T`** (repeatable) keeps only classes carrying that exact stored tag — reserved
  `mount:`/`faces:` tags filter here like any other (`--tag faces:+x`). **`--drawtype DT`** keeps
  only classes whose resolved `DrawType` default equals `DT` (case-insensitive; an unknown token
  **exits 2** listing the valid ones). `--drawtype` reads each surviving class's defaults, so it
  costs more than a name/tag match.
- Plain output is one `Package.Class` per line to stdout (the match count on stderr); **no match** is
  a clean exit 0 with empty stdout. **`--json`** emits one object per match:
  `{ref, score, classified, tags, description}`. With no composed package path, `search` **exits 2**
  (`no package search path`).

See also: [`class list`](list.md), [`class classify`](classify.md).
