# UnrealScript bytecode — codec + AST lowering

The compiled script stored in `UStruct::Script` (functions and states). The full byte-exact codec is
`uedcli/uscript/bytecode.py` (`decode_script`/`encode_script`, `Tok(op, parts)`); this doc records the
opcode facts and how source lowers to tokens. Pinned by `test_uscript_bytecode.py` (all **3581**
UFunction/UState scripts across all 32 UED22 packages round-trip byte-exact).

## Stream shape
A token = opcode byte + operands, walked with a DUAL cursor: on-disk (compact obj/name refs are
variable width) vs in-memory `ScriptSize` (those refs count as 4 bytes). No stored on-disk length —
walk until the memory cursor hits `ScriptSize`. `Tok`'s parts are `("raw",bytes) | ("obj",id) |
("name",id) | ("sub",Tok) | ("parms",(Tok,…))` — index-independent, so token streams compare equal
iff they encode identically (this is the lowering oracle: lowered tokens == UCC-decoded tokens).

## Opcode essentials (full table in `bytecode.py`)
- `0x00` LocalVariable(obj), `0x01` InstanceVariable(obj), `0x02` DefaultVariable(obj).
- `0x04` Return(expr); `0x0B` Nothing; `0x0F` Let(expr,expr); `0x14` LetBool(expr,expr).
- Consts: `0x1D` IntConst(u32), `0x2C` IntConstByte(u8), `0x1F` StringConst(bytes+NUL), `0x2E`
  FloatConst(f32), `0x24` ByteConst(u8), `0x25` IntZero, `0x26` IntOne, `0x27` True, `0x28` False,
  `0x29` NoObject, name/object/rotation/vector consts likewise verbatim.
- Calls: `0x1B` VirtualFunction(name,parms), `0x1C` FinalFunction(obj,parms). Args are an expression
  run terminated by `0x16` EndFunctionParms.
- **Native calls carry NO object ref — the index IS the opcode:** `0x70–0xFF` single-byte native
  (index = the byte); `0x60–0x6F` ExtendedNative (index = `((op-0x60)<<8)|nextByte`). Args then run
  to `0x16`.
- Control flow (jumps are absolute u16 MEMORY offsets): `0x06` Jump(u16), `0x07` JumpIfNot(u16,expr),
  `0x0A` Switch, `0x09`/`0x08` Case/Iterator etc. Six opcodes (`0x03,0x10,0x15,0x2B,0x35,0x37`) are
  defined but unused in the whole corpus.

## Lowering patterns (measured — the compile targets)
- **Every function body ends with an implicit `Return(Nothing)`.** An explicit `return;` emits its own
  `Return(Nothing)` before it; `return E` → `Return(E)`.
- Assignment `lhs = rhs` → `Let(lhs, rhs)` (bool lhs → `LetBool`).
- A local/param reference → `LocalVariable(<its UProperty>)`; a member var → `InstanceVariable(<prop>)`.
- Int literal: 0→IntZero, 1→IntOne, fits a byte→IntConstByte, else IntConst. String→StringConst.
- **Operators and calls to `native(N)` functions → the native-opcode call (index N), args then
  `EndFunctionParms`.** N comes from the callee's declaration: `Object.uc` declares every operator as
  `native(N) … operator …` and built-ins like `Log` as `native(N) …`. Resolve by reading the callee
  UFunction's `iNative` from its home package (`env`). Overloaded operators resolve by operand type
  (e.g. int `+`=146, int `>`=151, `Log`=231). A non-native script function call → `VirtualFunction`
  (by name) or `FinalFunction` (by obj) per the callee's `FUNC_Final`.

## UFunction body (after the UStruct part `…ScriptText,Children,FriendlyName,Line,TextPos,ScriptSize,script`)
`u16 iNative (always present; 0 unless index-bound native) + u8 OperPrecedence + u32 FunctionFlags
(FUNC_*) + [u16 RepOffset iff FunctionFlags & FUNC_Net(0x40)]`. `ParmsSize`/`NumParms`/
`ReturnValueOffset` are NOT serialized — the engine recomputes them at link from the `Children`
properties (params first, then the return value, then locals). UState tail: `u64 ProbeMask, u64
IgnoreMask, u16 LabelTableOffset, u32 StateFlags`.

## Field chains (integration)
Two `Children`/`Next` linked lists of UField:
- **Class `Children`** → the class's first field; every member var, function, enum, struct and const
  is a UField child, threaded by `Next`.
- **Function `Children`** → the function's own first child: **params in declaration order, then the
  return value (`ReturnValue`, a UProperty of the return type), then locals.** Each is a UProperty
  export with `Outer` = the function.
`FunctionFlags` for a plain `function F(){}` = `0x00000002` (FUNC_Defined). Script of an empty body =
`Return(Nothing)` (`04 0b`). A function's export ObjectFlags = `0x00070004`, class-of = the
`Function` import. Verified against a fresh UCC compile (`UscFn`).
