// TryToMerge @ 0x10034b10  size=815
typedef struct struct_0 {
    char padding_0[448];
    unsigned int field_1c0;
} struct_0;

int sub_10034b10(struct_0 *a0, unsigned int a1)
{
    unsigned long v22;  // ldt
    unsigned long v23;  // gdt
    struct_0 *v32;  // ecx
    int v33;  // eax
    int v34;  // edx
    int v35;  // eax
    int v36;  // edx
    int v37;  // eax
    unsigned int v38;  // ecx
    int v39;  // eax
    int i;  // ecx
    int v41;  // edx
    unsigned short v24;  // fs
    struct_0 *v42;  // eax
    unsigned int idx;  // edx
    unsigned int v44;  // ecx
    int v45;  // edi
    unsigned int v46;  // eax
    unsigned int index;  // edx
    unsigned int v48;  // ecx
    unsigned long long v49;  // 4120
    unsigned int v50;  // eax
    unsigned long long v25;  // 4217
    unsigned long long v26;  // 4221
    struct_0 *v27;  // ecx
    unsigned int v28;  // edx
    int v29;  // esi
    int iter;  // edi
    int node;  // esi
    struct_0 *v0;  // [bp-0x23c], Other Possible Types: unsigned int
    unsigned int v1;  // [bp-0x238]
    int v2;  // [bp-0x21c], Other Possible Types: unsigned int
    int v3;  // [bp-0x218]
    int v4;  // [bp-0x214]
    int v5;  // [bp-0x210]
    int v6;  // [bp-0x20c], Other Possible Types: unsigned int
    int v7;  // [bp-0x208], Other Possible Types: unsigned int
    int v8;  // [bp-0x204]
    unsigned int v9;  // [bp-0x200], Other Possible Types: int
    int v10;  // [bp-0x1fc]
    unsigned int v11;  // [bp-0x1f8]
    struct_0 *v12;  // [bp-0x1f4]
    char v13;  // [bp-0x1f0]
    char v14;  // [bp-0x1c0]
    char v15;  // [bp-0x1bc]
    char v16;  // [bp-0x1b8]
    int v17;  // [bp-0x30]
    unsigned int v18;  // [bp-0x14]
    unsigned int v19;  // [bp-0x10]
    unsigned int v20;  // [bp-0xc]
    unsigned int v21;  // [bp-0x8]

    v21 = 0xffffffff;
    v20 = sub_100c4b60;
    v25 = _ccall(v22, v23, (unsigned int)v24, 0);
    v19 = *((int *)(unsigned int)v25);
    v26 = _ccall(v22, v23, (unsigned int)v24, 0);
    *((unsigned int **)(unsigned int)v26) = &v19;
    v18 = &/* unsupported instruction */;
    v27 = a0;
    v12 = v27;
    v28 = a1;
    v11 = v28;
    v21 = 0;
    v29 = *((int *)(v28 + 448));
    v8 = v29;
    if (v27->field_1c0 + v29 > 16)
    {
        v49 = _ccall(v22, v23, (unsigned int)v24, 0);
        *((unsigned int *)(unsigned int)v49) = v19;
        return v50;
    }
    v7 = 0;
    v9 = 0;
    iter = 0;
    while (1)
    {
        v7 = iter;
        if (iter >= v27->field_1c0)
            break;
        node = 0;
        while (1)
        {
            v9 = node;
            if (node >= v29)
                break;
            v32 = v12;
            if (sub_10032b90(&v27->padding_0[48 + 12 * iter], v28 + (node + 4) * 12))
            {
                v33 = iter + 1;
                v6 = v32->field_1c0;
                v34 = 0;
                if (v33 < v32->field_1c0)
                    v34 = v33;
                v5 = v34;
                v35 = node - 1;
                v36 = v8 - 1;
                if (v35 >= 0)
                    v36 = v35;
                v3 = v36;
                v1 = v11 + (v36 + 4) * 12;
                v0 = &v32->padding_0[48 + 12 * v5];
                if (sub_10032b90())
                {
                    iter = v5;
                    v9 = v3;
                }
                else
                {
                    v37 = iter - 1;
                    v38 = v6 - 1;
                    if (v37 >= 0)
                        v38 = v37;
                    v6 = v38;
                    v39 = node + 1;
                    node = 0;
                    if (v39 < v8)
                        node = v39;
                    v1 = v11 + (node + 4) * 12;
                    v0 = &v12->padding_0[48 + 12 * v38];
                    if (!sub_10032b90())
                    {
                        v49 = _ccall(v22, v23, (unsigned int)v24, 0);
                        *((unsigned int *)(unsigned int)v49) = v19;
                        return v50;
                    }
                    v7 = v6;
                }
                FPoly::FPoly(&v13, v12);
                i = 0;
                v17 = 0;
                v10 = iter;
                v41 = 0;
                v4 = 0;
                for (v42 = v12; v41 < v42->field_1c0; i = v17)
                {
                    idx = i * 3;
                    v17 = i + 1;
                    v44 = iter * 3;
                    *((int *)&(&v14)[4 * idx]) = *((int *)&v42->padding_0[48 + 4 * v44]);
                    v42 = v12;
                    *((int *)&(&v15)[4 * idx]) = *((int *)&v42->padding_0[52 + 4 * v44]);
                    *((int *)&(&v16)[4 * idx]) = *((int *)&v42->padding_0[56 + 4 * v44]);
                    iter += 1;
                    v10 = iter;
                    if (iter >= v42->field_1c0)
                        iter = 0;
                    v10 = iter;
                    v4 += 1;
                }
                v10 = node;
                v45 = 0;
                v2 = 0;
                for (v46 = v11; v45 < *((int *)(v46 + 448)) - 2; i = v17)
                {
                    node += 1;
                    v10 = node;
                    if (node >= *((int *)(v46 + 448)))
                        node = 0;
                    v10 = node;
                    index = i * 3;
                    v17 = i + 1;
                    v48 = node * 3;
                    *((int *)&(&v14)[4 * index]) = *((int *)(v11 + v48 * 4 + 48));
                    v46 = v11;
                    *((int *)&(&v15)[4 * index]) = *((int *)(v46 + v48 * 4 + 52));
                    *((int *)&(&v16)[4 * index]) = *((int *)(v46 + v48 * 4 + 56));
                    v2 = v45 + 1;
                }
                if (!FPoly::RemoveColinears(&v13))
                {
                    v49 = _ccall(v22, v23, (unsigned int)v24, 0);
                    *((unsigned int *)(unsigned int)v49) = v19;
                    return v50;
                }
                else if (v17 > 16)
                {
                    v49 = _ccall(v22, v23, (unsigned int)v24, 0);
                    *((unsigned int *)(unsigned int)v49) = v19;
                    return v50;
                }
                else
                {
                    FPoly::operator=(v12, &v13);
                    *((unsigned int *)(v11 + 448)) = 0;
                    v49 = _ccall(v22, v23, (unsigned int)v24, 0);
                    *((unsigned int *)(unsigned int)v49) = v19;
                    return v50;
                }
            }
            node += 1;
            v28 = v11;
            v29 = v8;
            v27 = v32;
        }
        iter += 1;
    }
    v49 = _ccall(v22, v23, (unsigned int)v24, 0);
    *((unsigned int *)(unsigned int)v49) = v19;
    return v50;
}
