import socket
import time

import serial


class TcpSerial:
    def __init__(self, host, port, connect_timeout=3.0, read_chunk=4096):
        self._sock = socket.create_connection((host, port), timeout=connect_timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._timeout = None
        self._sock.settimeout(self._timeout)
        self._buffer = bytearray()
        self._open = True
        self._read_chunk = read_chunk

    def isOpen(self):
        return self._open

    def close(self):
        if not self._open:
            return
        self._open = False
        try:
            self._sock.close()
        except OSError:
            pass

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        self._timeout = value
        try:
            self._sock.settimeout(self._timeout)
        except OSError as exc:
            raise serial.SerialException(str(exc)) from exc

    def _recv_once(self, timeout):
        try:
            self._sock.settimeout(timeout)
            data = self._sock.recv(self._read_chunk)
            if not data:
                raise serial.SerialException("TCP connection closed")
            self._buffer.extend(data)
            return True
        except socket.timeout:
            return False
        except OSError as exc:
            raise serial.SerialException(str(exc)) from exc

    def _fill_nonblocking(self):
        old_timeout = self._timeout
        try:
            self._sock.settimeout(0.0)
            while True:
                data = self._sock.recv(self._read_chunk)
                if not data:
                    raise serial.SerialException("TCP connection closed")
                self._buffer.extend(data)
        except (BlockingIOError, socket.timeout):
            return
        except OSError as exc:
            raise serial.SerialException(str(exc)) from exc
        finally:
            try:
                self._sock.settimeout(old_timeout)
            except OSError as exc:
                raise serial.SerialException(str(exc)) from exc

    def inWaiting(self):
        self._fill_nonblocking()
        return len(self._buffer)

    def read_all(self):
        self._fill_nonblocking()
        if not self._buffer:
            return b""
        data = bytes(self._buffer)
        self._buffer.clear()
        return data

    def read(self, size=1):
        if size <= 0:
            return b""
        deadline = None if self._timeout is None else time.monotonic() + self._timeout
        while len(self._buffer) < size:
            timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
            if timeout == 0.0:
                break
            ok = self._recv_once(timeout)
            if not ok and deadline is not None:
                break
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def read_until(self, terminator=b"\n"):
        if not terminator:
            return b""
        deadline = None if self._timeout is None else time.monotonic() + self._timeout
        while True:
            idx = self._buffer.find(terminator)
            if idx != -1:
                end = idx + len(terminator)
                data = bytes(self._buffer[:end])
                del self._buffer[:end]
                return data

            timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
            if timeout == 0.0:
                data = bytes(self._buffer)
                self._buffer.clear()
                return data
            ok = self._recv_once(timeout)
            if not ok and deadline is not None:
                data = bytes(self._buffer)
                self._buffer.clear()
                return data

    def readline(self):
        return self.read_until(b"\n")

    def write(self, data):
        try:
            self._sock.sendall(data)
        except OSError as exc:
            raise serial.SerialException(str(exc)) from exc
