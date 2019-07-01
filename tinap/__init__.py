# encoding: utf-8
import signal
import asyncio
import argparse
import time

from queue import Queue, Empty


REMOVE_TCP_OVERHEAD = 1460.0 / 1500.0
UPSTREAMS = []


class UpstreamConnection(asyncio.Protocol):
    """Forwards all data upstream.
    """

    def __init__(self, downstream):
        self.downstream = downstream
        self.transport = None
        self.offline_data = Queue()

    def connection_made(self, transport):
        self.transport = transport
        UPSTREAMS.append(self)
        while True:
            try:
                data = self.offline_data.get_nowait()
            except Empty:
                break
            self.transport.write(data)

    def data_received(self, data):
        asyncio.ensure_future(self.downstream.forward_data(data))

    def connection_lost(self, exc):
        UPSTREAMS.remove(self)
        self.downstream.close()

    def forward_data(self, data):
        if self.transport is None:
            self.offline_data.put_nowait(data)
        else:
            self.transport.write(data)

    def close(self):
        if self.transport is None:
            return
        if self.transport.is_closing():
            return
        self.transport.close()


class BandwidthControl:
    def __init__(self, maxbps):
        self.last_tick = time.clock()
        self.maxbps = maxbps * 1000.0 / 8.0

    def _max_sendable(self):
        elapsed = time.clock() - self.last_tick
        return elapsed * self.maxbps

    async def available(self, data):
        if self.maxbps == 0:
            return
        extra = len(data) - self._max_sendable()
        if extra > 0:
            await asyncio.sleep(float(extra) / float(self.maxbps))

        self.last_tick = time.clock()


class Throttler(asyncio.Protocol):
    """ Creates the connection upstream to forward the data.
    With some throttling.
    """

    def __init__(self, host, port, latency, inkbps, outkbps):
        self.host = host
        self.port = port
        self.upstream = None
        self.loop = asyncio.get_event_loop()
        self.latency = latency
        self.bandwidth_in = BandwidthControl(inkbps)
        self.bandwidth_out = BandwidthControl(outkbps)
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.upstream = UpstreamConnection(self)
        asyncio.ensure_future(
            self.loop.create_connection(lambda: self.upstream, self.host, self.port)
        )

    async def forward_data(self, data):
        """Data received from upstream.
        """
        await asyncio.sleep(self.latency)
        await self.bandwidth_in.available(data)
        self.transport.write(data)

    def data_received(self, data):
        """Data received from downstream.
        """

        async def _received():
            await asyncio.sleep(self.latency)
            await self.bandwidth_out.available(data)
            self.upstream.forward_data(data)

        asyncio.ensure_future(_received())

    def connection_lost(self, exc):
        self.upstream.close()

    def close(self):
        if self.transport is not None:
            self.transport.close()


async def shutdown(sig, server, loop):
    for upstream in UPSTREAMS:
        upstream.close()
    server.close()
    print("Bye!")


def get_args():
    parser = argparse.ArgumentParser(description="Tinap port forwarder")
    parser.add_argument("--upstream-port", type=int, help="upstream port", default=8080)

    parser.add_argument(
        "--upstream-host", type=str, help="upstream host", default="127.0.0.1"
    )
    parser.add_argument("--port", type=int, help="port", default=8888)
    parser.add_argument("--host", type=str, help="host", default="127.0.0.1")

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
    if args is None:
        args = get_args()

    loop = asyncio.get_event_loop()

    def throttler_factory():
        return Throttler(
            args.upstream_host,
            args.upstream_port,
            args.rtt / 2000.,
            args.inkbps * REMOVE_TCP_OVERHEAD,
            args.outkbps * REMOVE_TCP_OVERHEAD,
        )

    print("Starting server %s:%d" % (args.host, args.port))
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
