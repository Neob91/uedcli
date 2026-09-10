"""Build index.html from every specs/<id>.py's `before` block plus every
rendered execution under runs/<task_id>/*/manifest.json (written by
render_manual.py). No task metadata lives in this file -- add a new task by
adding a new specs/<file>.py, not by editing this script; executions appear
automatically as render_manual.py writes them, no registration needed.
Grading is manual: each execution card POSTs a score (0-10) + note to
serve.py's /api/grade and reloads it from /api/grades -- this script only
lays out the form, it never computes a verdict."""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS

ROOT = pathlib.Path("/workspace/uedcli/.claude/worktrees/geom-eval/dev/evals/2026-09-08-geometry-alignment-eval-reference")
DEST_IMG = ROOT / "img"
RUNS = ROOT / "runs"

used = set()  # (task_id, name) pairs actually referenced, for the missing-file check
def img(task_id, name):
    used.add((task_id, name))
    return f"img/{task_id}/{name}.png"

run_used = set()  # (task_id, run_id, relpath) -- relpath already includes ".png"
def run_img(task_id, run_id, relpath):
    run_used.add((task_id, run_id, relpath))
    return f"runs/{task_id}/{run_id}/img/{relpath}"

ALL_CAROUSELS = {}

def discover_executions(task_id):
    d = RUNS / task_id
    if not d.exists():
        return []
    runs = []
    for p in sorted(d.iterdir()):
        mf = p / "manifest.json"
        if mf.exists():
            runs.append(json.loads(mf.read_text()))
    runs.sort(key=lambda r: r["rendered_at"], reverse=True)
    return runs

BUCKET_ORDER = {"created": 0, "updated": 1, "unchanged": 2, "deleted": 3}

def execution_card(task_id, task, run):
    run_id = run["run_id"]
    key = f"{task_id}__exec__{run_id}"
    gid = f"{task_id}--{run_id}"

    entries = sorted(run["entries"], key=lambda e: (BUCKET_ORDER[e["bucket"]], e["actor"]))
    items = [{"default": 1, "variants": [
                {"src": run_img(task_id, run_id, e["img_before"]), "cap": f"BEFORE — {e['actor']}: {e['what']}"},
                {"src": run_img(task_id, run_id, e["img_after"]), "cap": f"{e['label']} — {e['actor']}: {e['what']}"},
              ]} for e in entries]
    items += [{"default": 0, "variants": [
                {"src": run_img(task_id, run_id, n), "cap": f"Photo, panorama frame {i}"},
                {"src": img(task_id, f"pan_before_{i}"), "cap": f"BEFORE — panorama frame {i}"},
              ]} for i, n in enumerate(run["panorama"])]
    ALL_CAROUSELS[key] = items

    grid = "".join(
        f'<figure class="egrid-item b-{e["bucket"]}">'
        f'<img src="{run_img(task_id, run_id, e["img_after"])}" alt="{e["actor"]}" loading="lazy" tabindex="0" '
        f'onclick="openLB(\'{key}\',{i})" onkeydown="if(event.key===\'Enter\')openLB(\'{key}\',{i})">'
        f'<figcaption><span class="elbl b-{e["bucket"]}">{e["label"]}</span> {e["actor"]}'
        f'<span class="ewhat">{e["what"]}</span></figcaption></figure>'
        for i, e in enumerate(entries))

    pan_thumbs = "".join(
        f'<img class="cthumb" src="{run_img(task_id, run_id, n)}" alt="panorama" loading="lazy" tabindex="0" '
        f'onclick="openLB(\'{key}\',{len(entries)+i})" onkeydown="if(event.key===\'Enter\')openLB(\'{key}\',{len(entries)+i})">'
        for i, n in enumerate(run["panorama"]))

    return f"""<div class="scen">
      <button class="scenhead" onclick="toggleScen(this)">
        <span class="chev">&#9656;</span><span class="stitle">{run['label']}</span>
        <span class="tmeta" data-gradebadge="{gid}">not yet graded</span>
      </button>
      <div class="scenbody" hidden>
        <p class="sdesc">Subject trunk: <code>{run['subject_trunk']}</code> · rendered {run['rendered_at'][:19]}Z</p>
        <div class="striplabel">360° panorama tour, this execution's final state</div>
        <div class="carousel">{pan_thumbs}</div>
        <div class="striplabel">Per-actor outcome — {len(entries)} of {run['n_task_entries']} task-relevant actors were actually touched (moved, created, or removed); one quad view (Top / Front / Iso / Side) per touched actor, only that actor highlighted</div>
        <div class="egrid">{grid}</div>
        <div class="gradebox" data-task="{task_id}" data-run="{run_id}">
          <label>Score (0–10)
            <input type="number" min="0" max="10" step="1" class="gscore" placeholder="—">
          </label>
          <label class="gnotelbl">Notes
            <textarea class="gnote" rows="3" placeholder="What's wrong, or why it's right..."></textarea>
          </label>
          <div class="grow">
            <button class="gsave" onclick="saveGrade(this)">Save grade</button>
            <span class="gstatus">not yet graded</span>
          </div>
        </div>
      </div></div>"""

def task_block(task_id, task):
    before = task["before"]
    bid = f"{task_id}__before"
    quad_cap = "Whole-room quad view (Top / Front / Iso / Side), before any edit."
    ALL_CAROUSELS[bid] = [{"default": 0, "variants": [{"src": img(task_id, before["quad"]), "cap": quad_cap}]}] + \
                          [{"default": 0, "variants": [{"src": img(task_id, n), "cap": "Panorama frame, before any edit."}]}
                           for n in before["photos"]]
    before_quad_html = (f'<figure class="dg dg-quad"><img src="{img(task_id, before["quad"])}" alt="{quad_cap}" '
                         f'onclick="openLB(\'{bid}\',0)"><figcaption>{before["note"]}</figcaption></figure>')
    before_thumbs = "".join(f'<img class="cthumb" src="{img(task_id, n)}" alt="panorama" loading="lazy" tabindex="0" '
                             f'onclick="openLB(\'{bid}\',{i+1})" onkeydown="if(event.key===\'Enter\')openLB(\'{bid}\',{i+1})">'
                             for i, n in enumerate(before["photos"]))
    runs = discover_executions(task_id)
    exec_html = ('<p class="sdesc">No executions rendered yet for this task — run '
                 '<code>scripts/render_manual.py '
                 f'{task_id} &lt;subject_trunk&gt;</code> and rebuild the page.</p>')
    if runs:
        exec_html = "".join(execution_card(task_id, task, r) for r in runs)
    return f"""<div class="taskblk">
      <button class="taskhead" onclick="toggleTask(this)">
        <span class="tchev">&#9656;</span><h2>{task['title']}</h2>
      </button>
      <div class="taskbody" hidden>
        <div class="task"><span class="t">REQUEST:</span> {task['req']}</div>
        <div class="beforeblk">
          <div class="diagrams">{before_quad_html}</div>
          <div class="striplabel">360° panorama tour, before any edit</div>
          <div class="carousel">{before_thumbs}</div>
        </div>
        <h3 class="scenh">Executions to grade — click to expand, score 0–10 + note, editable anytime</h3>
        {exec_html}
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
.dg-quad{max-width:560px;margin:0 auto}
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
.tmeta.graded{color:var(--good)}

.egrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:0 0 4px}
.egrid-item{margin:0;background:#13140d;border:1px solid var(--line);border-left:3px solid var(--faint);border-radius:3px;overflow:hidden}
.egrid-item img{display:block;width:100%;height:auto;cursor:zoom-in}
.egrid-item figcaption{font-size:11.5px;color:var(--dim);padding:6px 8px 8px}
.egrid-item .ewhat{display:block;color:var(--faint);font-size:10.5px;margin-top:2px}
.elbl{font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;padding:1px 5px;border-radius:2px;margin-right:5px}
.egrid-item.b-created{border-left-color:var(--cyan)}.elbl.b-created{background:color-mix(in srgb,var(--cyan) 25%,transparent);color:var(--cyan)}
.egrid-item.b-updated{border-left-color:var(--gold)}.elbl.b-updated{background:color-mix(in srgb,var(--gold) 25%,transparent);color:var(--gold-soft)}
.egrid-item.b-unchanged{border-left-color:var(--faint)}.elbl.b-unchanged{background:color-mix(in srgb,var(--faint) 25%,transparent);color:var(--dim)}
.egrid-item.b-deleted{border-left-color:var(--bad)}.elbl.b-deleted{background:color-mix(in srgb,var(--bad) 25%,transparent);color:var(--bad)}

.gradebox{margin:18px 0 0;padding:14px 16px;border:1px solid color-mix(in srgb,var(--cyan) 35%,var(--line));border-radius:4px;background:#13140d;display:flex;flex-wrap:wrap;gap:14px 20px;align-items:flex-end}
.gradebox label{display:flex;flex-direction:column;gap:5px;font-family:var(--mono);font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint)}
.gradebox .gnotelbl{flex:1;min-width:220px}
.gradebox input.gscore{width:70px;font:inherit;font-size:16px;background:var(--panel2);border:1px solid var(--line);border-radius:3px;color:var(--ink);padding:6px 8px}
.gradebox textarea.gnote{font:inherit;font-size:13.5px;background:var(--panel2);border:1px solid var(--line);border-radius:3px;color:var(--ink);padding:8px;resize:vertical;min-height:38px}
.gradebox .grow{display:flex;align-items:center;gap:10px}
.gradebox .gsave{font:inherit;font-size:13px;font-weight:600;background:var(--gold);color:#1a1608;border:0;border-radius:3px;padding:8px 16px;cursor:pointer}
.gradebox .gsave:hover{background:var(--gold-soft)}
.gradebox .gsave:disabled{opacity:.5;cursor:default}
.gradebox .gstatus{font-family:var(--mono);font-size:11.5px;color:var(--faint)}
.gradebox .gstatus.saved{color:var(--good)}
.gradebox .gstatus.error{color:var(--bad)}

.foot{color:var(--faint);font-size:13px;font-family:var(--mono);margin-top:26px;border-top:1px solid var(--line);padding-top:14px}
code{font-family:var(--mono);font-size:.9em;background:var(--panel2);padding:1px 5px;border-radius:2px;color:var(--gold-soft)}

.lb{position:fixed;inset:0;background:rgba(6,7,4,.94);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:50;padding:24px}
.lb[hidden]{display:none}
.lbimgwrap{position:relative;max-width:100%;max-height:78vh;display:flex;align-items:center;justify-content:center;overflow:auto}
.lb img{max-width:100%;max-height:78vh;border-radius:3px;box-shadow:0 8px 40px rgba(0,0,0,.6);cursor:zoom-in}
.lb img.zoomed{max-width:none;max-height:none;cursor:zoom-out}
.lbcap{color:var(--ink);font-size:15px;max-width:70ch;text-align:center;margin-top:16px;padding:0 12px}
.lbnav{position:fixed;top:0;bottom:0;width:80px;background:transparent;border:0;color:var(--ink);font-size:36px;cursor:pointer;opacity:.7;transition:opacity .12s}
.lbnav:hover{opacity:1}
.lbprev{left:0}.lbnext{right:0}
.lbclose{position:fixed;top:14px;right:18px;font-family:var(--mono);font-size:12px;color:var(--dim);background:transparent;border:1px solid var(--line);border-radius:3px;padding:6px 10px;cursor:pointer}
.lbcount{position:fixed;top:16px;left:18px;font-family:var(--mono);font-size:12px;color:var(--dim)}
.lbvariant{position:fixed;top:16px;left:50%;transform:translateX(-50%);font-family:var(--mono);font-size:12px;color:var(--cyan);letter-spacing:.04em;background:rgba(6,7,4,.6);padding:5px 12px;border-radius:12px}
.lbvnav{position:fixed;left:50%;transform:translateX(-50%);width:56px;height:44px;background:rgba(6,7,4,.55);border:1px solid var(--line);border-radius:8px;color:var(--ink);font-size:20px;line-height:1;cursor:pointer;opacity:.75;transition:opacity .12s;display:flex;align-items:center;justify-content:center}
.lbvnav:hover{opacity:1}
.lbvnav:disabled{opacity:.2;cursor:default}
.lbvup{top:52px}
.lbvdown{bottom:52px}
</style></head>
<body>
<div class="wrap">
  <p class="eyebrow">uedcli · geometry-alignment eval · batch 1 of 5 · UNATCO HQ</p>
  <h1 class="lede">Grade subagent executions &mdash; before/after, generated, not hand-built.</h1>
  <p class="sub">Each task is collapsed by default &mdash; open one and the previous one closes. Inside, each execution is its own collapsible card: a panorama tour plus one quad picture per actor that execution actually touched. Click any picture to enlarge; arrows/swipe cycle between actors, up/down (or a vertical swipe) flips before/after.</p>
  <p class="pipeline"><b>Every picture is generated, never hand-built.</b> Grading is manual: each task's <b>executions</b> section shows every task-relevant actor's actual outcome — one quad view (Top/Front/Iso/Side) per actor that was actually touched, labeled CREATED/UPDATED/UNCHANGED/DELETED by what the task expects of it — plus a full panorama tour, so you can score 0–10 and leave a note from the pictures alone. A DELETED actor's quad shows the final room with that actor reinserted (from its last known position) so its absence is visible, not just implied. The crop is computed per execution (the bbox of everything it touched, not a hand-picked frame) and shared by EVERY picture in it, so an actor that didn't move lands in the same spot whether you're looking at it or another actor, before or after — open one and press <b>↑/↓</b> to flip BEFORE/AFTER, ←/→ to move between actors (keeping your before/after choice). Scores save immediately and stay editable.</p>
  <p class="orient">Orientation (matching UnrealEd's own axis convention): in the <b>Top</b> pane of every quad view, <b>East = right</b> edge of the image, <b>West = left</b>, <b>North = up</b>, <b>South = down</b>.</p>
  __BODY__
  <p class="foot">Batch 1 = UNATCO HQ (2 tasks), swept exhaustively — every actor within a wide margin of the moved geometry individually classified, each assigned its OWN anchor by verified geometry (some fixtures split across both wall volumes). Remaining: NYC_Bar, WanChai Market, OceanLab, + one more, each with the same pipeline. Diagrams: <code>actor diagram</code>, cropped to what each execution actually touched (not the whole level). Photos: <code>level photo --native --faces textured</code>; procedural FX skins render solid <b>red</b>.</p>
</div>

<div id="lb" class="lb" hidden>
  <button class="lbclose" onclick="closeLB()">✕ close (Esc)</button>
  <span id="lbcount" class="lbcount"></span>
  <span id="lbvariant" class="lbvariant"></span>
  <button class="lbnav lbprev" onclick="lbStep(-1)" aria-label="previous">&#10094;</button>
  <button class="lbnav lbnext" onclick="lbStep(1)" aria-label="next">&#10095;</button>
  <button id="lbvup" class="lbvnav lbvup" onclick="cycleVariant(-1)" aria-label="previous view">&#9650;</button>
  <button id="lbvdown" class="lbvnav lbvdown" onclick="cycleVariant(1)" aria-label="next view">&#9660;</button>
  <div id="lbimgwrap" class="lbimgwrap"><img id="lbimg" alt="" onclick="toggleZoom(event)"></div>
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

function applyGrade(gid, rec){
  const box = document.querySelector(`.gradebox[data-task="${rec.task_id}"][data-run="${rec.run_id}"]`);
  const badge = document.querySelector(`[data-gradebadge="${gid}"]`);
  if (box){
    box.querySelector('.gscore').value = (rec.score === null || rec.score === undefined) ? '' : rec.score;
    box.querySelector('.gnote').value = rec.note || '';
    setStatus(box, rec);
  }
  if (badge){
    badge.textContent = (rec.score === null || rec.score === undefined) ? 'not yet graded' : `graded ${rec.score}/10`;
    badge.classList.toggle('graded', rec.score !== null && rec.score !== undefined);
  }
}
function setStatus(box, rec){
  const s = box.querySelector('.gstatus');
  s.classList.remove('error');
  if (rec && rec.updated_at){
    s.textContent = `saved ${rec.updated_at.slice(0,19)}Z`;
    s.classList.add('saved');
  } else {
    s.textContent = 'not yet graded';
    s.classList.remove('saved');
  }
}
async function loadGrades(){
  try {
    const res = await fetch('/api/grades');
    const grades = await res.json();
    for (const key in grades){
      const rec = grades[key];
      applyGrade(`${rec.task_id}--${rec.run_id}`, rec);
    }
  } catch (e) { console.error('loadGrades failed', e); }
}
async function saveGrade(btn){
  const box = btn.closest('.gradebox');
  const task_id = box.dataset.task, run_id = box.dataset.run;
  const scoreRaw = box.querySelector('.gscore').value;
  const score = scoreRaw === '' ? null : Math.max(0, Math.min(10, parseInt(scoreRaw, 10)));
  const note = box.querySelector('.gnote').value;
  btn.disabled = true;
  const s = box.querySelector('.gstatus');
  s.textContent = 'saving…'; s.classList.remove('saved','error');
  try {
    const res = await fetch('/api/grade', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({task_id, run_id, score, note}),
    });
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);
    const rec = await res.json();
    applyGrade(`${task_id}--${run_id}`, rec);
  } catch (e) {
    s.textContent = 'save failed: ' + e.message;
    s.classList.add('error');
  } finally {
    btn.disabled = false;
  }
}
loadGrades();
let lbVariant = 0;
function openLB(scenId, idx){
  lbScen = scenId; lbIdx = idx;
  lbVariant = CAROUSELS[lbScen][lbIdx].default || 0;
  renderLB();
  document.getElementById('lb').hidden = false;
}
function renderLB(){
  renderVariant();
  document.getElementById('lbcount').textContent = (lbIdx+1) + ' / ' + CAROUSELS[lbScen].length;
}
function renderVariant(){
  const item = CAROUSELS[lbScen][lbIdx];
  const v = item.variants[lbVariant];
  const img = document.getElementById('lbimg');
  img.src = v.src;
  img.classList.remove('zoomed');
  document.getElementById('lbimgwrap').scrollTo(0, 0);
  document.getElementById('lbcap').textContent = v.cap;
  const vbar = document.getElementById('lbvariant');
  const hasVariants = item.variants.length > 1;
  vbar.hidden = !hasVariants;
  if (hasVariants) vbar.textContent = `view ${lbVariant+1}/${item.variants.length} — ↑↓ or swipe`;
  document.getElementById('lbvup').disabled = !hasVariants;
  document.getElementById('lbvdown').disabled = !hasVariants;
}
function lbStep(d){
  const list = CAROUSELS[lbScen];
  lbIdx = (lbIdx + d + list.length) % list.length;
  // left/right moves between actors/frames but keeps the current
  // before/after (up/down) choice, clamped in case the new item has fewer
  // variants than the one you were just on
  lbVariant = Math.min(lbVariant, list[lbIdx].variants.length - 1);
  renderLB();
}
function cycleVariant(d){
  const item = CAROUSELS[lbScen][lbIdx];
  if (item.variants.length < 2) return;
  lbVariant = (lbVariant + d + item.variants.length) % item.variants.length;
  renderVariant();
}
function toggleZoom(e){
  e.stopPropagation();
  document.getElementById('lbimg').classList.toggle('zoomed');
}
function closeLB(){ document.getElementById('lb').hidden = true; }
document.addEventListener('keydown', e => {
  if (document.getElementById('lb').hidden) return;
  if (e.key === 'Escape') closeLB();
  if (e.key === 'ArrowLeft') lbStep(-1);
  if (e.key === 'ArrowRight') lbStep(1);
  if (e.key === 'ArrowUp') { e.preventDefault(); cycleVariant(-1); }
  if (e.key === 'ArrowDown') { e.preventDefault(); cycleVariant(1); }
});
document.getElementById('lb').addEventListener('click', e => {
  if (e.target.id === 'lb') closeLB();
});
let lbTouchX = null, lbTouchY = null;
document.getElementById('lb').addEventListener('touchstart', e => {
  // a tap that starts on a button (close/prev/next/up/down) is its own
  // gesture -- swipe detection would preventDefault the touchmove and
  // suppress the button's synthetic click, so leave it alone entirely
  if (e.touches.length !== 1 || e.target.closest('button')) { lbTouchX = null; return; }
  lbTouchX = e.touches[0].clientX;
  lbTouchY = e.touches[0].clientY;
}, {passive: true});
document.getElementById('lb').addEventListener('touchmove', e => {
  // block the page (and the modal backdrop) from scrolling under a swipe;
  // NOT blocked while zoomed, so panning a zoomed image via native
  // touch-scroll still works
  if (lbTouchX !== null && !document.getElementById('lbimg').classList.contains('zoomed')) {
    e.preventDefault();
  }
}, {passive: false});
document.getElementById('lb').addEventListener('touchend', e => {
  if (lbTouchX === null) return;
  // zoomed images pan via native touch-scroll -- don't hijack that as a swipe
  if (document.getElementById('lbimg').classList.contains('zoomed')) { lbTouchX = null; return; }
  const dx = e.changedTouches[0].clientX - lbTouchX;
  const dy = e.changedTouches[0].clientY - lbTouchY;
  lbTouchX = null;
  const SWIPE = 40;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < SWIPE) return;  // tap, not a swipe
  if (Math.abs(dx) > Math.abs(dy)) lbStep(dx < 0 ? 1 : -1);
  else cycleVariant(dy < 0 ? -1 : 1);
});
</script>
</body></html>
"""
(ROOT / "index.html").write_text(HTML.replace("__BODY__", BODY).replace("__CAROUSEL_JSON__", CAROUSEL_JSON))

missing = [f"{t}/{n}" for t, n in sorted(used) if not (DEST_IMG / t / f"{n}.png").exists()]
missing += [f"runs/{t}/{r}/img/{n}" for t, r, n in sorted(run_used) if not (RUNS / t / r / "img" / n).exists()]
print("wrote", ROOT / "index.html")
print("images used:", len(used), "+", len(run_used), "trial images; missing:", missing)
