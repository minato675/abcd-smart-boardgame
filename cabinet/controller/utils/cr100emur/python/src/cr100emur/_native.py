from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path

CR100_OK = 0
CR100_TIMEOUT = 1
CR100_ERR_ARGUMENT = -1
CR100_ERR_NOT_FOUND = -2
CR100_ERR_ACCESS = -3
CR100_ERR_IO = -4
CR100_ERR_BAUD = -5
CR100_ERR_DISCONNECTED = -6
CR100_ERR_OVERFLOW = -7

DEFAULT_BAUD = 9600
UID_BYTES = 5
UID_HEX_LENGTH = 10


class NativeCard(ctypes.Structure):
    _fields_ = [
        ("uid", ctypes.c_uint8 * UID_BYTES),
        ("hex", ctypes.c_char * (UID_HEX_LENGTH + 1)),
        ("value", ctypes.c_uint64),
    ]


class NativeParser(ctypes.Structure):
    _fields_ = [
        ("candidate", ctypes.c_char * (UID_HEX_LENGTH + 1)),
        ("candidate_length", ctypes.c_size_t),
    ]


def _library_candidates() -> list[str]:
    candidates: list[str] = []
    override = os.environ.get("CR100EMUR_LIBRARY")
    if override:
        candidates.append(override)

    repository_root = Path(__file__).resolve().parents[3]
    candidates.extend(
        str(repository_root / "build" / name)
        for name in (
            "libcr100emur.so",
            "libcr100emur.so.0",
            "libcr100emur.so.0.2.0",
        )
    )

    discovered = ctypes.util.find_library("cr100emur")
    if discovered:
        candidates.append(discovered)

    candidates.extend(
        (
            "/usr/local/lib/libcr100emur.so.0",
            "/usr/lib/libcr100emur.so.0",
            "/usr/lib64/libcr100emur.so.0",
        )
    )
    return candidates


def _load_library() -> ctypes.CDLL:
    errors: list[str] = []
    seen: set[str] = set()

    for candidate in _library_candidates():
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return ctypes.CDLL(candidate, use_errno=True)
        except OSError as error:
            errors.append(f"{candidate}: {error}")

    details = "\n".join(errors)
    raise ImportError(
        "libcr100emur could not be loaded. Run `make` in the repository, "
        "install it with `sudo make install && sudo ldconfig`, or set "
        "CR100EMUR_LIBRARY to its path."
        + (f"\nTried:\n{details}" if details else "")
    )


lib = _load_library()

lib.cr100_find_device.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
lib.cr100_find_device.restype = ctypes.c_int

lib.cr100_open.argtypes = [
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_char_p,
    ctypes.c_uint,
]
lib.cr100_open.restype = ctypes.c_int

lib.cr100_close.argtypes = [ctypes.c_void_p]
lib.cr100_close.restype = None

lib.cr100_device_path.argtypes = [ctypes.c_void_p]
lib.cr100_device_path.restype = ctypes.c_char_p

lib.cr100_get_fd.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
]
lib.cr100_get_fd.restype = ctypes.c_int

lib.cr100_read_card.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(NativeCard),
    ctypes.c_int,
]
lib.cr100_read_card.restype = ctypes.c_int

lib.cr100_read_raw.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
    ctypes.c_int,
]
lib.cr100_read_raw.restype = ctypes.c_int

lib.cr100_parser_init.argtypes = [ctypes.POINTER(NativeParser)]
lib.cr100_parser_init.restype = None

lib.cr100_parser_feed.argtypes = [
    ctypes.POINTER(NativeParser),
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_size_t,
    ctypes.POINTER(NativeCard),
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
lib.cr100_parser_feed.restype = ctypes.c_int

lib.cr100_card_from_hex.argtypes = [
    ctypes.c_char_p,
    ctypes.POINTER(NativeCard),
]
lib.cr100_card_from_hex.restype = ctypes.c_int

lib.cr100_strerror.argtypes = [ctypes.c_int]
lib.cr100_strerror.restype = ctypes.c_char_p
