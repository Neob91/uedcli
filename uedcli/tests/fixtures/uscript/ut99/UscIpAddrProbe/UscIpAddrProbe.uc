class UscIpAddrProbe extends UdpLink;

// A member VAR typed to a struct declared in a DIFFERENT package (IpDrv's IpAddr, on
// InternetLink) - the real gap real UT99 IpServer.UdpServerUplink.MasterServerIpAddr hit.
var IpAddr Target;

function SetTarget(IpAddr NewTarget)
{
	Target.Addr = NewTarget.Addr;
	Target.Port = NewTarget.Port;
}
