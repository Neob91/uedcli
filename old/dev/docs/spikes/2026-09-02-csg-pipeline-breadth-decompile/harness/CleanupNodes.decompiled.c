// CleanupNodes @ 0x10032100  size=650
typedef struct struct_1 {
    char padding_0[32];
    void* field_20;
    void* field_24;
    struct struct_0 *field_28;
    char padding_2c[11];
    char field_37;
} struct_1;

typedef struct struct_0 {
    uint128_t field_0;
    uint128_t field_10;
    struct struct_0 *field_20;
    struct struct_0 *field_24;
    char padding_28[8];
    uint128_t field_30;
} struct_0;

typedef struct struct_3 {
    uint128_t field_0;
    uint128_t field_10;
    unsigned int field_20[4];
    struct struct_0 *field_28;
    char padding_2c[4];
    char field_30[16];
    char field_36;
} struct_3;

extern char GError;
extern char GUndo;

struct_0 * sub_10032100(unsigned int *iter, int a1, unsigned int a2)
{
    unsigned int v4;  // ecx
    unsigned int v5;  // ebx
    unsigned int v14;  // edi
    struct_0 **idx;  // edi
    struct_0 *v16;  // eax
    struct_0 *v17;  // eax
    struct_0 *v18;  // eax
    struct_0 *v19;  // edi
    struct_0 *v20;  // eax
    unsigned int v21;  // edx
    struct_0 *v22;  // eax
    uint128_t *idx1;  // edi
    unsigned int v6;  // esi
    struct_0 **idx2;  // esi
    struct_0 *v25;  // eax
    unsigned int v7;  // edi
    unsigned int v8;  // ecx
    struct_1 *v9;  // esi
    struct_0 *v10;  // eax
    unsigned int *v11;  // ecx
    struct_3 *v12;  // esi
    struct_0 *v13;  // eax
    unsigned int v0;  // [bp-0x14]
    unsigned int v1;  // [bp-0x10]
    unsigned int v2;  // [bp-0xc]
    struct_0 *index;  // [bp-0x8], Other Possible Types: unsigned int

    index = v4;
    v2 = v5;
    v1 = v6;
    v0 = v7;
    v8 = a1 * 64;
    v9 = iter[22] + v8;
    iter += 22;
    a1 = v8;
    v9->field_37 = v9->field_37 & 31;
    if (v9->field_24 != 0xffffffff)
        sub_10032100(iter, v9->field_24, a1);
    if (v9->field_20 != 0xffffffff)
        sub_10032100(iter, v9->field_20, a1);
    v10 = v9->field_28;
    if (v10 != 0xffffffff)
        v10 = sub_10032100(iter, v10, a1);
    v11 = iter;
    v12 = *(v11) + a1;
    if (v12->padding_2c[2])
        return v10;
    if (v12->field_20[2] != 0xffffffff)
    {
        if (*((int *)&GUndo))
        {
            (*((int *)(*((int *)*((int *)&GUndo)) + 8)))(v11[3], v11, v12->field_20[2], 1, 0, 64, operator<<, sub_10012f80);
            v11 = iter;
        }
        index = v12->field_20[2] * 64 + *(v11);
        FPlane::operator|(v12, index);
        if (/* unsupported instruction */)
        {
            a1 = /* unsupported instruction */;
            /* unsupported instruction */
        }
        else
        {
            a1 = nan;
            /* unsupported instruction */
        }
        if ((CmpF(a1, 0) & 1) != 1)
        {
            index->field_24 = v12->field_20[1];
            v13 = v12->field_20[0];
        }
        else
        {
            index->field_24 = v12->field_20[0];
            v13 = v12->field_20[1];
        }
        index->field_20 = v13;
        v14 = a2;
        if (v14 == 0xffffffff)
        {
            if (*((int *)&GUndo))
                (*((int *)(*((int *)*((int *)&GUndo)) + 8)))(iter[3], iter, a1, 1, 0, 64, operator<<, sub_10012f80);
            v12->field_0 = index->field_0;
            v12->field_10 = index->field_10;
            *((int128_t *)&v12->field_20[0]) = *((int128_t *)&index->field_20);
            *((uint128_t *)&v12->field_28) = index->field_30;
            *((char *)&index->field_30 + 6) = 0;
            return index;
        }
        else
        {
            if (*((int *)&GUndo))
                (*((int *)(*((int *)*((int *)&GUndo)) + 8)))(iter[3], iter, v14, 1, 0, 64, operator<<, sub_10012f80);
            idx = v14 * 64 + *(iter);
            if (idx[9] == a1)
            {
                v16 = v12->field_20[2];
                idx[9] = v16;
                return v16;
            }
            else if (idx[8] == a1)
            {
                v17 = v12->field_20[2];
                idx[8] = v17;
                return v17;
            }
            else if (idx[10] == a1)
            {
                v18 = v12->field_20[2];
                idx[10] = v18;
                return v18;
            }
        }
    }
    else
    {
        v19 = v12->field_20[1];
        v20 = v12->field_20[0];
        if (v12->field_20[1] == 0xffffffff)
        {
            v19 = 0xffffffff;
            if (v20 != 0xffffffff)
                v19 = v20;
        }
        else if (v20 != 0xffffffff)
        {
            return v20;
        }
        v21 = a2;
        if (v21 != 0xffffffff)
        {
            idx2 = v21 * 64 + *(v11);
            v25 = *((int *)&GUndo);
            iter = *((int *)&GUndo);
            if (*((int *)&GUndo))
                v25 = (*((int *)(*((int *)*((int *)&GUndo)) + 8)))(v11[3], v11, v21, 1, 0, 64, operator<<, sub_10012f80);
            if (idx2[9] == a1)
            {
                idx2[9] = v19;
                return v25;
            }
            if (idx2[8] == a1)
            {
                idx2[8] = v19;
                return v25;
            }
            if (idx2[10] == a1)
            {
                idx2[10] = v19;
                return v25;
            }
        }
        else if (v19 == 0xffffffff)
        {
            return sub_10032ae0(0);
        }
        else
        {
            v22 = sub_10034020(a1);
            idx1 = v19 * 64 + *(iter);
            v12->field_0 = *(idx1);
            v12->field_10 = idx1[1];
            *((uint128_t *)&v12->field_20[0]) = idx1[2];
            *((uint128_t *)&v12->field_28) = idx1[3];
            return v22;
        }
    }
    return (unsigned int)FOutputDevice::Logf(*((int *)&GError), L"CleanupNodes: Parent and child are unlinked");
}
