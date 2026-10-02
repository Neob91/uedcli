+++
priority = "p3"
kind = "debug"
summary = "umodel_parser harness PF_PORTAL constant is wrong (0x0080 = FakeBackdrop)"
+++

# umodel_parser harness PF_PORTAL constant is wrong (0x0080 = FakeBackdrop)

`dev/docs/spikes/bspspike/umodel_parser.py:447` sets `PF_PORTAL = 0x0080`. Real UE1
`PF_Portal = 0x04000000` (`uedcli/doctor.py:31`, `uedcli/native/csg_golden.py:48`); `0x0080` is
`PF_FakeBackdrop`. Used only in `report_model`'s `PF_Portal surfs` diagnostic count — the raw
`poly_flags` u32 still parses correctly, but that one printed count is mislabeled.

Left unedited on purpose: the 2026-06-28 spike doc records a decision to leave `umodel_parser.py`
unmodified because `uedcli/tests/test_native_materialize.py` imports it directly. The P0-gate test
(`test_umodel_p0_gate.py`) already uses the correct constants, and the D1 promotion will use
`doctor.py`'s. Fix the harness constant only if someone touches that file for another reason.

Found during the P0 feasibility-gate verification (2026-08-03).
