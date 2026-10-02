// MergeCoplanarPolys @ 0x10033cb0  size=210
typedef struct struct_0 {
    char field_0;
    char padding_1[39];
    unsigned int field_28;
} struct_0;

typedef struct struct_1 {
    char padding_0[84];
    struct struct_0 *field_54;
} struct_1;

extern unsigned int g_10140164;

struct_0 * sub_10033cb0(struct_1 *idx, unsigned int *a1, int a2)
{
    unsigned long v10;  // ldt
    unsigned long v11;  // gdt
    int v20;  // edx
    int iter;  // esi
    int v22;  // ecx
    unsigned long long v23;  // 4122
    unsigned short v12;  // fs
    unsigned long long v13;  // 4144
    struct_0 *v14;  // eax
    unsigned long long v15;  // 4164
    unsigned int i;  // edi
    unsigned int *v17;  // esi
    int v18;  // ecx
    int index;  // ebx
    unsigned int v0;  // [bp-0x3c]
    int v1;  // [bp-0x24]
    int v2;  // [bp-0x20]
    int v3;  // [bp-0x1c]
    unsigned int v4;  // [bp-0x18]
    char *v5;  // [bp-0x14]
    unsigned int v6;  // [bp-0x10]
    unsigned int v7;  // [bp-0xc]
    unsigned int v8;  // [bp-0x8]
    char v9;  // [bp-0x4]

    v8 = 0xffffffff;
    v7 = sub_100c4a30;
    v13 = _ccall(v10, v11, (unsigned int)v12, 0);
    v6 = *((int *)(unsigned int)v13);
    v0 = g_10140164 ^ &v9;
    v14 = &v6;
    v15 = _ccall(v10, v11, (unsigned int)v12, 0);
    *((unsigned int **)(unsigned int)v15) = &v6;
    v5 = &v0;
    v8 = 0;
    i = 1;
    v4 = 1;
    v17 = a1;
    v18 = a2;
    while (i)
    {
        i = 0;
        v4 = 0;
        index = 0;
        while (1)
        {
            v1 = index;
            if (index >= v18)
                break;
            v14 = idx->field_54;
            v20 = v17[index] * 472 + v14->field_28;
            v3 = v20;
            index += 1;
            if (*((int *)(v20 + 448)) <= 0)
                continue;
            iter = index;
            while (1)
            {
                v2 = iter;
                if (iter >= v18)
                    break;
                v14 = idx->field_54;
                v22 = a1[iter] * 472 + idx->field_54->field_28;
                if (*((int *)(v22 + 448)) > 0)
                {
                    v14 = 0x1;
                    if (sub_10034b10(v20, v22))
                        i = 1;
                    v4 = i;
                    v20 = v3;
                }
                iter += 1;
                v18 = a2;
            }
            v17 = a1;
        }
    }
    v23 = _ccall(v10, v11, (unsigned int)v12, 0);
    *((unsigned int *)(unsigned int)v23) = v6;
    return v14;
}
