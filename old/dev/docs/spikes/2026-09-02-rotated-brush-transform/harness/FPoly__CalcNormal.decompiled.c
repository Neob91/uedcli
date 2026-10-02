extern unsigned int g_10279424;
extern char GLog;

int FPoly::CalcNormal(void* this, int arg_0)
{
    unsigned long v22;  // ldt
    unsigned long v23;  // gdt
    uint128_t v31;  // xmm5
    uint128_t v32;  // xmm2
    uint128_t v33;  // xmm4
    uint128_t v34;  // xmm1
    uint128_t v35;  // xmm3
    unsigned short v24;  // fs
    uint128_t v36;  // xmm0
    unsigned int v37;  // eax
    int v39;  // xmm5
    int v41;  // xmm2
    int v42;  // xmm2
    int v43;  // xmm2
    int v45;  // xmm4
    unsigned long long v25;  // 4147
    int v47;  // xmm1
    int v48;  // xmm1
    int v49;  // xmm1
    int v51;  // xmm3
    int v53;  // xmm0
    int v54;  // xmm0
    int v55;  // xmm0
    unsigned int v26;  // ebx
    unsigned int v56;  // eax
    int v58;  // xmm2
    int v59;  // xmm2
    int v61;  // xmm1
    int v62;  // xmm1
    int v64;  // xmm0
    int v65;  // xmm0
    unsigned int v27;  // esi
    unsigned int v66;  // eax
    unsigned long long v67;  // 4119
    unsigned int v28;  // edi
    unsigned long long v29;  // 4167
    int v30;  // esi
    unsigned int v0;  // [bp-0x70]
    unsigned int v1;  // [bp-0x6c]
    unsigned int v2;  // [bp-0x60]
    unsigned int v3;  // [bp-0x5c]
    unsigned int v4;  // [bp-0x58]
    unsigned int v5;  // [bp-0x54]
    char v6;  // [bp-0x50]
    unsigned int v7;  // [bp-0x44]
    unsigned int v8;  // [bp-0x40]
    unsigned int v9;  // [bp-0x3c]
    unsigned int v10;  // [bp-0x38]
    unsigned int v11;  // [bp-0x34]
    unsigned int v12;  // [bp-0x30]
    unsigned int v13;  // [bp-0x2c]
    unsigned int v14;  // [bp-0x28]
    unsigned int v15;  // [bp-0x24]
    int v16;  // [bp-0x18]
    char *v17;  // [bp-0x14]
    unsigned int v18;  // [bp-0x10]
    unsigned int v19;  // [bp-0xc]
    unsigned int v20;  // [bp-0x8]
    char v21;  // [bp-0x4]

    v20 = 0xffffffff;
    v19 = sub_101f1860;
    v25 = _ccall(v22, v23, (unsigned int)v24, 0);
    v18 = *((int *)(unsigned int)v25);
    v5 = v26;
    v4 = v27;
    v3 = v28;
    v2 = g_10279424 ^ &v21;
    v29 = _ccall(v22, v23, (unsigned int)v24, 0);
    *((unsigned int **)(unsigned int)v29) = &v18;
    v17 = &v2;
    v20 = 0;
    v7 = 0;
    v8 = 0;
    v9 = 0;
    memset(this + 12, 0, 12);
    v30 = 2;
    while (1)
    {
        v16 = v30;
        if (v30 >= (int)this[448])
            break;
        v37 = v30 * 3;
        v39 = (int)_INSERT(_INSERT(v31, 8, 0), 4, 0);
        v31 = _INSERT(v39, 0, (int)this[48]);
        v41 = (int)_INSERT(_INSERT(v32, 8, 0), 4, 0);
        v42 = (int)_INSERT(v41, 0, *((int *)((char *)this + 4 * v37 + 48)));
        v43 = SubV(v42, v31);
        v45 = (int)_INSERT(_INSERT(v33, 8, 0), 4, 0);
        v33 = _INSERT(v45, 0, (int)this[52]);
        v47 = (int)_INSERT(_INSERT(v34, 8, 0), 4, 0);
        v48 = (int)_INSERT(v47, 0, *((int *)((char *)this + 4 * v37 + 52)));
        v49 = SubV(v48, v33);
        v51 = (int)_INSERT(_INSERT(v35, 8, 0), 4, 0);
        v35 = _INSERT(v51, 0, (int)this[56]);
        v53 = (int)_INSERT(_INSERT(v36, 8, 0), 4, 0);
        v54 = (int)_INSERT(v53, 0, *((int *)((char *)this + 4 * v37 + 56)));
        v55 = SubV(v54, v35);
        v13 = *((unsigned int *)&v43);
        v14 = *((unsigned int *)&v49);
        v15 = *((unsigned int *)&v55);
        v56 = v30 * 3;
        v58 = (int)_INSERT(_INSERT(v43, 8, 0), 4, 0);
        v59 = (int)_INSERT(v58, 0, *((int *)((char *)this + 4 * v56 + 36)));
        v32 = (uint128_t)(SubV(v59, v31));
        v61 = (int)_INSERT(_INSERT(v49, 8, 0), 4, 0);
        v62 = (int)_INSERT(v61, 0, *((int *)((char *)this + 4 * v56 + 40)));
        v34 = (uint128_t)(SubV(v62, v33));
        v64 = (int)_INSERT(_INSERT(v55, 8, 0), 4, 0);
        v65 = (int)_INSERT(v64, 0, *((int *)((char *)this + 4 * v56 + 44)));
        v36 = (uint128_t)(SubV(v65, v35));
        v10 = v32;
        v11 = v34;
        v12 = v36;
        v1 = &v13;
        v0 = (unsigned int)FVector::operator^(&v10, &v7);
        FVector::operator+=(this + 12, &v6);
        v30 += 1;
    }
    if (!FVector::NormalizeSlow(this + 12))
    {
        if (!arg_0)
        {
            v0 = 0x2ff;
            FOutputDevice::Logf(*((int *)&GLog), L"FPoly::CalcNormal: Zero-area polygon");
        }
        v66 = 1;
    }
    else
    {
        v66 = 0;
    }
    v67 = _ccall(v22, v23, (unsigned int)v24, 0);
    *((unsigned int *)(unsigned int)v67) = v18;
    return v66;
}
