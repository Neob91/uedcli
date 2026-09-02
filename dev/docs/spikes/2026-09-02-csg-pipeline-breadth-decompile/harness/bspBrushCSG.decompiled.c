// bspBrushCSG @ 0x100355e0  size=2226
typedef struct struct_7 {
    struct struct_0 *field_0;
    char padding_4[168];
    struct struct_6 *field_ac;
    unsigned int field_b0;
} struct_7;

typedef struct struct_35 {
    char padding_0[84];
    struct struct_33 *field_54;
    char padding_58[156];
    unsigned int field_f4;
} struct_35;

typedef struct struct_1 {
    unsigned int field_0;
} struct_1;

class class ABrush {
} class ABrush;

class class FModelCoords {
} class FModelCoords;

class class UModel {
} class UModel;

class enum ECsgOper {
} enum ECsgOper;

typedef struct struct_14 {
    char padding_0[436];
    unsigned int field_1b4;
    char padding_1b8[16];
    int field_1c8;
} struct_14;

typedef struct struct_5 {
    char padding_0[40];
    unsigned int field_28;
    int field_2c;
} struct_5;

typedef struct struct_33 {
    char padding_0[44];
    unsigned int field_2c;
} struct_33;

typedef struct struct_0 {
    char padding_0[508];
    struct struct_1 *field_1fc;
    char padding_200[4];
    struct struct_1 *field_204;
    struct struct_1 *field_208;
    char padding_20c[4];
    struct struct_1 *field_210;
} struct_0;

typedef struct struct_6 {
    char padding_0[84];
    struct struct_5 *field_54;
} struct_6;

extern unsigned int g_101491b4;
extern unsigned int g_101491c8;
extern char GWarn;

int UEditorEngine::bspBrushCSG(void* this, class ABrush *arg_0, class UModel *index, unsigned long arg_2, enum ECsgOper arg_3, int arg_4)
{
    unsigned long v46;  // ldt
    unsigned long v47;  // gdt
    unsigned int v56;  // edx
    int v57;  // esi
    uint128_t v58;  // xmm1
    uint128_t v59;  // xmm2
    uint128_t v60;  // xmm4
    uint128_t v61;  // xmm5
    unsigned short v48;  // fs
    struct_35 *idx;  // edx
    unsigned int v63;  // ecx
    struct_33 *v64;  // eax
    int v66;  // xmm0
    int v67;  // xmm0
    int v68;  // xmm0
    int v70;  // xmm1
    int v71;  // xmm1
    unsigned long long v49;  // 4236
    int v72;  // xmm1
    int v74;  // xmm2
    int v75;  // xmm2
    int v77;  // xmm4
    int v79;  // xmm5
    int v81;  // xmm1
    unsigned int v50;  // ebx
    int v82;  // xmm3
    void* v83;  // eax
    int v84;  // esi
    unsigned int v85;  // ecx
    unsigned int v86;  // eax
    struct_35 *v87;  // esi
    int v88;  // esi
    unsigned int v89;  // eax
    int v90;  // edx
    struct_35 *idx1;  // esi
    unsigned int v51;  // esi
    int iter;  // eax
    unsigned int v93;  // esi
    unsigned int v94;  // edi
    int v95;  // edx
    int node;  // ecx
    int v97;  // edx
    unsigned int v98;  // esi
    unsigned int v99;  // edi
    int v100;  // edi
    struct_14 *idx2;  // esi
    unsigned int v52;  // edi
    unsigned int v102;  // ecx
    unsigned long long v103;  // 4120
    unsigned int v104;  // eax
    unsigned long long v53;  // 4240
    struct_7 *v54;  // edi
    unsigned int v55;  // eax
    unsigned int v0;  // [bp-0x51c]
    unsigned int v1;  // [bp-0x510]
    class UModel *v2;  // [bp-0x50c]
    char *v3;  // [bp-0x508], Other Possible Types: unsigned int
    unsigned int v4;  // [bp-0x4f0]
    unsigned int v5;  // [bp-0x4ec]
    unsigned int v6;  // [bp-0x4e8]
    class FModelCoords v7;  // [bp-0x4e4]
    class FModelCoords v8;  // [bp-0x484]
    char v9;  // [bp-0x424]
    unsigned int v10;  // [bp-0x418]
    unsigned int v11;  // [bp-0x414]
    unsigned int v12;  // [bp-0x410]
    unsigned int v13;  // [bp-0x408]
    unsigned int v14;  // [bp-0x404]
    unsigned int v15;  // [bp-0x400]
    unsigned int v16;  // [bp-0x3f8]
    struct_7 *v17;  // [bp-0x3f4]
    unsigned int v18;  // [bp-0x3f0], Other Possible Types: int
    int v19;  // [bp-0x3ec]
    unsigned int v20;  // [bp-0x3e8]
    unsigned int v21;  // [bp-0x3e4]
    unsigned int v22;  // [bp-0x3e0]
    int v23;  // [bp-0x3d8]
    struct_35 *v24;  // [bp-0x3d0]
    unsigned int v25;  // [bp-0x3cc], Other Possible Types: int
    char v26;  // [bp-0x3c8]
    unsigned int v27;  // [bp-0x3c4]
    unsigned int v28;  // [bp-0x3c0]
    unsigned int v29;  // [bp-0x3bc]
    unsigned int v30;  // [bp-0x3b8]
    unsigned int v31;  // [bp-0x3b4]
    unsigned int v32;  // [bp-0x398]
    unsigned int v33;  // [bp-0x394]
    unsigned int v34;  // [bp-0x390]
    unsigned int v35;  // [bp-0x218]
    int v36;  // [bp-0x204]
    int v37;  // [bp-0x200]
    char v38;  // [bp-0x1f0]
    unsigned int v39;  // [bp-0x40]
    int v40;  // [bp-0x2c]
    unsigned int v41;  // [bp-0x14]
    unsigned int v42;  // [bp-0x10]
    unsigned int v43;  // [bp-0xc]
    unsigned int v44;  // [bp-0x8]
    int v45;  // [bp+0x10]

    v44 = 0xffffffff;
    v43 = sub_100c4bf0;
    v49 = _ccall(v46, v47, (unsigned int)v48, 0);
    v42 = *((int *)(unsigned int)v49);
    v6 = v50;
    v5 = v51;
    v4 = v52;
    v53 = _ccall(v46, v47, (unsigned int)v48, 0);
    *((unsigned int **)(unsigned int)v53) = &v42;
    v41 = &/* unsupported instruction */;
    v54 = this;
    v17 = v54;
    v23 = v45;
    v44 = 0;
    v55 = 0;
    v16 = 0;
    v19 = 0;
    v24 = (int)arg_0[78];
    g_101491b4 = 0;
    if (v24)
    {
        v20 = 40;
        if (v45 != 1)
            v55 = v20;
        v16 = v55;
        UModel::Modify(index, 0);
        if (v23 == 2)
            *((unsigned int *)&index[64]) = 0;
        (*((int *)(*((int *)arg_0) + 28)))();
        UModel::Modify(v24, 0);
        UModel::EmptyModel(v54->field_ac, 1, 1);
        ABrush::BuildCoords(arg_0, &v8, &v7);
        if (/* unsupported instruction */)
        {
            v20 = /* unsupported instruction */;
            /* unsupported instruction */
        }
        else
        {
            v20 = nan;
            /* unsupported instruction */
        }
        v22 = v24->field_54->field_2c;
        if (v24->field_54->field_2c > 200)
        {
            switch (v23)
            {
            case 1:
                v56 = L"Adding brush to world";
                break;
            case 2:
                v56 = L"Subtracting brush from world";
                break;
            case 3:
                v56 = L"Intersecting brush with world";
                break;
            case 4:
                v56 = L"Deintersecting brush with world";
                break;
            default:
                v56 = L"Performing CSG operation";
                break;
            }
            (*((int *)(*((int *)*((int *)&GWarn)) + 8)))(v56, 1, 0);
            UEditorEngine::FixBrushLinks(arg_0);
            (*((int *)(*((int *)*((int *)&GWarn)) + 16)))(*((int *)&GWarn), 0, 0, "%", L"Transforming");
        }
        else
        {
            UEditorEngine::FixBrushLinks(arg_0);
        }
        v57 = 0;
        while (1)
        {
            v25 = v57;
            idx = v24;
            if (v57 >= idx->field_54->field_2c)
                break;
            v63 = v57 * 472;
            v21 = *((int *)&idx->field_54->padding_0[40]);
            if (!*((int *)(*((int *)&idx->field_54->padding_0[40]) + v63 + 440)))
                *((unsigned int *)(v21 + v63 + 440)) = v54->field_b0;
            v64 = idx->field_54;
            v54 = v17;
            if (*((int *)(*((int *)&v64->padding_0[40]) + v63 + 452)) < NULL || (v54 = v17, idx = v24, *((int *)(*((int *)&v64->padding_0[40]) + v63 + 452)) >= v64->field_2c))
                *((unsigned int *)(*((int *)&v64->padding_0[40]) + v63 + 452)) = 0xffffffff;
            FPoly::FPoly(&v26, *((int *)&idx->field_54->padding_0[40]) + v63);
            v37 = v57;
            v35 = (v35 | arg_2) & ~(v16);
            if (v36 == -0x1)
                v36 = v57;
            v3 = v35;
            FPoly::Transform(&v26, &v8, arg_0 + 80, arg_0 + 52, v20);
            v66 = (int)_INSERT(_INSERT(v20 CONCAT 0, 8, 0), 4, 0);
            v67 = (int)_INSERT(v66, 0, v32);
            v68 = SubV(v67, v26);
            v70 = (int)_INSERT(_INSERT(v58, 8, 0), 4, 0);
            v71 = (int)_INSERT(v70, 0, v33);
            v72 = SubV(v71, v27);
            v74 = (int)_INSERT(_INSERT(v59, 8, 0), 4, 0);
            v75 = (int)_INSERT(v74, 0, v34);
            v59 = (uint128_t)(SubV(v75, v28));
            v10 = *((unsigned int *)&v68);
            v11 = *((unsigned int *)&v72);
            v12 = v59;
            v77 = (int)_INSERT(_INSERT(v60, 8, 0), 4, 0);
            v60 = _INSERT(v77, 0, v29);
            v79 = (int)_INSERT(_INSERT(v61, 8, 0), 4, 0);
            v61 = _INSERT(v79, 0, v30);
            v81 = (int)_INSERT(_INSERT(v72, 8, 0), 4, 0);
            v58 = _INSERT(v81, 0, v31);
            v82 = AddV(AddV(MulV(v60, v68), MulV(v61, v72)), MulV(v58, v59));
            if (((CmpF(*((unsigned int *)&v82 & 0x7fffffff7fffffff7fffffff7fffffff), 4547007122018943789) & 69 | (char)((CmpF(*((unsigned int *)&v82 & 0x7fffffff7fffffff7fffffff7fffffff), 4547007122018943789) & 69) >> 6)) & 1) != 1)
            {
                v60 = (uint128_t)(MulV(v60, v82));
                v61 = (uint128_t)(MulV(v61, v82));
                v58 = (uint128_t)(MulV(v58, v82));
                v13 = v60;
                v14 = v61;
                v15 = v58;
                v3 = &v13;
                FVector::operator+=(&v26, &v9);
            }
            v83 = sub_10015710(472, &v54->field_ac->field_54->field_28);
            if (v83)
                FPoly::FPoly(v83, &v26);
            v57 += 1;
        }
        if (v22 > 200)
        {
            (*((int *)(*((int *)*((int *)&GWarn)) + 16)))(*((int *)&GWarn), 0, 0, "%", L"Filtering brush");
            idx = v24;
        }
        if (v23 != 3 && v23 != 4)
        {
            v84 = 0;
            for (v25 = 0; v84 < idx->field_54->field_2c; idx = v24)
            {
                v21 = v84 * 472;
                FPoly::FPoly(&v38, v54->field_ac->field_54->field_28 + v21);
                v39 &= 0x7fffffff;
                if (v40 == v84)
                {
                    v85 = (int)index[39];
                    *((unsigned int *)(v54->field_ac->field_54->field_28 + v21 + 452)) = v85;
                    v40 = v85;
                }
                else
                {
                    v40 = *((int *)(v54->field_ac->field_54->field_28 + v40 * 472 + 452));
                }
                v3 = &v38;
                v2 = index;
                v86 = sub_100348c0;
                if (v23 == 1)
                    v86 = sub_10031770;
                v1 = v86;
                sub_10031f50();
                v25 = v84 + 1;
            }
            v87 = v24;
        }
        else
        {
            UModel::EmptyModel(idx, 1, 1);
            v88 = 0;
            while (1)
            {
                v25 = v88;
                if (v88 >= v54->field_ac->field_54->field_2c)
                    break;
                FPoly::FPoly(&v38, v88 * 472 + v54->field_ac->field_54->field_28);
                g_101491c8 = v24;
                v3 = &v38;
                v2 = index;
                v89 = sub_10032390;
                if (v23 == 3)
                    v89 = sub_100339e0;
                v1 = v89;
                sub_10031f50();
                v88 += 1;
            }
            v87 = v24;
            v19 = v87->field_54->field_2c;
        }
        if ((int)index[23] && !((char)arg_2 & 40))
        {
            if (v22 > 200)
                (*((int *)(*((int *)*((int *)&GWarn)) + 16)))(*((int *)&GWarn), 0, 0, "%", L"Building Bsp");
            v54->field_0->field_1fc(v54->field_ac, 0, 0, 1, 0);
            if (v22 > 200)
                (*((int *)(*((int *)*((int *)&GWarn)) + 16)))(*((int *)&GWarn), 0, 0, "%", L"Filtering world");
            g_101491c8 = v87;
            UModel::BuildBound(v54->field_ac);
            UModel::BuildBound(v54->field_ac);
            sub_10033250(index, v54->field_ac, v23, 0, &v54->field_ac->padding_0[0x44]);
        }
        v90 = v23;
        if (v90 == 3 || v90 == 4)
        {
            if (v22 > 200)
                (*((int *)(*((int *)*((int *)&GWarn)) + 16)))(*((int *)&GWarn), 0, 0, "%", L"Adjusting brush");
            iter = v19;
            while (1)
            {
                iter -= 1;
                v25 = iter;
                idx1 = v24;
                if (iter < NULL)
                    break;
                v93 = *((int *)&idx1->field_54->padding_0[40]);
                v94 = iter * 472;
                v95 = 0;
                v18 = 0;
                while (1)
                {
                    if (v95 >= iter)
                    {
                        *((int *)(v94 + v93 + 452)) = iter;
                        break;
                    }
                    else if (*((int *)(v94 + v93 + 452)) == *((int *)(v95 * 472 + v93 + 452)))
                    {
                        *((int *)(v94 + v93 + 452)) = v95;
                        iter = v25;
                        break;
                    }
                    else
                    {
                        v95 += 1;
                        v18 = v95;
                        iter = v25;
                    }
                }
            }
            node = idx1->field_54->field_2c - 1;
            v25 = node;
            while (1)
            {
                v97 = v19;
                if (node < v97)
                    break;
                v98 = *((int *)&idx1->field_54->padding_0[40]);
                v99 = node * 472;
                v18 = v97;
                while (1)
                {
                    if (v97 >= node)
                    {
                        *((int *)(v99 + v98 + 452)) = node;
                        v25 = node - 1;
                        idx1 = v24;
                        break;
                    }
                    else if (*((int *)(v99 + v98 + 452)) == *((int *)(v97 * 472 + v98 + 452)))
                    {
                        *((int *)(v99 + v98 + 452)) = v97;
                        v25 -= 1;
                        idx1 = v24;
                        break;
                    }
                    else
                    {
                        v97 += 1;
                        v18 = v97;
                        node = v25;
                    }
                }
            }
            idx1->field_f4 = 1;
            v100 = 0;
            for (v25 = 0; v100 < idx1->field_54->field_2c; idx1 = v24)
            {
                idx2 = v100 * 472 + *((int *)&idx1->field_54->padding_0[40]);
                v0 = v102;
                FPoly::Transform(idx2, &v7, arg_0 + 52, arg_0 + 80, v20);
                FPoly::Fix(idx2);
                idx2->field_1b4 = 0;
                idx2->field_1c8 = v100;
                v25 = v100 + 1;
            }
            v54 = v17;
            v90 = v23;
        }
        else
        {
            idx1 = v24;
        }
        if (v90 == 1 || v90 == 2)
        {
            v54->field_0->field_204(index);
            if (arg_3)
                v54->field_0->field_208(index);
            *((unsigned int *)&index[449]) = (int)index[449] + 1;
        }
        UModel::EmptyModel(v54->field_ac, 1, 1);
        if (v23 == 3 || v23 == 4)
        {
            if (v22 > 200)
                (*((int *)(*((int *)*((int *)&GWarn)) + 16)))(*((int *)&GWarn), 0, 0, "%", L"Merging");
            if (arg_4)
                v54->field_0->field_210(idx1, 1, 0);
        }
        if (v22 > 200)
            (*((int *)(*((int *)*((int *)&GWarn)) + 12)))();
    }
    v103 = _ccall(v46, v47, (unsigned int)v48, 0);
    *((unsigned int *)(unsigned int)v103) = v42;
    return v104;
}
