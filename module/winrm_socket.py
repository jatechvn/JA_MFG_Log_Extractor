"""Paramiko socket adapter: binary TCP via native Windows PowerShell WinRM."""
import base64
import json
import os
import queue
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional


class WinRMSocket:
    """Serialize short RPCs so Paramiko reader and writer share one PSSession."""

    def __init__(
        self, bridge: str, username: str, password: str,
        host: str, port: int, timeout: int, https: bool = False,
    ):
        if os.name != "nt":
            raise OSError("WinRM bridge yêu cầu Windows PowerShell trên máy chạy tool.")
        self._timeout: Optional[float] = timeout
        self._rpc_timeout = max(timeout + 5, 10)
        self._closed = False
        self._lock = threading.Lock()
        self._responses = queue.Queue()
        self._broken = False
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        helper_env = os.environ.copy()
        # A Python process started by pwsh inherits PS7 modules incompatible with PS5.1.
        helper_env["PSModulePath"] = str(powershell.parent / "Modules")
        self._process = subprocess.Popen(
            [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File",
             str(Path(__file__).with_name("winrm_bridge.ps1"))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
            env=helper_env,
        )
        self._reader = threading.Thread(target=self._read_responses, daemon=True)
        self._reader.start()
        try:
            self._rpc({
                "bridge": bridge, "user": username, "password": password,
                "host": host, "port": port, "timeout": timeout, "https": https,
            })
        except (OSError, ValueError):
            self.close()
            raise

    def _read_responses(self) -> None:
        try:
            for line in self._process.stdout:
                self._responses.put(line)
        finally:
            self._responses.put(None)

    def _rpc(self, request: dict) -> dict:
        with self._lock:
            if self._closed or self._broken:
                raise OSError("WinRM stream đã đóng.")
            self._process.stdin.write(json.dumps(request) + "\n")
            self._process.stdin.flush()
            try:
                line = self._responses.get(timeout=self._rpc_timeout)
            except queue.Empty as exc:
                self._broken = True
                raise OSError("WinRM RPC timeout.") from exc
            if line is None:
                raise OSError("Phiên WinRM đã ngắt.")
            result = json.loads(line)
            if not result.get("ok"):
                raise OSError(result.get("error", "WinRM RPC thất bại."))
            return result

    def send(self, data: bytes) -> int:
        chunk = bytes(data[:32768])
        result = self._rpc({"op": "send", "data": base64.b64encode(chunk).decode("ascii")})
        return result["count"]

    def recv(self, size: int) -> bytes:
        if size <= 0 or self._closed:
            return b""
        deadline = None if self._timeout is None else time.monotonic() + self._timeout
        while not self._closed:
            result = self._rpc({"op": "recv", "size": min(size, 65536)})
            data = base64.b64decode(result.get("data", ""), validate=True)
            if data or result.get("eof"):
                return data
            if deadline is not None and time.monotonic() >= deadline:
                raise socket.timeout("WinRM TCP read timeout")
            time.sleep(0.02)
        return b""

    def settimeout(self, timeout: Optional[float]) -> None:
        self._timeout = timeout

    def gettimeout(self) -> Optional[float]:
        return self._timeout

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Kill only our own helper if bounded graceful shutdown does not finish.
        try:
            if self._lock.acquire(timeout=0.5):
                try:
                    if self._process.poll() is None:
                        self._process.stdin.write('{"op":"close"}\n')
                        self._process.stdin.flush()
                finally:
                    self._lock.release()
            self._process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            if self._process.poll() is None:
                self._process.kill()
                self._process.wait(timeout=3)
        finally:
            self._reader.join(timeout=1)
            for stream in (self._process.stdin, self._process.stdout):
                if stream is not None:
                    stream.close()
