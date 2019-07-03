# encoding: utf-8
import asyncio
import time
from queue import Queue, Empty


class BandwidthControl:
    """Adds delays to limit the bandwidth, given a max bps.
    """

    def __init__(self, maxbps):
        self.last_tick = time.perf_counter()
        self.maxbps = maxbps * 1000.0 / 8.0

    def _max_sendable(self):
        elapsed = time.perf_counter() - self.last_tick
        return elapsed * self.maxbps

    async def available(self, data):
        if self.maxbps == 0:
            return
        extra = len(data) - self._max_sendable()
        if extra > 0:
            await asyncio.sleep(float(extra) / float(self.maxbps))
        self.last_tick = time.perf_counter()


class Throttler:
    def __init__(self, name, transport, latency, bandwidth):
        self._data = Queue()
        if bandwidth == 0:
            self._ctrl = None
        else:
            self._ctrl = BandwidthControl(bandwidth)
        self.latency = latency
        self.running = False
        self.transport = transport
        self.name = name

    def start(self):
        asyncio.ensure_future(self._dequeue())
        self.running = True

    def stop(self):
        self.running = False

    def put(self, data):
        self._data.put_nowait(data)

    async def _dequeue(self):
        # XXX CPU intensive ? can be improved with a blocking wait
        while self.running:
            try:
                data = self._data.get_nowait()
            except Empty:
                break
            await asyncio.sleep(self.latency)
            if self._ctrl is not None:
                await self._ctrl.available(data)
            self.transport.write(data)
        asyncio.ensure_future(self._dequeue())
