# encoding: utf-8
import signal
import asyncio
import argparse

from tinap.fwd import ForwardServer
from tinap.socks import SocksServer
from tinap.util import shutdown

# TCP overhead (value taken from tsproxy)
REMOVE_TCP_OVERHEAD = 1460.0 / 1500.0


def get_args():
    parser = argparse.ArgumentParser(description="Tinap port forwarder")
    parser.add_argument("--upstream-port", type=int, help="upstream port", default=8080)

    parser.add_argument(
        "--upstream-host", type=str, help="upstream host", default="127.0.0.1"
    )
    parser.add_argument("--port", type=int, help="port", default=8888)
    parser.add_argument("--host", type=str, help="host", default="127.0.0.1")

    parser.add_argument("--mode", choices=["forward", "socks5"],
            type=str, help="", default="forward")
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

    return parser.parse_args()


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
            klass = ForwardServer
        elif args.mode == "socks5":
            klass = SocksServer
        else:
            raise NotImplementedError()

        return klass(
            args.upstream_host,
            args.upstream_port,
            # the latency is in seconds, and divided by two for each direction.
            args.rtt / 2000.,
            args.inkbps * REMOVE_TCP_OVERHEAD,
            args.outkbps * REMOVE_TCP_OVERHEAD,
        )

    print("Starting server %s:%d" % (args.host, args.port))
    print("Mode of operation: %s" % args.mode)
    if args.rtt > 0:
        print("Round Trip Latency (ms): %.d" % args.rtt)
    else:
        print("No latency added.")
    if args.inkbps > 0:
        print("Download bandwidth (kbps): %s" % args.inkbps)
    else:
        print("Free Download bandwidth")
    if args.outkbps > 0:
        print("Upload bandwidth (kbps): %s" % args.outkbps)
    else:
        print("Free Upload bandwidth")

    server = loop.create_server(throttler_factory, args.host, args.port)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.ensure_future(shutdown(sig, server, loop))
        )

    server = loop.run_until_complete(server)
    loop.run_until_complete(server.wait_closed())


if __name__ == "__main__":
    main()
