"""Route target SSH/SFTP through the dual-NIC Windows bridge."""
import getpass
import ipaddress
import logging
import os
import socket
import warnings
from dataclasses import dataclass, field
from typing import Optional, Union

import paramiko

from . import config
from .exceptions import SshConnectionError
from .winrm_socket import WinRMSocket

logger = logging.getLogger("log_downloader.bridge")


@dataclass
class BridgeSettings:
    mode: str = config.LOCAL_SETTINGS["bridge"].get("connection", "auto")
    host: str = config.LOCAL_SETTINGS["bridge"]["host"]
    username: str = config.LOCAL_SETTINGS["bridge"]["username"]
    password: str = field(default=config.LOCAL_SETTINGS["bridge"].get("password", ""), repr=False)
    transport: str = config.LOCAL_SETTINGS["bridge"].get("transport", "auto")
    ssh_port: int = config.LOCAL_SETTINGS["bridge"].get("ssh_port", 22)
    winrm_https: bool = config.LOCAL_SETTINGS["bridge"].get("winrm_https", False)
    target_network: str = config.LOCAL_SETTINGS["network"].get("target_network", "172.19.0.0/16")
    client_network: str = config.LOCAL_SETTINGS["network"].get("client_network", "172.21.0.0/16")

    def resolve_password(self) -> str:
        """Ask only when a bridge is actually needed; reuse for a batch."""
        if not self.password:
            self.password = os.environ.get("LOG_DL_BRIDGE_PASSWORD", "")
        if not self.password:
            self.password = config.LOCAL_SETTINGS["bridge"].get("password", "")
        if not self.password:
            self.password = os.environ.get("LOG_DL_WIN_PASSWORD", "")
        if not self.password:
            self.password = config.LOCAL_SETTINGS["windows_ssh"].get("password", "")
        if not self.password:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", getpass.GetPassWarning)
                    self.password = getpass.getpass(
                        f"Mật khẩu bridge {self.username}@{self.host}: "
                    )
            except (EOFError, OSError, getpass.GetPassWarning) as exc:
                raise SshConnectionError(
                    "Không đọc được mật khẩu bridge; hãy điền bridge.password trong config.json hoặc đặt LOG_DL_BRIDGE_PASSWORD."
                ) from exc
        if not self.password:
            raise SshConnectionError("Chưa cung cấp mật khẩu máy bridge.")
        return self.password


def build_bridge_settings(
    mode: Optional[str] = None,
    transport: Optional[str] = None,
    host: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> BridgeSettings:
    """Khởi tạo BridgeSettings từ config.json kết hợp tham số CLI ghi đè."""
    b_cfg = config.LOCAL_SETTINGS["bridge"]
    n_cfg = config.LOCAL_SETTINGS["network"]
    return BridgeSettings(
        mode=mode or b_cfg.get("connection", "auto"),
        host=host or b_cfg.get("host", "172.21.168.241"),
        username=username or b_cfg.get("username", "V1801179"),
        password=password if password is not None else b_cfg.get("password", ""),
        transport=transport or b_cfg.get("transport", "auto"),
        ssh_port=int(b_cfg.get("ssh_port", 22)),
        winrm_https=bool(b_cfg.get("winrm_https", False)),
        target_network=n_cfg.get("target_network", "172.19.0.0/16"),
        client_network=n_cfg.get("client_network", "172.21.0.0/16"),
    )


def should_use_bridge(host: str, port: int, settings: BridgeSettings) -> bool:
    """Prefer reachable direct targets; otherwise bridge 172.19 from 172.21."""
    if settings.mode != "auto":
        return settings.mode == "bridge"
    try:
        target = ipaddress.ip_address(host)
    except ValueError:
        return False
    if target not in ipaddress.ip_network(settings.target_network):
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # UDP connect selects the local route without sending any packet.
            probe.connect((settings.host, settings.ssh_port))
            local_ip = ipaddress.ip_address(probe.getsockname()[0])
        if local_ip not in ipaddress.ip_network(settings.client_network):
            return False
    except OSError:
        return False
    try:
        with socket.create_connection((host, port), timeout=2):
            return False
    except OSError:
        return True


class BridgeConnector:
    """Own the bridge SSH client; each target auth attempt gets a new stream."""

    def __init__(self, settings: BridgeSettings):
        self.settings = settings
        self._client: Optional[paramiko.SSHClient] = None
        self._selected_transport = settings.transport

    def open_socket(self, host: str, port: int, timeout: int) -> Union[paramiko.Channel, WinRMSocket]:
        password = self.settings.resolve_password()
        if self._selected_transport in ("auto", "ssh"):
            try:
                channel = self._open_ssh(host, port, password, timeout)
                self._selected_transport = "ssh"
                return channel
            except (paramiko.SSHException, OSError) as exc:
                self.close()
                if self._selected_transport == "ssh":
                    raise SshConnectionError(
                        f"SSH bridge {self.settings.host} thất bại: {type(exc).__name__}"
                    ) from exc
                logger.info("SSH bridge không khả dụng; thử WinRM qua %s", self.settings.host)
                self._selected_transport = "winrm"
        try:
            return WinRMSocket(
                self.settings.host, self.settings.username, password,
                host, port, timeout, self.settings.winrm_https,
            )
        except (OSError, ValueError) as exc:
            raise SshConnectionError(
                f"WinRM bridge {self.settings.host} thất bại: {exc}"
            ) from exc

    def _open_ssh(self, host: str, port: int, password: str, timeout: int) -> paramiko.Channel:
        if self._client is None:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    self.settings.host, port=self.settings.ssh_port,
                    username=self.settings.username, password=password,
                    timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
                    allow_agent=False, look_for_keys=False,
                )
                client.get_transport().set_keepalive(15)
            except (paramiko.SSHException, OSError):
                client.close()
                raise
            self._client = client
        return self._client.get_transport().open_channel(
            "direct-tcpip", (host, port), ("127.0.0.1", 0), timeout=timeout,
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
