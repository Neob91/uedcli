// MakeEdPolys @ 0x10033bb0  size=244
typedef struct struct_4 {
    struct struct_2 *field_0;
} struct_4;

typedef struct struct_3 {
    unsigned int field_0;
} struct_3;

typedef struct struct_2 {
    char padding_0[504];
    struct struct_3 *field_1f8;
} struct_2;

typedef struct struct_1 {
    char padding_0[40];
    unsigned int field_28;
    char padding_2c[8];
    unsigned int field_34;
} struct_1;

typedef struct struct_0 {
    char padding_0[84];
    struct struct_1 *field_54;
    unsigned int field_58;
} struct_0;

extern struct_4 *GEditor;
extern char GUndo;

int sub_10033bb0(struct_0 *idx, unsigned int a1)
{
    unsigned int v5;  // ebx
    unsigned int v6;  // esi
    unsigned int v7;  // edi
    void* *v8;  // edi
    unsigned int v9;  // esi
    int v10;  // eax
    unsigned int v11;  // ecx
    unsigned int v12;  // eax
    unsigned int v0;  // [bp-0x1f0]
    unsigned int v1;  // [bp-0x1ec]
    unsigned int v2;  // [bp-0x1e8]
    int v3;  // [bp-0x1e4]
    char v4;  // [bp-0x1e0]

    v2 = v5;
    v1 = v6;
    v0 = v7;
    v8 = a1 * 64 + idx->field_58;
    FPoly::FPoly(&v4);
    if (GEditor->field_0->field_1f8(idx, a1, &v4) >= 3)
    {
        v9 = &idx->field_54->field_28;
        v10 = FArray::Add(v9, 1, 472);
        v3 = v10;
        if (*((int *)&GUndo))
        {
            (*((int *)(*((int *)*((int *)&GUndo)) + 8)))(*((int *)(v9 + 12)), v9, v10, 1, 1, 472, operator<<, sub_10012f80);
            v10 = v3;
        }
        v11 = v10 * 472;
        if (v11 + *((int *)v9))
            FPoly::FPoly(v11 + *((int *)v9), &v4);
    }
    if (v8[9] != 0xffffffff)
        sub_10033bb0(idx, v8[9]);
    if (v8[8] != 0xffffffff)
        sub_10033bb0(idx, v8[8]);
    if (v8[10] != 0xffffffff)
        sub_10033bb0(idx, v8[10]);
    return v12;
}
