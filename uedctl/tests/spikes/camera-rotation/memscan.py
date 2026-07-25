import ctypes, os, struct, sys, re
libc=ctypes.CDLL("libc.so.6",use_errno=True)
class iovec(ctypes.Structure):
    _fields_=[("base",ctypes.c_void_p),("len",ctypes.c_size_t)]
libc.process_vm_readv.restype=ctypes.c_ssize_t
libc.process_vm_readv.argtypes=[ctypes.c_int,ctypes.POINTER(iovec),ctypes.c_ulong,ctypes.POINTER(iovec),ctypes.c_ulong,ctypes.c_ulong]
libc.process_vm_writev.restype=ctypes.c_ssize_t
libc.process_vm_writev.argtypes=libc.process_vm_readv.argtypes
def rd(pid,addr,n):
    buf=(ctypes.c_char*n)()
    lo=iovec(ctypes.cast(buf,ctypes.c_void_p),n); ro=iovec(ctypes.c_void_p(addr),n)
    r=libc.process_vm_readv(pid,ctypes.byref(lo),1,ctypes.byref(ro),1,0)
    return bytes(buf[:r]) if r>0 else b""
def wr(pid,addr,data):
    buf=ctypes.create_string_buffer(data,len(data))
    lo=iovec(ctypes.cast(buf,ctypes.c_void_p),len(data)); ro=iovec(ctypes.c_void_p(addr),len(data))
    return libc.process_vm_writev(pid,ctypes.byref(lo),1,ctypes.byref(ro),1,0)
def maps(pid):
    out=[]
    for line in open(f"/proc/{pid}/maps"):
        parts=line.split()
        rng=parts[0]; perm=parts[1]
        if "rw" in perm:
            s,e=rng.split("-"); out.append((int(s,16),int(e,16),line.strip()))
    return out
if __name__=="__main__":
    pid=int(open("/run/uned.pid").read())
    cmd=sys.argv[1]
    if cmd=="scan":
        # find FRotator triple where Pitch in [target-tol,target+tol], roll==0
        tp,ty,tr=int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4])
        tol=int(sys.argv[5]) if len(sys.argv)>5 else 400
        hits=[]
        for s,e,desc in maps(pid):
            size=e-s
            if size>200*1024*1024: 
                # chunk
                pass
            off=s
            CH=4*1024*1024
            while off<e:
                n=min(CH,e-off)
                d=rd(pid,off,n)
                if not d: off+=n; continue
                for m in range(0,len(d)-12,4):
                    p,y,r=struct.unpack_from("<iii",d,m)
                    if abs(p-tp)<=tol and r==tr and abs(((y-ty+32768)%65536)-32768)<=tol+2000:
                        hits.append((off+m,p,y,r))
                off+=n
        print(f"pid={pid} hits={len(hits)}")
        for a,p,y,r in hits[:80]:
            print(f"  {hex(a)} P={p} Y={y} R={r}")
