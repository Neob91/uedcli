// Platform-aware additive-modifier detection (owner ruling): macOS remaps Control+primary-click to
// a secondary (right) click at the OS level, BEFORE the browser ever sees a left-button
// mousedown/pointerdown -- so a Ctrl+click/Ctrl+drag that starts with Ctrl already held never
// reaches this app as a left-button press on a Mac at all (live owner report: "Ctrl+LMB drag doesn't
// work -- you need to start dragging, then add Ctrl", which is exactly what this predicts: Ctrl
// added mid-drag has no fresh click left to reinterpret, but Ctrl-from-the-start does). Cmd isn't
// remapped this way, so it's the one modifier that actually works for every additive gesture
// (multi-select click, Ctrl/Cmd-drag actor move, the org panel's find-focus) on a Mac.
//
// Every additive-modifier check in the app reads `isAdditiveModifier` below instead of
// blanket-accepting both `ctrlKey` and `metaKey` (the previous convention, which silently tolerated
// a modifier -- Ctrl -- that doesn't actually work for a fresh click/drag on Mac): on a Mac, ONLY
// `metaKey` counts; everywhere else, ONLY `ctrlKey` does. `metaKey` (the Windows/Super key) is left
// alone on non-Mac platforms deliberately -- there's no equivalent OS-level reason to accept it there.
export function isMac(): boolean {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } }
  const platform = nav.userAgentData?.platform || navigator.platform || navigator.userAgent
  return /mac/i.test(platform)
}

export function isAdditiveModifier(e: { ctrlKey: boolean; metaKey: boolean }): boolean {
  return isMac() ? e.metaKey : e.ctrlKey
}
