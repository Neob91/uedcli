+++
priority = "p2"
kind = "unknown"
summary = "N=33 soup divergence = a merge-blocking clip on a DEAD merlon-east node; a cumulative incremental-tree-ORDER divergence, NOT any local rule — BLOCKED on an editor-tree oracle"
+++

# N=33 soup divergence = a merge-blocking clip on a DEAD merlon-east node; a cumulative incremental-tree-ORDER divergence, NOT any local rule — BLOCKED on an editor-tree oracle

Traced to
full mechanism + instruction level 2026-07-17 (`sections/82 §10.6`, supersedes §10.5's read). The
`x=112` "box" is `Merlon_y4jykf`'s east face (brush 10/N=11); `TowerNE`'s west face is `x=111.958`
(brush 31/N=32); `RoofNE` is N=33. The roof underside splits at WallBack-north `y=160` into an upper
band (→ reaches `TowerNE` west, clips `111.958` ✓) and a lower band (`y∈[128,160]`) that descends
WallBack-**top** into the merlon east-face `iFront` staircase and SPLITs at **`node[80]` (`x=112`,
`nv=0` — DEAD, deleted by TowerNE's FWTB)**. `node[80]`'s live coplanar sibling `node[255]`
(`x=111.958`, the TowerNE-west fragment, absorbed there at N=32 because `0.042 < 0.25`) is on its
`iPlane` chain, which `SP_Split` does NOT consult — so the lower band keeps `x=112`. The two same-plane
bands then fail `TryToMerge` (`y=160` corner `111.958` vs `112`, `0.042 > 0.002` box); the editor
produces BOTH at `111.958` and merges to one 5-vert face. **Three decisive negatives (§10.6):**
(1) disasm of `FilterEdPoly 0x32bf0` proves the engine has **no dead-node (`nv==0`) skip** — it splits
at every node's surf plane, so the editor clips `111.958` only because `node[80]` is off its roof-B
path (tree structure, not a rule); (2) the `0.25` threshold is **non-separable** — a `very_precise`
probe fixes the roof but symmetrically un-merges the mirror sliver on the tower SW diagonal
(`-0.707,-0.707,0,-178.2`), same `0.042` gap; (3) **only the SOUP matters** (final tree is rebuilt
from it) — editor `golden32/33` final trees carry the same `x=112`/`x=111.958` plane multiset (`2/2`)
as native, the sole difference is this one roof soup face. The temp-brush-`LAME/0/0` and coplanar-seed
hypotheses were prior disproven. **The whole `only-editor` family (`-248/-280/-295.7/BRoof`) is this
shape.** Ordered `node_diff` prefix stays `0/1156`. **The editor's INCREMENTAL tree is not dumpable
(only its soup-rebuilt final tree is), so pinning the earlier order rule that diverges is blocked; the
next lever is an editor-tree oracle (e.g. an `MAP REBUILD` with node-add logging), NOT another blind
local tweak.** Do NOT force the merge/clip — forcing regressed twice.
