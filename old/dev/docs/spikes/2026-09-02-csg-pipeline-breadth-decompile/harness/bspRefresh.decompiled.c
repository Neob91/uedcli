// bspRefresh @ 0x10036cd0  size=1218
typedef struct struct_0 {
    char padding_0[88];
    unsigned int field_58;
    char padding_5c[12];
    unsigned int field_68;
    char padding_6c[12];
    unsigned int field_78;
    int field_7c;
    char padding_80[8];
    unsigned int field_88;
    int field_8c;
    char padding_90[8];
    unsigned int field_98;
    int field_9c;
} struct_0;

class class UModel {
} class UModel;

typedef struct struct_1 {
    char padding_0[24];
    unsigned int field_18;
    char padding_1c[26];
    char field_36;
} struct_1;

extern unsigned int g_10140164;
extern char GMem;
extern char FPlane::PlaneDot;
extern char GLog;

void UEditorEngine::bspRefresh(void* this, class UModel *arg_0, int arg_1)
{
    unsigned long v24;  // ldt
    unsigned long v25;  // gdt
    int v34;  // ecx
    int idx;  // esi
    struct_0 *v36;  // edx
    int v37;  // ecx
    int idx1;  // esi
    struct_0 *v39;  // edx
    uint128_t *idx2;  // edx
    uint128_t *v41;  // ecx
    struct_0 *v42;  // esi
    int v43;  // edx
    unsigned short v26;  // fs
    unsigned int *v44;  // ecx
    int v45;  // edx
    unsigned int *v46;  // ecx
    unsigned int v47;  // edi
    int v48;  // eax
    struct_1 *v49;  // esi
    unsigned int *v50;  // edx
    char v51;  // cl
    int v52;  // ecx
    int node;  // eax
    unsigned long long v27;  // 4160
    unsigned int v54;  // esi
    unsigned int v55;  // esi
    unsigned int v56;  // edx
    unsigned int v57;  // ecx
    int v58;  // ecx
    int v59;  // esi
    int v60;  // ecx
    int iter;  // eax
    struct_0 *v62;  // esi
    unsigned int v63;  // esi
    unsigned long long v28;  // 4180
    unsigned int v64;  // edx
    unsigned int v65;  // ecx
    int v66;  // edx
    unsigned int *index;  // ecx
    unsigned int v68;  // edi
    int v69;  // eax
    struct_1 *v70;  // esi
    unsigned int *iter1;  // ecx
    char v72;  // dl
    unsigned long long v73;  // 4122
    struct_0 *v29;  // edi
    int v30;  // edi
    int v31;  // esi
    int v32;  // ebx
    int v33;  // ecx
    unsigned int v0;  // [bp-0x84]
    int v1;  // [bp-0x7c], Other Possible Types: unsigned int
    int v2;  // [bp-0x78]
    int v3;  // [bp-0x74], Other Possible Types: unsigned int
    int v4;  // [bp-0x70]
    int v5;  // [bp-0x6c], Other Possible Types: unsigned int
    int v6;  // [bp-0x68]
    int v7;  // [bp-0x64]
    int v8;  // [bp-0x60]
    unsigned int v9;  // [bp-0x58]
    unsigned int v10;  // [bp-0x48]
    unsigned int *v11;  // [bp-0x34]
    unsigned int *v12;  // [bp-0x30]
    struct_0 *v13;  // [bp-0x2c]
    int v14;  // [bp-0x28], Other Possible Types: unsigned int
    int v15;  // [bp-0x24]
    int v16;  // [bp-0x20]
    unsigned int i;  // [bp-0x1c], Other Possible Types: int
    char v18;  // [bp-0x15]
    char *v19;  // [bp-0x14]
    unsigned int v20;  // [bp-0x10]
    unsigned int v21;  // [bp-0xc]
    unsigned int v22;  // [bp-0x8]
    char v23;  // [bp-0x4]

    v22 = 0xffffffff;
    v21 = sub_100c4cf0;
    v27 = _ccall(v24, v25, (unsigned int)v26, 0);
    v20 = *((int *)(unsigned int)v27);
    v9 = g_10140164 ^ &v23;
    v28 = _ccall(v24, v25, (unsigned int)v26, 0);
    *((unsigned int **)(unsigned int)v28) = &v20;
    v19 = &v9;
    v29 = arg_0;
    v22 = 0;
    v10 = &GMem;
    v14 = sub_10031410(4, &GMem, 1, *((int *)&v29->padding_5c[0]), 16, g_10140164 ^ &v23, v30, v31, v32, &GMem, *((int *)&GMem), *((int *)&FPlane::PlaneDot));
    v33 = sub_10031410(4, &GMem, 1, v29->field_9c, 16);
    v15 = v33;
    if (*((int *)&v29->padding_5c[0]) > 0)
    {
        sub_10034aa0(v29, v14, v33, 0);
        v33 = v15;
    }
    if (arg_1)
        sub_100ae140(v33, 0, v29->field_9c * 4);
    v34 = 0;
    v16 = 0;
    idx = 0;
    v36 = &v29->field_98;
    v13 = v36;
    while (1)
    {
        i = idx;
        if (idx >= v29->field_9c)
            break;
        if (*((int *)(v15 + idx * 4)) != 0xffffffff)
        {
            sub_10031480(idx * 64 + *((int *)&v36->padding_0[0]));
            *((int *)(v15 + idx * 4)) = v16;
            v34 = v16 + 1;
            v16 = v34;
            v36 = &v29->field_98;
        }
        idx += 1;
    }
    v8 = v34;
    v7 = v29->field_9c;
    v5 = 760;
    FOutputDevice::Logf(*((int *)&GLog), L"Polys: %i -> %i");
    sub_100340f0(v16, v29->field_9c - v16);
    v37 = 0;
    v16 = 0;
    idx1 = 0;
    v39 = &v29->field_58;
    while (1)
    {
        i = idx1;
        if (idx1 >= *((int *)&v29->padding_5c[0]))
            break;
        if (*((int *)(v14 + idx1 * 4)) != 0xffffffff)
        {
            idx2 = idx1 * 64 + *((int *)&v39->padding_0[0]);
            v41 = v37 * 64 + *((int *)&v39->padding_0[0]);
            *(v41) = *(idx2);
            v41[1] = idx2[1];
            v41[2] = idx2[2];
            v41[3] = idx2[3];
            *((int *)(v14 + idx1 * 4)) = v16;
            v37 = v16 + 1;
            v16 = v37;
            v39 = &v29->field_58;
        }
        idx1 += 1;
    }
    v6 = v37;
    v5 = *((int *)&v29->padding_5c[0]);
    v3 = 760;
    FOutputDevice::Logf(*((int *)&GLog), L"Nodes: %i -> %i");
    v42 = &v29->field_58;
    sub_10034050(v16, *((int *)&v29->padding_5c[0]) - v16);
    v43 = 0;
    while (1)
    {
        i = v43;
        if (v43 >= *((int *)&v29->padding_5c[0]))
            break;
        v44 = v43 * 64 + *((int *)&v42->padding_0[0]);
        v44[7] = *((int *)(v15 + v44[7] * 4));
        if (v44[9] != 0xffffffff)
            v44[9] = *((int *)(v14 + v44[9] * 4));
        if (v44[8] != 0xffffffff)
            v44[8] = *((int *)(v14 + v44[8] * 4));
        if (v44[10] != 0xffffffff)
            v44[10] = *((int *)(v14 + v44[10] * 4));
        v43 += 1;
        v42 = &v29->field_58;
    }
    v14 = sub_10031410(4, &GMem, 1, v29->field_7c, 16);
    arg_1 = sub_10031410(4, &GMem, 1, v29->field_8c, 16);
    v45 = 0;
    while (1)
    {
        i = v45;
        if (v45 >= v29->field_9c)
            break;
        v46 = v45 * 64 + *((int *)&v13->padding_0[0]);
        v47 = v14;
        *((unsigned int *)(v47 + v46[3] * 4)) = 0;
        *((unsigned int *)(v47 + v46[4] * 4)) = 0;
        *((unsigned int *)(v47 + v46[5] * 4)) = 0;
        *((unsigned int *)(arg_1 + v46[2] * 4)) = 0;
        v29 = arg_0;
        v45 += 1;
    }
    v48 = 0;
    while (1)
    {
        i = v48;
        if (v48 >= *((int *)&v29->padding_5c[0]))
            break;
        v49 = v48 * 64 + v29->field_58;
        v50 = v29->field_68 + v49->field_18 * 8;
        v51 = 0;
        while (1)
        {
            v12 = v50;
            v18 = v51;
            if (v51 >= v49->field_36)
                break;
            *((unsigned int *)(arg_1 + *(v50) * 4)) = 0;
            v50 += 2;
            v29 = arg_0;
            v51 += 1;
        }
        v48 = i + 1;
    }
    v52 = 0;
    v16 = 0;
    node = 0;
    i = 0;
    for (v54 = arg_1; node < v29->field_8c; i = node + 1)
    {
        if (*((int *)(v54 + node * 4)) != 0xffffffff)
        {
            v55 = v29->field_88;
            v56 = node * 3;
            v57 = v52 * 3;
            *((int *)(v55 + v57 * 4)) = *((int *)(v55 + v56 * 4));
            *((int *)(v55 + v57 * 4 + 4)) = *((int *)(v55 + v56 * 4 + 4));
            *((int *)(v55 + v57 * 4 + 8)) = *((int *)(v55 + v56 * 4 + 8));
            v54 = arg_1;
            node = i;
            v58 = v16;
            *((int *)(v54 + node * 4)) = v58;
            v52 = v58 + 1;
            v16 = v52;
        }
    }
    v4 = v52;
    v3 = v29->field_8c;
    v1 = 760;
    FOutputDevice::Logf(*((int *)&GLog), L"Points: %i -> %i");
    v59 = v16;
    sub_10034310(v59, v29->field_8c - v59);
    if (v29->field_8c != v59)
        appFailAssert("Model->Points.Num()==n", "C:\\GameDev\\UnrealTournament\\Editor\\Src\\UnBsp.cpp", 2751);
    v60 = 0;
    v16 = 0;
    iter = 0;
    v62 = &v29->field_78;
    while (1)
    {
        i = iter;
        if (iter >= v29->field_7c)
            break;
        if (*((int *)(v14 + iter * 4)) != 0xffffffff)
        {
            v63 = *((int *)&v62->padding_0[0]);
            v64 = iter * 3;
            v65 = v60 * 3;
            *((int *)(v63 + v65 * 4)) = *((int *)(v63 + v64 * 4));
            *((int *)(v63 + v65 * 4 + 4)) = *((int *)(v63 + v64 * 4 + 4));
            *((int *)(v63 + v65 * 4 + 8)) = *((int *)(v63 + v64 * 4 + 8));
            iter = i;
            *((int *)(v14 + iter * 4)) = v16;
            v60 = v16 + 1;
            v16 = v60;
            v62 = &v29->field_78;
        }
        iter += 1;
    }
    v2 = v60;
    v1 = v29->field_7c;
    v0 = 760;
    FOutputDevice::Logf(*((int *)&GLog), L"Vectors: %i -> %i");
    sub_10034310(v16, v29->field_7c - v16);
    v66 = 0;
    for (i = 0; v66 < v29->field_9c; i = v66 + 1)
    {
        index = v66 * 64 + *((int *)&v13->padding_0[0]);
        v68 = v14;
        index[3] = *((int *)(v68 + index[3] * 4));
        index[4] = *((int *)(v68 + index[4] * 4));
        index[5] = *((int *)(v68 + index[5] * 4));
        index[2] = *((int *)(arg_1 + index[2] * 4));
        v29 = arg_0;
    }
    v69 = 0;
    while (1)
    {
        i = v69;
        if (v69 >= *((int *)&v29->padding_5c[0]))
            break;
        v70 = v69 * 64 + v29->field_58;
        iter1 = v29->field_68 + v70->field_18 * 8;
        v72 = 0;
        while (1)
        {
            v11 = iter1;
            v18 = v72;
            if (v72 >= v70->field_36)
                break;
            *(iter1) = *((int *)(arg_1 + *(iter1) * 4));
            iter1 += 2;
            v29 = arg_0;
            v72 += 1;
        }
        v69 = i + 1;
    }
    UModel::ShrinkModel(v29);
    FMemMark::Pop(&v10);
    v73 = _ccall(v24, v25, (unsigned int)v26, 0);
    *((unsigned int *)(unsigned int)v73) = v20;
    return;
}
