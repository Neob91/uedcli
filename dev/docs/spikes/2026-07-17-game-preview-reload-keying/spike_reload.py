#!/usr/bin/env python3
"""SP-R — live spike for the warm-container reload-keying GATE (spec
board item `warm-game-remnants` §8).

Boots ONE warm game container and drives repeated POST-BOOT, SYMLINKED, Nth
travels — the two deltas the shipped `--game` tier never exercised (it boots
fresh, `docker cp`s ONE real file, travels once, dies). Answers:

  (a) FName-not-GUID keying / no resident reuse: travel stemA(content A) then a
      fresh unique stemB(content B), assert B renders (GetURLMap==stemB).
  (b) THE GATE: an Nth `open` of a brand-new POST-BOOT SYMLINKED stem in a REUSED
      container resolves. Repeated across many distinct stems.
  (a') identical bytes under a NEW name still load fresh (fresh linker).
  (c) NAME_SIZE: pin the FName cap empirically — travel stems of growing length
      and two stems differing only past char 63; watch GetURLMap for truncation
      / collision.
  (d) RSS across travels (calibrate the reboot ceiling).
  (e) OBSERVE a mission-map (conversation-prone) frame — screenshot only.

Run: .venv/bin/python dev/docs/spikes/.../spike_reload.py
Throwaway output (logs, screenshots) → _scratch/spike-reload/. Results markdown
is written next to this script (durable).
"""
import sys, time, hashlib, subprocess
from pathlib import Path

UEDCLI = Path(__file__).resolve().parents[4]           # Tools/uedcli (dev/docs/spikes/<slug>/file)
sys.path.insert(0, str(UEDCLI))
from uedcli import config, preview_game as pg           # noqa: E402

MAPS = Path("/home/neob91/Games/LutrisDX/drive_c/DX/Maps")
OUT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/spike-reload")
OUT.mkdir(parents=True, exist_ok=True)
POOL = "/work/spikepool"                                # in-container: real files live here
MAPSDIR = "/work/dx/Maps"                               # symlinks point in from here
SIZE = (640, 480)                                       # small = fast load
LOG = OUT / "spike.log"


def log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def dexec(container, *args, timeout=60):
    return subprocess.run(["docker", "exec", container, *args],
                          capture_output=True, text=True, timeout=timeout)


def rss(container) -> str:
    r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container],
                       capture_output=True, text=True, timeout=20)
    return r.stdout.strip()


def url_map(container) -> str:
    return pg._level_name_of(pg.link_cmd(container, "GetCurrentLevelName"))


def inject_symlink(container, src: Path, stem: str):
    """Place a REAL map file in POOL, then SYMLINK it into the Maps dir POST-BOOT.
    This is the production delivery form the shipped tier never used."""
    dexec(container, "mkdir", "-p", POOL)
    subprocess.run(["docker", "cp", str(src), f"{container}:{POOL}/{stem}.dx"],
                   capture_output=True, text=True, timeout=60, check=True)
    # ln -sf: tolerate re-preview EEXIST (spec §4.4)
    r = dexec(container, "ln", "-sf", f"{POOL}/{stem}.dx", f"{MAPSDIR}/{stem}.dx")
    if r.returncode != 0:
        raise RuntimeError(f"symlink failed for {stem}: {r.stderr}")


def _position(container) -> tuple[int, int, int] | None:
    for ln in pg.link_cmd(container, "GetPlayerPosition"):
        if "Position " in ln:
            x, y, z = ln.split("Position ", 1)[1].split()[:3]
            return int(x), int(y), int(z)
    return None


def travel_and_check(container, stem: str, row, *, shot: str | None = None) -> tuple[bool, str]:
    """Drive the shipped 3-phase handshake to `stem`; return (resolved?, GetURLMap).
    For a shot: pose the pawn at its own spawn (clean freeze via the Screenshot verb),
    then X-grab the window (the real capture path — the verb only poses)."""
    try:
        pg.travel_to(container, stem)
        ok_travel = True
    except pg.GamePreviewError as e:
        log(f"    travel_to raised: {e}")
        ok_travel = False
    got = url_map(container)
    resolved = ok_travel and pg._stem(got).casefold() == stem.casefold()
    if shot and resolved:
        pos = _position(container)
        if pos:
            pg.link_cmd(container, f"Screenshot {pos[0]} {pos[1]} {pos[2]} 0 0")
            time.sleep(1)
        try:
            pg.xgrab(container, row, OUT / shot)
        except Exception as e:
            log(f"    xgrab failed: {e}")
    return resolved, got


def content_hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def main():
    LOG.write_text("")
    results = []

    # small retail maps that reliably carve + spawn a player
    m_entry = MAPS / "Entry.dx"
    m_dx = MAPS / "DX.dx"
    m_end = MAPS / "99_Endgame4.dx"
    m_mission = MAPS / "08_NYC_Bar.dx"
    for m in (m_entry, m_dx, m_end, m_mission):
        assert m.exists(), f"missing test map {m}"
    log(f"content hashes: Entry={content_hash(m_entry)} DX={content_hash(m_dx)} "
        f"End={content_hash(m_end)}")

    project = config.load_project(str(UEDCLI.parent.parent / "uedcli"))
    user_config = config.load_user_config()
    row = pg._substrate_row(project.game)

    log("booting ONE warm container (start_game) …")
    t0 = time.time()
    container, vnc = pg.start_game(project, user_config, row, SIZE)
    log(f"READY in {time.time()-t0:.0f}s  container={container} novnc={vnc}")

    try:
        log(f"boot-map RSS: {rss(container)}  boot GetURLMap={url_map(container)!r}")

        # ---- (a)+(b)+(a'): a run of POST-BOOT SYMLINKED travels in ONE container ----
        # unique dot-free lowercased stems, production-shaped (materialized__ prefix)
        plan = [
            ("materialized__entry__aaaaaaaaaaaa", m_entry, "t_a1_entry.png"),   # 1st post-boot symlink
            ("materialized__dx__bbbbbbbbbbbb",    m_dx,    "t_b1_dx.png"),       # Nth open, diff content
            ("materialized__end__cccccccccccc",   m_end,   "t_c1_end.png"),      # Nth open, diff content
            ("materialized__entry__dddddddddddd", m_entry, "t_a2_entry_dup.png"),# same bytes, NEW name
            ("materialized__dx__eeeeeeeeeeee",    m_dx,    "t_b2_dx.png"),       # more Nth churn
        ]
        for i, (stem, src, shot) in enumerate(plan, 1):
            inject_symlink(container, src, stem)
            resolved, got = travel_and_check(container, stem, row, shot=shot)
            r = rss(container)
            log(f"  travel #{i}: stem={stem[:40]} src={src.name} -> resolved={resolved} "
                f"GetURLMap={got!r} RSS={r}")
            results.append(("travel", i, stem, src.name, resolved, got, r))

        # ---- (c): NAME_SIZE cap — does a long stem LOAD, and do two stems differing
        # ONLY past char 63 COLLIDE?  GetURLMap returns the travel URL (full stem) so it
        # can't reveal FName truncation — the rigorous test is DIFFERENT CONTENT under the
        # two past-63-differing names + a SCREENSHOT-HASH compare.  If the FName caps at 63,
        # collide_b truncates to collide_a's interned name → the engine serves the RESIDENT
        # collide_a package → collide_b's shot == collide_a's (Entry, not DX).
        long70 = ("materialized__long__" + "z" * 46)   # 66 chars, well past a 63 cap
        inject_symlink(container, m_entry, long70)
        resolved, got = travel_and_check(container, long70, row)
        log(f"  NAME_SIZE long len={len(long70)}: LOADS={resolved} GetURLMap={got!r}")
        results.append(("namesize-long", len(long70), long70, "Entry.dx", resolved, got, ""))

        p = "materialized__collide__" + "z" * (63 - len("materialized__collide__"))
        assert len(p) == 63
        collide_a = p + "aaaaaaa"                       # 70 chars, differ ONLY past 63
        collide_b = p + "bbbbbbb"
        inject_symlink(container, m_entry, collide_a)   # content A = Entry
        ra, _ = travel_and_check(container, collide_a, row, shot="collide_a.png")
        inject_symlink(container, m_dx, collide_b)      # content B = DX (DIFFERENT!)
        rb, _ = travel_and_check(container, collide_b, row, shot="collide_b.png")
        ha = content_hash(OUT / "collide_a.png") if (OUT / "collide_a.png").exists() else "?"
        hb = content_hash(OUT / "collide_b.png") if (OUT / "collide_b.png").exists() else "?"
        collided = ha == hb and ha != "?"
        log(f"  COLLISION CHECK (differ past char 63): a_loads={ra} b_loads={rb}  "
            f"shotA_hash={ha} shotB_hash={hb}  COLLIDED={collided} "
            f"(collided ⇒ FName caps ≤63 and b served resident A)")
        results.append(("collision", 63, collide_a, "Entry-vs-DX", not collided, f"{ha}/{hb}", ""))

        # ---- (e): conversation-prone mission map — observe the frame ----
        stem_m = "materialized__nycbar__ffffffffffff"
        inject_symlink(container, m_mission, stem_m)
        resolved, got = travel_and_check(container, stem_m, row, shot="t_mission_08nycbar.png")
        log(f"  MISSION obs: resolved={resolved} GetURLMap={got!r} shot=t_mission_08nycbar.png "
            f"RSS={rss(container)}")

        log("=== SPIKE COMPLETE ===")
    finally:
        log(f"tearing down {container}")
        pg.stop_game(container)


if __name__ == "__main__":
    main()
