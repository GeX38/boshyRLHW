"""Read Boshy telemetry with the Windows API, without modifying game memory.

Offsets: AnsoWizard/AutoSplitters and Pixelsuft/boshyst; permalinks and
attribution are in docs/SOURCES.md.
"""

import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
from pathlib import Path
import struct


TUTORIAL_ROOM = 36  # LiveSplit room number (runtime scene 35).
TUTORIAL_PLAYER = 16  # Player object handle in the tutorial.
_EXE_NAMES = {"i wanna be the boshy.exe", "boshy.exe"}
SOURCE = "LiveSplit ASL + Pixelsuft/boshyst (ReadProcessMemory)"


class MemoryReadError(RuntimeError):
    """The game process or its telemetry cannot be read."""


@dataclass(frozen=True)
class BoshySnapshot:
    room: int
    x: int | None
    y: int | None
    dead: bool
    source: str = SOURCE
    frame: int | None = None


class _ProcessEntry(C.Structure):
    _fields_ = [
        ("dwSize", W.DWORD), ("cntUsage", W.DWORD),
        ("th32ProcessID", W.DWORD), ("th32DefaultHeapID", C.c_size_t),
        ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
        ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", W.LONG),
        ("dwFlags", W.DWORD), ("szExeFile", W.WCHAR * 260),
    ]


class _ModuleEntry(C.Structure):
    _fields_ = [
        ("dwSize", W.DWORD), ("th32ModuleID", W.DWORD),
        ("th32ProcessID", W.DWORD), ("GlblcntUsage", W.DWORD),
        ("ProccntUsage", W.DWORD), ("modBaseAddr", C.c_void_p),
        ("modBaseSize", W.DWORD), ("hModule", W.HMODULE),
        ("szModule", W.WCHAR * 256), ("szExePath", W.WCHAR * 260),
    ]


def _kernel32():
    # Load only when attaching, so tests can import the environment without a game.
    try:
        api = C.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        raise MemoryReadError("Run the environment with Python for Windows.") from exc
    api.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    api.CreateToolhelp32Snapshot.restype = W.HANDLE
    for prefix, entry_type in (("Process", _ProcessEntry), ("Module", _ModuleEntry)):
        for suffix in ("FirstW", "NextW"):
            function = getattr(api, prefix + "32" + suffix)
            function.argtypes = [W.HANDLE, C.POINTER(entry_type)]
            function.restype = W.BOOL
    api.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    api.OpenProcess.restype = W.HANDLE
    api.ReadProcessMemory.argtypes = [
        W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t),
    ]
    api.ReadProcessMemory.restype = W.BOOL
    api.CloseHandle.argtypes = [W.HANDLE]
    api.CloseHandle.restype = W.BOOL
    return api


def _entries(api, flags, pid, entry_type, first, next_):
    snapshot = api.CreateToolhelp32Snapshot(flags, pid)
    if snapshot == C.c_void_p(-1).value:
        raise MemoryReadError(f"Cannot enumerate Boshy: {C.WinError(C.get_last_error())}")
    try:
        entry = entry_type()
        entry.dwSize = C.sizeof(entry)
        result = []
        available = first(snapshot, C.byref(entry))
        while available:
            result.append(entry_type.from_buffer_copy(entry))
            available = next_(snapshot, C.byref(entry))
        return result
    finally:
        api.CloseHandle(snapshot)


def _find_pid(api, exe_path: Path | None) -> int:
    names = {exe_path.name.casefold()} if exe_path else _EXE_NAMES
    processes = _entries(api, 0x02, 0, _ProcessEntry, api.Process32FirstW, api.Process32NextW)
    matches = [entry.th32ProcessID for entry in processes if entry.szExeFile.casefold() in names]
    if len(matches) != 1:
        raise MemoryReadError("Launch one Boshy instance or specify game_pid.")
    return matches[0]


def _find_module(api, pid: int, exe_path: Path | None) -> tuple[int, Path]:
    names = {exe_path.name.casefold()} if exe_path else _EXE_NAMES
    # SNAPMODULE | SNAPMODULE32 includes the 32-bit game with 64-bit Python.
    modules = _entries(api, 0x08 | 0x10, pid, _ModuleEntry, api.Module32FirstW, api.Module32NextW)
    for entry in modules:
        if entry.szModule.casefold() in names:
            return entry.modBaseAddr, Path(entry.szExePath)
    raise MemoryReadError(f"Cannot find the Boshy executable module in process {pid}.")


class BoshyMemoryReader:
    """Read room, tutorial player coordinates, death, and runtime frame counter."""

    def __init__(self, pid: int | None = None, exe_path: Path | str | None = None):
        path = Path(exe_path).expanduser().resolve() if exe_path is not None else None
        self._api = _kernel32()
        self.pid = pid if pid is not None else _find_pid(self._api, path)
        self.base, self.exe_path = _find_module(self._api, self.pid, path)
        self._handle = self._api.OpenProcess(0x0010, False, self.pid)  # PROCESS_VM_READ only.
        if not self._handle:
            raise MemoryReadError(f"Cannot open Boshy memory: {C.WinError(C.get_last_error())}")

    def _read(self, address: int, size: int) -> bytes:
        if self._handle is None:
            raise MemoryReadError("Boshy memory reader is closed.")
        data = C.create_string_buffer(size)
        count = C.c_size_t()
        if not self._api.ReadProcessMemory(self._handle, address, data, size, C.byref(count)):
            raise MemoryReadError(f"Cannot read Boshy memory at 0x{address:x}: {C.WinError(C.get_last_error())}")
        if count.value != size:
            raise MemoryReadError(f"Short Boshy memory read at 0x{address:x}.")
        return data.raw

    def _u32(self, address: int) -> int:
        return struct.unpack("<I", self._read(address, 4))[0]

    def _i32(self, address: int) -> int:
        return struct.unpack("<i", self._read(address, 4))[0]

    def _pointer(self, address: int) -> int:
        # Boshy is 32-bit even when the controlling Python process is 64-bit.
        value = self._u32(address)
        if not value:
            raise MemoryReadError(f"Null Boshy pointer at 0x{address:x}; load the game first.")
        return value

    def _room(self) -> int:
        app = self._pointer(self.base + 0x59A94)
        return self._i32(self._pointer(app + 0x268) + 0xA8)

    def read(self) -> BoshySnapshot:
        room = self._room()
        if room != TUTORIAL_ROOM:
            return BoshySnapshot(room, None, None, False)
        run = self._pointer(self.base + 0x59A9C)
        frame = self._i32(run + 0xD0)
        objects = self._pointer(run + 0x1278)
        player = self._u32(objects + TUTORIAL_PLAYER * 8)
        x, y = (self._i32(player + 0x4C), self._i32(player + 0x54)) if player else (None, None)
        dead = player == 0 or x > 60000 or y == 0
        room_after = self._room()  # Avoid mixing data from two rooms at a transition.
        if room_after != room:
            return BoshySnapshot(room_after, None, None, False)
        return BoshySnapshot(room, None if dead else x, None if dead else y, dead, frame=frame)

    def close(self) -> None:
        if getattr(self, "_handle", None) is not None:
            self._api.CloseHandle(self._handle)
            self._handle = None
