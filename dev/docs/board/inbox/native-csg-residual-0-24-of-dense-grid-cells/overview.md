+++
priority = "p3"
kind = "debug"
summary = "native CSG residual: ~0.24% of dense-grid cells read native-SOLID where the editor is EMPTY (thin shells along octagonal-tower/diagonal-wall slant planes)"
+++

# native CSG residual: ~0.24% of dense-grid cells read native-SOLID where the editor is EMPTY (thin shells along octagonal-tower/diagonal-wall slant planes)

p3 native CSG residual: ~0.24% of dense-grid cells read native-SOLID where the editor is
EMPTY (thin shells along octagonal-tower/diagonal-wall slant planes). Root cause is the un-ported
`bspOptGeom`/Balance=50 BSP-quality trim + `zones::assign_leaves` `outside` propagation marking
some cells solid; the point-in-solid leaf correction (build.rs) only clears spurious EMPTY leaves,
not spurious solid. Centroid divergence is already 0 and grid agreement 99.76% (was ~89%). Would
need either the bspOptGeom trim or a full point-in-solid leaf re-assignment (touches zones.rs).
