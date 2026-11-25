"""Wait until each service answers its health address, or give up (spec appendix 10, section 5).

The deployment check's last wait: the memory server, the API and the web app each report
healthy. A developer can run it by hand against their own kind cluster, from the repo root:

    conda run -n agentic-jev-trader python infra/wait_healthy.py http://localhost:8765/health http://localhost:8000/health http://localhost:8080/

The addresses are the memory server's, the API's and the web app's, wherever the cluster's
services are reachable from (these examples assume each is forwarded to this computer).

Each address is asked every `--every` seconds until it answers with a success (any 2xx or 3xx
status); one that has answered is not asked again. It ends with 0 once all have answered, or
with 1 after `--timeout` seconds, naming the ones that never did. Output is plain ASCII:
`conda run` on Windows fails on other characters.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence

# How long one question to one address may take before it counts as no answer.
SECONDS_PER_ASK = 5


def answers_healthy(url: str) -> bool:
    """Whether `url` answers now with a success status."""
    try:
        with urllib.request.urlopen(url, timeout=SECONDS_PER_ASK) as answer:
            return 200 <= answer.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_until_healthy(
    urls: Sequence[str],
    timeout: float,
    every: float,
    *,
    is_healthy: Callable[[str], bool] = answers_healthy,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    say: Callable[[str], None] = print,
) -> list[str]:
    """Ask each address until all are healthy or `timeout` seconds have passed. Returns the
    addresses that never answered healthy: an empty list means all did."""
    deadline = clock() + timeout
    waiting = list(urls)
    while True:
        for url in list(waiting):
            if is_healthy(url):
                say(f"healthy: {url}")
                waiting.remove(url)
        left = deadline - clock()
        if not waiting or left <= 0:
            return waiting
        sleep(min(every, left))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python infra/wait_healthy.py")
    parser.add_argument("urls", nargs="+", help="health addresses to wait for")
    parser.add_argument(
        "--timeout",
        type=float,
        default=300,
        help="seconds to wait in all (default 300)",
    )
    parser.add_argument(
        "--every",
        type=float,
        default=5,
        help="seconds between rounds of asking (default 5)",
    )
    args = parser.parse_args(argv)
    # Named here, not left to the default, so it is looked up when called (tests replace it).
    never = wait_until_healthy(
        args.urls, args.timeout, args.every, is_healthy=answers_healthy
    )
    for url in never:
        print(f"not healthy after {args.timeout:g} seconds: {url}")
    return 1 if never else 0


if __name__ == "__main__":
    sys.exit(main())
