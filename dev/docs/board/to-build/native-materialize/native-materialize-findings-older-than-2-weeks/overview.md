+++
priority = "p1"
kind = "owner-question"
summary = "Owner rulings steering the geometry/lighting parity push (2026-08-28): (1) ignore any native-materialize finding older than ~2 weeks — the code has moved; (2) never trust a test on a non-OG (non-original shipped) Deus Ex level — only original retail levels are valid parity evidence."
+++

# Owner rulings: freshness and level-source validity for the parity push (2026-08-28)

Given live while planning the Wanchai + Points-residual push. Both bind the whole effort.

1. **Native-materialize findings older than 2 weeks are not trustworthy.** The Rust
   `uedcli-native` core has changed a lot (the 913→448→0 geometry push, the native lighting bake).
   When a board item or spike cites a native count/behavior measured before ~2026-08-14, re-measure
   before relying on it — do not assume it still reproduces.

2. **Never trust any non-OG Deus Ex level test.** Only original, shipped (retail) Deus Ex levels
   count as valid parity evidence. `Test_Castle.dx`, `TestMap`, and other non-retail fixtures do
   not — a result on them is not evidence of parity with how UnrealEd builds retail content.

These came through the plan questions 2026-08-28; this item parks them until folded into a durable
process doc (conventions/direction), which needs the owner's yes to edit.
