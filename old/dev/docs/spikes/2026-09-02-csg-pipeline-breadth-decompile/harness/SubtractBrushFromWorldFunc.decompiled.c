// SubtractBrushFromWorldFunc @ 0x100348c0  size=133
typedef struct struct_1 {
    unsigned int field_0;
} struct_1;

typedef struct struct_0 {
    char padding_0[548];
    struct struct_1 *field_224;
} struct_0;

typedef struct struct_2 {
    struct struct_0 *field_0;
} struct_2;

extern unsigned int g_10140164;
extern struct_2 *GEditor;

int sub_100348c0(unsigned int a0, unsigned int a1, void* a2, unsigned int a3, unsigned int a4)
{
    unsigned long v9;  // ldt
    unsigned long v10;  // gdt
    unsigned long long v19;  // 4122
    unsigned short v11;  // fs
    unsigned long long v12;  // 4186
    unsigned int v13;  // ebx
    unsigned int v14;  // esi
    unsigned int v15;  // edi
    unsigned long long v16;  // 4190
    unsigned int v17;  // eax
    unsigned int v18;  // eax
    unsigned int v0;  // [bp-0x2c]
    unsigned int v1;  // [bp-0x28]
    unsigned int v2;  // [bp-0x24]
    unsigned int v3;  // [bp-0x20]
    char *v4;  // [bp-0x14]
    unsigned int v5;  // [bp-0x10]
    unsigned int v6;  // [bp-0xc]
    unsigned int v7;  // [bp-0x8]
    char v8;  // [bp-0x4]

    v7 = 0xffffffff;
    v6 = sub_100c4b20;
    v12 = _ccall(v9, v10, (unsigned int)v11, 0);
    v5 = *((int *)(unsigned int)v12);
    v3 = v13;
    v2 = v14;
    v1 = v15;
    v0 = g_10140164 ^ &v8;
    v16 = _ccall(v9, v10, (unsigned int)v11, 0);
    *((unsigned int **)(unsigned int)v16) = &v5;
    v4 = &v0;
    v7 = 0;
    v17 = a3 - 1;
    if (a3 == 1 || (v18 = v17 - 2, v17 == 2))
    {
        FPoly::Reverse(a2);
        GEditor->field_0->field_224(a0, a1, a4, 32, a2);
        v18 = (unsigned int)FPoly::Reverse(a2);
    }
    v19 = _ccall(v9, v10, (unsigned int)v11, 0);
    *((unsigned int *)(unsigned int)v19) = v5;
    return v18;
}
