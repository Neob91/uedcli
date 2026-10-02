class UscStateForeach expands Actor;

function Trigger(Actor Other, Pawn EventInstigator) {
    GotoState('Active');
}

function CleanUp() {
    local Inventory Inv;

    foreach AllActors(class'Inventory', Inv) {
        Inv.Destroy();
    }
}

state Active {
Begin:
    Sleep(1.0);
    GotoState('');
}
