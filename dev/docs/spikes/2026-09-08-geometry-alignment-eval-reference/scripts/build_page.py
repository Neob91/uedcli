"""Build index.html from every specs/<id>.py's `before`/`scenarios` (titles,
notes, view, members, extra_photos) plus the real .diff files under diffs/,
plus every graded trial under runs/<task_id>/*/result.json (written by
eval_trial.py). No task metadata lives in this file -- add a new task by
adding a new specs/<file>.py, not by editing this script; trials appear
automatically as eval_trial.py writes them, no registration needed."""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS

ROOT = pathlib.Path("/workspace/uedcli/.claude/worktrees/geom-eval/dev/docs/spikes/2026-09-08-geometry-alignment-eval-reference")
DEST_IMG = ROOT / "img"
DIFFS = ROOT / "diffs"
RUNS = ROOT / "runs"

used = set()  # (task_id, name) pairs actually referenced, for the missing-file check
def img(task_id, name):
    used.add((task_id, name))
    return f"img/{task_id}/{name}.png"

run_used = set()  # (task_id, run_id, name)
def run_img(task_id, run_id, name):
    run_used.add((task_id, run_id, name))
    return f"runs/{task_id}/{run_id}/img/{name}.png"

ALL_CAROUSELS = {}

def scenario_images(task_id, scen_id, note, members):
    imgs = [(scen_id, f"[CORRECT] {note} (highlighted: {', '.join(members)})")]
    imgs += TASKS[task_id]["scenarios"][scen_id].get("extra_photos", [])
    return imgs

def carousel_html(task_id, scen_id, images):
    key = f"{task_id}__{scen_id}"
    items, thumbs = [], ""
    for i, (name, cap) in enumerate(images):
        items.append({"src": img(task_id, name), "cap": cap})
        thumbs += (f'<img class="cthumb" src="{img(task_id, name)}" alt="{cap}" loading="lazy" tabindex="0" '
                   f'onclick="openLB(\'{key}\',{i})" onkeydown="if(event.key===\'Enter\')openLB(\'{key}\',{i})">')
    ALL_CAROUSELS[key] = items
    return thumbs

def scenario_card(task_id, scen_id, scen):
    images = scenario_images(task_id, scen_id, scen["note"], scen["members"])
    thumbs = carousel_html(task_id, scen_id, images)
    diff_path = DIFFS / task_id / f"{scen_id}.diff"
    diff_text = diff_path.read_text()
    diff_note = "" if diff_text.strip() else "<p class=\"nochange\">Zero-line diff — this aspect asserts these actors are UNCHANGED from the baseline, and they are.</p>"
    diff_rel = f"diffs/{task_id}/{scen_id}.diff"
    return f"""<div class="scen">
      <button class="scenhead" onclick="toggleScen(this)">
        <span class="chev">&#9656;</span><span class="stitle">{scen['title']}</span>
      </button>
      <div class="scenbody" hidden>
        <p class="sdesc">{scen['note']}</p>
        <div class="carousel">{thumbs}</div>
        <details class="diffbox"><summary>Diff — real <code>diff -u</code> output this picture is generated from (<a href="{diff_rel}">{diff_rel}</a>)</summary>
          {diff_note}<pre class="diffpre">{diff_text}</pre>
        </details>
      </div></div>"""

def discover_runs(task_id):
    d = RUNS / task_id
    if not d.exists():
        return []
    runs = []
    for p in sorted(d.iterdir()):
        rf = p / "result.json"
        if rf.exists():
            runs.append(json.loads(rf.read_text()))
    runs.sort(key=lambda r: r["graded_at"], reverse=True)
    return runs

def trial_card(task_id, task, run):
    run_id = run["run_id"]
    key = f"{task_id}__trial__{run_id}"
    scen_names = list(task["scenarios"].keys())
    pan_names = [f"pan_{i}" for i in range(8)]
    images = [(n, f"Plan — {task['scenarios'][n]['title']}") for n in scen_names] + \
             [(n, f"Photo, panorama frame {i}") for i, n in enumerate(pan_names)]
    items, thumbs = [], ""
    for i, (name, cap) in enumerate(images):
        items.append({"src": run_img(task_id, run_id, name), "cap": cap})
        thumbs += (f'<img class="cthumb" src="{run_img(task_id, run_id, name)}" alt="{cap}" loading="lazy" tabindex="0" '
                   f'onclick="openLB(\'{key}\',{i})" onkeydown="if(event.key===\'Enter\')openLB(\'{key}\',{i})">')
    ALL_CAROUSELS[key] = items

    def sort_key(r):
        return (0 if r["verdict"] != "correct" else 1, r["actor"])
    rows = "".join(
        f'<tr class="{"bad" if r["verdict"] != "correct" else "ok"}">'
        f'<td>{r["actor"]}</td><td>{r["role"]}</td><td>{r["verdict"]}</td>'
        f'<td>{r["why"] if r["verdict"] != "correct" else ""}</td></tr>'
        for r in sorted(run["results"], key=sort_key))

    badge = "okv" if run["passed"] else "badv"
    badge_text = "PASS" if run["passed"] else "FAIL"
    return f"""<div class="scen">
      <button class="scenhead" onclick="toggleScen(this)">
        <span class="chev">&#9656;</span><span class="stitle">{run['label']}</span>
        <span class="lbl {badge}">{badge_text}</span>
        <span class="tmeta">{run['n_correct']}/{run['n_total']} · {run['graded_at'][:19]}Z</span>
      </button>
      <div class="scenbody" hidden>
        <p class="sdesc">Subject trunk: <code>{run['subject_trunk']}</code></p>
        <div class="carousel">{thumbs}</div>
        <table class="tresults"><thead><tr><th>actor</th><th>role</th><th>verdict</th><th>why (if failed)</th></tr></thead>
        <tbody>{rows}</tbody></table>
      </div></div>"""

def task_block(task_id, task):
    before = task["before"]
    diag_html = "".join(f'<figure class="dg"><img src="{img(task_id, n)}" alt="{c}" onclick="openLB(\'{task_id}__before\',{i})"><figcaption>{c}</figcaption></figure>'
                         for i, (n, c) in enumerate(before["diags"]))
    bid = f"{task_id}__before"
    ALL_CAROUSELS[bid] = [{"src": img(task_id, n), "cap": "Panorama frame, before any edit."} for n in before["photos"]]
    before_thumbs = "".join(f'<img class="cthumb" src="{img(task_id, n)}" alt="panorama" loading="lazy" tabindex="0" '
                             f'onclick="openLB(\'{bid}\',{i})" onkeydown="if(event.key===\'Enter\')openLB(\'{bid}\',{i})">'
                             for i, n in enumerate(before["photos"]))
    scen_html = "".join(scenario_card(task_id, scen_id, scen) for scen_id, scen in task["scenarios"].items())
    runs = discover_runs(task_id)
    trials_html = ""
    if runs:
        trials_html = ('<h3 class="scenh">Trial results — graded runs (auto-discovered from runs/) — click to expand</h3>'
                        + "".join(trial_card(task_id, task, r) for r in runs))
    return f"""<div class="taskblk">
      <button class="taskhead" onclick="toggleTask(this)">
        <span class="tchev">&#9656;</span><h2>{task['title']}</h2>
      </button>
      <div class="taskbody" hidden>
        <div class="task"><span class="t">REQUEST:</span> {task['req']}</div>
        <div class="beforeblk">
          <div class="diagrams">{diag_html}</div>
          <div class="striplabel">360° panorama tour, before any edit</div>
          <div class="carousel">{before_thumbs}</div>
        </div>
        <h3 class="scenh">Per-aspect scenarios — click to expand</h3>
        {scen_html}
        {trials_html}
      </div></div>"""

BODY = "".join(task_block(tid, task) for tid, task in TASKS.items())
CAROUSEL_JSON = json.dumps(ALL_CAROUSELS)

HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Widen &amp; Ceiling · Reference Solutions</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--ground:#12130f;--panel:#1b1c16;--panel2:#22241c;--line:#33352a;--ink:#e7e3d4;--dim:#9a9585;--faint:#6f6a5c;
--gold:#c9a24b;--gold-soft:#e0c274;--cyan:#57d4e0;--good:#5bbf7a;--bad:#e8574d;
--mono:'IBM Plex Mono',ui-monospace,Menlo,monospace;--body:'IBM Plex Sans',system-ui,sans-serif;--disp:'Rajdhani',var(--body);}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--body);line-height:1.55;font-size:16px;-webkit-font-smoothing:antialiased}
img{max-width:100%}
.wrap{max-width:1040px;margin:0 auto;padding:clamp(20px,4vw,52px)}
h1,h2,h3{font-family:var(--disp);font-weight:600;text-wrap:balance;letter-spacing:.01em;margin:0}
.eyebrow{font-family:var(--mono);font-size:12.5px;letter-spacing:.22em;text-transform:uppercase;color:var(--gold);margin:0 0 14px}
.lede{font-size:clamp(26px,4vw,40px);line-height:1.08;margin:0 0 16px;letter-spacing:-.01em}
.sub{color:var(--dim);max-width:70ch;font-size:16.5px;margin:0}
.orient{font-size:13.5px;color:var(--dim);margin:14px 0 0;padding:10px 14px;border:1px solid var(--line);border-left:3px solid var(--cyan);background:var(--panel2);border-radius:2px}
.pipeline{font-size:13.5px;color:var(--dim);margin:10px 0 0;padding:10px 14px;border:1px solid var(--line);border-left:3px solid var(--gold);background:var(--panel2);border-radius:2px}

.taskblk{margin:28px 0 0;border:1px solid var(--line);border-radius:6px;overflow:hidden;background:var(--panel)}
.taskhead{width:100%;text-align:left;background:var(--panel2);border:0;border-bottom:1px solid var(--line);padding:16px 20px;
  display:flex;align-items:center;gap:12px;cursor:pointer;font:inherit;color:inherit}
.taskhead h2{font-size:clamp(19px,2.6vw,25px);flex:1}
.tchev{font-size:18px;color:var(--gold);transition:transform .15s;flex-shrink:0}
.taskblk.open .tchev{transform:rotate(90deg)}
.taskblk.open .taskhead{border-bottom-color:var(--gold)}
.taskbody{padding:20px}
.task{margin:0 0 20px;padding:14px 16px;border:1px solid var(--line);border-left:3px solid var(--gold);background:var(--panel2);border-radius:2px;font-size:15px;color:var(--dim)}
.task .t{font-family:var(--mono);color:var(--gold);font-size:12px;letter-spacing:.1em}

.beforeblk{margin:0 0 26px;padding:14px;border:1px solid color-mix(in srgb,var(--gold) 30%,var(--line));border-radius:4px;background:var(--panel2)}
.diagrams{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px;background:#13140d;padding:8px;border-radius:3px}
.dg{margin:0}.dg img{display:block;width:100%;height:auto;border-radius:2px;cursor:zoom-in}
.dg figcaption{font-family:var(--mono);font-size:11px;color:var(--dim);padding:5px 2px 2px}
.striplabel{font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:.06em;margin:12px 0 8px}

.scenh{font-size:13px;font-family:var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--faint);margin:24px 0 10px;padding-top:14px;border-top:1px solid var(--line)}
.scen{border:1px solid var(--line);border-radius:4px;margin:0 0 10px;overflow:hidden;background:var(--panel2)}
.scenhead{width:100%;text-align:left;background:transparent;border:0;padding:12px 16px;display:flex;align-items:center;gap:10px;cursor:pointer;font:inherit;color:inherit}
.chev{font-size:13px;color:var(--gold);transition:transform .15s;flex-shrink:0}
.scen.open .chev{transform:rotate(90deg)}
.stitle{font-size:15.5px;font-weight:600;flex:1}
.scenbody{padding:0 16px 16px}
.sdesc{color:var(--dim);font-size:14px;margin:0 0 12px}
.carousel{display:flex;flex-wrap:wrap;gap:6px}
.cthumb{width:130px;height:97px;object-fit:cover;border-radius:2px;border:1px solid var(--line);cursor:zoom-in;transition:border-color .12s}
.cthumb:hover,.cthumb:focus{border-color:var(--gold);outline:none}
.diffbox{margin:14px 0 0;font-size:13px}
.diffbox summary{cursor:pointer;color:var(--gold-soft);font-family:var(--mono);font-size:12px}
.diffbox a{color:var(--cyan)}
.diffpre{margin:10px 0 0;padding:12px;background:#0d0e08;border:1px solid var(--line);border-radius:3px;overflow-x:auto;
  color:var(--dim);font-family:var(--mono);font-size:11.5px;line-height:1.55;white-space:pre}
.nochange{color:var(--gold-soft);font-family:var(--mono);font-size:12px;margin:10px 0 0}
.tmeta{font-family:var(--mono);font-size:11.5px;color:var(--faint);margin-left:auto}
.tresults{width:100%;border-collapse:collapse;margin:14px 0 0;font-size:12.5px}
.tresults th{text-align:left;font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);padding:4px 8px;border-bottom:1px solid var(--line)}
.tresults td{padding:4px 8px;border-bottom:1px solid var(--line);color:var(--dim);vertical-align:top}
.tresults tr.bad td:nth-child(1),.tresults tr.bad td:nth-child(3){color:var(--bad)}
.tresults tr.ok td:nth-child(3){color:var(--good)}

.foot{color:var(--faint);font-size:13px;font-family:var(--mono);margin-top:26px;border-top:1px solid var(--line);padding-top:14px}
code{font-family:var(--mono);font-size:.9em;background:var(--panel2);padding:1px 5px;border-radius:2px;color:var(--gold-soft)}

.lb{position:fixed;inset:0;background:rgba(6,7,4,.94);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:50;padding:24px}
.lb[hidden]{display:none}
.lbimgwrap{position:relative;max-width:100%;max-height:78vh;display:flex;align-items:center;justify-content:center}
.lb img{max-width:100%;max-height:78vh;border-radius:3px;box-shadow:0 8px 40px rgba(0,0,0,.6)}
.lbcap{color:var(--ink);font-size:15px;max-width:70ch;text-align:center;margin-top:16px;padding:0 12px}
.lbnav{position:fixed;top:0;bottom:0;width:80px;background:transparent;border:0;color:var(--ink);font-size:36px;cursor:pointer;opacity:.55;transition:opacity .12s}
.lbnav:hover{opacity:1}
.lbprev{left:0}.lbnext{right:0}
.lbclose{position:fixed;top:14px;right:18px;font-family:var(--mono);font-size:12px;color:var(--dim);background:transparent;border:1px solid var(--line);border-radius:3px;padding:6px 10px;cursor:pointer}
.lbcount{position:fixed;top:16px;left:18px;font-family:var(--mono);font-size:12px;color:var(--dim)}
</style></head>
<body>
<div class="wrap">
  <p class="eyebrow">uedcli · reference solutions · batch 1 of 5 · UNATCO HQ</p>
  <h1 class="lede">Reference solutions to validate &mdash; per-aspect, diff-generated.</h1>
  <p class="sub">Each task is collapsed by default &mdash; open one and the previous one closes. Inside, each aspect of the change is its own collapsible scenario, showing the fully-correct outcome with just that aspect's actors highlighted. Click any picture to enlarge; arrows cycle through that scenario's images; the enlarged view always shows its caption.</p>
  <p class="pipeline"><b>Every picture is generated, never hand-built:</b> each scenario is backed by a REAL <code>diff -u</code> (not a custom format) between the baseline and the fully-correct trunk, over each actor's normalized state (brush corners, or Location). Grading is separate from this display grouping: a flat per-task oracle (<code>oracle/&lt;task&gt;.json</code>) classifies each actor as an <code>update</code> (an absolute target — a task-pinned delta, or "= baseline"), an <code>anchor</code> (must match a SPECIFIC other actor's actual delta — the wall volume it's physically attached to, verified per-actor, not one shared number), or (documented, not yet needed) <code>create</code>/<code>delete</code>. <code>check_trunk.py</code> grades any trunk against it.</p>
  <p class="orient">Orientation, top-down plans (matching UnrealEd's own axis convention): <b>East = right</b> edge of the image, <b>West = left</b>, <b>North = up</b>, <b>South = down</b>. A small compass is burned into the top-left corner of every plan below as a direct check.</p>
  __BODY__
  <p class="foot">Batch 1 = UNATCO HQ (2 tasks), swept exhaustively — every actor within a wide margin of the moved geometry individually classified, each assigned its OWN anchor by verified geometry (some fixtures split across both wall volumes). Remaining: NYC_Bar, WanChai Market, OceanLab, + one more, each with the same pipeline. Diagrams: <code>actor diagram</code>, cropped to the room this task edits (not the whole level). Photos: <code>level photo --native --faces textured</code>; procedural FX skins render solid <b>red</b>.</p>
</div>

<div id="lb" class="lb" hidden>
  <button class="lbclose" onclick="closeLB()">✕ close (Esc)</button>
  <span id="lbcount" class="lbcount"></span>
  <button class="lbnav lbprev" onclick="lbStep(-1)" aria-label="previous">&#10094;</button>
  <button class="lbnav lbnext" onclick="lbStep(1)" aria-label="next">&#10095;</button>
  <div class="lbimgwrap"><img id="lbimg" alt=""></div>
  <p id="lbcap" class="lbcap"></p>
</div>

<script>
const CAROUSELS = __CAROUSEL_JSON__;
let lbScen = null, lbIdx = 0;

function toggleTask(btn){
  const blk = btn.closest('.taskblk');
  const wasOpen = blk.classList.contains('open');
  document.querySelectorAll('.taskblk.open').forEach(b => {
    b.classList.remove('open');
    b.querySelector('.taskbody').hidden = true;
  });
  if (!wasOpen){
    blk.classList.add('open');
    blk.querySelector('.taskbody').hidden = false;
  }
}
function toggleScen(btn){
  const scen = btn.closest('.scen');
  const body = scen.querySelector('.scenbody');
  const open = scen.classList.toggle('open');
  body.hidden = !open;
}
function openLB(scenId, idx){
  lbScen = scenId; lbIdx = idx;
  renderLB();
  document.getElementById('lb').hidden = false;
}
function renderLB(){
  const list = CAROUSELS[lbScen];
  const item = list[lbIdx];
  document.getElementById('lbimg').src = item.src;
  document.getElementById('lbcap').textContent = item.cap;
  document.getElementById('lbcount').textContent = (lbIdx+1) + ' / ' + list.length;
}
function lbStep(d){
  const list = CAROUSELS[lbScen];
  lbIdx = (lbIdx + d + list.length) % list.length;
  renderLB();
}
function closeLB(){ document.getElementById('lb').hidden = true; }
document.addEventListener('keydown', e => {
  if (document.getElementById('lb').hidden) return;
  if (e.key === 'Escape') closeLB();
  if (e.key === 'ArrowLeft') lbStep(-1);
  if (e.key === 'ArrowRight') lbStep(1);
});
document.getElementById('lb').addEventListener('click', e => {
  if (e.target.id === 'lb') closeLB();
});
</script>
</body></html>
"""
(ROOT / "index.html").write_text(HTML.replace("__BODY__", BODY).replace("__CAROUSEL_JSON__", CAROUSEL_JSON))

missing = [f"{t}/{n}" for t, n in sorted(used) if not (DEST_IMG / t / f"{n}.png").exists()]
missing += [f"runs/{t}/{r}/{n}" for t, r, n in sorted(run_used) if not (RUNS / t / r / "img" / f"{n}.png").exists()]
print("wrote", ROOT / "index.html")
print("images used:", len(used), "+", len(run_used), "trial images; missing:", missing)
