// bspValidateBrush @ 0x10037290  size=631
typedef struct struct_1 {
    char padding_0[84];
    struct struct_0 *field_54;
    char padding_58[156];
    unsigned int field_f4;
} struct_1;

class class UModel {
} class UModel;

typedef struct struct_0 {
    char padding_0[40];
    unsigned int field_28;
} struct_0;

typedef struct struct_3 {
    unsigned int field_0;
    unsigned int field_4;
    unsigned int field_8;
    unsigned int field_c;
    unsigned int field_10;
    unsigned int field_14;
    unsigned int field_18;
    unsigned int field_1c;
    unsigned int field_20;
    unsigned int field_24;
    unsigned int field_28;
    unsigned int field_2c;
    char padding_30[384];
    unsigned int field_1b0;
    char padding_1b4[4];
    unsigned int field_1b8;
    char padding_1bc[8];
    int field_1c4;
} struct_3;

typedef struct struct_2 {
    unsigned int field_0;
    unsigned int field_4;
    unsigned int field_8;
    unsigned int field_c;
    unsigned int field_10;
    unsigned int field_14;
    unsigned int field_18;
    unsigned int field_1c;
    unsigned int field_20;
    unsigned int field_24;
    unsigned int field_28;
    unsigned int field_2c;
} struct_2;

extern unsigned int g_10140164;
extern char GNull;

void UEditorEngine::bspValidateBrush(void* this, class UModel *arg_0, int arg_1, int arg_2)
{
    unsigned long v16;  // ldt
    unsigned long v17;  // gdt
    struct_2 *v26;  // edx
    int v27;  // ecx
    int v28;  // esi
    uint128_t v29;  // xmm4
    uint128_t v30;  // xmm3
    uint128_t v31;  // xmm5
    unsigned short v18;  // fs
    uint128_t v32;  // xmm2
    struct_3 *v33;  // ecx
    char v34;  // al
    unsigned int v35;  // 4136
    char v36;  // al
    unsigned int v37;  // 4136
    char v38;  // al
    unsigned int v39;  // 4136
    char v40;  // al
    unsigned int v41;  // 4136
    unsigned long long v19;  // 4147
    unsigned short v42;  // ax
    unsigned int v43;  // 4136
    unsigned int v44;  // 4136
    int v46;  // xmm4
    int v48;  // xmm3
    int v50;  // xmm5
    int v51;  // xmm1
    unsigned long long v20;  // 4167
    unsigned long v52;  // xmm0
    int v54;  // xmm2
    int v55;  // xmm2
    int v57;  // xmm0
    int v58;  // xmm0
    int v59;  // xmm0
    int v61;  // xmm1
    struct_1 *index;  // esi
    int v62;  // xmm1
    int v63;  // xmm1
    unsigned long v64;  // xmm0
    unsigned long long v65;  // 4122
    int v22;  // edx
    struct_0 *idx;  // eax
    unsigned int v24;  // edi
    int i;  // ebx
    unsigned int v0;  // [bp-0x58]
    unsigned int v1;  // [bp-0x50]
    int v2;  // [bp-0x4c]
    unsigned int v3;  // [bp-0x48]
    unsigned int v4;  // [bp-0x38]
    unsigned int v5;  // [bp-0x34]
    unsigned int v6;  // [bp-0x30]
    unsigned int v7;  // [bp-0x24], Other Possible Types: int
    int v8;  // [bp-0x20]
    unsigned int v9;  // [bp-0x1c]
    int v10;  // [bp-0x18]
    char *v11;  // [bp-0x14]
    unsigned int v12;  // [bp-0x10]
    unsigned int v13;  // [bp-0xc]
    unsigned int v14;  // [bp-0x8]
    char v15;  // [bp-0x4]

    v14 = 0xffffffff;
    v13 = sub_100c4d30;
    v19 = _ccall(v16, v17, (unsigned int)v18, 0);
    v12 = *((int *)(unsigned int)v19);
    v3 = g_10140164 ^ &v15;
    v20 = _ccall(v16, v17, (unsigned int)v18, 0);
    *((unsigned int **)(unsigned int)v20) = &v12;
    v11 = &v3;
    v14 = 0;
    index = arg_0;
    UModel::Modify(index, 0);
    if (arg_1 || !index->field_f4)
    {
        index->field_f4 = 1;
        v22 = 0;
        while (1)
        {
            v10 = v22;
            idx = index->field_54;
            if (v22 >= *((int *)&idx[1].padding_0[0]))
                break;
            *((int *)(idx->field_28 + v22 * 472 + 452)) = v22;
            v22 += 1;
        }
        v24 = 0;
        v9 = 0;
        i = 0;
        v7 = 0;
        while (i < *((int *)&idx[1].padding_0[0]))
        {
            v26 = i * 472 + idx->field_28;
            v27 = i + 1;
            arg_1 = v27;
            if (v26[9].field_14 == i)
            {
                v28 = v27;
                while (1)
                {
                    v8 = v28;
                    idx = (int)arg_0[21];
                    if (v28 >= *((int *)&idx[1].padding_0[0]))
                        break;
                    v33 = v28 * 472 + idx->field_28;
                    if (v33->field_1c4 == v28 && v33->field_1b8 == v26[9].field_8)
                    {
                        v34 = (char)v33->field_1b8 | (CmpF(v33->field_18, v26->field_18) & 69 & 213 | 2) * 0;
                        v35 = _ccall(10, 13, (unsigned int)(v34 & 0x44), 0, 0);
                        if (!(v35 & 1))
                        {
                            v36 = v34 | (CmpF(v33->field_1c, v26->field_1c) & 69 & 213 | 2) * 0;
                            v37 = _ccall(10, 13, (unsigned int)(v36 & 0x44), 0, 0);
                            if (!(v37 & 1))
                            {
                                v38 = v36 | (CmpF(v33->field_20, v26->field_20) & 69 & 213 | 2) * 0;
                                v39 = _ccall(10, 13, (unsigned int)(v38 & 0x44), 0, 0);
                                if (!(v39 & 1))
                                {
                                    v40 = v38 | (CmpF(v33->field_24, v26->field_24) & 69 & 213 | 2) * 0;
                                    v41 = _ccall(10, 13, (unsigned int)(v40 & 0x44), 0, 0);
                                    if (!(v41 & 1))
                                    {
                                        v42 = v40 | (CmpF(v33->field_28, v26->field_28) & 69 & 2261 & 213 | 2) * 0x100;
                                        v43 = _ccall(10, 13, (unsigned int)((char)v42 & 0x44), 0, 0);
                                        if (!(v43 & 1))
                                        {
                                            v44 = _ccall(10, 13, (unsigned int)(*((char *)((void*)&(unsigned int)v42 & 0xffff00ff | (CmpF((unsigned long long)v33->field_2c, (unsigned long long)v26->field_2c) & 69 & 2261 & 213 | 2) * 0x100 + 1)) & 0x44), 0, 0);
                                            if (!(v44 & 1) && v33->field_1b0 == v26[9].field_0)
                                            {
                                                v46 = (int)_INSERT(_INSERT(v29, 8, 0), 4, 0);
                                                v29 = _INSERT(v46, 0, v26->field_10);
                                                v48 = (int)_INSERT(_INSERT(v30, 8, 0), 4, 0);
                                                v30 = _INSERT(v48, 0, v26->field_c);
                                                v50 = (int)_INSERT(_INSERT(v31, 8, 0), 4, 0);
                                                v31 = _INSERT(v50, 0, v26->field_14);
                                                v51 = (int)(AddV(AddV(MulV(v29, v33->field_10), MulV(v30, v33->field_c)), MulV(v31, v33->field_14)));
                                                v52 = *((unsigned int *)&v51);
                                                if (((CmpF(v52, 0x3fefff2e48e8a71e) & 69 | (char)((CmpF(v52, 0x3fefff2e48e8a71e) & 69) >> 6)) & 1) != 1)
                                                {
                                                    v54 = (int)_INSERT(_INSERT(v32, 8, 0), 4, 0);
                                                    v55 = (int)_INSERT(v54, 0, v33->field_0);
                                                    v32 = (uint128_t)(SubV(v55, v26->field_0));
                                                    v57 = (int)_INSERT(_INSERT(v52 CONCAT 0, 8, 0), 4, 0);
                                                    v58 = (int)_INSERT(v57, 0, v33->field_4);
                                                    v59 = SubV(v58, v26->field_4);
                                                    v61 = (int)_INSERT(_INSERT(v51, 8, 0), 4, 0);
                                                    v62 = (int)_INSERT(v61, 0, v33->field_8);
                                                    v63 = SubV(v62, v26->field_8);
                                                    v4 = v32;
                                                    v5 = *((unsigned int *)&v59);
                                                    v6 = *((unsigned int *)&v63);
                                                    v29 = (uint128_t)(MulV(v29, v59));
                                                    v31 = (uint128_t)(MulV(v31, v63));
                                                    v30 = AddV(AddV(MulV(v30, v32), v29), v31);
                                                    v64 = v30;
                                                    if (((CmpF(v64, 13785626545772145148) & 69 | (char)((CmpF(v64, 13785626545772145148) & 69) >> 6)) & 1) != 1 && ((CmpF(4562254508917369340, v64) & 69 | (char)((CmpF(4562254508917369340, v64) & 69) >> 6)) & 1) != 1)
                                                    {
                                                        v33->field_1c4 = i;
                                                        v24 += 1;
                                                        v9 = v24;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    v28 += 1;
                }
                v7 = arg_1;
            }
            else
            {
                v7 = v27;
            }
        }
        v2 = *((int *)&idx[1].padding_0[0]);
        v1 = v24;
        v0 = 760;
        FOutputDevice::Logf(*((int *)&GNull), L"BspValidateBrush linked %i of %i polys");
        index = arg_0;
    }
    UModel::BuildBound(index);
    v65 = _ccall(v16, v17, (unsigned int)v18, 0);
    *((unsigned int *)(unsigned int)v65) = v12;
    return;
}
