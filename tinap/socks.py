import asyncio
from struct import pack, unpack
from enum import IntEnum, unique
import socket

from tinap.base import UpstreamConnection, BaseServer
from tinap.throttler import Throttler
from tinap.util import resolve


@unique
class State(IntEnum):
    HELLO = 1
    AUTH = 2
    INIT = 3
    DATA = 4


@unique
class Method(IntEnum):
    NOAUTH = 0
    USER = 2
    NOAC = 255


@unique
class Command(IntEnum):
    CONNECT = 1
    BIND = 2
    UDP_ASSOCIATE = 3


@unique
class Connection(IntEnum):
    IPV4 = 1
    DOMAIN = 3
    IPV6 = 4


class SocksServer(BaseServer):
    def __init__(self, args):
        BaseServer.__init__(self, args)
        self.port_mapping = args.mapports
        self.dest_host = args.desthost
        self.dest_address = None

    def _get_dest_port(self, port):
        if self.port_mapping is None:
            return port
        src_port = str(port)
        if src_port in self.port_mapping:
            return self.port_mapping[src_port]
        elif "default" in self.port_mapping:
            return self.port_mapping["default"]
        return port

    def connection_made(self, transport):
        self.transport = transport
        self.state = State.HELLO
        self.method = Method.USER

    def data_received(self, data):
        if self.state is State.HELLO:
            version, nmethods = unpack("!BB", data[0:2])
            if version != 5:
                raise Exception("Unsupported version %d" % version)
            methods = unpack("!" + "B" * nmethods, data[2 : 2 + nmethods])
            if Method.USER in methods:
                self.method = Method.USER
            elif Method.NOAUTH in methods:
                self.method = Method.NOAUTH
            else:
                self.method = Method.NOAC

            data_s = b"\05" + pack("!B", self.method)
            self.transport.write(data_s)

            if self.method is Method.NOAC:
                self.transport.close()
                return
            if self.method is Method.NOAUTH:
                self.state = State.INIT
            else:
                self.state = State.AUTH

        elif self.state is State.AUTH:
            raise NotImplementedError()

        elif self.state is State.INIT:
            ver, cmd, rsv, atype = unpack("!BBBB", data[0:4])
            if cmd == Command.CONNECT:
                host, port = self.parse_connect(atype, data)
                asyncio.ensure_future(self.connect(host, port))
                self.state = State.DATA
            elif cmd == Command.BIND:
                pass
            else:
                raise NotImplementedError()
        elif self.state is State.DATA:
            BaseServer.data_received(self, data)

    async def connect(self, host, port):
        port = self._get_dest_port(port)
        if self.dest_host is not None and self.dest_address is None:
            host = self.dest_address = await resolve(self.dest_host, port)

        def upstream():
            self.upstream = UpstreamConnection(self)
            self.data_in = Throttler("up", self.upstream, self.latency, self.inkbps)
            self.data_out = Throttler(
                "down", self.transport, self.latency, self.outkbps
            )
            return self.upstream

        try:
            t, c = await asyncio.wait_for(
                self.loop.create_connection(upstream, host, port), timeout=5
            )
        except (asyncio.TimeoutError, OSError):
            print("Timeout or error connecting to %s:%d" % (host, port))
            self.close()
            return
        self.upstream = c
        hostip, port = t.get_extra_info("sockname")
        host = unpack("!I", socket.inet_aton(hostip))[0]
        self.transport.write(pack("!BBBBIH", 0x05, 0x00, 0x00, 0x01, host, port))
        self.data_in.start()
        self.data_out.start()

    def parse_connect(self, atype, data):
        cur = 4
        if atype == Connection.DOMAIN:
            host_len = unpack("!B", data[cur : cur + 1])[0]
            cur += 1
            host = data[cur : cur + host_len].decode()
            cur += host_len
        elif atype == Connection.IPV4:
            host = socket.inet_ntop(socket.AF_INET, data[cur : cur + 4])
            cur += 4
        elif atype == Connection.IPV6:
            host = socket.inet_ntop(socket.AF_INET6, data[cur : cur + 16])
            cur += 16
        else:
            raise Exception("Unknown address type!")
        port = unpack("!H", data[cur : cur + 2])[0]
        return host, port
