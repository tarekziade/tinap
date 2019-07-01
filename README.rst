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

For instance, it can be used as the HTTP(S) proxy in Firefox, as long
as it's put in front of a real proxy, like Mitmproxy.


Setting up tinap with mitmproxy
===============================

You don't need to configure a new certificate in this configuration.

1. run tinap locally on port 8080, set to forward requests to mitmproxy::

   $ tinap --port 8080 --upstream-port 8888

2. run mitmproxy on port 8888::

   $ mitmdump --listen-port 8888

3. set your browser proxy to point to localhost:8080


Adding delays
=============

tinap can be used with the same options than tsproxy. Example for a regular 3G::

   $ tinap --port 8080 --upstream-port 8888 --inkbps 750 --outkbps 250 --rtt 100
