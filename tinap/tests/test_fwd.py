import unittest
import signal
import os
import time
import threading

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

    res = []

    def ping(self):
        time.sleep(1)
        start = time.time()
        try:
            resp = requests.get("http://localhost:8887")
        except Exception as e:
            resp = e
        duration = time.time() - start
        self.res.append((duration, resp))
        os.kill(os.getpid(), signal.SIGTERM)

    def _run_test(self, **kw):
        args = FakeArgs()
        for k, v in kw.items():
            setattr(args, k, v)
        thread = threading.Thread(target=self.ping)
        thread.start()
        main(args)
        duration, resp = self.res[-1]
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
        duration, resp = self._run_test(rtt=200)
        # we've added 200ms, the round trip should be higher
        self.assertTrue(duration > 0.2, duration)
        # make sure we're getting the directory listing through tinap
        self.assertTrue("Directory listing" in resp.text)

    @coserver()
    def test_kpbs(self):
        # this should be slow, but work
        duration, resp = self._run_test(inkbps=1, outkbps=1)
        self.assertTrue("Directory listing" in resp.text)

    @coserver()
    def test_kpbs_and_rtt(self):
        # this should be slow, but work
        duration, resp = self._run_test(inkbps=10, outkbps=10, rtt=20)
        self.assertTrue("Directory listing" in resp.text)
