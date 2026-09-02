// SubtractWorldToBrushFunc @ 0x10034980  size=201
typedef struct struct_1 {
    char padding_0[432];
    int field_1b0;
} struct_1;

typedef struct struct_3 {
    unsigned int field_0;
} struct_3;

typedef struct struct_2 {
    char padding_0[504];
    struct struct_3 *field_1f8;
} struct_2;

typedef struct struct_4 {
    struct struct_2 *field_0;
} struct_4;

typedef struct struct_0 {
    char padding_0[88];
    unsigned int field_58;
} struct_0;

extern unsigned int g_10140164;
extern unsigned int g_101491b8;
extern int g_101491bc;
extern unsigned int g_101491c0;
extern struct_0 *g_101491c8;
extern struct_4 *GEditor;

unsigned int sub_10034980(unsigned int a0, unsigned int a1, struct_1 *a2, unsigned int a3)
{
    unsigned long v9;  // ldt
    unsigned long v10;  // gdt
    unsigned short v11;  // fs
    unsigned long long v12;  // 4186
    unsigned int v13;  // ebx
    unsigned int v14;  // esi
    unsigned int v15;  // edi
    unsigned long long v16;  // 4190
    unsigned int v17;  // eax
    unsigned long long v18;  // 4122
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
    v6 = sub_100c4b40;
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
    v17 = a3;
    switch (v17)
    {
    case 0: case 2: case 4:
        if (a2->field_1b0 < 0)
        {
            v17 = (*((int *)&GEditor->field_0[1].padding_0[40]))(g_101491c8, g_101491c0, 2, 32, a2);
            break;
        }
        break;
    case 1: case 3: case 5:
        g_101491b8 = g_101491b8 + 1;
        v17 = g_101491c8->field_58;
        if (*((char *)(g_101491bc * 64 + v17 + 54)))
        {
            sub_10034020(g_101491bc);
            v17 = g_101491c8->field_58;
            *((char *)(g_101491bc * 64 + v17 + 54)) = 0;
            break;
        }
        break;
    }
    v18 = _ccall(v9, v10, (unsigned int)v11, 0);
    *((unsigned int *)(unsigned int)v18) = v5;
    return v17;
}
