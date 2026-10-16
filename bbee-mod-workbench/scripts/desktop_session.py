"""Read-only desktop preflight for the calling process on Windows 10/11 x64.

Only the first 20 bytes of WTSSessionInfoEx are copied: level, session ID,
connection state and lock flag. Account names and all remaining WTS fields
are neither copied nor decoded. No UI, registry, file or session changes occur.

Microsoft references:
https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ns-wtsapi32-wtsinfoex_level1_w
https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/nf-wtsapi32-wtsquerysessioninformationw
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import struct
import sys


class DesktopSessionError(RuntimeError):
    def __init__(self, record):
        self.record = record
        super().__init__("An unlocked current desktop session could not be established")


def _record(status, reason):
    return {"status": status, "unlocked": status == "unlocked", "locked": status == "locked",
            "known": status != "unknown", "reason": reason,
            "method": "current_process_WTSSessionInfoEx_first_20_bytes",
            "supported_platform": "Windows 10/11 x64"}


def _supported_platform():
    if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
        return False
    version = sys.getwindowsversion()
    # Windows 7 reverses LOCK/UNLOCK due to a documented API defect. Keep the
    # interpretation deliberately limited to current Windows workstation OSes.
    return version.major == 10 and version.build >= 10240 and version.product_type == 1


def _query_header():
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
    kernel.GetCurrentProcessId.argtypes = ()
    kernel.GetCurrentProcessId.restype = wintypes.DWORD
    kernel.ProcessIdToSessionId.argtypes = (wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    kernel.ProcessIdToSessionId.restype = wintypes.BOOL
    wts.WTSQuerySessionInformationW.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
                                               ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD))
    wts.WTSQuerySessionInformationW.restype = wintypes.BOOL
    wts.WTSFreeMemory.argtypes = (ctypes.c_void_p,)
    wts.WTSFreeMemory.restype = None
    session = wintypes.DWORD()
    if not kernel.ProcessIdToSessionId(kernel.GetCurrentProcessId(), ctypes.byref(session)):
        raise OSError("Current process session query failed")
    buffer = ctypes.c_void_p()
    size = wintypes.DWORD()
    try:
        if not wts.WTSQuerySessionInformationW(None, session.value, 25, ctypes.byref(buffer), ctypes.byref(size)):
            raise OSError("Current session information query failed")
        if not buffer.value or size.value < 20:
            return session.value, b""
        # WTSINFOEXW has an 8-byte-aligned Data union on native Windows x64.
        # Do not read the following WinStationName/UserName/DomainName fields.
        return session.value, ctypes.string_at(buffer, 20)
    finally:
        if buffer.value:
            wts.WTSFreeMemory(buffer)


def inspect_session():
    try:
        if not _supported_platform():
            return _record("unknown", "unsupported_platform")
        expected_session, prefix = _query_header()
        if not isinstance(prefix, bytes) or len(prefix) != 20:
            return _record("unknown", "malformed_response")
        level, actual_session, connection_state, flags = struct.unpack("<I4xIIi", prefix)
        if level != 1:
            return _record("unknown", "unsupported_information_level")
        if actual_session != expected_session:
            return _record("unknown", "session_mismatch")
        if connection_state != 0:  # WTSActive is required for an interactive run.
            return _record("unknown", "session_not_active")
        if flags == 0:
            return _record("locked", "current_session_locked")
        if flags == 1:
            return _record("unlocked", "current_session_unlocked")
        return _record("unknown", "unknown_session_flags")
    except Exception:
        # Never expose OS exception strings or unrelated session information.
        return _record("unknown", "session_query_failed")


def require_unlocked():
    result = inspect_session()
    if result["unlocked"] is not True:
        raise DesktopSessionError(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("check",), default="check")
    parser.parse_args()
    result = inspect_session()
    print(json.dumps(result))
    return 0 if result["unlocked"] else 2 if result["locked"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
