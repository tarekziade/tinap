# Utilities
import asyncio
import logging

UPSTREAMS = []


def append_upstream(upstream):
    UPSTREAMS.append(upstream)


def remove_upstream(upstream):
    UPSTREAMS.remove(upstream)


def sync_shutdown(servers, *args, **kw):
    """Called on any SIGTERM/SIGINT to gracefully shutdown tinap.
    """
    for upstream in UPSTREAMS:
        upstream.close()
    for server in servers:
        server.close()
    return 1


async def shutdown(servers):
    """Called on any SIGTERM/SIGKILL to gracefully shutdown tinap.
    """
    sync_shutdown(servers)


_DNS_CACHE = {}


async def resolve(host, port=80):
    if host in _DNS_CACHE:
        return _DNS_CACHE[host]
    addrinfo = await asyncio.get_event_loop().getaddrinfo(host, port)
    _DNS_CACHE[host] = addrinfo[0][4][0]
    return _DNS_CACHE[host]


_LOGGER = None


def set_logger(level=logging.INFO):
    global _LOGGER
    _LOGGER = logging.getLogger("tinap")
    _LOGGER.setLevel(level)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    _LOGGER.addHandler(ch)
    return _LOGGER


def get_logger():
    if _LOGGER is None:
        raise Exception("Logging not configured yet")
    return _LOGGER
