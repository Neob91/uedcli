"""Instruction-level simulator of the FindBestSplit CANDIDATE-SELECTION loop
(Editor.dll FindBestSplit, RVA 0x335d0). Traces the asm register/stack state
exactly as decoded, and reports the SEQUENCE of chosen candidate indices.

We model only candidate selection (the part that was buggy): which poly indices
get used as the splitter `i`. The inner classify loop and score are validated
separately/structurally; here we want the candidate sequence the binary visits.

Register/stack map decoded from the disassembly:
  [ebp+8]   = num            (esi at entry)
  [ebp+0xc] = poly array     (edi)
  ebx       = inc            ([ebp-0x18] mirror)
  [ebp-0x40]= all_structural (1 if every poly is structural)
  [ebp-0x24]= threshold      (slot accumulator)
  esi       = current candidate index
  [ebp-0x3c]= esi mirror (esi-1 then esi)

A poly is "structural-skip" iff (flags & 0x28) != 0 AND (flags & 0x4000000)==0
i.e. structural-non-portal. test al,0x28 uses only the low byte; 0x28 fits in al.
"""


def chosen_candidates_asm(num: int, inc: int, flags: list[int]) -> list[int]:
    """Faithful trace of the candidate loop. Returns list of candidate indices
    `i` for which the inner classify/score body executes."""
    PF_STRUCTURAL = 0x28
    PF_PORTAL = 0x04000000

    # 0x336cb-0x336ef: all_structural pre-pass.
    # ecx scans from 0 while poly[ecx] structural (flags&0x28); all_structural = (ecx>=num)
    ecx = 0
    while ecx < num and (flags[ecx] & PF_STRUCTURAL):
        ecx += 1
    all_structural = 1 if ecx >= num else 0

    # 0x336ff: xor esi,esi ; [ebp-0x24]=0  (esi=0, threshold=0)
    esi = 0
    threshold = 0
    chosen: list[int] = []

    while True:
        # 0x33707: cmp esi,edx(num); jge end
        if esi >= num:
            break
        # 0x3370f-0x33731: threshold = threshold + inc  (ecx = [ebp-0x24]+ebx; [ebp-0x24]=ecx)
        # Note: at loop re-entry (0x338c1) esi has been set to [ebp-0x24] (== prior threshold).
        ecx = threshold + inc
        threshold = ecx  # [ebp-0x24] = threshold+inc

        # 0x33726: dec esi ; [ebp-0x3c]=esi  -> sets up the inner skip-advance "do/while"
        esi -= 1
        # inner skip-advance loop, top at 0x33734
        while True:
            # 0x33734: inc esi ; [ebp-0x3c]=esi
            esi += 1
            # 0x3373b: cmp esi,ecx(threshold) ; jge 0x338c1 (slot exhausted -> loop back, no cand)
            if esi >= ecx:
                cand = None
                break
            # 0x33743: cmp esi,edx(num) ; jge 0x338c1 (ran off end -> loop back, no cand)
            if esi >= num:
                cand = None
                break
            # 0x3374b: eax = flags[esi]; test al,0x28 ; je 0x33762 (not structural -> eligible)
            f = flags[esi]
            if (f & PF_STRUCTURAL):
                # 0x33755: test eax,0x4000000 ; jne 0x33762 (portal -> eligible)
                if not (f & PF_PORTAL):
                    # 0x3375c: cmp [ebp-0x40](all_structural),0 ; je 0x33734 (skip, advance)
                    if all_structural == 0:
                        continue  # skip this poly, advance esi within the window
                    # all_structural != 0 -> fall through, eligible
            # eligible: 0x33762 cmp esi,edx ; jge 0x338c1 (redundant safety) then run body
            if esi >= num:
                cand = None
                break
            cand = esi
            break

        if cand is not None:
            chosen.append(cand)
        # whether or not a candidate ran, control reaches 0x338c1:
        # 0x338c1: esi = [ebp-0x24] (threshold) ; loop back to 0x33707
        esi = threshold

    return chosen
