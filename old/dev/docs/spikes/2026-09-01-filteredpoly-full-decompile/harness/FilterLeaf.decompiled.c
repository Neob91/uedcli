extern unsigned int g_10140164;

int sub_10033130(unsigned int *a0, unsigned int *a1, unsigned int a2, unsigned int a3, unsigned int a4, int a5, int a6, int a7, unsigned int a8, int a9, unsigned int a10)
{
    unsigned long v14;  // ldt
    unsigned long v15;  // gdt
    unsigned short v16;  // fs
    unsigned long long v17;  // 4186
    unsigned long long v18;  // 4190
    int v19;  // eax
    int v20;  // ecx
    int v21;  // eax
    unsigned int v22;  // eax
    unsigned long long v23;  // 4122
    unsigned int v0;  // [bp-0x44]
    unsigned int v1;  // [bp-0x40]
    unsigned int v2;  // [bp-0x3c]
    unsigned int v3;  // [bp-0x38]
    unsigned int v4;  // [bp-0x34]
    unsigned int v5;  // [bp-0x30]
    unsigned int v6;  // [bp-0x2c]
    unsigned int v7;  // [bp-0x28]
    unsigned int v8;  // [bp-0x24]
    char *v9;  // [bp-0x14]
    unsigned int v10;  // [bp-0x10]
    unsigned int v11;  // [bp-0xc]
    unsigned int v12;  // [bp-0x8]
    char v13;  // [bp-0x4]

    v12 = 0xffffffff;
    v11 = sub_100c4940;
    v17 = _ccall(v14, v15, (unsigned int)v16, 0);
    v10 = *((int *)(unsigned int)v17);
    v6 = g_10140164 ^ &v13;
    v18 = _ccall(v14, v15, (unsigned int)v16, 0);
    *((unsigned int **)(unsigned int)v18) = &v10;
    v9 = &v6;
    v12 = 0;
    if (a4 == -0x1)
    {
        v5 = a10;
        v4 = !a9;
        v3 = a3;
        v2 = a2;
        goto LABEL_100331f4;
    }
    if (!a8)
    {
        v19 = a9;
        a7 = v19;
        if (a5 == -0x1)
        {
            v20 = a6;
LABEL_100331cb:
            if (!v20)
            {
                v22 = (!v19 ? 3 : 5);
            }
            else
            {
                v22 = 2;
                if (!v19)
                    v22 = 4;
            }
            v5 = 2;
            v4 = v22;
            v3 = a3;
            v2 = a4;
LABEL_100331f4:
            v21 = a0(a1);
        }
        else
        {
            a8 = 1;
            memcpy(&v0, &a4, 16);
            v21 = sub_10032bf0(a0, a1, a5, a3, v0, v1, v2, v3, 1, a6, g_10140164 ^ &v13, v7, v8);
        }
    }
    else
    {
        v20 = a9;
        v19 = a7;
        goto LABEL_100331cb;
    }
    v23 = _ccall(v14, v15, (unsigned int)v16, 0);
    *((unsigned int *)(unsigned int)v23) = v10;
    return v21;
}
