class UscNetConnectionProbe expands Object;
function bool Check(Object O)
{
    return NetConnection(O) != None;
}
