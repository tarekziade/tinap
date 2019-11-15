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


def get_args():
    parser = argparse.ArgumentParser(description="Tinap port forwarder")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose mode", default=False
    )
    parser.add_argument("--port", type=int, help="port", default=8888)
    parser.add_argument("--host", type=str, help="host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, help="upstream port", default=8080)
    parser.add_argument(
        "--upstream-host", type=str, help="upstream host", default="127.0.0.1"
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

    logger = set_logger(args.verbose and logging.DEBUG or logging.INFO)

    loop = asyncio.get_event_loop()
    logger.info(
        "Starting Forwarder %s:%d => %s:%s"
        % (args.host, args.port, args.upstream_host, args.upstream_port)
    )
    if args.verbose:
        if args.rtt > 0:
            logger.debug("Round Trip Latency (ms): %.d" % args.rtt)
            # the latency is in seconds, and divided by two for each direction.
            args.rtt = args.rtt / 2000.0
        else:
            logger.debug("No latency added.")
        if args.inkbps > 0:
            logger.debug("Download bandwidth (kbps): %s" % args.inkbps)
            args.inkbps = args.inkbps * REMOVE_TCP_OVERHEAD
        else:
            logger.debug("Unlimited Download bandwidth")
        if args.outkbps > 0:
            logger.debug("Upload bandwidth (kbps): %s" % args.outkbps)
            args.outkbps = args.outkbps * REMOVE_TCP_OVERHEAD
        else:
            logger.debug("Unlimited Upload bandwidth")

    server = loop.create_server(
        functools.partial(Forwarder, args), args.host, args.port
    )
    server = loop.run_until_complete(server)
    assert server is not None

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig, lambda sig=sig: asyncio.ensure_future(shutdown(server))
            )
    else:
        try:
            import win32api
        except ImportError:
            print("You need to run 'pip install pywin32'")
            raise
        win32api.SetConsoleCtrlHandler(functools.partial(loop.call_soon_threadsafe, sync_shutdown, server), True) 

    try:
        loop.run_until_complete(server.wait_closed())
    finally:
        loop.close()
    print("Bye")

if __name__ == "__main__":
    main()
