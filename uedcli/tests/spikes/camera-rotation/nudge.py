# Tiny mouse interaction in the perspective pane to force a view recompute, minimal delta.
import subprocess, time, re, sys
W=["python3","/repo/Tools/uedcli/uned/wine_ctl.py"]
def run(*a): return subprocess.run(list(a),capture_output=True,text=True)
st=run(*(W+["status"])).stdout
win=re.search(r"window=(\d+)",st).group(1)
geo=run("xdotool","getwindowgeometry","--shell",win).stdout
g={k:int(v) for k,v in re.findall(r"(\w+)=(\d+)",geo)}
run(*(W+["focus"])); time.sleep(0.3)
px=g["X"]+g["WIDTH"]//4; py=g["Y"]+g["HEIGHT"]*3//4
mode=sys.argv[1] if len(sys.argv)>1 else "rmb1"
run("xdotool","mousemove",str(px),str(py)); time.sleep(0.2)
if mode=="rmb1":
    # RMB press+release with a 1px move (adds ~tiny yaw, recompute fires)
    run("xdotool","mousedown","3"); time.sleep(0.15)
    run("xdotool","mousemove",str(px+1),str(py)); time.sleep(0.1)
    run("xdotool","mouseup","3")
elif mode=="rmbclick":
    run("xdotool","mousedown","3"); time.sleep(0.1); run("xdotool","mouseup","3")
time.sleep(0.4)
print("nudged",mode)
