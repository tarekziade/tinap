import asyncio
from queue import Queue, Empty

from tinap.util import append_upstream, remove_upstream
from tinap.throttler import BandwidthControl


class UpstreamConnection(asyncio.Protocol):
    def __init__(self, downstream):
        self.downstream = downstream
        self.offline_data = Queue()
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        append_upstream(self)
        # Dequeuing offline data if any...
        while True:
            try:
                data = self.offline_data.get_nowait()
            except Empty:
                break
            self.transport.write(data)

    def data_received(self, data):
        asyncio.ensure_future(self.downstream.forward_data(data))

    def forward_data(self, data):
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


class BaseServer(asyncio.Protocol):
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

    def data_received(self, data):
        """Data received from downstream.
        """

        async def _received():
            await asyncio.sleep(self.latency)
            await self.bandwidth_out.available(data)
            self.upstream.forward_data(data)

        asyncio.ensure_future(_received())

    def connection_lost(self, exc):
        if exc is not None:
            print(exc)
        if self.upstream is not None:
            self.upstream.close()

    def close(self):
        if self.transport is None:
            return
        if self.transport.is_closing():
            return
        self.transport.close()

    async def forward_data(self, data):
        """Data received from upstream.
        """
        await asyncio.sleep(self.latency)
        # XXX breaks everything.. something's not right..
        # await self.bandwidth_in.available(data)    # noqa
        if self.transport is None:
            return
        if self.transport.is_closing():
            return
        self.transport.write(data)
