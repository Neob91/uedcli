import struct, sys
def rd_idx(b,o):
    b0=b[o]; o+=1
    neg=b0&0x40; val=b0&0x3f; shift=6
    if b0&0x80:
        while True:
            x=b[o]; o+=1; val|=(x&0x7f)<<shift; shift+=7
            if not (x&0x80): break
    return (-val if neg else val), o

def parse(path):
    data=open(path,'rb').read()
    name_count,name_off=struct.unpack_from('<II',data,12)
    export_count,export_off=struct.unpack_from('<II',data,20)
    import_count,import_off=struct.unpack_from('<II',data,28)
    o=name_off; names=[]
    for i in range(name_count):
        ln,o=rd_idx(data,o); s=data[o:o+ln-1].decode('latin1'); o+=ln; o+=4; names.append(s)
    # Imports
    o=import_off; imports=[]
    for i in range(import_count):
        cpkg,o=rd_idx(data,o); ccls,o=rd_idx(data,o)
        pkgidx=struct.unpack_from('<i',data,o)[0]; o+=4
        objname,o=rd_idx(data,o)
        imports.append((names[cpkg],names[ccls],names[objname]))
    # Exports
    o=export_off; exports=[]
    for i in range(export_count):
        cls,o=rd_idx(data,o); sup,o=rd_idx(data,o)
        pkg=struct.unpack_from('<i',data,o)[0]; o+=4
        objname,o=rd_idx(data,o)
        oflags=struct.unpack_from('<I',data,o)[0]; o+=4
        size,o=rd_idx(data,o); offset,o=rd_idx(data,o)
        exports.append({'class':cls,'name':names[objname],'size':size,'offset':offset})
    return data,names,imports,exports

def rotators_in_export(data,names,exp):
    # Walk property tags in the export body, return dict of struct/int props
    o=exp['offset']; end=exp['offset']+exp['size']; props={}
    while o<end:
        nidx,o=rd_idx(data,o)
        pname=names[nidx]
        if pname=='None': break
        info=data[o]; o+=1
        ptype=info&0x0f
        sizebits=(info>>4)&0x07
        isarray=info&0x80
        # struct name for type 10 (StructProperty)
        structname=None
        if ptype==10:
            sidx,o=rd_idx(data,o); structname=names[sidx]
        sizemap={0:1,1:2,2:4,3:12,4:16,5:None,6:None,7:None}
        if sizebits<=4:
            psize=sizemap[sizebits]
        elif sizebits==5:
            psize=data[o]; o+=1
        elif sizebits==6:
            psize=struct.unpack_from('<H',data,o)[0]; o+=2
        else:
            psize=struct.unpack_from('<I',data,o)[0]; o+=4
        if isarray and ptype!=3:
            arridx=data[o]; o+=1
        val=None
        if ptype==10 and structname=='Rotator':
            p,y,r=struct.unpack_from('<iii',data,o); val=('Rotator',p,y,r)
        elif ptype==10 and structname=='Vector':
            x,yy,z=struct.unpack_from('<fff',data,o); val=('Vector',x,yy,z)
        props.setdefault(pname,[]).append((structname,psize,val,o))
        o+=psize
    return props

if __name__=='__main__':
    data,names,imports,exports=parse(sys.argv[1])
    for e in exports:
        if e['name'].startswith('Camera'):
            pr=rotators_in_export(data,names,e)
            vr=pr.get('ViewRotation'); rot=pr.get('Rotation')
            print(e['name'], 'ViewRotation=', vr, 'Rotation=', rot)

def read_view_rotation(path):
    """Return (pitch,yaw,roll) of the FIRST Camera with a non-default ViewRotation, or None."""
    data,names,_,_=parse(path)
    try:
        vr_idx=names.index('ViewRotation'); rotator_idx=names.index('Rotator')
    except ValueError:
        return None
    for o in range(len(data)-20):
        n,o2=rd_idx(data,o)
        if n!=vr_idx: continue
        info=data[o2]; o2+=1
        if (info&0x0f)!=10: continue
        s,o3=rd_idx(data,o2)
        if s!=rotator_idx: continue
        sb=(info>>4)&7
        if sb<5: o3+=0
        elif sb==5: o3+=1
        elif sb==6: o3+=2
        else: o3+=4
        if info&0x80: o3+=1
        return struct.unpack_from('<iii',data,o3)
    return None
