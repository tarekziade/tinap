import unittest
import signal
import os
import time
import threading
import functools
import uuid
import asyncio

import requests

from tinap.tests.support import coserver
from tinap import main


class FakeArgs:
    upstream_host = "localhost"
    upstream_port = 8888
    port = 8887
    host = "localhost"
    rtt = 0.0
    inkbps = 0.0
    outkbps = 0.0
    mode = "forward"
    mapports = None
    desthost = None


class TestTinap(unittest.TestCase):

    res = {}

    def ping(self, uuid_):
        time.sleep(1)
        start = time.time()
        try:
            resp = requests.get("http://localhost:8887")
        except Exception as e:
            resp = e
        duration = time.time() - start
        self.res[uuid_] = duration, resp
        os.kill(os.getpid(), signal.SIGTERM)

    def _run_test(self, **kw):
        old_loop = asyncio.get_event_loop()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        uuid_ = str(uuid.uuid4())
        args = FakeArgs()
        for k, v in kw.items():
            setattr(args, k, v)
        thread = threading.Thread(target=functools.partial(self.ping, uuid_))
        thread.start()
        try:
            main(args)
        finally:
            thread.join()
            asyncio.set_event_loop(old_loop)
        duration, resp = self.res[uuid_]
        if isinstance(resp, requests.exceptions.ConnectionError):
            raise resp
        return duration, resp

    @coserver()
    def test_main(self):
        duration, resp = self._run_test()
        # make sure we're getting the directory listing through tinap
        self.assertTrue("Directory listing" in resp.text)

    @coserver()
    def test_rtt(self):
        duration, resp = self._run_test(rtt=2000)
        # we've added 200ms, the round trip should be higher
        self.assertTrue(duration > 2.0, duration)
        # the added duration should be less than 3 sec
        self.assertTrue(duration < 3.0, duration)
        # make sure we're getting the directory listing through tinap
        self.assertTrue("Directory listing" in resp.text)

    @coserver()
    def test_kpbs(self):
        # this should be slow, but work
        duration, resp = self._run_test(inkbps=5, outkbps=5, rtt=2)
        self.assertTrue("Directory listing" in resp.text)
