import asyncio
from struct import pack, unpack
from enum import IntEnum, unique
import socket

from tinap.base import UpstreamConnection, BaseServer


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
                self.state = State.DATA
                asyncio.ensure_future(self.connect(host, port))
                self.state = State.DATA
            elif cmd == Command.BIND:
                pass
            else:
                raise NotImplementedError()
        elif self.state is State.DATA:
            BaseServer.data_received(self, data)

    async def connect(self, host, port):
        t, c = await self.loop.create_connection(
            lambda: UpstreamConnection(self), host, port
        )
        self.upstream = c
        hostip, port = t.get_extra_info("sockname")
        host = unpack("!I", socket.inet_aton(hostip))[0]
        self.transport.write(pack("!BBBBIH", 0x05, 0x00, 0x00, 0x01, host, port))
        asyncio.ensure_future(self._dequeue())

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
