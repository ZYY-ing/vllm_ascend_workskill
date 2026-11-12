#requires -Version 7.4
# Local HTTPS CONNECT relay using the current Windows user's proxy credentials.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$UpstreamProxyHost,
    [ValidateRange(1, 65535)]
    [int]$UpstreamProxyPort = 8080,
    [ValidateRange(1, 65535)]
    [int]$ListenPort = 17889
)
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Net.Security;
using System.Security.Principal;
using System.Text;
using System.Threading.Tasks;
public static class WeightDownloadProxy {
  static string ProxyHost;
  static int ProxyPort;
  static async Task<string> Header(Stream s) {
    var b=new MemoryStream(); var one=new byte[1]; int tail=0;
    while(b.Length<65536) {
      if(await s.ReadAsync(one,0,1)==0) throw new IOException("Peer closed during headers");
      b.WriteByte(one[0]); tail=(tail<<8)|one[0]; if(tail==0x0d0a0d0a) return Encoding.ASCII.GetString(b.ToArray());
    }
    throw new IOException("Oversized header");
  }
  static string Value(string h,string name) {
    foreach(var line in h.Split(new[]{"\r\n"},StringSplitOptions.None))
      if(line.StartsWith(name+":",StringComparison.OrdinalIgnoreCase)) return line.Substring(name.Length+1).Trim();
    return "";
  }
  static async Task Handle(TcpClient client) {
    using(client) {
      TcpClient upstream=null;
      try {
        client.NoDelay=true; var local=client.GetStream(); var request=await Header(local).WaitAsync(TimeSpan.FromSeconds(30));
        var first=request.Split('\n')[0].Trim().Split(' ');
        if(first.Length<3 || first[0]!="CONNECT" || !first[1].EndsWith(":443")) throw new IOException("Only HTTPS CONNECT supported");
        string target=first[1];
        upstream=new TcpClient(); upstream.NoDelay=true;
        await upstream.ConnectAsync(ProxyHost,ProxyPort).WaitAsync(TimeSpan.FromSeconds(15)); var remote=upstream.GetStream();
        using(var auth=new NegotiateAuthentication(new NegotiateAuthenticationClientOptions {
          Package="Negotiate",Credential=CredentialCache.DefaultNetworkCredentials,
          TargetName="HTTP/"+ProxyHost,RequiredProtectionLevel=ProtectionLevel.None,
          AllowedImpersonationLevel=TokenImpersonationLevel.Identification
        })) {
          string token=null; bool ok=false;
          for(int i=0;i<5;i++) {
            string q="CONNECT "+target+" HTTP/1.1\r\nHost: "+target+"\r\nProxy-Connection: Keep-Alive\r\n";
            if(token!=null) q+="Proxy-Authorization: Negotiate "+token+"\r\n";
            var bytes=Encoding.ASCII.GetBytes(q+"\r\n"); await remote.WriteAsync(bytes,0,bytes.Length);
            var response=await Header(remote).WaitAsync(TimeSpan.FromSeconds(30)); var status=response.Split('\n')[0];
            if(status.Contains(" 200 ")) {ok=true;break;}
            if(!status.Contains(" 407 ")) throw new IOException("Upstream "+status.Trim());
            if(Value(response,"Transfer-Encoding").Length!=0) throw new IOException("Chunked proxy authentication response is unsupported");
            int length; if(int.TryParse(Value(response,"Content-Length"),out length)) {
              var discard=new byte[8192]; while(length>0) {var n=await remote.ReadAsync(discard,0,Math.Min(length,discard.Length));if(n==0)break;length-=n;}
            }
            string challenge=null;
            foreach(var line in response.Split(new[]{"\r\n"},StringSplitOptions.None)) {
              if(line.StartsWith("Proxy-Authenticate: Negotiate",StringComparison.OrdinalIgnoreCase)) challenge=line.Substring("Proxy-Authenticate: Negotiate".Length).Trim();
            }
            if(challenge==null) throw new IOException("Upstream does not offer Negotiate");
            NegotiateAuthenticationStatusCode code;
            token=auth.GetOutgoingBlob(challenge.Length==0?null:challenge,out code);
            if(code!=NegotiateAuthenticationStatusCode.Completed && code!=NegotiateAuthenticationStatusCode.ContinueNeeded) throw new IOException("SSPI "+code);
            if(Value(response,"Connection").Equals("close",StringComparison.OrdinalIgnoreCase)||Value(response,"Proxy-Connection").Equals("close",StringComparison.OrdinalIgnoreCase)) {
              upstream.Dispose();upstream=new TcpClient();upstream.NoDelay=true;await upstream.ConnectAsync(ProxyHost,ProxyPort).WaitAsync(TimeSpan.FromSeconds(15));remote=upstream.GetStream();
            }
          }
          if(!ok) throw new IOException("Proxy authentication did not complete");
        }
        var established=Encoding.ASCII.GetBytes("HTTP/1.1 200 Connection Established\r\n\r\n");
        await local.WriteAsync(established,0,established.Length);
        await Task.WhenAny(local.CopyToAsync(remote,262144),remote.CopyToAsync(local,262144));
      } catch(Exception e) {
        Console.Error.WriteLine(DateTime.Now.ToString("s")+" "+e.GetType().Name+" "+e.Message);
        try {var b=Encoding.ASCII.GetBytes("HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n");await client.GetStream().WriteAsync(b,0,b.Length);}catch{}
      } finally {if(upstream!=null)upstream.Dispose();}
    }
  }
  public static async Task Run(string host, int port, int listenPort) {
    ProxyHost=host; ProxyPort=port;
    var listener=new TcpListener(IPAddress.Loopback,listenPort);listener.Start(256);
    Console.WriteLine("HTTPS relay listening on 127.0.0.1:"+listenPort);
    while(true) {var c=await listener.AcceptTcpClientAsync();_=Handle(c);}
  }
}
'@
[WeightDownloadProxy]::Run($UpstreamProxyHost, $UpstreamProxyPort, $ListenPort).GetAwaiter().GetResult()
