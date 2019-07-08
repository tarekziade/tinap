# encoding: utf-8
import signal
import asyncio
import argparse
import sys

from tinap.base import BaseServer
from tinap.socks import SocksServer
from tinap.util import shutdown, parse_port_mappings

# TCP overhead (value taken from tsproxy)
REMOVE_TCP_OVERHEAD = 1460.0 / 1500.0


def get_args():
    parser = argparse.ArgumentParser(description="Tinap port forwarder")
    parser.add_argument("--port", type=int, help="port", default=8888)
    parser.add_argument("--host", type=str, help="host", default="127.0.0.1")
    subparsers = parser.add_subparsers(help="Mode of operation", dest="mode")

    # fwd mode
    parser_fwd = subparsers.add_parser("forward", help="Port forwarding")
    parser_fwd.add_argument(
        "--upstream-port", type=int, help="upstream port", default=8080
    )
    parser_fwd.add_argument(
        "--upstream-host", type=str, help="upstream host", default="127.0.0.1"
    )

    # socks5 mode
    parser_socks5 = subparsers.add_parser("socks5", help="Socks5 Proxy")
    parser_socks5.add_argument(
        "-d",
        "--desthost",
        help="Redirect all outbound connections to the specified host.",
    )
    parser_socks5.add_argument(
        "-m",
        "--mapports",
        help=(
            "Remap outbound ports. Comma-separated list of original:new with * as a wildcard."
            "--mapports '443:8443,*:8080'"
        ),
    )

    # throttling options
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

    args = parser.parse_args()
    if args.mode is None:
        print("You need to define a mode of operation.")
        print("")
        parser.print_help()
        return sys.exit(1)

    return args


def main(args=None):
    """
    Creates the asyncio loop with a Throttler handler for each
    new connection.
    """
    if args is None:
        args = get_args()

    loop = asyncio.get_event_loop()

    def throttler_factory():
        if args.mode == "forward":
            klass = BaseServer
        elif args.mode == "socks5":
            klass = SocksServer
        else:
            raise NotImplementedError()
        return klass(args)

    print("Starting server %s:%d" % (args.host, args.port))
    print("Mode of operation: %s" % args.mode)
    if args.rtt > 0:
        print("Round Trip Latency (ms): %.d" % args.rtt)
        # the latency is in seconds, and divided by two for each direction.
        args.rtt = args.rtt / 2000.0
    else:
        print("No latency added.")
    if args.inkbps > 0:
        print("Download bandwidth (kbps): %s" % args.inkbps)
        args.inkbps = args.inkbps * REMOVE_TCP_OVERHEAD
    else:
        print("Free Download bandwidth")
    if args.outkbps > 0:
        print("Upload bandwidth (kbps): %s" % args.outkbps)
        args.outkbps = args.outkbps * REMOVE_TCP_OVERHEAD
    else:
        print("Free Upload bandwidth")

    if args.mode == "socks5" and args.mapports is not None:
        args.mapports = parse_port_mappings(args.mapports)
        print("Port mapping: %s" % args.mapports)

    if args.mode == "socks5" and args.desthost:
        print("Using %s for all outbound connections" % args.desthost)

    if args.mode == "forward":
        print("Upstream server: %s:%s" % (args.upstream_host, args.upstream_port))
    server = loop.create_server(throttler_factory, args.host, args.port)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.ensure_future(shutdown(sig, server, loop))
        )

    server = loop.run_until_complete(server)
    loop.run_until_complete(server.wait_closed())


if __name__ == "__main__":
    main()
