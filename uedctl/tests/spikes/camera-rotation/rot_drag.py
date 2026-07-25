# Inside container: focus editor, click into perspective pane, RMB-drag to change PITCH, save .dx
import subprocess, time, sys
W=["python3","/repo/Tools/uedctl/uned/wine_ctl.py"]
def run(*a): return subprocess.run(list(a),capture_output=True,text=True)
def ex(l): run(*(W+["exec",l])); time.sleep(0.4)
def wid():
    return run(*(W+["status"])).stdout
def focus(): run(*(W+["focus"])); time.sleep(0.3)
# Get window geometry to compute perspective pane center.
import re
st=wid()
win=re.search(r"window=(\d+)",st).group(1)
geo=run("xdotool","getwindowgeometry","--shell",win).stdout
g={k:int(v) for k,v in re.findall(r"(\w+)=(\d+)",geo)}
print("win geom",g)
# perspective pane is bottom-left quadrant of the 4-pane layout
focus()
# In UnrealEd 4-pane: panes are 2x2. Perspective = bottom-left typically.
# Click to make perspective current, then RMB drag.
px = g["X"] + g["WIDTH"]//4
py = g["Y"] + g["HEIGHT"]*3//4
tag=sys.argv[1]; dx=int(sys.argv[2]); dy=int(sys.argv[3])
run("xdotool","mousemove",str(px),str(py))
time.sleep(0.2)
# RMB down, move (pitch = vertical), up
run("xdotool","mousedown","3"); time.sleep(0.2)
steps=20
for i in range(1,steps+1):
    run("xdotool","mousemove",str(px+dx*i//steps),str(py+dy*i//steps)); time.sleep(0.02)
time.sleep(0.2)
run("xdotool","mouseup","3"); time.sleep(0.4)
ex(f"MAP SAVE FILE=/repo/_scratch/camspike/{tag}.dx")
time.sleep(1.2)
print("saved",tag)
