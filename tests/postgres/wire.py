"""A pretend line to the database, which counts what goes along it (spec appendix 11, section 4).

A `Line` sits between a program and the local Postgres: the program connects to the line's port
on this computer, and the line passes every byte on, both ways. Along the way it notes:

- **connections**: how many connections the program opened through it;
- **statements**: every statement the program ran, with the values it sent, in order, read from
  Postgres's own message format (a `Parse` names a statement's text; each `Bind` runs it with
  values; a `Query` runs a text as it is);
- **a far-away database**: with `delay`, every answer from Postgres reaches the program that
  many seconds late, as from Montreal, so a program that waits for each statement's answer
  before sending the next takes one delay per statement, and one that sends them together takes
  one delay in all.

The program's own code is untouched: the line only sees the bytes.
"""

import socket
import struct
import threading
import time
from collections import deque
from typing import Self

from tests.postgres.helpers import LOCAL_HOST, LOCAL_PORT

# The first message of a connection has no type letter; these codes ask for encryption first,
# which the local Postgres (no encryption) answers with a single "N".
_ENCRYPTION_REQUESTS = {80877103, 80877104}


class _Reader:
    """Reads the program's side of one connection, message by message."""

    def __init__(self, line: "Line"):
        self.line = line
        self.buffer = b""
        self.started = False
        self.texts: dict[bytes, str] = {}  # a prepared statement's name: its text

    def feed(self, data: bytes) -> None:
        self.buffer += data
        while True:
            if not self.started:
                if len(self.buffer) < 8:
                    return
                (length,) = struct.unpack("!i", self.buffer[:4])
                if len(self.buffer) < length:
                    return
                (code,) = struct.unpack("!i", self.buffer[4:8])
                self.buffer = self.buffer[length:]
                self.started = code not in _ENCRYPTION_REQUESTS
                continue
            if len(self.buffer) < 5:
                return
            kind = self.buffer[:1]
            (length,) = struct.unpack("!i", self.buffer[1:5])
            if len(self.buffer) < 1 + length:
                return
            body = self.buffer[5 : 1 + length]
            self.buffer = self.buffer[1 + length :]
            self._message(kind, body)

    def _message(self, kind: bytes, body: bytes) -> None:
        if kind == b"Q":
            self.line._ran(body.split(b"\0", 1)[0].decode(), ())
        elif kind == b"P":
            name, rest = body.split(b"\0", 1)
            self.texts[name] = rest.split(b"\0", 1)[0].decode()
        elif kind == b"B":
            _portal, rest = body.split(b"\0", 1)
            name, rest = rest.split(b"\0", 1)
            (formats,) = struct.unpack("!h", rest[:2])
            rest = rest[2 + 2 * formats :]
            (count,) = struct.unpack("!h", rest[:2])
            rest = rest[2:]
            values = []
            for _ in range(count):
                (size,) = struct.unpack("!i", rest[:4])
                rest = rest[4:]
                values.append(None if size < 0 else rest[:size])
                rest = rest[max(size, 0) :]
            self.line._ran(self.texts.get(name, "?"), tuple(values))


class Line:
    """Use as `with Line(delay=0.3) as line:`; connect to `line.port` on this computer."""

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.connections = 0
        self.statements: list[tuple[str, tuple]] = []
        self._lock = threading.Lock()
        self._listener = socket.create_server((LOCAL_HOST, 0))
        self.port = self._listener.getsockname()[1]
        self._closed = False
        self._sockets: list[socket.socket] = []

    def __enter__(self) -> Self:
        threading.Thread(target=self._accept, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self._closed = True
        self._listener.close()
        for s in self._sockets:
            try:
                s.close()
            except OSError:
                pass

    def clear(self) -> None:
        """Forget the statements noted so far."""
        with self._lock:
            self.statements.clear()

    def _ran(self, text: str, values: tuple) -> None:
        with self._lock:
            self.statements.append((text, values))

    def _accept(self) -> None:
        while not self._closed:
            try:
                program, _ = self._listener.accept()
            except OSError:
                return
            database = socket.create_connection((LOCAL_HOST, LOCAL_PORT))
            for s in (program, database):
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sockets += [program, database]
            with self._lock:
                self.connections += 1
            reader = _Reader(self)
            threading.Thread(
                target=self._pass_on, args=(program, database, reader), daemon=True
            ).start()
            late: deque = deque()
            ready = threading.Condition()
            threading.Thread(
                target=self._receive, args=(database, late, ready), daemon=True
            ).start()
            threading.Thread(
                target=self._deliver, args=(program, late, ready), daemon=True
            ).start()

    @staticmethod
    def _pass_on(program, database, reader: _Reader) -> None:
        """The program's messages go on at once."""
        try:
            while data := program.recv(65536):
                reader.feed(data)
                database.sendall(data)
        except OSError:
            pass
        finally:
            database.close()

    def _receive(self, database, late: deque, ready: threading.Condition) -> None:
        """Postgres's answers wait in `late` until `delay` after they arrived."""
        try:
            while data := database.recv(65536):
                with ready:
                    late.append((time.monotonic() + self.delay, data))
                    ready.notify()
        except OSError:
            pass
        with ready:
            late.append((0.0, b""))
            ready.notify()

    @staticmethod
    def _deliver(program, late: deque, ready: threading.Condition) -> None:
        while True:
            with ready:
                while not late:
                    ready.wait()
                due, data = late.popleft()
            if not data:
                program.close()
                return
            time.sleep(max(0.0, due - time.monotonic()))
            try:
                program.sendall(data)
            except OSError:
                return
