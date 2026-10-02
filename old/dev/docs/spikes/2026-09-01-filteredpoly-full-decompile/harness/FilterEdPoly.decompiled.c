typedef struct struct_1 {
    char padding_0[32];
    int field_20;
} struct_1;

typedef struct struct_3 {
    char padding_0[36];
    unsigned int field_24;
} struct_3;

class class FPoly {
} class FPoly;

extern unsigned int g_101491b4;
extern char GLog;

int sub_10032bf0(int a0, unsigned int *a1, int a2, unsigned int a3, uint128_t a4, unsigned int a5, unsigned int a6, unsigned int a7, int a8, int a9)
{
    unsigned long v25;  // ldt
    unsigned long v26;  // gdt
    int v35;  // esi
    int v36;  // esi
    unsigned int v37;  // esi
    int v38;  // eax
    int v39;  // eax
    struct_1 *idx;  // ecx
    int v41;  // edx
    int v42;  // eax
    int v43;  // ecx
    int v44;  // ecx
    unsigned short v27;  // fs
    unsigned int v45;  // eax
    int v46;  // edx
    uint128_t v47;  // xmm0
    int v48;  // esi
    uint128_t v49;  // xmm0
    unsigned long long v50;  // 4123
    unsigned int v51;  // eax
    unsigned long long v28;  // 4151
    unsigned int v29;  // ebx
    unsigned int v30;  // esi
    unsigned int v31;  // edi
    unsigned long long v32;  // 4174
    unsigned int *index;  // edi
    unsigned int v34;  // eax
    char *v0;  // [bp-0x608], Other Possible Types: unsigned int
    int v1;  // [bp-0x604]
    int v2;  // [bp-0x5f4]
    char *v3;  // [bp-0x5f0], Other Possible Types: int
    unsigned int v4;  // [bp-0x5ec]
    unsigned int v5;  // [bp-0x5dc]
    unsigned int v6;  // [bp-0x5d8]
    unsigned int v7;  // [bp-0x5d4]
    int v8;  // [bp-0x5c8]
    int v9;  // [bp-0x5c4]
    unsigned int v10;  // [bp-0x5c0], Other Possible Types: int
    unsigned int *v11;  // [bp-0x5b8], Other Possible Types: int
    int v12;  // [bp-0x5b4], Other Possible Types: unsigned int
    unsigned int v13;  // [bp-0x5b0]
    struct_1 *idx1;  // [bp-0x5ac], Other Possible Types: struct_3 *, unsigned int, int
    int v15;  // [bp-0x5a8]
    int v16;  // [bp-0x5a4]
    class FPoly v17;  // [bp-0x5a0]
    class FPoly v18;  // [bp-0x3c8]
    class FPoly v19;  // [bp-0x1f0]
    unsigned int v20;  // [bp-0x14]
    unsigned int v21;  // [bp-0x10]
    unsigned int v22;  // [bp-0xc]
    unsigned int v23;  // [bp-0x8]
    int v24;  // [bp+0x14]

    v23 = 0xffffffff;
    v22 = sub_100c4910;
    v28 = _ccall(v25, v26, (unsigned int)v27, 0);
    v21 = *((int *)(unsigned int)v28);
    v7 = v29;
    v6 = v30;
    v5 = v31;
    v32 = _ccall(v25, v26, (unsigned int)v27, 0);
    *((unsigned int **)(unsigned int)v32) = &v21;
    v20 = &/* unsupported instruction */;
    index = a1;
    v11 = index;
    v15 = a2;
    v34 = a3;
    v13 = v34;
    v23 = 0;
    v35 = a9;
    while (1)
    {
        v16 = v35;
        while (1)
        {
LABEL_10032c56:
            if (*((int *)(v34 + 448)) >= 14)
            {
                FPoly::FPoly(&v17);
                FPoly::SplitInHalf(v13, &v17);
                memcpy(&v1 - 8, &a4, 16);
                *((class FPoly **)&(&v1)[4]) = &v17;
                v36 = v15;
                *((int *)&v1) = v36;
                sub_10032bf0(a0, index, *((unsigned int *)&v1), *((unsigned int *)(&v1 + 4)), *((unsigned int *)(&v1 + 8)), *((unsigned int *)(&v1 + 12)), *((unsigned int *)(&v1 + 16)), v3, a8, v35);
            }
            else
            {
                v36 = v15;
            }
            FPoly::FPoly(&v19);
            FPoly::FPoly(&v18);
            v12 = v36 * 64;
            v37 = *((int *)(index[22] + v12 + 28)) * 64;
            v3 = &v19;
            *((unsigned int *)&(&v1)[16]) = index[30] + *((int *)(v37 + index[38] + 12)) * 12;
            *((unsigned int *)&(&v1)[12]) = v11[0x22] + *((int *)(v37 + index[38] + 8)) * 12;
            if (FPoly::SplitWithPlane(v13, *((unsigned int *)(&v1 + 12)), *((unsigned int *)(&v1 + 16)), &v19, &v18, 0) != 1)
                break;
LABEL_10032db7:
            index = v11;
            idx1 = index[22] + v12;
            if (!v16 && !sub_10033b80(0))
                v35 = 0;
            else
                v35 = 1;
            v16 = v35;
            v39 = idx1->field_24;
            if (v39 == 0xffffffff)
            {
                v4 = 1;
                v3 = v35;
                v44 = a8;
                v0 = v13;
                memcpy(&v1, &a4, 16);
                *((int *)&(&v1)[16]) = v44;
                sub_10033130(a0, index, v15);
                v23 = 0xffffffff;
                v50 = _ccall(v25, v26, (unsigned int)v27, 0);
                *((unsigned int *)(unsigned int)v50) = v21;
                return v51;
            }
LABEL_100330da:
            v15 = v39;
            v34 = v13;
        }
        if (v38 == 2)
        {
            index = v11;
            idx1 = index[22] + v12;
            if (v16 && !sub_10033b80(0))
                v35 = 1;
            else
                v35 = 0;
            v16 = v35;
            v39 = idx1->field_20;
            if (v39 == 0xffffffff)
            {
                v4 = 0;
                v3 = v35;
                v0 = v13;
                memcpy(&v1, &a4, 16);
                *((int *)&(&v1)[16]) = v44;
                sub_10033130(a0, index, v15);
                v23 = 0xffffffff;
                v50 = _ccall(v25, v26, (unsigned int)v27, 0);
                *((unsigned int *)(unsigned int)v50) = v21;
                return v51;
            }
            goto LABEL_100330da;
        }
        if (v38)
        {
            if (v38 == 3)
            {
                index = v11;
                v45 = sub_10033b80(0);
                idx1 = 1;
                if (v45)
                    v46 = idx1;
                else
                    v46 = v16;
                v10 = v46;
                v11 = 0;
                if (!v45)
                    v11 = v16;
                v47 = a4;
                v48 = a8;
                if (*((int *)(index[22] + v12 + 36)) == 0xffffffff)
                {
                    v4 = 1;
                    v3 = v46;
                    v2 = a8;
                    sub_10033130(a0, index, v15, &v19, v47);
                }
                else
                {
                    sub_10032bf0(a0, index, *((int *)(index[22] + v12 + 36)), &v19, (unsigned int)v47, *((unsigned int *)((void*)&v47 + 4)), *((unsigned int *)((void*)&v47 + 8)), *((unsigned int *)((void*)&v47 + 12)), v48, v46);
                }
                v49 = a4;
                if (*((int *)(index[22] + v12 + 32)) != 0xffffffff)
                {
                    v1 = (int)_INSERT(v47 CONCAT 0, 4, v49);
                    *((class FPoly **)&v1) = &v18;
                    sub_10032bf0(a0, index, *((int *)(index[22] + v12 + 32)), *((unsigned int *)&v1), *((unsigned int *)(&v1 + 4)), *((unsigned int *)(&v1 + 8)), *((unsigned int *)(&v1 + 12)), *((unsigned int *)(&v1 + 16)), v48, v11);
                    v23 = 0xffffffff;
                    v50 = _ccall(v25, v26, (unsigned int)v27, 0);
                    *((unsigned int *)(unsigned int)v50) = v21;
                    return v51;
                }
                v4 = 0;
                v3 = v11;
                v1 = (int)_INSERT(v47 CONCAT 0, 0, v49);
                *((int *)&(&v1)[16]) = v48;
                v0 = &v18;
                sub_10033130(a0, index, v15);
                v23 = 0xffffffff;
                v50 = _ccall(v25, v26, (unsigned int)v27, 0);
                *((unsigned int *)(unsigned int)v50) = v21;
                return v51;
            }
            else
            {
                v23 = 0xffffffff;
                v50 = _ccall(v25, v26, (unsigned int)v27, 0);
                *((unsigned int *)(unsigned int)v50) = v21;
                return v51;
            }
        }
        if ((unsigned int)a4 != 0xffffffff)
        {
            g_101491b4 = g_101491b4 + 1;
            v4 = 0x2ff;
            v3 = *((int *)&GLog);
            FOutputDevice::Logf(*((int *)&GLog), L"FilterEdPoly: Encountered out-of-place coplanar");
            goto LABEL_10032db7;
        }
        v24 = (int)_INSERT(a4, 0, v15);
        a5 = 0xffffffff;
        a8 = 0;
        v35 = v16;
        a6 = v35;
        v10 = a6;
        index = v11;
        FPlane::operator|(index[22] + v12, v13 + 12);
        if (/* unsupported instruction */)
        {
            idx1 = /* unsupported instruction */;
            /* unsupported instruction */
        }
        else
        {
            idx1 = nan;
            /* unsupported instruction */
        }
        idx = index[22] + v12;
        if ((CmpF(idx1, 0) & 1) != 1)
        {
            idx1 = *((int *)&idx[1].padding_0[0]);
            v9 = *((int *)&idx[1].padding_0[0]);
            v12 = idx->field_20;
            v8 = idx->field_20;
            v16 = v35;
            if (sub_10033b80(0))
            {
                a6 = 0;
                v10 = 1;
                v35 = 0;
                v16 = 0;
            }
        }
        else
        {
            idx1 = idx->field_20;
            v9 = idx->field_20;
            v12 = *((int *)&idx[1].padding_0[0]);
            v8 = *((int *)&idx[1].padding_0[0]);
            v16 = v35;
            if (sub_10033b80(0))
            {
                v41 = 1;
                a6 = 1;
                v42 = 0;
                v10 = 0;
                v35 = 1;
                v16 = 1;
LABEL_10032ea7:
                v43 = v12;
                if (idx1 == 0xffffffff)
                {
                    if (v43 == 0xffffffff)
                    {
                        a8 = 1;
                        a7 = v42;
                        v4 = 2;
                        v3 = v41;
                        v0 = v13;
                        memcpy(&v1, &a4, 16);
                        *((int *)&(&v1)[16]) = 1;
                        sub_10033130(a0, index, v15);
                        v23 = 0xffffffff;
                        v50 = _ccall(v25, v26, (unsigned int)v27, 0);
                        *((unsigned int *)(unsigned int)v50) = v21;
                        return v51;
                    }
                    a8 = 1;
                    a5 = v43;
                    a7 = v42;
                    v15 = v43;
                    v34 = v13;
                    goto LABEL_10032c56;
                }
                else
                {
                    a8 = 0;
                    a5 = v43;
                    v15 = idx1;
                    v35 = v42;
                    v34 = v13;
                    continue;
                }
            }
        }
        v41 = a6;
        v42 = v10;
        goto LABEL_10032ea7;
    }
}
