// csgRebuild @ 0x1004a650  size=1212
typedef struct struct_20 {
    struct struct_17 *field_0;
    char padding_4[264];
    unsigned int field_10c;
} struct_20;

typedef struct struct_1 {
    unsigned int field_0;
} struct_1;

class class ABrush {
} class ABrush;

class class ULevel {
} class ULevel;

typedef struct struct_3 {
    char padding_0[44];
    unsigned int field_2c;
} struct_3;

typedef struct struct_17 {
    char padding_0[520];
    struct struct_1 *field_208;
    char padding_20c[12];
    struct struct_1 *field_218;
} struct_17;

typedef struct struct_24 {
    char padding_0[524];
    char field_20c;
    char padding_20d[83];
    unsigned int field_260;
} struct_24;

typedef struct struct_8 {
    char padding_0[492];
    struct struct_1 *field_1ec;
    char padding_1f0[116];
    struct struct_1 *field_264;
} struct_8;

typedef struct struct_11 {
    char field_0[4];
    int field_4;
} struct_11;

extern unsigned int g_10140164;
extern char GWarn;

void UEditorEngine::csgRebuild(void* idx, class ULevel *arg_0, int arg_1)
{
    unsigned long v20;  // ldt
    unsigned long v21;  // gdt
    int i;  // esi
    int v31;  // ecx
    class ABrush *v32;  // eax
    struct_3 *idx1;  // ebx
    int v34;  // edx
    int k;  // esi
    int v36;  // ecx
    class ABrush *v37;  // eax
    unsigned int v38;  // esi
    struct_24 *index;  // ecx
    unsigned short v22;  // fs
    unsigned int v40;  // eax
    struct_24 *v41;  // ecx
    struct_8 **v42;  // esi
    struct_3 *n;  // ebx
    int v44;  // edx
    int m;  // esi
    int v46;  // ecx
    class ABrush *v47;  // eax
    struct_24 *v48;  // ecx
    struct_11 *i0;  // ebx
    unsigned long long v23;  // 4155
    int v50;  // esi
    int v51;  // eax
    int v52;  // ecx
    struct_11 *i1;  // edx
    int v54;  // esi
    int v55;  // eax
    int v56;  // ecx
    struct_20 *idx2;  // ebx
    unsigned long long v58;  // 4122
    unsigned long long v24;  // 4175
    unsigned int v25;  // edi
    unsigned int v26;  // esi
    unsigned int v27;  // ebx
    struct_3 *j;  // ebx
    int v29;  // edx
    unsigned int v0;  // [bp-0x78]
    char v1;  // [bp-0x68]
    char v2;  // [bp-0x5c]
    struct_11 *v3;  // [bp-0x50]
    int v4;  // [bp-0x4c], Other Possible Types: unsigned int
    struct_11 *v5;  // [bp-0x48]
    int v6;  // [bp-0x44], Other Possible Types: unsigned int
    struct_3 *v7;  // [bp-0x40]
    int v8;  // [bp-0x3c], Other Possible Types: unsigned int
    struct_3 *v9;  // [bp-0x38]
    int v10;  // [bp-0x34], Other Possible Types: unsigned int
    struct_3 *v11;  // [bp-0x30]
    int v12;  // [bp-0x2c], Other Possible Types: unsigned int
    unsigned int v13;  // [bp-0x20]
    unsigned int iter;  // [bp-0x18]
    char *v15;  // [bp-0x14]
    unsigned int v16;  // [bp-0x10]
    unsigned int v17;  // [bp-0xc]
    unsigned int v18;  // [bp-0x8], Other Possible Types: char
    char v19;  // [bp-0x4]

    v18 = 0xffffffff;
    v17 = sub_100c5d85;
    v23 = _ccall(v20, v21, (unsigned int)v22, 0);
    v16 = *((int *)(unsigned int)v23);
    v0 = g_10140164 ^ &v19;
    v24 = _ccall(v20, v21, (unsigned int)v22, 0);
    *((unsigned int **)(unsigned int)v24) = &v16;
    v15 = &v0;
    v18 = 0;
    (*((int *)(*((int *)*((int *)&GWarn)) + 8)))(L"Rebuilding geometry", 1, 0, g_10140164 ^ &v19, v25, v26, v27);
    *((unsigned int *)&idx[268]) = (int)idx[268] | 1;
    (*((int *)(*((int *)idx) + 180)))(arg_0);
    UModel::EmptyModel((int)arg_0[38], 1, 1);
    v13 = 0;
    iter = 0;
    v11 = arg_0;
    v12 = 0xffffffff;
    v29 = 0;
    arg_0 = 0;
    i = 0;
    v12 = 0;
    if ((int)arg_0[12] > NULL)
    {
        v31 = 0;
        do
        {
            if (!*((int *)((int)arg_0[11] + v31 * 4)))
                continue;
            if (AActor::IsStaticBrush(*((int *)((int)arg_0[11] + v31 * 4))))
                goto LABEL_0x1004a720;
            v29 = arg_0;
            v29 += 1;
            arg_0 = v29;
            i = v29;
            v31 = i;
            v12 = i;
        } while (i < (int)arg_0[12]);
    }
    j = NULL;
    for (v11 = NULL; j; j = v11)
    {
        if (!arg_1 || !(*((char *)(*((int *)(j->field_2c + i * 4)) + 284)) & 1))
        {
            v32 = ULevel::Brush(arg_0);
            if (*((int *)(j->field_2c + i * 4)) != v32)
                v13 += 1;
        }
        sub_10049210();
        i = v12;
    }
    v9 = arg_0;
    v10 = 0xffffffff;
    v34 = 0;
    arg_0 = 0;
    k = 0;
    v10 = 0;
    if ((int)arg_0[12] > NULL)
    {
        v36 = 0;
        do
        {
            if (!*((int *)((int)arg_0[11] + v36 * 4)))
                continue;
            if (AActor::IsStaticBrush(*((int *)((int)arg_0[11] + v36 * 4))))
                goto LABEL_0x1004a7b0;
            v34 = arg_0;
            v34 += 1;
            arg_0 = v34;
            k = v34;
            v36 = k;
            v10 = k;
        } while (k < (int)arg_0[12]);
    }
    idx1 = NULL;
    for (v9 = NULL; idx1; idx1 = v9)
    {
        if (!arg_1 || !(*((char *)(*((int *)(idx1->field_2c + k * 4)) + 284)) & 1))
        {
            arg_0 = k * 4;
            v37 = ULevel::Brush(arg_0);
            if (*((int *)(arg_0 + idx1->field_2c)) != v37)
            {
                v38 = arg_0;
                index = *((int *)(v38 + idx1->field_2c));
                v40 = index->field_260;
                if (!((char)v40 & 32) || index->field_20c != 1 || v40 & 0x4000000)
                {
                    if (v40 & 0x4000000)
                        index->field_260 = v40 & 0xffffffdf | 8;
                    iter += 1;
                    (*((int *)(*((int *)*((int *)&GWarn)) + 16)))(*((int *)&GWarn), iter, v13, L"Applying structural brush %i of %i", iter, v13);
                    v41 = *((int *)(v38 + idx1->field_2c));
                    (*((int *)(*((int *)idx) + 532)))(v41, (int)arg_0[38], v41->field_260, v41->field_20c, 0, 1);
                }
            }
        }
        sub_10049210();
        k = v10;
    }
    v42 = idx;
    *(v42)->field_1ec((int)arg_0[38], 0, 0);
    *(v42)->field_264(arg_0, (int)arg_0[38], 0, 0);
    sub_10011be0(arg_0, (int)arg_0[38], 0, 0);
    v18 = 1;
    sub_10011be0();
    v18 = 2;
    if (*((int *)((int)arg_0[38] + 92)))
        sub_10049380((int)arg_0[38], &v1, &v2, 0);
    v7 = arg_0;
    v8 = 0xffffffff;
    v44 = 0;
    arg_0 = 0;
    m = 0;
    v8 = 0;
    if ((int)arg_0[12] > NULL)
    {
        v46 = 0;
        do
        {
            if (!*((int *)((int)arg_0[11] + v46 * 4)))
                continue;
            if (AActor::IsStaticBrush(*((int *)((int)arg_0[11] + v46 * 4))))
                goto LABEL_0x1004a940;
            v44 = arg_0;
            v44 += 1;
            arg_0 = v44;
            m = v44;
            v46 = m;
            v8 = m;
        } while (m < (int)arg_0[12]);
    }
    n = NULL;
    for (v7 = NULL; n; n = v7)
    {
        if (!arg_1 || !(*((char *)(*((int *)(n->field_2c + m * 4)) + 284)) & 1))
        {
            arg_0 = m * 4;
            v47 = ULevel::Brush(arg_0);
            if (*((int *)(arg_0 + n->field_2c)) != v47 && (*((int *)(*((int *)(arg_0 + n->field_2c)) + 608)) & 67108896) == 32 && *((char *)(*((int *)(arg_0 + n->field_2c)) + 524)) == 1)
            {
                iter += 1;
                (*((int *)(*((int *)*((int *)&GWarn)) + 16)))(*((int *)&GWarn), iter, v13, L"Applying detail brush %i of %i", iter, v13);
                v48 = *((int *)(arg_0 + n->field_2c));
                (*((int *)(*((int *)idx) + 532)))(v48, (int)arg_0[38], v48->field_260, v48->field_20c, 0, 1);
            }
        }
        sub_10049210();
        m = v8;
    }
    i0 = &v1;
    v5 = &v1;
    v6 = 0xffffffff;
    v50 = 0;
    v6 = 0;
    v51 = 0;
    for (v52 = 0; v51 < i0->field_4; i0 = v5)
    {
        if (*((int *)(*((int *)&i0->field_0[4 * v52]) * 64 + *((int *)((int)arg_0[38] + 88)) + 36)) != 0xffffffff)
            (*((int *)(*((int *)idx) + 492)))((int)arg_0[38], *((int *)(*((int *)&i0->field_0[4 * v52]) * 64 + *((int *)((int)arg_0[38] + 88)) + 36)), 2);
        v50 += 1;
        v52 = v50;
        v51 = v50;
        v6 = v50;
    }
    i1 = &v2;
    v3 = &v2;
    v4 = 0xffffffff;
    v54 = 0;
    v4 = 0;
    v55 = 0;
    for (v56 = 0; v55 < i1->field_4; i1 = v3)
    {
        if (*((int *)(*((int *)((int)arg_0[38] + 88)) + *((int *)&i1->field_0[4 * v56]) * 64 + 32)) != 0xffffffff)
            (*((int *)(*((int *)idx) + 492)))((int)arg_0[38], *((int *)(*((int *)((int)arg_0[38] + 88)) + *((int *)&i1->field_0[4 * v56]) * 64 + 32)), 2);
        v54 += 1;
        v56 = v54;
        v55 = v54;
        v4 = v54;
    }
    idx2 = idx;
    idx2->field_0->field_218((int)arg_0[38]);
    idx2->field_0->field_208((int)arg_0[38]);
    idx2->field_10c = idx2->field_10c & 0xfffffffe;
    (*((int *)(*((int *)*((int *)&GWarn)) + 12)))((int)arg_0[38]);
    v18 = 1;
    sub_10006960();
    v18 = 0;
    sub_10006960();
    v58 = _ccall(v20, v21, (unsigned int)v22, 0);
    *((unsigned int *)(unsigned int)v58) = v16;
    return;
}
