"""Live check of the pivot-cross change in THIS GUI (headless Chromium against this session's own
dev server on 5211 / backend 8795 — never the owner's 5173/8765).

Selects actors through the org panel (the same `onSelectActor` path a viewport click takes), then
reads the live three.js scenes back: how many sprites carry the pivot gizmo's renderOrder (40) and
where they sit. Screenshots each state for the record.
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

URL = "http://localhost:5211/"
OUT = "/workspace/uedcli/.claude/worktrees/agent-af7a9d5b5d2b653b1/_scratch/pivotre"

# `__r3f` is react-three-fiber's own store handle, hung off each mounted canvas element.
POS_JS = """
() => {
  const out = []
  for (const c of document.querySelectorAll('canvas')) {
    const state = (c.__r3f?.root ?? c.__r3f?.store)?.getState?.()
    if (!state) continue
    const hits = []
    state.scene.traverse((o) => {
      if (o.isSprite && o.renderOrder === 40) hits.push([o.position.x, o.position.y, o.position.z])
    })
    out.push(hits)
  }
  return out
}
"""


def settle(page, seconds=6):
    page.wait_for_selector("canvas", timeout=60000)
    time.sleep(seconds)


def main() -> int:
    with sync_playwright() as p:
        # The installed build (1243) doesn't match this playwright package's expected revision, so
        # point at the real binary rather than reinstalling browsers on a shared host.
        browser = p.chromium.launch(
            executable_path="/home/agent/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell",
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(URL)
        settle(page, 10)
        page.screenshot(path=f"{OUT}/gui_boot.png")

        brushes = page.evaluate(
            "async () => (await (await fetch('/api/scene')).json()).actors"
            ".filter(a => a.brush).slice(0, 2).map(a => [a.name, a.location])"
        )
        print("brush actors:", json.dumps(brushes))
        if len(brushes) < 2:
            print("not enough brushes")
            return 1
        (a_name, a_loc), (b_name, b_loc) = brushes

        states = [
            ("none", []),
            ("one-A", [(a_name, False)]),
            ("two-AB", [(a_name, False), (b_name, True)]),
            ("back-to-B", [(a_name, False), (b_name, True), (a_name, True)]),
        ]
        for label, steps in states:
            page.reload()
            settle(page)
            for name, additive in steps:
                page.get_by_text(name, exact=True).first.click(
                    modifiers=["Control"] if additive else []
                )
                time.sleep(1.0)
            time.sleep(1.5)
            per_canvas = page.evaluate(POS_JS)
            total = sum(len(h) for h in per_canvas)
            first = next((h[0] for h in per_canvas if h), None)
            print(f"{label}: {total} pivot sprite(s) across {len(per_canvas)} canvases; at {first}")
            page.screenshot(path=f"{OUT}/gui_{label}.png")
        print("A at", a_loc, " B at", b_loc)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
