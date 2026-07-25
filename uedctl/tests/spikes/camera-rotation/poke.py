import sys, struct
sys.path.insert(0,"/tmp")
import memscan as M
pid=int(open("/run/uned.pid").read())
addrs=[int(a,16) for a in sys.argv[1].split(",")]
P,Y,R=int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4])
data=struct.pack("<iii",P,Y,R)
for a in addrs:
    before=M.rd(pid,a,12)
    n=M.wr(pid,a,data)
    after=M.rd(pid,a,12)
    print(f"@{hex(a)} wrote {n}B  before={before.hex()} after={after.hex()}")
