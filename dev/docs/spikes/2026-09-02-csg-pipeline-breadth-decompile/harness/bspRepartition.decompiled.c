// bspRepartition @ 0x10049fc0  size=186
extern unsigned int g_10140164;

void UEditorEngine::bspRepartition(void* this, class UModel *arg_0, int arg_1, int arg_2)
{
    unsigned long v6;  // ldt
    unsigned long v7;  // gdt
    unsigned short v8;  // fs
    unsigned long long v9;  // 4154
    unsigned long long v10;  // 4174
    unsigned int v11;  // edi
    unsigned int v12;  // esi
    unsigned int v13;  // ebx
    unsigned long long v14;  // 4122
    unsigned int v0;  // [bp-0x2c]
    char *v1;  // [bp-0x14]
    unsigned int v2;  // [bp-0x10]
    unsigned int v3;  // [bp-0xc]
    unsigned int v4;  // [bp-0x8]
    char v5;  // [bp-0x4]

    v4 = 0xffffffff;
    v3 = sub_100c5cd0;
    v9 = _ccall(v6, v7, (unsigned int)v8, 0);
    v2 = *((int *)(unsigned int)v9);
    v0 = g_10140164 ^ &v5;
    v10 = _ccall(v6, v7, (unsigned int)v8, 0);
    *((unsigned int **)(unsigned int)v10) = &v2;
    v1 = &v0;
    v4 = 0;
    (*((int *)(*((int *)this) + 524)))(*((int *)((int)this[168] + 152)), 1, arg_1, g_10140164 ^ &v5, v11, v12, v13);
    (*((int *)(*((int *)this) + 528)))(*((int *)((int)this[168] + 152)), 0, 0);
    (*((int *)(*((int *)this) + 508)))(*((int *)((int)this[168] + 152)), 1, 12, arg_2, arg_1);
    (*((int *)(*((int *)this) + 0x200)))(*((int *)((int)this[168] + 152)), 1);
    v14 = _ccall(v6, v7, (unsigned int)v8, 0);
    *((unsigned int *)(unsigned int)v14) = v2;
    return;
}
