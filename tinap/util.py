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
