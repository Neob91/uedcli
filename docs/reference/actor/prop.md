# actor prop

get / set / unset

`actor prop get <name|-> [KEY…] [--kv | --json]` — print the EFFECTIVE value of each KEY, one per
line, in the order given: the stored value if set, else the class default (decoded offline from the
game packages), else the type's zero. A whole static array prints as one `(0=V,1=W,…)` line; a whole
struct prints every member. With **no KEYs**, dumps the actor's STORED props (plus
`Location`). `--kv` prints round-trippable `KEY=VALUE` lines (feeds back into `actor prop set`);
`--json` emits a `{key: value}` object (values as strings). The name may be `-` to read a stdin name
list and dump every piped actor (output is then `<name>\t<key>=<value>`).

`actor prop set <name> KEY[.PATH]=VALUE…` — set properties in one atomic, schema-validated edit.
`KEY=VALUE` replaces the whole value (static array: tuple form `KEY=(0=V,3=W)`, clearing unmentioned
elements; Vector/Rotator: comma sugar `KEY=X,Y,Z`); `KEY.N=V` edits one array element; `KEY.Member=V`
edits one struct member (siblings preserved; an unset prop bases on the class default). Unknown name
/ bad enum / out-of-bounds index / overlapping tokens are rejected; `Name`/`Brush` and the mover-key
geometry (`KeyPos`/`KeyRot`/`KeyNum`) are refused, but `NumKeys` is settable (2..8, ==
[`mover key count`](../mover.md)); `Location` routes to the typed field (a partial struct zero-fills).

`actor prop unset <name> KEY[.PATH]…` — clear properties (revert to class default). Clears the whole
prop, one array element (`KEY.N`), or one struct member (`KEY.Member`); clearing something not
stored succeeds silently; `unset Location` resets to the origin.

See also: [`actor find`](find.md), [`actor build`](build.md).
