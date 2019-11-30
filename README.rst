=====
tinap
=====

tinap -- stands for "This Is Not A Proxy"

It's also a beautiful place in Bangladesh with the biggest waterfall of that country.

The Urban Dictionary also `says <https://www.urbandictionary.com/define.php?term=tinap>`_ it's "young people who go to rave parties who are dressed in bright and extreme styles of clothing".

Features:

- Plain port forwarding or Socks5 proxy mode
- Network traffic shaping copied from `tsproxy <This is intended to replace tsproxy https://github.com/WPO-Foundation/tsproxy>`_

Installation
============

Tinap is a pure Python script, you can install it with::

   $ pip install tinap

If you are under windows you need to install pywin32 as well::

   $ pip install pywin32



How to use
==========

Tinap has a few general options, followed by a mode (forward or socks)::

   $ tinap --help
   usage: tinap [-h] [-v] [--host HOST] [--upstream-host UPSTREAM_HOST]
               [--port PORT] [--upstream-port UPSTREAM_PORT]
               [--port-mapping PORT_MAPPING] [-r RTT] [-i INKBPS] [-o OUTKBPS]

   Tinap port forwarder

   optional arguments:
   -h, --help            show this help message and exit
   -v, --verbose         Verbose mode
   --host HOST           host
   --upstream-host UPSTREAM_HOST
                           upstream host
   --port PORT           port
   --upstream-port UPSTREAM_PORT
                           upstream port
   --port-mapping PORT_MAPPING
                           Comma-separated list of port forwarding rules each
                           rule is composed of <source_host>:<source_port>/<targe
                           t_host>:<target_port> Example (forwards port 80 and
                           443 to 8080 and 8282): 127.0.0.1:80/127.0.0.1:8080,127
                           .0.0.1:443/127.0.0.1:8282
   -r RTT, --rtt RTT     Round Trip Time Latency (in ms).
   -i INKBPS, --inkbps INKBPS
                           Download Bandwidth (in 1000 bits/s - Kbps).
   -o OUTKBPS, --outkbps OUTKBPS
                           Upload Bandwidth (in 1000 bits/s - Kbps).


Configuration examples
======================

XXX show 2 full setups:
- firefox <> tinap <> wpr
- firefox <> tinap <> mitmproxy


