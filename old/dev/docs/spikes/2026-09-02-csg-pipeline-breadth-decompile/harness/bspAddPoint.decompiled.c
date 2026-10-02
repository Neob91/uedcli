// bspAddPoint @ 0x10035430  size=199
class class FVector {
} class FVector;

class class UModel {
} class UModel;

extern unsigned int g_10140164;

int UEditorEngine::bspAddPoint(void* this, class UModel *arg_0, class FVector *arg_1, int arg_2)
{
    unsigned long v9;  // ldt
    unsigned long v10;  // gdt
    unsigned short v11;  // fs
    unsigned long long v12;  // 4186
    unsigned long long v13;  // 4190
    unsigned int v14;  // eax
    unsigned int v15;  // ecx
    unsigned long long v16;  // 4119
    void* v0;  // [bp-0x44], Other Possible Types: unsigned int
    unsigned int v1;  // [bp-0x3c]
    char v2;  // [bp-0x2c]
    char v3;  // [bp-0x18], Other Possible Types: unsigned int
    char *v4;  // [bp-0x14]
    unsigned int v5;  // [bp-0x10]
    unsigned int v6;  // [bp-0xc]
    unsigned int v7;  // [bp-0x8]
    char v8;  // [bp-0x4]

    v7 = 0xffffffff;
    v6 = sub_100c4bb0;
    v12 = _ccall(v9, v10, (unsigned int)v11, 0);
    v5 = *((int *)(unsigned int)v12);
    v1 = g_10140164 ^ &v8;
    v13 = _ccall(v9, v10, (unsigned int)v11, 0);
    *((unsigned int **)(unsigned int)v13) = &v5;
    v4 = &v1;
    v7 = 0;
    arg_2 = (!arg_2 ? 1014350479 : 990057071);
    v0 = this;
    UModel::FindNearestVertex(arg_0, arg_1, &v2, arg_2, &v3);
    if (/* unsupported instruction */)
    {
        arg_0 = /* unsupported instruction */;
        /* unsupported instruction */
    }
    else
    {
        arg_0 = nan;
        /* unsupported instruction */
    }
    if ((CmpF(arg_0, 0) & 1) != 1 && (CmpF(arg_2, arg_0) & 1) != 1)
    {
        v14 = v3;
    }
    else
    {
        v0 = v15;
        v14 = sub_10031ae0(arg_0 + 0x22, arg_1, arg_2, ~((int)this[268]) & 1);
    }
    v16 = _ccall(v9, v10, (unsigned int)v11, 0);
    *((unsigned int *)(unsigned int)v16) = v5;
    return v14;
}
