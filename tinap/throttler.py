# encoding: utf-8
import asyncio
import time


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
            print("not ready")
            await asyncio.sleep(float(extra) / float(self.maxbps))
        self.last_tick = time.perf_counter()
