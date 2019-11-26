# encoding: utf-8
import signal
import asyncio
import argparse
import functools
import logging
import sys

from tinap.forwarder import Forwarder
from tinap.util import shutdown, sync_shutdown, set_logger

# TCP overhead (value taken from tsproxy)
REMOVE_TCP_OVERHEAD = 1460.0 / 1500.0
_PORT_MAPPING_HELP = """\
Comma-separated list of port forwarding rules each rule
is composed of <source_host>:<source_port>/<target_host>:<target_port>

Example (forwards port 80 and 443 to 8080 and 8282):

  127.0.0.1:80/127.0.0.1:8080,127.0.0.1:443/127.0.0.1:8282
"""


def get_args():
    parser = argparse.ArgumentParser(description="Tinap port forwarder")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose mode", default=False
    )
    # port mapping options
    parser.add_argument("--host", type=str, help="host", default="127.0.0.1")
    parser.add_argument(
        "--upstream-host", type=str, help="upstream host", default="127.0.0.1"
    )
    parser.add_argument("--port", type=int, help="port", default=8888)
    parser.add_argument("--upstream-port", type=int, help="upstream port", default=8080)
    parser.add_argument(
        "--port-mapping", type=str, help=_PORT_MAPPING_HELP, default=None
    )

    parser.add_argument(
        "-r", "--rtt", type=float, default=0.0, help="Round Trip Time Latency (in ms)."
    )
    parser.add_argument(
        "-i",
        "--inkbps",
        type=float,
        default=0.0,
        help="Download Bandwidth (in 1000 bits/s - Kbps).",
    )
    parser.add_argument(
        "-o",
        "--outkbps",
        type=float,
        default=0.0,
        help="Upload Bandwidth (in 1000 bits/s - Kbps).",
    )

    return parser.parse_args()


def main(args=None):
    """
    Creates the asyncio loop with a Throttler handler for each
    new connection.
    """
    if args is None:
        args = get_args()

    port_mapping = {}
    if args.port_mapping is not None:
        for item in args.port_mapping.split(","):
            item = item.strip()
            if not item:
                continue
            source, target = item.split("/")
            source_host, source_port = source.split(":")
            target_host, target_port = target.split(":")
            port_mapping[source_host, int(source_port)] = target_host, int(target_port)
    else:
        port_mapping[args.host, args.port] = args.upstream_host, args.upstream_port

    logger = set_logger(args.verbose and logging.DEBUG or logging.INFO)
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()

    if args.verbose:
        for (host, port), (upstream_host, upstream_port) in port_mapping.items():
            logger.info(
                "Starting Forwarder %s:%d => %s:%s"
                % (host, port, upstream_host, upstream_port)
            )
        if args.rtt > 0:
            logger.debug("Round Trip Latency (ms): %d" % args.rtt)
        else:
            logger.debug("No latency added.")
        if args.inkbps > 0:
            logger.debug("Download bandwidth (kbps): %s" % args.inkbps)
        else:
            logger.debug("Unlimited Download bandwidth")
        if args.outkbps > 0:
            logger.debug("Upload bandwidth (kbps): %s" % args.outkbps)
        else:
            logger.debug("Unlimited Upload bandwidth")
    else:

        for (host, port), (upstream_host, upstream_port) in port_mapping.items():
            logger.info(
                "Starting Forwarder %s:%d => %s:%d (rtt=%d, inkbps=%s, outkbps=%s)"
                % (
                    host,
                    port,
                    upstream_host,
                    upstream_port,
                    args.rtt,
                    args.inkbps,
                    args.outkbps,
                )
            )

    if args.rtt > 0:
        # the latency is in seconds, and divided by two for each direction.
        args.rtt = args.rtt / 2000.0
    if args.outkbps > 0:
        args.outkbps = args.outkbps * REMOVE_TCP_OVERHEAD
    if args.inkbps > 0:
        args.inkbps = args.inkbps * REMOVE_TCP_OVERHEAD

    servers = []
    for (host, port), (upstream_host, upstream_port) in port_mapping.items():
        server = loop.create_server(
            functools.partial(
                Forwarder, host, port, upstream_host, upstream_port, args
            ),
            host,
            port,
        )
        server = loop.run_until_complete(server)
        assert server is not None
        servers.append(server)

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig, lambda sig=sig: asyncio.ensure_future(shutdown(servers))
            )
    else:
        try:
            import win32api
        except ImportError:
            print("You need to run 'pip install pywin32'")
            raise
        win32api.SetConsoleCtrlHandler(
            functools.partial(loop.call_soon_threadsafe, sync_shutdown, servers), True
        )

    try:
        for server in servers:
            loop.run_until_complete(server.wait_closed())
    finally:
        loop.close()
    print("Bye")


if __name__ == "__main__":
    main()
