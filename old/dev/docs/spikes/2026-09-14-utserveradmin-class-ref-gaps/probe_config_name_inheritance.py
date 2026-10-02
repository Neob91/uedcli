import sys, struct
sys.path.insert(0, ".")
from uedcli.upackage import load_package, read_compact_index as rci, read_array_index as rai
from uedcli.uprops.ufield import _skip_script


def config_name(pkg, idx1):
    e = pkg.exports[idx1 - 1]
    buf, p = pkg.buf, e["soff"]
    for _ in range(5):
        _, p = rci(buf, p)
    p += 8
    ssz = struct.unpack_from("<I", buf, p)[0]; p += 4
    p = _skip_script(pkg, p, ssz)
    p += 8 + 8 + 2 + 4 + 4 + 16
    count, p = rai(buf, p)
    for _ in range(count):
        _, p = rci(buf, p); p += 8
    picnt, p = rci(buf, p)
    for _ in range(picnt):
        _, p = rci(buf, p)
    within, p = rci(buf, p)
    cfgname, p = rci(buf, p)
    within_nm = pkg.name_of_ref(within) if within else "Object"
    cfgname_nm = pkg.names[cfgname] if 0 < cfgname < len(pkg.names) else "System"
    return within_nm, cfgname_nm


pkg = load_package("uned/UT99/System/Engine.u")
for nm_want in ("MessagingSpectator", "Spectator", "PlayerPawn"):
    for i, e in enumerate(pkg.exports):
        nm = pkg.names[e["nm"]] if 0 <= e["nm"] < len(pkg.names) else "?"
        if e["cls"] == 0 and nm == nm_want:
            print(nm_want, config_name(pkg, i + 1))
            break
