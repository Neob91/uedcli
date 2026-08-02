+++
priority = "p3"
kind = "implement"
summary = "Materialize should fail/WARN loudly instead of silently dropping textures when the composed search path resolves to 0 packages or a referenced package is missing"
+++

# Materialize should fail/WARN loudly instead of silently dropping textures when the composed search path resolves to 0 packages or a referenced package is missing

p3` **Materialize should fail/WARN loudly instead of silently dropping textures when the composed search path resolves to 0 packages or a referenced package is missing.** Residual hardening of the two now-fixed texture CRITICALs (H3 re-export can't-find-package; symlink-outside-repo 0-package drop). The underlying resolution is fixed (host-native CLI + uniform mount), but the failure mode was *silent* — a dangling glob / missing package dropped every face's `Texture=` with no error and a misleading "0 packages" report. Add: (i) WARN on a 0-package composed path / dangling glob; (ii) materialize fails loudly on a referenced package absent from the load set (vs. a later opaque H3 mismatch).
