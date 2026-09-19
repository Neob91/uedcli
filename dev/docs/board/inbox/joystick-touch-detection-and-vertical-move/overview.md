+++
priority = "p2"
kind = "investigate"
summary = "joystick touch-detection is static/unreliable; owner wants Q/E replaced with a modifier+W/S/LMB vertical scheme -- needs a conflict-free modifier"
+++

# Joystick visibility detection + Q/E replacement

Two related owner questions, logged together (2026-09-19).

## 1. Joystick touch detection: static capability check, possibly wrong approach

`web/src/scene/touchCapability.ts`'s `isTouchCapableDevice()` is computed ONCE per mount via static
feature detection (`'ontouchstart' in window || navigator.maxTouchPoints > 0`), gating whether
`MoveJoystick` renders at all (`Viewport3D.tsx`). This is a known-unreliable heuristic -- it
false-positives on hybrid/touchscreen laptops (and, per this session's own findings, Steam Deck)
even when the device is only ever driven by a mouse, and it can never correct itself mid-session if
wrong.

Owner's question: should the joystick instead only appear once a REAL touch event actually fires
(lazy, event-driven detection on the first genuine `pointerdown`/`touchstart` with
`pointerType === 'touch'`), rather than sniffing capability up front? This would eliminate false
positives entirely -- a device that merely CAN touch but is never touched would never show the
control -- at the cost of the joystick not being visible from the very first frame on a genuinely
touch-first device (it would pop in after the user's first real touch). Needs a design decision, not
just an implementation swap: does "appears after first touch, not before" read as broken/missing on
a real touchscreen, or is it an acceptable, even unnoticeable, tradeoff? Worth prototyping both to
compare, or checking how other touch-aware web apps handle this same detection problem.

## 2. Replace Q/E with a modifier + W/S (and LMB) for vertical movement

Owner isn't sold on Q/E for up/down and would rather hold a modifier key that repurposes the
EXISTING W/S keys (and LMB) for vertical movement instead of a dedicated key pair. Needs: which
modifier key is actually free to use, without conflicting with (a) real UED22's own key bindings,
and (b) this app's own already-established modifier conventions.

**(a) Real UED22 bindings, so far confirmed:** `dev/docs/unrealed/commands.md` only documents one
concrete modifier combo directly: **`Ctrl+A` = "select all actors"** (real, confirmed -- it's why
`commands.md`'s own test-harness notes avoid `Ctrl+A` for text-selection). No broader survey of
UED22's viewport-navigation modifier bindings (Ctrl/Alt/Shift's role during camera movement
specifically) has been done -- this needs real RE (disassembly of `Editor.dll`'s input handling, or
a live capture) before picking a modifier, per `GUI-PARITY.md`'s standing method and its hard
own-binary-evidence rule. Don't guess from general UE1 folklore.

**(b) This app's OWN already-claimed modifiers** (`Viewport3D.tsx`'s `onDrag` callback, `dragGesture.ts`):
- **Alt** + LMB-drag = orbit (`if (altKey && (buttons & 1) !== 0) return orbit(...)`).
- **Ctrl**/**Meta** + click = additive multi-select.
- **Shift** = threaded through as the brush-selection-tap gate (`selection.ts`'s
  `canSelectBrushTap`).

So all three standard modifiers already mean something in this GUI's existing controls -- there is
no modifier that is simply "free." The real design question is whether a NEW modifier+W/S/LMB
vertical-move scheme can safely REUSE one of these (e.g. Alt, since `Alt+LMB-drag` = orbit and
`Alt+W`/`Alt+S` = vertical-move are different input channels -- keyboard keys vs. a mouse-drag --
and might not actually collide in practice), or whether it needs a modifier none of the above touch
at all. This needs to be resolved with the real UED22 RE from (a) and a deliberate scoping decision,
not assumed safe just because the channels differ.

## What to do, when picked up

1. RE UED22's actual viewport-navigation modifier-key bindings against `uned/UED22/Editor.dll`
   (disassembly and/or live capture), per `GUI-PARITY.md`'s method -- confirm what Ctrl/Alt/Shift
   (if anything) do during fly/orbit camera movement specifically, not just the one `Ctrl+A` binding
   already known.
2. Cross-reference against this app's own already-claimed modifiers (listed above) and decide
   whether reuse is safe or a fresh modifier is needed.
3. Separately, decide the touch-detection question (event-driven vs. static) -- unrelated to the
   modifier-key question, bundled here only because both came from the same owner message.

## Where to look

`web/src/scene/touchCapability.ts`, `web/src/scene/Viewport3D.tsx` (`FlyKeys`, `onDrag`, `FLY_KEYS`),
`web/src/scene/dragGesture.ts`, `dev/docs/unrealed/commands.md`, `GUI-PARITY.md` (RE method).
