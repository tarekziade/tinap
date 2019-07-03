=====
tinap
=====

tinap -- stands for This Is Not A Proxy

Features:
- Plain port forwarding or Socks5 proxy mode
- Network traffic shaping copied from `tsproxy <This is intended to replace tsproxy https://github.com/WPO-Foundation/tsproxy>`_


How to use
==========

Tinap has a few general options, followed by a mode (forward or socks)::

   $ tinap --help
   usage: tinap [-h] [--port PORT] [--host HOST] [-r RTT] [-i INKBPS]
               [-o OUTKBPS]
               {forward,socks5} ...

   Tinap port forwarder

   positional arguments:
   {forward,socks5}      Mode of operation
      forward             Port forwarding
      socks5              Socks5 Pproxy

   optional arguments:
   -h, --help            show this help message and exit
   --port PORT           port
   --host HOST           host
   -r RTT, --rtt RTT     Round Trip Time Latency (in ms).
   -i INKBPS, --inkbps INKBPS
                           Download Bandwidth (in 1000 bits/s - Kbps).
   -o OUTKBPS, --outkbps OUTKBPS
                           Upload Bandwidth (in 1000 bits/s - Kbps).

The forward mode needs to know where to forward things::

   $ tinap forward --help
   usage: tinap forward [-h] [--upstream-port UPSTREAM_PORT]
                        [--upstream-host UPSTREAM_HOST]

   optional arguments:
   -h, --help            show this help message and exit
   --upstream-port UPSTREAM_PORT
                           upstream port
   --upstream-host UPSTREAM_HOST
                           upstream host

And the socks mode has its own extra options, copied from tsproxy::

   $ tinap socks5 --help
   usage: tinap socks5 [-h] [-d DESTHOST] [-m MAPPORTS]

   optional arguments:
   -h, --help            show this help message and exit
   -d DESTHOST, --desthost DESTHOST
                           Redirect all outbound connections to the specified
                           host.
   -m MAPPORTS, --mapports MAPPORTS
                           Remap outbound ports. Comma-separated list of
                           original:new with * as a wildcard.--mapports
                           '443:8443,*:8080'


Configuration examples
======================

XXX show 2 full setups:
- firefox <> tinap <> wpr
- firefox <> tinap <> mitmproxy


