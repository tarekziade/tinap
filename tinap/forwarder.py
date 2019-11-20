import asyncio
from queue import Queue, Empty

from tinap.util import append_upstream, remove_upstream, get_logger
from tinap.throttler import Throttler


class UpstreamConnection(asyncio.Protocol):
    def __init__(self, downstream):
        self.downstream = downstream
        self.offline_data = Queue()
        self.transport = None
        self.logger = get_logger()

    def connection_made(self, transport):
        self.logger.debug("Connection made")
        self.transport = transport
        append_upstream(self)
        # Dequeuing offline data if any...
        # XXX move this to asyncio.Queue
        while True:
            try:
                data = self.offline_data.get_nowait()
            except Empty:
                break
            self.transport.write(data)

    def data_received(self, data):
        self.downstream.forward_data(data)

    def write(self, data):
        if self.transport is None:
            self.offline_data.put_nowait(data)
        else:
            self.transport.write(data)

    def connection_lost(self, *args):
        remove_upstream(self)
        self.downstream.close()

    def close(self):
        if self.transport is None:
            return
        if self.transport.is_closing():
            return
        self.transport.close()


class Forwarder(asyncio.Protocol):
    def __init__(self, host, port, upstream_host, upstream_port, args):
        self.downstream_host = host
        self.downstream_port = port
        self.host = upstream_host
        self.port = upstream_port
        self.upstream = None
        self.loop = asyncio.get_event_loop()
        self.latency = args.rtt
        self.data_in = None
        self.data_out = None
        self.outkbps = args.outkbps
        self.inkbps = args.inkbps
        self.transport = None
        self.args = args
        self.logger = get_logger()

    async def _sconnect(self):
        try:
            await asyncio.wait_for(
                self.loop.create_connection(
                    lambda: self.upstream, self.host, self.port
                ),
                timeout=5,
            )
        except (asyncio.TimeoutError, OSError):
            print("Timeout or error connecting to %s:%d" % (self.host, self.port))
            self.close()
            return
        self.data_in.start()
        self.data_out.start()

    def connection_made(self, transport):
        self.transport = transport
        self.upstream = UpstreamConnection(self)
        self.data_in = Throttler("up", self.upstream, self.latency, self.inkbps)
        self.data_out = Throttler("down", self.transport, self.latency, self.outkbps)
        asyncio.ensure_future(self._sconnect())

    def connection_lost(self, exc):
        if exc is not None:
            print(exc)
        if self.upstream is not None:
            self.upstream.close()

    def close(self):
        async def _drain():
            if self.data_in is not None:
                await self.data_in.stop()
            if self.data_out is not None:
                await self.data_out.stop()
            if self.transport is None:
                return
            if self.transport.is_closing():
                return
            self.transport.close()

        asyncio.ensure_future(_drain())

    def forward_data(self, data):
        self.logger.debug(
            "%s:%d => %s:%s",
            self.downstream_host,
            self.downstream_port,
            self.host,
            self.port,
        )
        self.data_out.put(data)

    def data_received(self, data):
        self.logger.debug(
            "%s:%d <= %s:%s",
            self.downstream_host,
            self.downstream_port,
            self.host,
            self.port,
        )
        self.data_in.put(data)
