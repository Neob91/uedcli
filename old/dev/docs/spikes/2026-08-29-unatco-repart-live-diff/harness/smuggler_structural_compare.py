#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
from uedcli.native import umodel as UM
import utexture_decode as UT

GOLDEN = "/workspace/uedcli/_scratch/smuggler-structural-only/golden_smuggler_structural_resume.dx"
pkg = UT.load_package(GOLDEN)
models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
print(f"editor structural-only: nodes={len(m.nodes)} surfs={len(m.surfs)} leaves={len(m.leaves)} "
      f"verts={len(m.verts)} points={len(m.points)} vectors={len(m.vectors)}")
