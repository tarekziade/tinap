# Utilities
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
