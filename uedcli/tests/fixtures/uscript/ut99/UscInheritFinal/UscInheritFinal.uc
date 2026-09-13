class UscInheritFinal expands UWindowDialogClientWindow;
function Created()
{
    local int w, h;
    SetSize(512, 512);
    Super.Created();
    w = WinWidth;
    h = WinHeight;
    SetSize(w, h);
}
