class UscRandomMutatorsGaps expands Mutator config(UscRandomMutatorsGaps);

var config String emptyDefaultField;

/*
function int SplitProbe(String str)
{
   local int x;
   x = 1;
   return x;
}
*/

function int SplitProbe(String str)
{
   local int x;
   x = 2;
   return x;
}

function bool ClassNameProbe(Mutator mut)
{
    local Mutator m;
    if (mut.Class.Name == m.Class.Name)
    {
        return True;
    }
    return False;
}

function Mutator CastCaseProbe(Object o)
{
    return mutator(o);
}

defaultproperties
{
    emptyDefaultField=
}
