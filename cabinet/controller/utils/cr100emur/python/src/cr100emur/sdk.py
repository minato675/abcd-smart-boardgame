from __future__ import annotations

import asyncio
import ctypes
import inspect
import math
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from . import _native

DEFAULT_BAUD: Final = _native.DEFAULT_BAUD
UID_BYTES: Final = _native.UID_BYTES
UID_HEX_LENGTH: Final = _native.UID_HEX_LENGTH


class CR100Error(RuntimeError):
    """Base error raised by the CR-100EMUR SDK."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class DeviceNotFoundError(CR100Error):
    pass


class PermissionDeniedError(CR100Error):
    pass


class DeviceDisconnectedError(CR100Error):
    pass


class UnsupportedBaudError(CR100Error):
    pass


class BufferOverflowError(CR100Error):
    pass


_ERROR_TYPES: Final = {
    _native.CR100_ERR_NOT_FOUND: DeviceNotFoundError,
    _native.CR100_ERR_ACCESS: PermissionDeniedError,
    _native.CR100_ERR_BAUD: UnsupportedBaudError,
    _native.CR100_ERR_DISCONNECTED: DeviceDisconnectedError,
    _native.CR100_ERR_OVERFLOW: BufferOverflowError,
}


def _raise_status(status: int, operation: str) -> None:
    native_message = _native.lib.cr100_strerror(status)
    message = (
        native_message.decode("utf-8", errors="replace")
        if native_message
        else f"unknown native error {status}"
    )
    if status in (_native.CR100_ERR_ACCESS, _native.CR100_ERR_IO):
        error_number = ctypes.get_errno()
        if error_number:
            message = f"{message}: {os.strerror(error_number)}"
    error_type = _ERROR_TYPES.get(status, CR100Error)
    raise error_type(status, f"{operation}: {message}")


def _timeout_milliseconds(
    timeout: float | timedelta | None,
) -> int:
    if timeout is None:
        return -1
    if isinstance(timeout, bool):
        raise TypeError("timeout must be seconds, a timedelta, or None")
    seconds = (
        timeout.total_seconds()
        if isinstance(timeout, timedelta)
        else float(timeout)
    )
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("timeout must be a finite non-negative number")
    milliseconds = math.ceil(seconds * 1000)
    if milliseconds > 2_147_483_647:
        raise ValueError("timeout is too large")
    return milliseconds


@dataclass(frozen=True, slots=True)
class Card:
    """A lossless five-byte EM card identity."""

    uid: bytes
    hex: str
    value: int

    @classmethod
    def from_hex(cls, text: str) -> Card:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        native = _native.NativeCard()
        status = _native.lib.cr100_card_from_hex(
            text.encode("ascii"), ctypes.byref(native)
        )
        if status != _native.CR100_OK:
            _raise_status(status, "parse card UID")
        return cls._from_native(native)

    @classmethod
    def _from_native(cls, native: _native.NativeCard) -> Card:
        return cls(
            uid=bytes(native.uid),
            hex=bytes(native.hex).split(b"\0", 1)[0].decode("ascii"),
            value=int(native.value),
        )

    def __str__(self) -> str:
        return self.hex


CardHandler = Callable[[Card], Awaitable[None] | None]
_CLOSED: Final = object()


def find_device() -> str:
    """Return the stable device path selected by the native SDK."""

    buffer = ctypes.create_string_buffer(512)
    status = _native.lib.cr100_find_device(buffer, len(buffer))
    if status != _native.CR100_OK:
        _raise_status(status, "find CR-100EMUR")
    return os.fsdecode(buffer.value)


class Parser:
    """Incremental parser for arbitrarily fragmented reader bytes."""

    __slots__ = ("_native",)

    def __init__(self) -> None:
        self._native = _native.NativeParser()
        _native.lib.cr100_parser_init(ctypes.byref(self._native))

    def feed(self, data: bytes | bytearray | memoryview) -> list[Card]:
        stream = bytes(data)
        if not stream:
            return []

        input_buffer = (ctypes.c_uint8 * len(stream)).from_buffer_copy(stream)
        capacity = len(stream) + 1
        output = (_native.NativeCard * capacity)()
        count = ctypes.c_size_t()
        status = _native.lib.cr100_parser_feed(
            ctypes.byref(self._native),
            input_buffer,
            len(stream),
            output,
            capacity,
            ctypes.byref(count),
        )
        if status != _native.CR100_OK:
            _raise_status(status, "parse card stream")
        return [Card._from_native(output[index]) for index in range(count.value)]


class Reader:
    """RAII-style/context-managed CR-100EMUR connection.

    A Reader owns one serial file descriptor and is not thread-safe. Do not
    interleave read() and read_raw() because raw reads bypass parser state.
    """

    __slots__ = ("_handle",)

    def __init__(
        self,
        device: str | os.PathLike[str] | None = None,
        baud: int = DEFAULT_BAUD,
    ) -> None:
        if not isinstance(baud, int) or isinstance(baud, bool):
            raise TypeError("baud must be an integer")
        encoded_device = (
            None if device is None else os.fsencode(os.fspath(device))
        )
        handle = ctypes.c_void_p()
        status = _native.lib.cr100_open(
            ctypes.byref(handle), encoded_device, baud
        )
        if status != _native.CR100_OK:
            _raise_status(status, "open CR-100EMUR")
        self._handle = handle

    @property
    def closed(self) -> bool:
        return not bool(self._handle.value)

    @property
    def device_path(self) -> str:
        handle = self._require_open()
        path = _native.lib.cr100_device_path(handle)
        return "" if not path else os.fsdecode(path)

    def fileno(self) -> int:
        """Return the borrowed descriptor used by readiness-based event loops."""

        descriptor = ctypes.c_int(-1)
        status = _native.lib.cr100_get_fd(
            self._require_open(), ctypes.byref(descriptor)
        )
        if status != _native.CR100_OK:
            _raise_status(status, "get CR-100EMUR descriptor")
        return descriptor.value

    def close(self) -> None:
        if self._handle.value:
            _native.lib.cr100_close(self._handle)
            self._handle = ctypes.c_void_p()

    def __enter__(self) -> Reader:
        self._require_open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _require_open(self) -> ctypes.c_void_p:
        if not self._handle.value:
            raise RuntimeError("CR-100EMUR reader is closed")
        return self._handle

    def read(
        self, timeout: float | timedelta | None = None
    ) -> Card | None:
        """Read one card, returning None on timeout.

        timeout is in seconds, a timedelta, or None to wait indefinitely.
        """

        native = _native.NativeCard()
        status = _native.lib.cr100_read_card(
            self._require_open(),
            ctypes.byref(native),
            _timeout_milliseconds(timeout),
        )
        if status == _native.CR100_TIMEOUT:
            return None
        if status != _native.CR100_OK:
            _raise_status(status, "read card")
        return Card._from_native(native)

    def read_raw(
        self,
        capacity: int = 256,
        timeout: float | timedelta | None = None,
    ) -> bytes | None:
        """Read one unparsed serial chunk, returning None on timeout."""

        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise TypeError("capacity must be an integer")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        buffer = (ctypes.c_uint8 * capacity)()
        size = ctypes.c_size_t()
        status = _native.lib.cr100_read_raw(
            self._require_open(),
            buffer,
            capacity,
            ctypes.byref(size),
            _timeout_milliseconds(timeout),
        )
        if status == _native.CR100_TIMEOUT:
            return None
        if status != _native.CR100_OK:
            _raise_status(status, "read raw bytes")
        return bytes(buffer[: size.value])


class AsyncReader:
    """Linux asyncio reader driven by descriptor-readiness notifications.

    No polling timer or executor thread is used. The event loop invokes the
    reader only when the CP210x serial descriptor becomes readable.
    """

    __slots__ = (
        "_reader",
        "_on_card",
        "_loop",
        "_queue",
        "_closed",
        "_failure",
        "_callback_tasks",
    )

    def __init__(
        self,
        device: str | os.PathLike[str] | None = None,
        baud: int = DEFAULT_BAUD,
        on_card: CardHandler | None = None,
    ) -> None:
        if on_card is not None and not callable(on_card):
            raise TypeError("on_card must be callable or None")
        self._reader = Reader(device=device, baud=baud)
        self._on_card = on_card
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[Card | BaseException | object] | None = None
        self._closed = False
        self._failure: BaseException | None = None
        self._callback_tasks: set[asyncio.Future[None]] = set()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def device_path(self) -> str:
        return self._reader.device_path

    def fileno(self) -> int:
        return self._reader.fileno()

    def start(self) -> AsyncReader:
        """Register the serial descriptor with the running asyncio loop."""

        if self._closed:
            raise RuntimeError("CR-100EMUR async reader is closed")

        loop = asyncio.get_running_loop()
        if self._loop is not None:
            if self._loop is not loop:
                raise RuntimeError(
                    "CR-100EMUR async reader belongs to another event loop"
                )
            return self

        queue: asyncio.Queue[Card | BaseException | object] = asyncio.Queue()
        loop.add_reader(self._reader.fileno(), self._on_readable)
        self._loop = loop
        self._queue = queue
        return self

    async def read(self) -> Card:
        """Wait asynchronously for the next card."""

        if self._failure is not None:
            raise self._failure
        if self._closed:
            raise RuntimeError("CR-100EMUR async reader is closed")

        self.start()
        assert self._queue is not None
        item = await self._queue.get()
        if item is _CLOSED:
            raise RuntimeError("CR-100EMUR async reader is closed")
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, Card)
        return item

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        if self._loop is not None and not self._loop.is_closed():
            self._loop.remove_reader(self._reader.fileno())
        self._reader.close()
        if self._queue is not None:
            self._queue.put_nowait(_CLOSED)
        for task in tuple(self._callback_tasks):
            task.cancel()
        self._callback_tasks.clear()

    async def __aenter__(self) -> AsyncReader:
        return self.start()

    async def __aexit__(self, *args: object) -> None:
        self.close()

    def __aiter__(self) -> AsyncReader:
        self.start()
        return self

    async def __anext__(self) -> Card:
        if self._closed and self._failure is None:
            raise StopAsyncIteration
        return await self.read()

    def _on_readable(self) -> None:
        try:
            assert self._queue is not None
            while True:
                card = self._reader.read(timeout=0)
                if card is None:
                    return
                self._queue.put_nowait(card)
                self._invoke_callback(card)
        except Exception as error:
            self._fail(error)

    def _invoke_callback(self, card: Card) -> None:
        if self._on_card is None:
            return
        assert self._loop is not None

        try:
            result = self._on_card(card)
        except Exception as error:
            self._report_callback_error(error)
            return

        if inspect.isawaitable(result):
            try:
                task = asyncio.ensure_future(result)
            except Exception as error:
                self._report_callback_error(error)
                return
            self._callback_tasks.add(task)
            task.add_done_callback(self._callback_done)

    def _callback_done(self, task: asyncio.Future[None]) -> None:
        self._callback_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._report_callback_error(error)

    def _report_callback_error(self, error: BaseException) -> None:
        assert self._loop is not None
        self._loop.call_exception_handler(
            {
                "message": "CR-100EMUR on_card callback failed",
                "exception": error,
                "async_reader": self,
            }
        )

    def _fail(self, error: BaseException) -> None:
        self._failure = error
        if self._loop is not None and not self._loop.is_closed():
            self._loop.remove_reader(self._reader.fileno())
        self._reader.close()
        self._closed = True
        if self._queue is not None:
            self._queue.put_nowait(error)
        for task in tuple(self._callback_tasks):
            task.cancel()
        self._callback_tasks.clear()


__all__ = [
    "DEFAULT_BAUD",
    "UID_BYTES",
    "UID_HEX_LENGTH",
    "AsyncReader",
    "BufferOverflowError",
    "CR100Error",
    "Card",
    "CardHandler",
    "DeviceDisconnectedError",
    "DeviceNotFoundError",
    "Parser",
    "PermissionDeniedError",
    "Reader",
    "UnsupportedBaudError",
    "find_device",
]
