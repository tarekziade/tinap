import unittest
import signal
import os
import time
import threading

import requests

from tinap.tests.support import coserver
from tinap import main


class TestTinap(unittest.TestCase):
    @coserver()
    def test_main(self):
        # the server is running on port 8888
        # let's set tinap on 8887
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

        args = FakeArgs()
        res = []

        def ping():
            time.sleep(1)
            res.append(requests.get("http://localhost:8887"))
            os.kill(os.getpid(), signal.SIGTERM)

        thread = threading.Thread(target=ping)
        thread.start()
        main(args)

        # make sure we're getting the directory listing through tinap
        self.assertTrue("Directory listing" in res[0].text)
