class UscImportIdentityProbe expands Actor;

// Reproduces the real UT99 `IpServer` collision (`uscript-cross-package-import-identity-collides`):
// `GameInfo`'s own member field `GameReplicationInfo` shares a display name with its TYPE, the class
// `Engine.GameReplicationInfo` -- two distinct import rows (a Class and an ObjectProperty) that must
// coexist under one display name.
function int TestFn()
{
    return Level.Game.GameReplicationInfo.Region;
}
