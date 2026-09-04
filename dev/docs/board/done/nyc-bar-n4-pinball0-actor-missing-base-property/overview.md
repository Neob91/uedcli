+++
priority = "p2"
kind = "debug"
summary = "RESOLVED — NYC_Bar N=4 pinball0 missing `Base` was native's wrong base-stamp gate; fixed to the measured bCollideWorld+ancestry rule. All 3 ladder levels pass N=1..4."
+++

# NYC_Bar N=4: Pinball actor omits the editor-set `Base` property — RESOLVED

Native's `_base_stamped` (`uedcli/native/unbuilt.py`) used the wrong gate
(`bStatic==False & bCollideWorld==True & Physics==PHYS_None`), which dropped `Base` on `Pinball0`
(class-default `PHYS_Falling`). The empirically measured UED22 rule (spike
`2026-09-04-base-stamp-rule`, 27-class matrix) is:

    stamped ⇔ no authored Base AND class-default bCollideWorld==True
              AND IsA(Engine.Decoration | Engine.Inventory | Engine.Pawn)

No physics clause, no bStatic clause. Implemented on branch `native-parity-incremental`; regression
test in `uedcli/tests/test_native_roundtrip.py` (`test_base_stamp_rule_collideworld_and_ancestry`).
Gate re-run: all three ladder levels PARITY YES at N=1..4. Only `Pinball0` changed vs the old native
code; NYC_Bar's Toilets were already stamped under the old rule; UNATCO/WanChai first-4 unaffected.
