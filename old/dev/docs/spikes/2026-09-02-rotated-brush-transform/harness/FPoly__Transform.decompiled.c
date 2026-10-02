typedef struct struct_0 {
    unsigned int field_0;
    unsigned int field_4;
    unsigned int field_8;
} struct_0;

extern unsigned int g_10279424;

void FPoly::Transform(void* idx, class FModelCoords &arg_0, class FVector &arg_1, class FVector &arg_2, float arg_3)
{
    unsigned long v37;  // ldt
    unsigned long v38;  // gdt
    unsigned int *idx1;  // eax
    unsigned int v48;  // xmm0
    int v50;  // xmm2
    int v51;  // xmm2
    unsigned int *v52;  // eax
    int v53;  // xmm2
    int v55;  // xmm1
    int v56;  // xmm1
    unsigned short v39;  // fs
    int v57;  // xmm1
    int v59;  // xmm0
    int v60;  // xmm0
    int v61;  // xmm0
    unsigned int *v62;  // eax
    int v64;  // xmm2
    int v65;  // xmm2
    unsigned int *v66;  // ecx
    unsigned long long v40;  // 4153
    uint128_t v67;  // xmm2
    int v69;  // xmm1
    int v70;  // xmm1
    uint128_t v71;  // xmm1
    int v73;  // xmm0
    int v74;  // xmm0
    uint128_t v75;  // xmm0
    int v76;  // ebx
    unsigned int v41;  // ebx
    int v77;  // eax
    unsigned int v78;  // esi
    int v80;  // xmm2
    int v81;  // xmm2
    unsigned int *v82;  // eax
    int v83;  // xmm2
    int v85;  // xmm1
    int v86;  // xmm1
    unsigned int v42;  // esi
    int v87;  // xmm1
    int v89;  // xmm0
    int v90;  // xmm0
    int v91;  // xmm0
    struct_0 *v92;  // eax
    struct_0 *v93;  // ecx
    int v95;  // xmm2
    int v96;  // xmm2
    unsigned int v43;  // edi
    int v98;  // xmm1
    int v99;  // xmm1
    int v101;  // xmm0
    int v102;  // xmm0
    int v103;  // esi
    unsigned int v104;  // edx
    unsigned int idx2;  // ecx
    unsigned int v106;  // eax
    unsigned long long v44;  // 4173
    unsigned int *v107;  // eax
    unsigned long long v108;  // 4122
    unsigned int v45;  // ebx
    unsigned int *index;  // eax
    unsigned int v0;  // [bp-0xd0]
    char *v1;  // [bp-0xcc], Other Possible Types: unsigned int
    unsigned int v2;  // [bp-0xc4]
    unsigned int v3;  // [bp-0xc0]
    unsigned int v4;  // [bp-0xbc]
    unsigned int v5;  // [bp-0xb8]
    unsigned int v6;  // [bp-0xb4]
    unsigned int v7;  // [bp-0xb0]
    unsigned int v8;  // [bp-0xac]
    char v9;  // [bp-0xa8]
    char v10;  // [bp-0x9c]
    char v11;  // [bp-0x90]
    char v12;  // [bp-0x84]
    char v13;  // [bp-0x78]
    char v14;  // [bp-0x6c]
    unsigned int v15;  // [bp-0x60]
    unsigned int v16;  // [bp-0x5c]
    unsigned int v17;  // [bp-0x58]
    unsigned int v18;  // [bp-0x54]
    unsigned int v19;  // [bp-0x50]
    unsigned int v20;  // [bp-0x4c]
    unsigned int v21;  // [bp-0x48]
    unsigned int v22;  // [bp-0x44]
    unsigned int v23;  // [bp-0x40]
    unsigned int v24;  // [bp-0x38]
    unsigned int v25;  // [bp-0x34]
    unsigned int v26;  // [bp-0x30]
    unsigned int v27;  // [bp-0x2c]
    unsigned int v28;  // [bp-0x28]
    unsigned int v29;  // [bp-0x24]
    unsigned int v30;  // [bp-0x1c]
    int v31;  // [bp-0x18]
    char *v32;  // [bp-0x14]
    unsigned int v33;  // [bp-0x10]
    unsigned int v34;  // [bp-0xc]
    unsigned int v35;  // [bp-0x8]
    char v36;  // [bp-0x4]

    v35 = 0xffffffff;
    v34 = sub_101f1a10;
    v40 = _ccall(v37, v38, (unsigned int)v39, 0);
    v33 = *((int *)(unsigned int)v40);
    v8 = v41;
    v7 = v42;
    v6 = v43;
    v5 = g_10279424 ^ &v36;
    v44 = _ccall(v37, v38, (unsigned int)v39, 0);
    *((unsigned int **)(unsigned int)v44) = &v33;
    v32 = &v5;
    v35 = 0;
    v45 = (unsigned int)arg_0;
    v30 = v45 + 48;
    v4 = v30;
    index = (unsigned int *)FVector::TransformVectorBy(idx + 24, &v14);
    *((unsigned int *)&idx[24]) = *(index);
    *((unsigned int *)&idx[28]) = index[1];
    *((unsigned int *)&idx[32]) = index[2];
    v3 = v45 + 48;
    idx1 = (unsigned int *)FVector::TransformVectorBy(idx + 36, &v13);
    *((unsigned int *)&idx[36]) = *(idx1);
    *((unsigned int *)&idx[40]) = idx1[1];
    v48 = idx1[2];
    *((unsigned int *)&idx[44]) = v48;
    v50 = (int)_INSERT(_INSERT(0, 8, 0), 4, 0);
    v51 = (int)_INSERT(v50, 0, *((int *)idx));
    v52 = (unsigned int *)arg_1;
    v53 = SubV(v51, *(v52));
    v55 = (int)_INSERT(_INSERT(0, 8, 0), 4, 0);
    v56 = (int)_INSERT(v55, 0, (int)idx[4]);
    v57 = SubV(v56, v52[1]);
    v59 = (int)_INSERT(_INSERT(v48 CONCAT 0, 8, 0), 4, 0);
    v60 = (int)_INSERT(v59, 0, (int)idx[8]);
    v61 = SubV(v60, v52[2]);
    v27 = *((unsigned int *)&v53);
    v28 = *((unsigned int *)&v57);
    v29 = *((unsigned int *)&v61);
    v2 = v45;
    v62 = (unsigned int *)FVector::TransformVectorBy(&v27, &v12);
    v64 = (int)_INSERT(_INSERT(v53, 8, 0), 4, 0);
    v65 = (int)_INSERT(v64, 0, *(v62));
    v66 = (unsigned int *)arg_2;
    v67 = (uint128_t)(AddV(v65, *(v66)));
    v69 = (int)_INSERT(_INSERT(v57, 8, 0), 4, 0);
    v70 = (int)_INSERT(v69, 0, v62[1]);
    v71 = (uint128_t)(AddV(v70, v66[1]));
    v73 = (int)_INSERT(_INSERT(v61, 8, 0), 4, 0);
    v74 = (int)_INSERT(v73, 0, v62[2]);
    v75 = (uint128_t)(AddV(v74, v66[2]));
    v21 = v67;
    v22 = v71;
    v23 = v75;
    *((unsigned int *)idx) = v67;
    *((unsigned int *)&idx[4]) = v71;
    *((unsigned int *)&idx[8]) = v75;
    v76 = 0;
    while (1)
    {
        v31 = v76;
        if (v76 >= (int)idx[448])
            break;
        v78 = v76 * 3;
        v80 = (int)_INSERT(_INSERT(v67, 8, 0), 4, 0);
        v81 = (int)_INSERT(v80, 0, *((int *)((char *)idx + 4 * v78 + 48)));
        v82 = (unsigned int *)arg_1;
        v83 = SubV(v81, *(v82));
        v85 = (int)_INSERT(_INSERT(v71, 8, 0), 4, 0);
        v86 = (int)_INSERT(v85, 0, *((int *)((char *)idx + 4 * v78 + 52)));
        v87 = SubV(v86, v82[1]);
        v89 = (int)_INSERT(_INSERT(v75, 8, 0), 4, 0);
        v90 = (int)_INSERT(v89, 0, *((int *)((char *)idx + 4 * v78 + 56)));
        v91 = SubV(v90, v82[2]);
        v24 = *((unsigned int *)&v83);
        v25 = *((unsigned int *)&v87);
        v26 = *((unsigned int *)&v91);
        v1 = (unsigned int)arg_0;
        v92 = (struct_0 *)FVector::TransformVectorBy(&v24, &v11);
        v93 = (struct_0 *)arg_2;
        v95 = (int)_INSERT(_INSERT(v83, 8, 0), 4, 0);
        v96 = (int)_INSERT(v95, 0, v93->field_0);
        v67 = (uint128_t)(AddV(v96, v92->field_0));
        v98 = (int)_INSERT(_INSERT(v87, 8, 0), 4, 0);
        v99 = (int)_INSERT(v98, 0, v92->field_4);
        v71 = (uint128_t)(AddV(v99, v93->field_4));
        v101 = (int)_INSERT(_INSERT(v91, 8, 0), 4, 0);
        v102 = (int)_INSERT(v101, 0, v92->field_8);
        v75 = (uint128_t)(AddV(v102, v93->field_8));
        v18 = v67;
        v19 = v71;
        v20 = v75;
        *((unsigned int *)((char *)idx + 4 * v78 + 48)) = v67;
        *((unsigned int *)((char *)idx + 4 * v78 + 52)) = v71;
        *((unsigned int *)((char *)idx + 4 * v78 + 56)) = v75;
        v76 += 1;
    }
    if (((CmpF(0, (unsigned int)arg_3) & 69 | (char)((CmpF(0, (unsigned int)arg_3) & 69) >> 6)) & 1) != 1)
    {
        v103 = 0;
        while (1)
        {
            v31 = v103;
            if (v103 >= v77 / 2)
                break;
            v104 = v103 * 3;
            v15 = *((int *)((char *)idx + 4 * v104 + 48));
            v16 = *((int *)((char *)idx + 4 * v104 + 52));
            v17 = *((int *)((char *)idx + 4 * v104 + 56));
            idx2 = ((int)idx[448] - v103 + 3) * 3;
            *((int *)((char *)idx + 4 * v104 + 48)) = *((int *)((char *)idx + 4 * idx2));
            *((int *)((char *)idx + 4 * v104 + 52)) = *((int *)((char *)idx + 4 * idx2 + 4));
            *((int *)((char *)idx + 4 * v104 + 56)) = *((int *)((char *)idx + 4 * idx2 + 8));
            v106 = ((int)idx[448] - v103 + 3) * 3;
            *((unsigned int *)((char *)idx + 4 * v106)) = v15;
            *((unsigned int *)((char *)idx + 4 * v106 + 4)) = v16;
            *((unsigned int *)((char *)idx + 4 * v106 + 8)) = v17;
            v103 += 1;
        }
    }
    v1 = &v10;
    v0 = v30;
    v107 = (unsigned int *)FVector::SafeNormalSlow(FVector::TransformVectorBy(idx + 12, &v9));
    *((unsigned int *)&idx[12]) = *(v107);
    *((unsigned int *)&idx[16]) = v107[1];
    *((unsigned int *)&idx[20]) = v107[2];
    FPoly::DiscardVertexDeltas(1);
    v108 = _ccall(v37, v38, (unsigned int)v39, 0);
    *((unsigned int *)(unsigned int)v108) = v33;
    return;
}
