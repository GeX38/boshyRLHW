"""Запуск оригинального EXE под Windows и подключение к его памяти."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import time

from .memory import BoshyMemoryReader, MemoryReadError


@contextmanager
def game_session(config):
    exe = Path(config.game_exe).resolve()
    process = subprocess.Popen([str(exe)], cwd=exe.parent)
    reader = None
    try:
        deadline = time.monotonic() + 30
        while reader is None:
            try:
                reader = BoshyMemoryReader(pid=process.pid, exe_path=exe)
            except MemoryReadError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise
                time.sleep(.1)
        yield reader
    finally:
        if reader is not None:
            reader.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
