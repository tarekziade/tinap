#!/usr/bin/env python3
#
# Copyright (c) 2018-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.
#
"""
This module was taken from Facebook's repo here and adapted:
https://github.com/facebookexperimental/doh-proxy

It's the proxy module + all its dependencies combined in this module.

For tinap, we are just plugging in the network throttling features
when the DNS resolver is called, and returning the ip where the tinap
port forwarder is set, so Firefox uses it.

Read DNS.rst for more info
"""
import asyncio
import collections
import struct
import time
from typing import Dict, List, Tuple
import io
import argparse
import ssl
import urllib.parse
import binascii
import base64

import dns.message
import dns.rcode
import dns.entropy
import dns.message

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import ConnectionTerminated, DataReceived, RequestReceived, StreamEnded
from h2.exceptions import ProtocolError

from tinap.util import get_logger, set_logger


DOH_URI = "/dns-query"
DOH_MEDIA_TYPE = "application/dns-message"
DOH_DNS_PARAM = "dns"
DOH_H2_NPN_PROTOCOLS = ["h2"]
DOH_CIPHERS = "ECDHE+AESGCM"
__version__ = "0.0.9"


class DOHException(Exception):
    def body(self):
        return self.args[0]


class DOHParamsException(DOHException):
    pass


class DOHDNSException(DOHException):
    pass


def doh_b64_decode(s: str) -> bytes:
    """Base 64 urlsafe decode, add padding as needed.
    :param s: input base64 encoded string with potentially missing padding.
    :return: decodes bytes
    """
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def sum_items(section: List[dns.rrset.RRset]) -> int:
    """ Helper function to return items in a section of dns answer
    """
    return sum(len(x) for x in section)


def msg2question(msg: dns.message.Message) -> str:
    """ Helper function to return a string of name class and type
    """
    question = "<empty>"
    if len(msg.question):
        q = msg.question[0]
        name = q.name.to_text()
        qclass = dns.rdataclass.to_text(q.rdclass)
        qtype = dns.rdatatype.to_text(q.rdtype)
        question = " ".join([name, qtype, qclass])
    return question


def msg2flags(msg: dns.message.Message) -> str:
    """ Helper function to return flags in a message
    """
    return "/".join(dns.flags.to_text(msg.flags).split(" "))


class DNSClient:

    DEFAULT_TIMEOUT = 10

    def __init__(self, upstream_resolver, upstream_port, logger=None):
        self.loop = asyncio.get_event_loop()
        self.upstream_resolver = upstream_resolver
        self.upstream_port = upstream_port
        if logger is None:
            logger = get_logger()
        self.logger = logger

    async def query(self, dnsq, clientip, timeout=DEFAULT_TIMEOUT):
        dnsr = await self.query_udp(dnsq, clientip, timeout=timeout)
        if dnsr is None or (dnsr.flags & dns.flags.TC):
            dnsr = await self.query_tcp(dnsq, clientip, timeout=timeout)
        return dnsr

    async def query_udp(self, dnsq, clientip, timeout=DEFAULT_TIMEOUT):
        qid = dnsq.id
        fut = asyncio.Future()
        await self.loop.create_datagram_endpoint(
            lambda: DNSClientProtocolUDP(dnsq, fut, clientip, logger=self.logger),
            remote_addr=(self.upstream_resolver, self.upstream_port),
        )
        return await self._try_query(fut, qid, timeout)

    async def query_tcp(self, dnsq, clientip, timeout=DEFAULT_TIMEOUT):
        qid = dnsq.id
        fut = asyncio.Future()
        await self.loop.create_connection(
            lambda: DNSClientProtocolTCP(dnsq, fut, clientip, logger=self.logger),
            self.upstream_resolver,
            self.upstream_port,
        )
        return await self._try_query(fut, qid, timeout)

    async def _try_query(self, fut, qid, timeout):
        try:
            await asyncio.wait_for(fut, timeout)
            dnsr = fut.result()
            dnsr.id = qid
        except asyncio.TimeoutError:
            self.logger.debug("Request timed out")
            dnsr = None
        return dnsr


class DNSClientProtocol(asyncio.Protocol):
    def __init__(self, dnsq, fut, clientip, logger=None):
        self.transport = None
        self.dnsq = dnsq
        self.fut = fut
        self.clientip = clientip
        if logger is None:
            logger = get_logger()
        self.logger = logger

    def connection_lost(self, exc):
        pass

    def connection_made(self, transport):
        raise NotImplementedError()

    def data_received(self, data):
        raise NotImplementedError()

    def datagram_received(self, data, addr):
        raise NotImplementedError()

    def error_received(self, exc):
        raise NotImplementedError()

    def eof_received(self):
        raise NotImplementedError()

    def send_helper(self, transport):
        self.transport = transport
        self.dnsq.id = dns.entropy.random_16()
        self.logger.info("[DNS] {} {}".format(self.clientip, dnsquery2log(self.dnsq)))
        self.time_stamp = time.time()

    def receive_helper(self, dnsr):
        interval = int((time.time() - self.time_stamp) * 1000)
        log_message = "[DNS] {} {} {}ms".format(
            self.clientip, dnsans2log(dnsr), interval
        )

        if not self.fut.cancelled():
            self.logger.info(log_message)
            self.fut.set_result(dnsr)
        else:
            self.logger.info(log_message + "(CANCELLED)")


class DNSClientProtocolUDP(DNSClientProtocol):
    def connection_made(self, transport):
        self.send_helper(transport)
        self.transport.sendto(self.dnsq.to_wire())

    def datagram_received(self, data, addr):
        dnsr = dns.message.from_wire(data)
        self.receive_helper(dnsr)
        self.transport.close()

    def error_received(self, exc):
        self.transport.close()
        self.logger.exception("Error received: " + str(exc))


class DNSClientProtocolTCP(DNSClientProtocol):
    def __init__(self, dnsq, fut, clientip, logger=None):
        super().__init__(dnsq, fut, clientip, logger=logger)
        self.buffer = bytes()

    def connection_made(self, transport):
        self.send_helper(transport)
        msg = self.dnsq.to_wire()
        tcpmsg = struct.pack("!H", len(msg)) + msg
        self.transport.write(tcpmsg)

    def data_received(self, data):
        self.buffer = self.buffer + data
        if len(self.buffer) < 2:
            return
        msglen = struct.unpack("!H", self.buffer[0:2])[0]
        while msglen + 2 <= len(self.buffer):
            dnsr = dns.message.from_wire(self.buffer[2 : msglen + 2])  # noqa
            self.receive_helper(dnsr)
            self.buffer = self.buffer[msglen + 2 :]  # noqa
            if len(self.buffer) < 2:
                return
            msglen = struct.unpack("!H", self.buffer[0:2])[0]

    def eof_received(self):
        if len(self.buffer) > 0:
            self.logger.debug("Discard incomplete message")
        self.transport.close()


RequestData = collections.namedtuple("RequestData", ["headers", "data"])


def dnsquery2log(msg: dns.message.Message) -> str:
    """ Helper function to return a readable excerpt from a dns query object.
    """
    question = msg2question(msg)
    flags = msg2flags(msg)

    return "{} {} {}".format(question, msg.id, flags)


def dnsans2log(msg: dns.message.Message) -> str:
    """ Helper function to return a readable excerpt from a dns answer object.
    """
    question = msg2question(msg)
    flags = msg2flags(msg)

    return "{} {} {} {}/{}/{} {}/{}/{} {}".format(
        question,
        msg.id,
        flags,
        sum_items(msg.answer),
        sum_items(msg.authority),
        sum_items(msg.additional),
        msg.edns,
        msg.ednsflags,
        msg.payload,
        dns.rcode.to_text(msg.rcode()),
    )


def extract_path_params(url: str) -> Tuple[str, Dict[str, List[str]]]:
    """ Given a URI, extract the path and the parameters
    """
    p = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(p.query, keep_blank_values=True)
    return p.path, params


def dns_query_from_body(body: bytes, debug: bool = False) -> dns.message.Message:
    """ Given a bytes-object, attempt to unpack a DNS Message.
    :param body: the bytes-object wired representation of a DNS message.
    :param debug: a boolean. When True, The error message sent to client will
    be more meaningful.
    :return: a dns.message.Message on success, raises DOHDNSException
    otherwise.
    """
    exc = b"Malformed DNS query"
    try:
        return dns.message.from_wire(body)
    except Exception as e:
        if debug:
            exc = str(e).encode("utf-8")
    raise DOHDNSException(exc)


def extract_ct_body(params: Dict[str, List[str]]) -> Tuple[str, bytes]:
    """ Extract the content type and body from a list of get parameters.
    :param params: A dictionary of key/value of parameters as provided by
        urllib.parse.parse_qs
    :return: a tuple that contains a string and bytes, respectively ct and
        body.
    :raises: a DOHParamsException with an explanatory message.
    """
    ct = DOH_MEDIA_TYPE
    if DOH_DNS_PARAM in params and len(params[DOH_DNS_PARAM]):
        try:
            body = doh_b64_decode(params[DOH_DNS_PARAM][0])
        except binascii.Error:
            raise DOHParamsException(b"Invalid Body Parameter")
        if not body:
            raise DOHParamsException(b"Missing Body")
    else:
        raise DOHParamsException(b"Missing Body Parameter")

    return ct, body


class H2Protocol(asyncio.Protocol):
    def __init__(
        self,
        upstream_resolver=None,
        upstream_port=None,
        uri=None,
        logger=None,
        debug=False,
    ):
        config = H2Configuration(client_side=False, header_encoding="utf-8")
        self.conn = H2Connection(config=config)
        self.logger = logger
        if logger is None:
            self.logger = get_logger()
        self.transport = None
        self.debug = debug
        self.stream_data = {}
        self.upstream_resolver = upstream_resolver
        self.upstream_port = upstream_port
        self.time_stamp = 0
        self.uri = DOH_URI if uri is None else uri
        assert upstream_resolver is not None, "An upstream resolver must be provided"
        assert upstream_port is not None, "An upstream resolver port must be provided"

    def connection_made(self, transport: asyncio.Transport):  # type: ignore
        self.transport = transport
        self.conn.initiate_connection()
        self.transport.write(self.conn.data_to_send())

    def data_received(self, data: bytes):
        try:
            events = self.conn.receive_data(data)
        except ProtocolError:
            self.transport.write(self.conn.data_to_send())
            self.transport.close()
        else:
            self.transport.write(self.conn.data_to_send())
            for event in events:
                if isinstance(event, RequestReceived):
                    self.request_received(event.headers, event.stream_id)
                elif isinstance(event, DataReceived):
                    self.receive_data(event.data, event.stream_id)
                elif isinstance(event, StreamEnded):
                    self.stream_complete(event.stream_id)
                elif isinstance(event, ConnectionTerminated):
                    self.transport.close()

                self.transport.write(self.conn.data_to_send())

    def request_received(self, headers: List[Tuple[str, str]], stream_id: int):
        _headers = collections.OrderedDict(headers)
        method = _headers[":method"]

        # We only support GET and POST.
        if method not in ["GET", "POST", "HEAD"]:
            self.return_501(stream_id)
            return

        # Store off the request data.
        request_data = RequestData(_headers, io.BytesIO())
        self.stream_data[stream_id] = request_data

    def stream_complete(self, stream_id: int):
        """
        When a stream is complete, we can send our response.
        """
        try:
            request_data = self.stream_data[stream_id]
        except KeyError:
            # Just return, we probably 405'd this already
            return

        headers = request_data.headers
        method = request_data.headers[":method"]

        # Handle the actual query
        path, params = extract_path_params(headers[":path"])

        if path != self.uri:
            self.return_404(stream_id)
            return

        if method in ["GET", "HEAD"]:
            try:
                ct, body = extract_ct_body(params)
            except DOHParamsException as e:
                self.return_400(stream_id, body=e.body())
                return
        elif method == "POST":
            body = request_data.data.getvalue()
            ct = headers.get("content-type")
        else:
            self.return_501(stream_id)
            return

        if ct != DOH_MEDIA_TYPE:
            self.return_415(stream_id)
            return

        # XXX todo: return immediatly Tinap's IP if
        # the option is used (--redirect-ip)
        # Do actual DNS Query
        try:
            dnsq = dns_query_from_body(body, self.debug)
        except DOHDNSException as e:
            self.return_400(stream_id, body=e.body())
            return

        clientip = self.transport.get_extra_info("peername")[0]
        self.logger.info("[HTTPS] {} {}".format(clientip, dnsquery2log(dnsq)))
        self.time_stamp = time.time()
        asyncio.ensure_future(self.resolve(dnsq, stream_id))

    def on_answer(self, stream_id, dnsr=None, dnsq=None):
        try:
            request_data = self.stream_data[stream_id]
        except KeyError:
            # Just return, we probably 405'd this already
            return

        response_headers = [
            (":status", "200"),
            ("content-type", DOH_MEDIA_TYPE),
            ("server", "asyncio-h2"),
        ]
        if dnsr is None:
            dnsr = dns.message.make_response(dnsq)
            dnsr.set_rcode(dns.rcode.SERVFAIL)
        elif len(dnsr.answer):
            ttl = min(r.ttl for r in dnsr.answer)
            response_headers.append(("cache-control", "max-age={}".format(ttl)))

        clientip = self.transport.get_extra_info("peername")[0]
        interval = int((time.time() - self.time_stamp) * 1000)
        self.logger.info(
            "[HTTPS] {} {} {}ms".format(clientip, dnsans2log(dnsr), interval)
        )
        if request_data.headers[":method"] == "HEAD":
            body = b""
        else:
            body = dnsr.to_wire()
        response_headers.append(("content-length", str(len(body))))

        self.conn.send_headers(stream_id, response_headers)
        self.conn.send_data(stream_id, body, end_stream=True)
        self.transport.write(self.conn.data_to_send())

    async def resolve(self, dnsq, stream_id):
        # XXX Todo add network throttling here when activated.
        # (same options than tinap's main script)
        clientip = self.transport.get_extra_info("peername")[0]
        dnsclient = DNSClient(
            self.upstream_resolver, self.upstream_port, logger=self.logger
        )
        dnsr = await dnsclient.query(dnsq, clientip)

        if dnsr is None:
            self.on_answer(stream_id, dnsq=dnsq)
        else:
            self.on_answer(stream_id, dnsr=dnsr)

    def return_XXX(self, stream_id: int, status: int, body: bytes = b""):
        """
        Wrapper to return a status code and some optional content.
        """
        response_headers = (
            (":status", str(status)),
            ("content-length", str(len(body))),
            ("server", "asyncio-h2"),
        )
        self.conn.send_headers(stream_id, response_headers)
        self.conn.send_data(stream_id, body, end_stream=True)

    def return_400(self, stream_id: int, body: bytes = b""):
        """
        We don't support the given PATH, so we want to return a 403 response.
        """
        self.return_XXX(stream_id, 400, body)

    def return_403(self, stream_id: int, body: bytes = b""):
        """
        We don't support the given PATH, so we want to return a 403 response.
        """
        self.return_XXX(stream_id, 403, body)

    def return_404(self, stream_id: int):
        """
        We don't support the given PATH, so we want to return a 403 response.
        """
        self.return_XXX(stream_id, 404, body=b"Wrong path")

    def return_405(self, stream_id: int):
        """
        We don't support the given method, so we want to return a 405 response.
        """
        self.return_XXX(stream_id, 405)

    def return_415(self, stream_id: int):
        """
        We don't support the given media, so we want to return a 415 response.
        """
        self.return_XXX(stream_id, 415, body=b"Unsupported content type")

    def return_501(self, stream_id: int):
        """
        We don't support the given method.
        """
        self.return_XXX(stream_id, 501, body=b"Not Implemented")

    def receive_data(self, data: bytes, stream_id: int):
        """
        We've received some data on a stream. If that stream is one we're
        expecting data on, save it off. Otherwise, reset the stream.
        """
        try:
            stream_data = self.stream_data[stream_id]
        except KeyError:
            # Unknown stream, log and ignore (the stream may already be ended)
            clientip = self.transport.get_extra_info("peername")[0]
            self.logger.info("[HTTPS] %s Unknown stream %d", clientip, stream_id)
        else:
            stream_data.data.write(data)


def create_ssl_context(
    options: argparse.Namespace, http2: bool = False
) -> ssl.SSLContext:
    """ Create SSL Context for the proxies
    :param options: where to find the certile and the keyfile
    :param http2: enable http2 into the context
    :return: An instance of ssl.SSLContext to be used by the proxies
    """
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(options.certfile, keyfile=options.keyfile)
    if http2:
        ctx.set_alpn_protocols(["h2"])
    ctx.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_COMPRESSION
    ctx.set_ciphers(DOH_CIPHERS)
    return ctx


def proxy_parser_base(*, port: int, secure: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--listen-address",
        default=["::1"],
        nargs="+",
        help="A list of addresses the proxy should listen on. "
        "Default: [%(default)s]",
    )
    parser.add_argument(
        "--port",
        "--listen-port",
        default=port,
        type=int,
        help="Port to listen on. Default: [%(default)s]",
    )
    parser.add_argument("--certfile", help="SSL cert file.", required=secure)
    parser.add_argument("--keyfile", help="SSL key file.", required=secure)
    parser.add_argument(
        "--upstream-resolver",
        default="::1",
        help="Upstream recursive resolver to send the query to. "
        "Default: [%(default)s]",
    )
    parser.add_argument(
        "--upstream-port",
        default=53,
        help="Upstream recursive resolver port to send the query to. "
        "Default: [%(default)s]",
    )
    parser.add_argument(
        "--uri", default=DOH_URI, help="DNS API URI. Default [%(default)s]"
    )
    parser.add_argument("--level", default="DEBUG", help="log level [%(default)s]")
    parser.add_argument("--debug", action="store_true", help="Debugging messages...")
    parser.add_argument(
        "--version", action="version", version="%(prog)s {}".format(__version__)
    )
    return parser


def main(args=None):
    if args is None:
        parser = proxy_parser_base(port=443, secure=True)
        args = parser.parse_args()

    set_logger(args.level)
    logger = get_logger()
    ssl_ctx = create_ssl_context(args, http2=True)
    loop = asyncio.get_event_loop()
    for addr in args.listen_address:
        coro = loop.create_server(
            lambda: H2Protocol(
                upstream_resolver=args.upstream_resolver,
                upstream_port=args.upstream_port,
                uri=args.uri,
                logger=logger,
                debug=args.debug,
            ),
            host=addr,
            port=args.port,
            ssl=ssl_ctx,
        )
        server = loop.run_until_complete(coro)

        # Serve requests until Ctrl+C is pressed
        logger.info("Serving on {}".format(server))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    # Close the server
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()


if __name__ == "__main__":
    main()
