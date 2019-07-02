import asyncio
from struct import pack, unpack
from enum import IntEnum, unique
import socket
from tinap.throttler import BandwidthControl


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


class SocksConnection(asyncio.Protocol):

    def __init__(self, latency, inkbps):
        self.latency = latency
        self.bandwidth_in = BandwidthControl(inkbps)
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.server_transport = None

    def data_received(self, data):
        async def _write(data):
            await asyncio.sleep(self.latency)
            await self.bandwidth_in.available(data)
            self.server_transport.write(data)
        asyncio.ensure_future(_write(data))

    def connection_lost(self, *args):
        self.server_transport.close()


class SocksServer(asyncio.Protocol):
    # XXX todo make a base class
    def __init__(self, host, port, latency, inkbps, outkbps):
        self.host = host
        self.port = port
        self.upstream = None
        self.loop = asyncio.get_event_loop()
        self.latency = latency
        self.inkbps = inkbps
        self.bandwidth_out = BandwidthControl(outkbps)
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.state = State.HELLO
        self.method = Method.USER
        self.loop = asyncio.get_event_loop()

    async def _create_conn(self, host, port):
        return await self.loop.create_connection(
                lambda: SocksConnection(self.latency, self.inkbps),
                                        host, port)

    def connection_lost(self, exc):
        self.transport.close()

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
                self.state = State.DATA
                asyncio.ensure_future(self.connect(host, port))
                self.state = State.DATA
            elif cmd == Command.BIND:
                pass
            else:
                raise NotImplementedError()
        elif self.state is State.DATA:
            self.client_write(data)

    def client_write(self, data):
        async def _write(data):
            await asyncio.sleep(self.latency)
            await self.bandwidth_out.available(data)
            self.client_transport.write(data)
        asyncio.ensure_future(_write(data))

    async def connect(self, host, port):
        transport, client = await self._create_conn(host, port)
        client.server_transport = self.transport
        self.client_transport = transport
        hostip, port = transport.get_extra_info("sockname")
        host = unpack("!I", socket.inet_aton(hostip))[0]
        self.transport.write(pack("!BBBBIH", 0x05, 0x00, 0x00, 0x01, host, port))

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
