class NoGunsMutator extends Mutator;

// This function is called every time a new item is about to be spawned on the map.
function bool CheckReplacement(Actor Other, out byte bSuperRelevant)
{
    // If the actor being spawned is a weapon, prevent it from spawning.
    if (Weapon(Other) != None)
    {
        return false;
    }
    
    return Super.CheckReplacement(Other, bSuperRelevant);
}

// This function is called when a player spawns in the game.
function ModifyPlayer(Pawn Other)
{
    local Inventory Inv;
    
    Super.ModifyPlayer(Other);
    
    // Loop through the player's inventory and remove all weapons.
    Inv = Other.Inventory;
    while (Inv != None)
    {
        if (Weapon(Inv) != None || Inv.IsA('Enforcer'))  // Also explicitly check for the Enforcer class
        {
            Inv.Destroy();
        }
        Inv = Inv.Inventory;
    }
    
    // Ensure the player doesn't spawn with any weapons.
    Other.Weapon = None;
    Other.PendingWeapon = None;
}

