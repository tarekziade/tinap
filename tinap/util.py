# Utilities
import asyncio

UPSTREAMS = []


def append_upstream(upstream):
    UPSTREAMS.append(upstream)


def remove_upstream(upstream):
    UPSTREAMS.remove(upstream)


async def shutdown(sig, server, loop):
    """Called on any SIGTERM/SIGKILL to gracefully shutdown tinap.
    """
    for upstream in UPSTREAMS:
        upstream.close()
    server.close()
    print("Bye!")


def parse_port_mappings(option):
    port_mappings = {}
    option = option.strip("'\" \t\r\n")
    for pair in option.split(","):
        src, dest = pair.split(":")
        if src == "*":
            port_mappings["default"] = int(dest)
        else:
            port_mappings[src] = int(dest)
    return port_mappings


_DNS_CACHE = {}


async def resolve(host, port=80):
    if host in _DNS_CACHE:
        return _DNS_CACHE[host]
    addrinfo = await asyncio.get_event_loop().getaddrinfo(host, port)
    _DNS_CACHE[host] = addrinfo[0][4][0]
    return _DNS_CACHE[host]
