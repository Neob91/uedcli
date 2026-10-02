import sys
ini, engine, cache = sys.argv[1], sys.argv[2], sys.argv[3]
raw = open(ini, "rb").read().decode("latin-1")
lines = raw.split("\r\n")
if engine == "stock":
    game_engine="Engine.GameEngine"; default_game="Engine.GameInfo"; player_class="Engine.Camera"; root=""; cache_section="[Engine.GameEngine]"
else:
    game_engine="DeusEx.DeusExGameEngine"; default_game="DeusEx.DeusExGameInfo"; player_class="DeusEx.JCDentonMale"; root="DeusEx.DeusExRootWindow"; cache_section="[DeusEx.DeusExGameEngine]"
eng_fix={"gameengine":f"GameEngine={game_engine}","gamerenderdevice":"GameRenderDevice=SoftDrv.SoftwareRenderDevice","renderdevice":"RenderDevice=SoftDrv.SoftwareRenderDevice","windowedrenderdevice":"WindowedRenderDevice=SoftDrv.SoftwareRenderDevice","console":"Console=UedPreview.UedPreviewConsole","defaultgame":f"DefaultGame={default_game}","defaultservergame":f"DefaultServerGame={default_game}","root":(f"Root={root}" if root else None),"editorengine":"EditorEngine=Editor.EditorEngine"}
url_fix={"localmap":"LocalMap=room.dx","map":"Map=room.dx","class":f"Class={player_class}"}
win_fix={"windowedcolorbits":"WindowedColorBits=32","windowedviewportx":"WindowedViewportX=640","windowedviewporty":"WindowedViewportY=480","startupfullscreen":"StartupFullscreen=False"}
firstrun_val="FirstRun=400"
out,section=[],""; saw_paths=False
for l in lines:
    s=l.strip()
    if s.startswith("[") and s.endswith("]"): section=s.lower(); out.append(l); continue
    k=l.split("=",1)[0].strip().lower()
    if k=="paths":
        if not saw_paths: out+=["Paths=../System/*.u","Paths=../Maps/*.dx","Paths=../Textures/*.utx"]; saw_paths=True
        continue
    if k=="firstrun": out.append(firstrun_val); continue
    if section=="[engine.engine]" and k in eng_fix:
        v=eng_fix.pop(k)
        if v is not None: out.append(v)
        continue
    if section=="[url]" and k in url_fix: out.append(url_fix.pop(k)); continue
    if section=="[windrv.windowsclient]" and k in win_fix: out.append(win_fix.pop(k)); continue
    out.append(l)
def inject(sec,kvs):
    if not kvs: return
    try: i=out.index(sec)
    except ValueError: out.append(sec); i=len(out)-1
    out[i+1:i+1]=kvs
inject("[Engine.Engine]",list(v for v in eng_fix.values() if v))
inject("[URL]",list(url_fix.values()))
inject("[WinDrv.WindowsClient]",list(win_fix.values()))
inject(cache_section,[f"CacheSizeMegs={cache}"])
# HUD hide base driver
out += ["", "[UedPreview.UedPreviewBaseDriver]", "HudHideCommands=ShowHud 0"]
open(ini,"wb").write(("\r\n".join(out)).encode("latin-1"))
print(f"ini: GameEngine={game_engine} DefaultGame={default_game} Class={player_class} cache={cache} root={root or '(none)'}")
