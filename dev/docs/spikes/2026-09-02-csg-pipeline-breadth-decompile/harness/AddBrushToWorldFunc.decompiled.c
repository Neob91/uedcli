// AddBrushToWorldFunc @ 0x10031770  size=136
typedef struct struct_0 {
    char padding_0[432];
    char field_1b0;
} struct_0;

typedef struct struct_2 {
    unsigned int field_0;
} struct_2;

typedef struct struct_1 {
    char padding_0[548];
    struct struct_2 *field_224;
} struct_1;

typedef struct struct_3 {
    struct struct_1 *field_0;
} struct_3;

extern unsigned int g_10140164;
extern struct_3 *GEditor;

unsigned int sub_10031770(unsigned int a0, unsigned int a1, struct_0 *a2, unsigned int a3)
{
    unsigned long v11;  // ldt
    unsigned long v12;  // gdt
    unsigned long long v21;  // 4122
    unsigned short v13;  // fs
    unsigned long long v14;  // 4186
    unsigned int v15;  // ebx
    unsigned int v16;  // esi
    unsigned int v17;  // edi
    unsigned long long v18;  // 4190
    unsigned int v19;  // eax
    unsigned int v20;  // eax
    struct_0 *v0;  // [bp-0x30]
    unsigned int v1;  // [bp-0x2c]
    unsigned int v2;  // [bp-0x28]
    unsigned int v3;  // [bp-0x24]
    unsigned int v4;  // [bp-0x20]
    char *v5;  // [bp-0x14]
    unsigned int v6;  // [bp-0x10]
    unsigned int v7;  // [bp-0xc]
    unsigned int v8;  // [bp-0x8]
    char v9;  // [bp-0x4]
    unsigned int v10;  // [bp+0x14]

    v8 = 0xffffffff;
    v7 = sub_100c4740;
    v14 = _ccall(v11, v12, (unsigned int)v13, 0);
    v6 = *((int *)(unsigned int)v14);
    v4 = v15;
    v3 = v16;
    v2 = v17;
    v1 = g_10140164 ^ &v9;
    v18 = _ccall(v11, v12, (unsigned int)v13, 0);
    *((unsigned int **)(unsigned int)v18) = &v6;
    v5 = &v1;
    v8 = 0;
    if (a3 && !(v19 = a3 - 2, a3 == 2))
    {
        v20 = v19 - 3;
        if (v19 != 3)
        {
            v21 = _ccall(v11, v12, (unsigned int)v13, 0);
            *((unsigned int *)(unsigned int)v21) = v6;
            return v20;
        }
        else if (!(a2->field_1b0 & 32))
        {
            v0 = a2;
        }
        else
        {
            v21 = _ccall(v11, v12, (unsigned int)v13, 0);
            *((unsigned int *)(unsigned int)v21) = v6;
            return v20;
        }
    }
    else
    {
        v0 = a2;
    }
    v20 = GEditor->field_0->field_224(a0, a1, v10, 32);
    v21 = _ccall(v11, v12, (unsigned int)v13, 0);
    *((unsigned int *)(unsigned int)v21) = v6;
    return v20;
}
