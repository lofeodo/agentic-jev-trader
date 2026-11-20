import socket

import pytest


def test_a_free_test_cannot_reach_the_network():
    # 192.0.2.1 is an address reserved for documentation: nothing real answers there.
    with pytest.raises(RuntimeError, match="Network is disabled"):
        socket.create_connection(("192.0.2.1", 443), timeout=1)
