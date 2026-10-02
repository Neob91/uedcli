// bspMergeCoplanars @ 0x10036200  size=887
class class UModel {
} class UModel;

typedef struct struct_3 {
    unsigned int field_0;
    unsigned int field_4;
    unsigned int field_8;
    unsigned int field_c;
    unsigned int field_10;
    unsigned int field_14;
    char padding_18[408];
    unsigned int field_1b0;
} struct_3;

typedef struct struct_0 {
    char padding_0[40];
    unsigned int field_28;
} struct_0;

typedef struct struct_2 {
    unsigned int field_0;
    unsigned int field_4;
    unsigned int field_8;
    unsigned int field_c;
    unsigned int field_10;
    unsigned int field_14;
    char padding_18[408];
    unsigned int field_1b0;
    char padding_1b4[12];
    int field_1c0;
    unsigned int field_1c4;
} struct_2;

typedef struct struct_1 {
    char padding_0[84];
    struct struct_0 *field_54;
} struct_1;

extern unsigned int g_10140164;
extern char GMem;
extern char FPlane::PlaneDot;
extern char GLog;

void UEditorEngine::bspMergeCoplanars(void* this, class UModel *arg_0, int arg_1, int arg_2)
{
    unsigned long v30;  // ldt
    unsigned long v31;  // gdt
    struct_0 *idx;  // edi
    int *v41;  // edi
    unsigned int v42;  // ebx
    int v43;  // ecx
    struct_2 *index;  // ebx
    int v45;  // eax
    int iter;  // edi
    uint128_t v47;  // xmm3
    unsigned short v32;  // fs
    uint128_t v48;  // xmm2
    uint128_t v49;  // xmm4
    uint128_t v50;  // xmm5
    uint128_t v51;  // xmm6
    unsigned long long v52;  // xmm0
    struct_0 *v53;  // ecx
    unsigned long long v33;  // 4148
    struct_3 *idx1;  // esi
    int v56;  // xmm3
    int v57;  // xmm3
    int v59;  // xmm0
    int v60;  // xmm0
    int v61;  // xmm0
    int v63;  // xmm2
    unsigned int v34;  // ebx
    int v64;  // xmm2
    int v66;  // xmm4
    int v68;  // xmm5
    int v70;  // xmm6
    unsigned int v71;  // ecx
    int idx2;  // eax
    int v73;  // ebx
    unsigned int v35;  // esi
    int v74;  // edi
    unsigned int v75;  // ecx
    int v76;  // ecx
    unsigned int v77;  // edx
    unsigned long long v78;  // 4122
    unsigned int v36;  // edi
    unsigned long long v37;  // 4168
    struct_1 *v38;  // esi
    int v39;  // edx
    unsigned int v0;  // [bp-0x84]
    int v1;  // [bp-0x7c], Other Possible Types: unsigned int
    int v2;  // [bp-0x78]
    unsigned int v3;  // [bp-0x74]
    struct_0 *v4;  // [bp-0x70], Other Possible Types: int, unsigned int
    unsigned int v5;  // [bp-0x6c]
    unsigned int v6;  // [bp-0x68]
    unsigned int v7;  // [bp-0x64]
    unsigned int v8;  // [bp-0x60]
    unsigned int v9;  // [bp-0x5c]
    unsigned int v10;  // [bp-0x58]
    unsigned int v11;  // [bp-0x54]
    unsigned int v12;  // [bp-0x50]
    unsigned int v13;  // [bp-0x4c]
    unsigned int v14;  // [bp-0x48]
    int v15;  // [bp-0x3c]
    int i;  // [bp-0x38], Other Possible Types: unsigned int
    int v17;  // [bp-0x34]
    int v18;  // [bp-0x30], Other Possible Types: unsigned int
    int v19;  // [bp-0x2c]
    int v20;  // [bp-0x28]
    int v21;  // [bp-0x24]
    int *v22;  // [bp-0x20]
    unsigned int v23;  // [bp-0x1c]
    int v24;  // [bp-0x18], Other Possible Types: unsigned int
    char *v25;  // [bp-0x14]
    unsigned int v26;  // [bp-0x10]
    unsigned int v27;  // [bp-0xc]
    unsigned int v28;  // [bp-0x8]
    char v29;  // [bp-0x4]

    v28 = 0xffffffff;
    v27 = sub_100c4c80;
    v33 = _ccall(v30, v31, (unsigned int)v32, 0);
    v26 = *((int *)(unsigned int)v33);
    v8 = v34;
    v7 = v35;
    v6 = v36;
    v5 = g_10140164 ^ &v29;
    v37 = _ccall(v30, v31, (unsigned int)v32, 0);
    *((unsigned int **)(unsigned int)v37) = &v26;
    v25 = &v5;
    v28 = 0;
    v38 = arg_0;
    v15 = *((int *)&v38->field_54[1].padding_0[0]);
    v39 = 0;
    while (1)
    {
        v20 = v39;
        idx = v38->field_54;
        if (v39 >= *((int *)&idx[1].padding_0[0]))
            break;
        *((unsigned int *)(idx->field_28 + v39 * 472 + 432)) = *((int *)(idx->field_28 + v39 * 472 + 432)) & 0xbfffffff;
        v39 += 1;
    }
    v12 = &GMem;
    v13 = *((int *)&GMem);
    v14 = *((int *)&FPlane::PlaneDot);
    v41 = FMemStack::PushBytes(&GMem, *((int *)&idx[1].padding_0[0]) * 4, 16);
    v22 = v41;
    v42 = 0;
    v23 = 0;
    v43 = 0;
    while (1)
    {
        v21 = v43;
        if (v43 >= *((int *)&v38->field_54[1].padding_0[0]))
            break;
        index = v43 * 472 + v38->field_54->field_28;
        if (index->field_1c0 > 0 && !(index->field_1b0 & 0x40000000))
        {
            v24 = 0;
            *(v41) = v43;
            v45 = 1;
            v24 = 1;
            index->field_1b0 = index->field_1b0 | 0x40000000;
            iter = v43 + 1;
            v19 = iter;
            while (1)
            {
                v53 = v38->field_54;
                if (iter >= *((int *)&v53[1].padding_0[0]))
                    break;
                idx1 = iter * 472 + v53->field_28;
                if (idx1[1].field_10 == index->field_1c4)
                {
                    v56 = (int)_INSERT(_INSERT(v47, 8, 0), 4, 0);
                    v57 = (int)_INSERT(v56, 0, idx1->field_0);
                    v47 = (uint128_t)(SubV(v57, index->field_0));
                    v59 = (int)_INSERT(_INSERT(v52 CONCAT 0, 8, 0), 4, 0);
                    v60 = (int)_INSERT(v59, 0, idx1->field_4);
                    v61 = SubV(v60, index->field_4);
                    v63 = (int)_INSERT(_INSERT(v48, 8, 0), 4, 0);
                    v64 = (int)_INSERT(v63, 0, idx1->field_8);
                    v48 = (uint128_t)(SubV(v64, index->field_8));
                    v9 = v47;
                    v10 = *((unsigned int *)&v61);
                    v11 = v48;
                    v66 = (int)_INSERT(_INSERT(v49, 8, 0), 4, 0);
                    v49 = _INSERT(v66, 0, index->field_10);
                    v68 = (int)_INSERT(_INSERT(v50, 8, 0), 4, 0);
                    v50 = _INSERT(v68, 0, index->field_c);
                    v70 = (int)_INSERT(_INSERT(v51, 8, 0), 4, 0);
                    v51 = _INSERT(v70, 0, index->field_14);
                    v52 = *((unsigned int *)&AddV(AddV(MulV(v49, v61), MulV(v50, v47)), MulV(v51, v48)));
                    if (((CmpF(v52, 13785626545772145148) & 69 | (char)((CmpF(v52, 13785626545772145148) & 69) >> 6)) & 1) != 1 && ((CmpF(4562254508917369340, v52) & 69 | (char)((CmpF(4562254508917369340, v52) & 69) >> 6)) & 1) != 1 && !(v50 = MulV(v50, (uint128_t)idx1->field_c), v51 = MulV(v51, (uint128_t)idx1->field_14), v49 = AddV(AddV(MulV(v49, (uint128_t)idx1->field_10), v50), v51), v52 = (unsigned long long)(unsigned int)v49, (((char)(CmpF(v52, 0x3fefff2e48e8a71e)) & 69 | (char)((CmpF(v52, 0x3fefff2e48e8a71e) & 69) >> 6)) & 1) == 1 || !arg_2 && !(v4 = v53, sub_10032b30(idx1 + 24, index + 24, 970045207) && !(v4 = v71, !sub_10032b30(idx1 + 36, index + 36, 970045207)))))
                    {
                        idx1->field_1b0 = idx1->field_1b0 | 0x40000000;
                        idx2 = v24;
                        v22[idx2] = iter;
                        v45 = idx2 + 1;
                        v24 = v45;
                        iter += 1;
                        v19 = iter;
                        v38 = arg_0;
                        continue;
                    }
                }
                v45 = v24;
                iter += 1;
                v19 = iter;
                v38 = arg_0;
            }
            v41 = v22;
            if (v45 > 1)
            {
                sub_10033cb0(v38, v41, v45);
                v42 = v23 + 1;
                v23 = v42;
                v43 = v21 + 1;
                continue;
            }
            else
            {
                v43 = v21;
            }
        }
        v42 = v23;
        v43 += 1;
    }
    v4 = *((int *)&v38->field_54[1].padding_0[0]);
    v3 = v42;
    v1 = 760;
    FOutputDevice::Logf(*((int *)&GLog), L"Found %i coplanar sets in %i");
    FMemMark::Pop(&v12);
    v73 = 0;
    v18 = 0;
    arg_0 = FMemStack::PushBytes(&GMem, *((int *)&v38->field_54[1].padding_0[0]) * 4, 16);
    v74 = 0;
    while (1)
    {
        v17 = v74;
        if (v74 >= *((int *)&v38->field_54[1].padding_0[0]))
            break;
        v75 = v74 * 472;
        if (*((int *)(v75 + v38->field_54->field_28 + 448)))
        {
            *((int *)&arg_0[4 * v74]) = v73;
            FPoly::operator=(v73 * 472 + v38->field_54->field_28, v38->field_54->field_28 + v75);
            v73 += 1;
            v18 = v73;
        }
        v74 += 1;
    }
    sub_10034260(v73, *((int *)&v38->field_54[1].padding_0[0]) - v73);
    if (arg_1)
    {
        v76 = 0;
        for (i = 0; v76 < *((int *)&v38->field_54[1].padding_0[0]); i = v76 + 1)
        {
            v77 = v76 * 472;
            if (*((int *)(v38->field_54->field_28 + v77 + 452)) != 0xffffffff)
                *((int *)(v38->field_54->field_28 + v77 + 452)) = *((int *)&arg_0[4 * *((int *)(v38->field_54->field_28 + v77 + 452))]);
        }
    }
    v2 = *((int *)&v38->field_54[1].padding_0[0]);
    v1 = v15;
    v0 = 760;
    FOutputDevice::Logf(*((int *)&GLog), L"BspMergeCoplanars reduced %i->%i");
    FMemMark::Pop(&v12);
    v78 = _ccall(v30, v31, (unsigned int)v32, 0);
    *((unsigned int *)(unsigned int)v78) = v26;
    return;
}
