=====
tinap
=====

tinap -- stands for This Is Not A Proxy

**port forwarding with network shaping**

This is intended to replace tsproxy https://github.com/WPO-Foundation/tsproxy
for throttling network connections.

Instead of implementing a SOCKS or HTTP proxy, this simply passes along
the data it receives to another port, and adds the throttling.

The benefit of using a raw stream TCP server is that we can put it
in front of any server to shape the network. 

For instance, it can be used as the HTTP proxy in Firefox, as long
as it's put in front of a real proxy, like Mitmproxy.

