// bspNodeToFPoly @ 0x100365b0  size=638
typedef struct struct_0 {
    char padding_0[244];
    struct struct_1 *field_f4;
} struct_0;

typedef struct struct_2 {
    unsigned int field_0;
    unsigned int field_4;
    unsigned int field_8;
    unsigned int field_c;
    unsigned int field_10;
    unsigned int field_14;
    char padding_18[4];
    unsigned int field_1c;
    unsigned short field_20;
    unsigned short field_22;
    unsigned int field_24;
} struct_2;

typedef struct struct_1 {
    unsigned int field_0;
} struct_1;

class class FPoly {
} class FPoly;

class class UModel {
} class UModel;

int UEditorEngine::bspNodeToFPoly(void* this, class UModel *index, int arg_1, class FPoly *idx)
{
    unsigned long v16;  // ldt
    unsigned long v17;  // gdt
    unsigned int v26;  // ecx
    unsigned int idx1;  // edx
    unsigned int v28;  // ecx
    struct_2 *idx2;  // ecx
    unsigned int v30;  // edx
    struct_2 *v31;  // ebx
    unsigned int v32;  // ecx
    unsigned int v33;  // ecx
    char v34;  // al
    char v35;  // bh
    unsigned short v18;  // fs
    char i;  // bl
    unsigned int v37;  // esi
    unsigned int v38;  // edx
    unsigned int v39;  // ecx
    unsigned long long v42;  // 4124
    unsigned int v43;  // eax
    unsigned long long v19;  // 4151
    unsigned int v20;  // ebx
    unsigned int v21;  // esi
    unsigned int v22;  // edi
    unsigned long long v23;  // 4174
    unsigned int *v24;  // esi
    unsigned int v25;  // edx
    unsigned int v0;  // [bp-0x21c]
    unsigned int v1;  // [bp-0x218]
    unsigned int v2;  // [bp-0x214]
    struct_0 **v3;  // [bp-0x204], Other Possible Types: unsigned int
    unsigned int v4;  // [bp-0x200]
    unsigned int *v5;  // [bp-0x1fc]
    struct_2 *v6;  // [bp-0x1f8]
    char v7;  // [bp-0x1f3]
    char v8;  // [bp-0x1f2]
    char v9;  // [bp-0x1f1]
    char v10;  // [bp-0x1f0]
    unsigned int v11;  // [bp-0x34]
    unsigned int v12;  // [bp-0x14]
    unsigned int v13;  // [bp-0x10]
    unsigned int v14;  // [bp-0xc]
    unsigned int v15;  // [bp-0x8]

    v15 = 0xffffffff;
    v14 = sub_100c4ca0;
    v19 = _ccall(v16, v17, (unsigned int)v18, 0);
    v13 = *((int *)(unsigned int)v19);
    v2 = v20;
    v1 = v21;
    v0 = v22;
    v23 = _ccall(v16, v17, (unsigned int)v18, 0);
    *((unsigned int **)(unsigned int)v23) = &v13;
    v12 = &/* unsupported instruction */;
    v3 = this;
    v15 = 0;
    FPoly::FPoly(&v10);
    v24 = arg_1 * 64 + (int)index[22];
    v5 = v24;
    v6 = v24[7] * 64 + (int)index[38];
    v4 = (int)index[26] + v24[6] * 8;
    v25 = v6->field_8 * 3;
    v26 = (int)index[0x22];
    *((int *)idx) = *((int *)(v26 + v25 * 4));
    *((int *)&idx[1]) = *((int *)(v26 + v25 * 4 + 4));
    *((int *)&idx[2]) = *((int *)(v26 + v25 * 4 + 8));
    idx1 = v6->field_c * 3;
    v28 = (int)index[30];
    *((int *)&idx[3]) = *((int *)(v28 + idx1 * 4));
    *((int *)&idx[4]) = *((int *)(v28 + idx1 * 4 + 4));
    *((int *)&idx[5]) = *((int *)(v28 + idx1 * 4 + 8));
    idx2 = v6;
    *((unsigned int *)&idx[108]) = idx2->field_4 & 0x3cffffff;
    *((unsigned int *)&idx[113]) = v5[7];
    *((unsigned int *)&idx[110]) = idx2->field_0;
    *((unsigned int *)&idx[109]) = idx2->field_24;
    *((unsigned int *)&idx[114]) = idx2->field_1c;
    *((unsigned short *)&idx[115]) = idx2->field_20;
    *((unsigned short *)((char *)&idx[115] + 2)) = idx2->field_22;
    if (*(v3)->field_f4(index, v5[7], &v10))
    {
        *((unsigned int *)&idx[111]) = v11;
    }
    else
    {
        v3 = 0;
        *((unsigned int *)&idx[111]) = 0;
    }
    v30 = (int)index[30];
    v31 = v6;
    v32 = v31->field_10 * 3;
    *((int *)&idx[6]) = *((int *)(v30 + v32 * 4));
    *((int *)&idx[7]) = *((int *)(v30 + v32 * 4 + 4));
    *((int *)&idx[8]) = *((int *)(v30 + v32 * 4 + 8));
    v33 = v31->field_14 * 3;
    *((int *)&idx[9]) = *((int *)(v30 + v33 * 4));
    *((int *)&idx[10]) = *((int *)(v30 + v33 * 4 + 4));
    *((int *)&idx[11]) = *((int *)(v30 + v33 * 4 + 8));
    v34 = *((char *)&v5[13] + 2);
    v7 = *((char *)&v5[13] + 2);
    v9 = 0;
    v35 = 0;
    v8 = 0;
    i = 0;
    for (v9 = 0; i < v34; i += 1)
    {
        v37 = *((int *)(v4 + i * 8)) * 3;
        v38 = (int)index[0x22];
        v39 = (v35 + 4) * 3;
        *((int *)&idx[v39]) = *((int *)(v38 + v37 * 4));
        *((int *)&idx[1 + v39]) = *((int *)(v38 + v37 * 4 + 4));
        *((int *)&idx[2 + v39]) = *((int *)(v38 + v37 * 4 + 8));
        v8 = v35 + 1;
        v9 = i + 1;
        v34 = v7;
        v35 += 1;
    }
    if (v35 >= 3)
        *((unsigned int *)&idx[112]) = v35;
    else
        *((unsigned int *)&idx[112]) = 0;
    FPoly::RemoveColinears(idx);
    v42 = _ccall(v16, v17, (unsigned int)v18, 0);
    *((unsigned int *)(unsigned int)v42) = v13;
    return v43;
}
