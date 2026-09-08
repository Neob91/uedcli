"""Build index.html from the diffs/ (source of truth for the diagrams) plus
a small set of hand-captured supplementary photos already committed under
img/ (EXTRA_PHOTOS below) that no diff drives -- run after
render_from_diff.py regenerates the diff-backed pictures.
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST_IMG = ROOT / "img"
DIFFS = ROOT / "diffs"

used = set()
def img(name):
    used.add(name)
    return f"img/{name}.png"

# extra photos beyond the diff-rendered plan, keyed by scenario id -- these
# are hand-captured evidence (a camera angle, a "before" panorama frame),
# not something a diff generates; they must already exist under img/.
EXTRA_PHOTOS = {
 "t1_safe": [("v7photo_safe_before","Before: the trophy shelf — a vase, a polished rock, a closed book, and a nanokey on display."),
             ("v7photo_safe_fixed","Correct: the whole shelf unit, including the hidden safe built into its back, moved out together with the wall."),
             ("v7photo_safe_side","Side view showing the shelf is a real wooden cabinet built into the wall, with actual depth."),
             ("v7photo_safe_behind","The space directly behind the safe: a sealed, empty dead-end — nothing else back there.")],
 "t1_flags": [("v7photo_flags_after","Photo confirming a flag sits flush back in its corner after the move.")],
 "t2_fixtures": [("v6pan_C_0","Photo, camera tilted upward, showing the raised ceiling with one of the light panels visible.")],
 "t2_niche": [("v6pan_C_0","Photo, camera tilted upward — the height step at the boundary with the niche is visible in the top-right.")],
}

TASK_META = {
 "t1": dict(title="Task 1 — Widen the office",
   req="&ldquo;Manderley&rsquo;s office is too narrow. Widen it eastward by 48 units &mdash; move its east wall out.&rdquo;",
   before_diags=[("v4_before_top","Top-down plan of the office before any change. It's built from TWO separate wall volumes that share one east wall (the south half is brush Brush418, the north half is brush Brush420) — a detail invisible to a player, but important for widening the wall correctly."),
                 ("v4_before_side","Side view (elevation) of the same office before any change, for height context.")],
   before_photos=[f"v4pan_before_{i}" for i in range(8)]),
 "t2": dict(title="Task 2 — Raise the ceiling",
   req="&ldquo;Manderley&rsquo;s office feels cramped. Raise its ceiling by 48 units.&rdquo;",
   before_diags=[("v4_before_side","Side view (elevation) of the office before any change — the ceiling is flat at z=416, spanning both wall volumes (Brush418 south, Brush420 north)."),
                 ("v4_before_top","Top-down plan of the same office, for footprint context.")],
   before_photos=[f"v6pan_beforeceil_{i}" for i in range(8)]),
}

OP_DESC = {
 "brush_vertex_move": lambda op: f"brush <code>{op['actor']}</code>: move corners {op['at']} by {tuple(op['by'])}",
 "actor_move": lambda op: f"actors <code>{', '.join(op['actors'])}</code>: move by {tuple(op['by'])}",
 "assert_unchanged": lambda op: f"actors <code>{', '.join(op['actors'])}</code>: must stay unchanged from the baseline",
}

ALL_CAROUSELS = {}

def scenario_images(scen_id, d):
    imgs = [(d["id"], f"[CORRECT] {d['note']} (highlighted: {', '.join(d['highlight'])})")]
    imgs += EXTRA_PHOTOS.get(scen_id, [])
    return imgs

def carousel_html(scen_id, images):
    items, thumbs = [], ""
    for i, (name, cap) in enumerate(images):
        items.append({"src": img(name), "cap": cap})
        thumbs += (f'<img class="cthumb" src="{img(name)}" alt="{cap}" loading="lazy" tabindex="0" '
                   f'onclick="openLB(\'{scen_id}\',{i})" onkeydown="if(event.key===\'Enter\')openLB(\'{scen_id}\',{i})">')
    ALL_CAROUSELS[scen_id] = items
    return thumbs

def scenario_card(d):
    images = scenario_images(d["id"], d)
    thumbs = carousel_html(d["id"], images)
    ops_html = "".join(f"<li>{OP_DESC[op['kind']](op)}</li>" for op in d["ops"])
    diff_rel = f"diffs/{d['id']}.json"
    return f"""<div class="scen">
      <button class="scenhead" onclick="toggleScen(this)">
        <span class="chev">&#9656;</span><span class="stitle">{d['title']}</span>
      </button>
      <div class="scenbody" hidden>
        <p class="sdesc">{d['note']}</p>
        <div class="carousel">{thumbs}</div>
        <details class="diffbox"><summary>Diff — the exact ops this picture is generated from (<a href="{diff_rel}">{diff_rel}</a>)</summary>
          <ul class="ops">{ops_html}</ul>
        </details>
      </div></div>"""

def task_block(task_id, scenario_diffs):
    meta = TASK_META[task_id]
    diag_html = "".join(f'<figure class="dg"><img src="{img(n)}" alt="{c}" onclick="openLB(\'{task_id}__before\',{i})"><figcaption>{c}</figcaption></figure>'
                         for i, (n, c) in enumerate(meta["before_diags"]))
    bid = f"{task_id}__before"
    ALL_CAROUSELS[bid] = [{"src": img(n), "cap": "Panorama frame, before any edit."} for n in meta["before_photos"]]
    before_thumbs = "".join(f'<img class="cthumb" src="{img(n)}" alt="panorama" loading="lazy" tabindex="0" '
                             f'onclick="openLB(\'{bid}\',{i})" onkeydown="if(event.key===\'Enter\')openLB(\'{bid}\',{i})">'
                             for i, n in enumerate(meta["before_photos"]))
    scen_html = "".join(scenario_card(d) for d in scenario_diffs)
    return f"""<div class="taskblk">
      <button class="taskhead" onclick="toggleTask(this)">
        <span class="tchev">&#9656;</span><h2>{meta['title']}</h2>
      </button>
      <div class="taskbody" hidden>
        <div class="task"><span class="t">REQUEST:</span> {meta['req']}</div>
        <div class="beforeblk">
          <div class="diagrams">{diag_html}</div>
          <div class="striplabel">360° panorama tour, before any edit</div>
          <div class="carousel">{before_thumbs}</div>
        </div>
        <h3 class="scenh">Per-aspect scenarios — click to expand</h3>
        {scen_html}
      </div></div>"""

ASPECT_IDS = {
 "t1": ["t1_wall", "t1_fixtures", "t1_safe", "t1_flags", "t1_niche"],
 "t2": ["t2_ceil", "t2_fixtures", "t2_niche", "t2_lights"],
}
BODY = ""
for task_id, ids in ASPECT_IDS.items():
    diffs = [json.loads((DIFFS / f"{i}.json").read_text()) for i in ids]
    BODY += task_block(task_id, diffs)

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
.ops{margin:8px 0 0;padding-left:20px;color:var(--dim);font-family:var(--mono);font-size:12px;line-height:1.7}
.ops code{color:var(--gold-soft)}

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
  <p class="pipeline"><b>Every picture is generated, never hand-built:</b> each scenario is backed by a small JSON diff (<code>diffs/&lt;id&gt;.json</code>) — the exact before→after ops for that aspect. Rendering applies the WHOLE task's diff to the untouched baseline first, then highlights just this aspect's actors, so a picture can never drift out of sync with the trunk it claims to show (open the "Diff" box in any scenario to see the exact ops, or read the JSON directly).</p>
  <p class="orient">Orientation, top-down plans (matching UnrealEd's own axis convention): <b>East = right</b> edge of the image, <b>West = left</b>, <b>North = up</b>, <b>South = down</b>. A small compass is burned into the top-left corner of every plan below as a direct check.</p>
  __BODY__
  <p class="foot">Batch 1 = UNATCO HQ (2 tasks), swept exhaustively — every actor within a wide margin of the moved geometry individually classified. Remaining: NYC_Bar, WanChai Market, OceanLab, + one more, each with the same diff-driven pipeline. Diagrams: <code>actor diagram</code>, full-office framing throughout. Photos: <code>level photo --native --faces textured</code>; procedural FX skins render solid <b>red</b>. Grading: for each scenario, apply the same ops/assertions to a subagent's trunk actor set and compare — the diff files are the oracle.</p>
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

missing = [n for n in sorted(used) if not (DEST_IMG / f"{n}.png").exists()]
print("wrote", ROOT / "index.html")
print("images used:", len(used), "missing:", missing)
