class UscIpAddrProbe extends UdpLink;

// A member VAR typed to a struct declared in a DIFFERENT package (IpDrv's IpAddr, on
// InternetLink) - the real gap real UT99 IpServer.UdpServerUplink.MasterServerIpAddr hit.
var IpAddr Target;

// The param is named `Addr`, same as IpAddr's own field `Addr` - the real UT99
// IpServer.UdpServerUplink.Resolved shape (`MasterServerIpAddr.Addr = Addr.Addr;`). A bare
// `StructMember` field identity used to resolve to the PARAM's own export instead of the
// struct field's import (uscript-struct-member-access-confuses-a-local).
function SetTarget(IpAddr Addr)
{
	Target.Addr = Addr.Addr;
	Target.Port = Addr.Port;
}
