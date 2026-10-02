// bspFilterFPoly @ 0x10031f50  size=157
extern unsigned int g_10140164;

unsigned int sub_10031f50(unsigned int *a0, unsigned int *a1, int a2)
{
    unsigned long v11;  // ldt
    unsigned long v12;  // gdt
    unsigned short v13;  // fs
    unsigned long long v14;  // 4196
    unsigned long long v15;  // 4200
    unsigned int v16;  // eax
    unsigned long long v17;  // 4122
    unsigned int v0;  // [bp-0x58]
    unsigned int v1;  // [bp-0x48]
    unsigned int v2;  // [bp-0x44]
    unsigned int v3;  // [bp-0x40]
    unsigned int v4;  // [bp-0x30]
    unsigned int v5;  // [bp-0x20]
    char *v6;  // [bp-0x14]
    unsigned int v7;  // [bp-0x10]
    unsigned int v8;  // [bp-0xc]
    unsigned int v9;  // [bp-0x8]
    char v10;  // [bp-0x4]

    v9 = 0xffffffff;
    v8 = sub_100c4800;
    v14 = _ccall(v11, v12, (unsigned int)v13, 0);
    v7 = *((int *)(unsigned int)v14);
    v3 = g_10140164 ^ &v10;
    v15 = _ccall(v11, v12, (unsigned int)v13, 0);
    *((unsigned int **)(unsigned int)v15) = &v7;
    v6 = &v3;
    v9 = 0;
    v4 = 0xffffffff;
    if (!a1[23])
    {
        v16 = a0(a1, 0, a2, !a1[60], 3);
    }
    else
    {
        v2 = a1[60];
        memcpy(&v0, &v4, 16);
        v1 = v5;
        v16 = sub_10032bf0(a0, a1, 0, a2, v0);
    }
    v17 = _ccall(v11, v12, (unsigned int)v13, 0);
    *((unsigned int *)(unsigned int)v17) = v7;
    return v16;
}
