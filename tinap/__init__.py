# encoding: utf-8
import signal
import sys
import os
import asyncio
import argparse
from queue import Queue, Empty


upstreams = []


class UpstreamConnection(asyncio.Protocol):
    """Forwards all data upstream.
    """

    def __init__(self, downstream):
        self.downstream = downstream
        self.transport = None
        self.offline_data = Queue()

    def connection_made(self, transport):
        self.transport = transport
        upstreams.append(self)
        while True:
            try:
                data = self.offline_data.get_nowait()
            except Empty:
                break
            self.transport.write(data)

    def data_received(self, data):
        self.downstream.write(data)

    def connection_lost(self, exc):
        upstreams.remove(self)
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


class Throttler(asyncio.Protocol):
    """ Creates the connection upstream to forward the data.
    With some throttling.
    """

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.upstream = None
        self.loop = asyncio.get_event_loop()

    def connection_made(self, transport):
        self.upstream = UpstreamConnection(transport)
        asyncio.async(
            self.loop.create_connection(lambda: self.upstream, self.host, self.port)
        )

    def data_received(self, data):
        self._throttle(data)
        self.upstream.forward_data(data)

    def connection_lost(self, exc):
        self.upstream.close()

    def _throttle(self, data):
        # XXX implement the throttling here
        pass


async def shutdown(sig, server, loop):
    for upstream in upstreams:
        upstream.close()
    server.close()
    print("Bye!")


def main():
    parser = argparse.ArgumentParser(description="utproxy")
    parser.add_argument("--upstream-port", type=int, help="upstream port", default=8080)

    parser.add_argument(
        "--upstream-host", type=str, help="upstream host", default="127.0.0.1"
    )

    parser.add_argument("--port", type=int, help="port", default=8888)

    parser.add_argument("--host", type=str, help="host", default="127.0.0.1")

    args = parser.parse_args()
    loop = asyncio.get_event_loop()

    def throttler_factory():
        return Throttler(args.upstream_host, args.upstream_port)

    print("Starting server %s:%d" % (args.host, args.port))
    server = loop.create_server(throttler_factory, args.host, args.port)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda sig=sig: asyncio.ensure_future(shutdown(sig, server, loop))
        )

    server = loop.run_until_complete(server)
    loop.run_until_complete(server.wait_closed())


if __name__ == "__main__":
    main()
