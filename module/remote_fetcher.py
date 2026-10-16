# -*- coding: utf-8 -*-
"""Tầng kết nối SSH/SFTP qua Bridge gián tiếp (172.21.168.241 -> 172.19.*.*) và Selective Fast Fetch.

Đặc điểm nổi bật:
- Tự động kết nối trực tiếp hoặc qua cầu nối (Bridge 172.21.168.241) bằng SSH direct-tcpip hoặc WinRM.
- Tự động thử chuỗi tài khoản (Linux root -> Linux seagate -> Windows V1801179).
- Tự động nhận diện hệ điều hành máy đích (Linux / Windows).
- Selective Fast Fetch: Khi phân tích trực tiếp, chỉ nén & tải các file log nhẹ cần thiết
  (debug.log, results.json, *.log, ctp_log_metadata.yaml, job.log, enc_logs/*), bỏ qua
  serial_logs, sysinfo, connection_configs, *.journal.sqlite, results.html giúp trích xuất
  chỉ mất 1-3 giây qua mạng xưởng.
- Tùy chọn --keep-raw-zip để giữ lại bản .zip gốc đầy đủ tại <App_Dir>/downloads/<IP>/.
"""
import logging
import os
import posixpath
import re
import shlex
import socket
import stat
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

import paramiko

from . import config
from .bridge import BridgeConnector, BridgeSettings, should_use_bridge
from .exceptions import DownloadError, RemoteCommandError, SshConnectionError
from .log_finder import RemoteLogEntry
from .path_utils import normalize_remote_path, safe_mkdir, to_long_path

logger = logging.getLogger("ja_mfg_extractor.remote_fetcher")

SELECTIVE_SKIP_DIRS = {"serial_logs", "sysinfo", "connection_configs"}
SELECTIVE_SKIP_SUFFIXES = (".journal.sqlite", "results.html", "results.tap", ".pcap")


class TransferProgress:
    """Hiển thị thanh tiến độ tải file SFTP gọn nhẹ trên dòng lệnh."""

    def __init__(self, label: str):
        self.label = label[:42]
        self.start_time = time.time()
        self.last_print = 0.0

    def update(self, transferred: int, total: int) -> None:
        now = time.time()
        if transferred < total and (now - self.last_print) < 0.15:
            return
        self.last_print = now
        elapsed = max(0.001, now - self.start_time)
        speed_mb = (transferred / (1024 * 1024)) / elapsed
        total_mb = total / (1024 * 1024) if total > 0 else 0.0
        trans_mb = transferred / (1024 * 1024)
        pct = (transferred * 100.0 / total) if total > 0 else 100.0
        msg = f"\r  -> Đang tải {self.label}: {pct:5.1f}% ({trans_mb:.2f}/{total_mb:.2f} MB | {speed_mb:.2f} MB/s)"
        sys.stdout.write(msg)
        sys.stdout.flush()

    def finish(self) -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()


def build_credentials_chain(
    custom_user: Optional[str] = None,
    custom_password: Optional[str] = None,
) -> Tuple[str, str, List[Tuple[str, str]]]:
    """Tạo danh sách tài khoản SSH ưu tiên:
    Nếu người dùng không chỉ định riêng, tự động thử:
    1. Linux SSH chính (root)
    2. Linux SSH dự phòng (seagate)
    3. Windows SSH (V1801179)
    """
    if custom_user and custom_password is not None:
        return custom_user, custom_password, []

    primary_user = custom_user or config.DEFAULT_SSH_USER
    primary_pass = custom_password if custom_password is not None else config.DEFAULT_SSH_PASSWORD

    fallbacks: List[Tuple[str, str]] = []
    for fb_user, fb_pass in config.LOCAL_SETTINGS.get("ssh", {}).get("fallback_credentials", []):
        if fb_user and fb_pass and (fb_user, fb_pass) != (primary_user, primary_pass):
            fallbacks.append((fb_user, fb_pass))

    win_user = config.DEFAULT_WIN_SSH_USER
    win_pass = config.DEFAULT_WIN_SSH_PASSWORD
    if win_user and win_pass and (win_user, win_pass) != (primary_user, primary_pass):
        if (win_user, win_pass) not in fallbacks:
            fallbacks.append((win_user, win_pass))

    return primary_user, primary_pass, fallbacks


class SshLogService:
    """Quản lý phiên SSH/SFTP tới máy test (trực tiếp hoặc qua Bridge 172.21.168.241)."""

    def __init__(
        self,
        host: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = config.DEFAULT_SSH_PORT,
        timeout: int = config.SSH_CONNECT_TIMEOUT_SEC,
        fallback_credentials: Optional[List[Tuple[str, str]]] = None,
        enable_precompress: bool = config.ENABLE_REMOTE_PRECOMPRESS,
        bridge_settings: Optional[BridgeSettings] = None,
        show_progress: bool = True,
    ):
        if username is None or password is None:
            p_user, p_pass, auto_fb = build_credentials_chain(username, password)
            self.username = p_user
            self.password = p_pass
            self.fallback_credentials = fallback_credentials if fallback_credentials is not None else auto_fb
        else:
            self.username = username
            self.password = password
            self.fallback_credentials = fallback_credentials or []

        self.host = host
        self.port = port
        self.timeout = timeout
        self.enable_precompress = enable_precompress
        self._ssh_client: Optional[paramiko.SSHClient] = None
        self.bridge_settings = bridge_settings
        self._bridge: Optional[BridgeConnector] = None
        self.remote_os: str = "linux"
        self.show_progress = show_progress
        self.used_bridge: bool = False

    def connect(self) -> None:
        """Thực hiện kết nối SSH tới máy đích (tự động qua Bridge nếu khác lớp mạng)."""
        if config.CONFIG_ERROR_MSG and not self.password:
            raise SshConnectionError(config.CONFIG_ERROR_MSG)
        if not self.password and not self.fallback_credentials:
            raise SshConnectionError(
                f"Chưa cấu hình mật khẩu SSH trong '{config.CONFIG_PATH}'. "
                f"Hãy sao chép 'config_sample.json' thành 'config.json' và điền mật khẩu."
            )

        credentials_to_try = [(self.username, self.password)]
        for cred in self.fallback_credentials:
            if cred not in credentials_to_try:
                credentials_to_try.append(cred)

        last_auth_error = None
        connected_client = None

        if self.bridge_settings and should_use_bridge(self.host, self.port, self.bridge_settings):
            self._bridge = BridgeConnector(self.bridge_settings)
            self.used_bridge = True
            logger.info(
                "Kết nối %s qua bridge %s (%s)",
                self.host,
                self.bridge_settings.host,
                self.bridge_settings.transport,
            )
        else:
            self.used_bridge = False
            logger.info("Kết nối trực tiếp tới %s", self.host)

        for user, pwd in credentials_to_try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            target_socket = None
            try:
                if self._bridge is not None:
                    target_socket = self._bridge.open_socket(self.host, self.port, self.timeout)
                client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=user,
                    password=pwd,
                    timeout=self.timeout,
                    banner_timeout=self.timeout,
                    auth_timeout=self.timeout,
                    look_for_keys=False,
                    allow_agent=False,
                    sock=target_socket,
                )
                connected_client = client
                self.username = user
                self.password = pwd
                logger.info("Đã kết nối SSH thành công tới %s@%s:%s", self.username, self.host, self.port)
                break
            except paramiko.AuthenticationException as exc:
                last_auth_error = exc
                client.close()
                if target_socket is not None:
                    target_socket.close()
                continue
            except SshConnectionError:
                client.close()
                self.disconnect()
                raise
            except (paramiko.SSHException, socket.timeout, socket.error, OSError) as exc:
                client.close()
                if target_socket is not None:
                    target_socket.close()
                self.disconnect()
                raise SshConnectionError(
                    f"Không kết nối được tới {self.host}:{self.port}: {exc}"
                ) from exc

        if connected_client is None:
            self.disconnect()
            if last_auth_error:
                raise SshConnectionError(
                    f"Sai tài khoản/mật khẩu SSH trên {self.host}:{self.port} "
                    f"(đã thử: {', '.join(u for u, _ in credentials_to_try)})"
                ) from last_auth_error
            raise SshConnectionError(f"Không thể kết nối SSH tới {self.host}:{self.port}")

        transport = connected_client.get_transport()
        if transport:
            transport.set_keepalive(config.SSH_KEEPALIVE_INTERVAL_SEC)

        self._ssh_client = connected_client
        self._detect_remote_os()

    def _detect_remote_os(self) -> None:
        """Nhận diện hệ điều hành của máy đích (Linux hay Windows)."""
        try:
            _, stdout, stderr = self._ssh_client.exec_command("uname -s", timeout=min(5, self.timeout))
            output = stdout.read().decode("utf-8", errors="replace").strip().lower()
            err = stderr.read().decode("utf-8", errors="replace").strip().lower()

            if any(os_name in output for os_name in ("linux", "darwin", "freebsd", "sunos")):
                self.remote_os = "linux"
            elif "not recognized" in err or "cannot find" in err or not output:
                _, win_out, _ = self._ssh_client.exec_command(
                    "[System.Environment]::OSVersion.Platform", timeout=min(5, self.timeout)
                )
                win_val = win_out.read().decode("utf-8", errors="replace").strip()
                if "Win" in win_val or not err:
                    self.remote_os = "windows"
                else:
                    self.remote_os = "linux"
            else:
                self.remote_os = "linux"
        except Exception:
            self.remote_os = "linux"

    def disconnect(self) -> None:
        if self._ssh_client is not None:
            self._ssh_client.close()
            self._ssh_client = None
        if self._bridge is not None:
            self._bridge.close()
            self._bridge = None

    def find_matching_entries(
        self,
        remote_base_path: Optional[str],
        serial_number: str,
        candidate_paths: Optional[List[str]] = None,
    ) -> Tuple[List[RemoteLogEntry], str]:
        """Tìm các thư mục/file log khớp với serial_number trên máy đích."""
        if not remote_base_path:
            remote_base_path = (
                config.DEFAULT_WIN_REMOTE_BASE_PATH
                if self.remote_os == "windows"
                else config.DEFAULT_REMOTE_BASE_PATH
            )
        if candidate_paths is None:
            candidate_paths = (
                config.WINDOWS_CANDIDATE_PATHS
                if self.remote_os == "windows"
                else config.LINUX_CANDIDATE_PATHS
            )

        norm_base_path = normalize_remote_path(remote_base_path)
        try:
            entries = self._execute_find_in_path(norm_base_path, serial_number)
            if entries:
                return entries, norm_base_path
        except Exception as exc:
            logger.debug("Tìm tại '%s' gặp lỗi (%s), chuyển sang quét candidate_paths...", norm_base_path, exc)

        for cand in candidate_paths or []:
            norm_cand = normalize_remote_path(cand)
            if norm_cand == norm_base_path:
                continue
            try:
                cand_entries = self._execute_find_in_path(norm_cand, serial_number)
                if cand_entries:
                    return cand_entries, norm_cand
            except Exception as exc:
                logger.debug("Quét thư mục ứng viên '%s' thất bại: %s", norm_cand, exc)

        return [], norm_base_path

    def _execute_find_in_path(self, remote_path: str, serial_number: str) -> List[RemoteLogEntry]:
        if self.remote_os == "windows":
            command = self._build_windows_find_command(remote_path, serial_number)
        else:
            command = self._build_linux_find_command(remote_path, serial_number)

        _, stdout, stderr = self._ssh_client.exec_command(command, timeout=self.timeout)
        exit_status = stdout.channel.recv_exit_status()
        output = stdout.read().decode("utf-8", errors="replace")
        error_output = stderr.read().decode("utf-8", errors="replace").strip()

        if exit_status != 0 and self.remote_os == "linux":
            raise RemoteCommandError(
                f"Lệnh liệt kê log tại '{remote_path}' trên {self.host} thất bại "
                f"(exit={exit_status}): {error_output or 'không rõ nguyên nhân'}"
            )

        return self._parse_find_output(output, remote_path)

    def fetch_selective_log_to_temp(
        self,
        entry: RemoteLogEntry,
        temp_root: Path,
        keep_raw_zip_dir: Optional[Path] = None,
    ) -> Tuple[Path, Optional[Path]]:
        """Tải log từ máy đích về thư mục tạm để phân tích ngay lập tức.

        - Nếu keep_raw_zip_dir được truyền vào (--keep-raw-zip):
          Tải bản .zip đầy đủ về keep_raw_zip_dir và trả về (saved_path, saved_path).
        - Nếu keep_raw_zip_dir là None (Mặc định - Selective Fast Fetch):
          Chỉ nén và tải các file log nhẹ cần cho trích xuất (debug.log, results.json, *.log,
          ctp_log_metadata.yaml, job.log, enc_logs/*), bỏ qua serial_logs/sysinfo/sqlite,
          giải nén vào temp_root / entry.name và trả về (local_dir, None).
        """
        safe_mkdir(temp_root)

        if keep_raw_zip_dir is not None:
            safe_mkdir(keep_raw_zip_dir)
            saved_path = self.download_entry(entry, keep_raw_zip_dir, selective=False)
            return saved_path, saved_path

        # Selective Fast Fetch vào temp_root
        if entry.entry_type == "dir" and self.enable_precompress:
            selective_zip = self._try_remote_precompress_dir(entry, temp_root, selective=True)
            if selective_zip is not None and selective_zip.is_file():
                extract_target = temp_root / entry.name
                try:
                    with zipfile.ZipFile(to_long_path(selective_zip), "r") as zf:
                        for member in zf.infolist():
                            rel_norm = os.path.normpath(member.filename)
                            if rel_norm.startswith("..") or os.path.isabs(rel_norm):
                                continue
                            dest_path = temp_root / rel_norm
                            if member.is_dir() or member.filename.endswith("/") or member.filename.endswith("\\"):
                                safe_mkdir(dest_path)
                            else:
                                safe_mkdir(dest_path.parent)
                                with zf.open(member, "r") as src_f, open(to_long_path(dest_path), "wb") as dst_f:
                                    while True:
                                        chunk = src_f.read(1024 * 256)
                                        if not chunk:
                                            break
                                        dst_f.write(chunk)
                    try:
                        os.remove(to_long_path(selective_zip))
                    except OSError:
                        pass
                    if extract_target.exists():
                        return extract_target, None
                    return temp_root, None
                except Exception as exc:
                    logger.debug("Giải nén selective zip thất bại (%s), dùng trực tiếp file zip", exc)
                    return selective_zip, None

        # Fallback: tải qua SFTP (có lọc bỏ các thư mục nặng khi selective=True)
        local_path = self.download_entry(entry, temp_root, selective=True)
        return local_path, None

    def download_entry(
        self,
        entry: RemoteLogEntry,
        local_parent_dir: Path,
        selective: bool = False,
    ) -> Path:
        """Tải một thư mục hoặc file rời về local_parent_dir."""
        safe_mkdir(local_parent_dir)

        if entry.entry_type == "dir" and self.enable_precompress:
            precompressed_zip = self._try_remote_precompress_dir(
                entry, local_parent_dir, selective=selective
            )
            if precompressed_zip is not None:
                return precompressed_zip

        local_target = local_parent_dir / entry.name
        try:
            sftp = self._ssh_client.open_sftp()
            try:
                if entry.entry_type == "dir":
                    self._download_dir_recursive(
                        sftp, entry.remote_path, local_target, selective=selective
                    )
                else:
                    progress = TransferProgress(entry.name) if self.show_progress else None
                    try:
                        self._download_file_with_retry(
                            sftp,
                            entry.remote_path,
                            to_long_path(local_target),
                            callback=progress.update if progress else None,
                        )
                    finally:
                        if progress:
                            progress.finish()
            finally:
                sftp.close()
        except (paramiko.SSHException, socket.timeout, OSError) as exc:
            raise DownloadError(f"Tải '{entry.remote_path}' từ {self.host} thất bại: {exc}") from exc

        return local_target

    def _try_remote_precompress_dir(
        self,
        entry: RemoteLogEntry,
        local_parent_dir: Path,
        selective: bool = False,
    ) -> Optional[Path]:
        """Nén thư mục trực tiếp trên máy đích trước khi tải qua SFTP.

        Khi selective=True, loại bỏ các thư mục/file nặng không cần cho phân tích
        (serial_logs, sysinfo, connection_configs, *.journal.sqlite, results.html, results.tap).
        """
        clean_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", entry.name)
        rand_tag = uuid.uuid4().hex[:8]
        norm_remote_path = normalize_remote_path(entry.remote_path)

        local_zip_path = local_parent_dir / f"{entry.name}.zip"
        long_local_zip_path = to_long_path(local_zip_path)

        if self.remote_os == "linux":
            parent_dir = posixpath.dirname(norm_remote_path) or "/"
            base_dir = posixpath.basename(norm_remote_path)
            remote_temp_zip = f"/tmp/ja_mfg_{clean_name}_{rand_tag}.zip"
            q_parent = shlex.quote(parent_dir)
            q_zip = shlex.quote(remote_temp_zip)
            q_base = shlex.quote(base_dir)
            if selective:
                py_selective = (
                    "import os,sys,zipfile; "
                    "zf=zipfile.ZipFile(sys.argv[1],'w',zipfile.ZIP_DEFLATED); "
                    "base=sys.argv[2]; "
                    "skip={'serial_logs','sysinfo','connection_configs'}; "
                    "suf=('.journal.sqlite','results.html','results.tap','.pcap'); "
                    "[zf.write(os.path.join(r,f)) for r,dirs,files in os.walk(base) "
                    "if not dirs.__setitem__(slice(None),[d for d in dirs if d not in skip]) "
                    "for f in files if not f.endswith(suf)]; "
                    "zf.close()"
                )
                q_py = shlex.quote(py_selective)
                compress_cmd = (
                    f"(cd {q_parent} && ("
                    f"zip -rq {q_zip} {q_base} "
                    f"-x '*/serial_logs/*' '*/sysinfo/*' '*/connection_configs/*' "
                    f"'*/*.journal.sqlite' '*/results.html' '*/results.tap' '*.pcap' 2>/dev/null || "
                    f"python3 -c {q_py} {q_zip} {q_base} 2>/dev/null || "
                    f"python -c {q_py} {q_zip} {q_base}"
                    f"))"
                )
            else:
                compress_cmd = (
                    f"(cd {q_parent} && ("
                    f"zip -rq {q_zip} {q_base} 2>/dev/null || "
                    f"python3 -m zipfile -c {q_zip} {q_base} 2>/dev/null || "
                    f"python -m zipfile -c {q_zip} {q_base}"
                    f"))"
                )
            cleanup_cmd = f"rm -f {q_zip}"
        else:
            import base64
            win_path = norm_remote_path.replace("/", "\\")
            remote_temp_zip = f"$env:TEMP\\ja_mfg_{clean_name}_{rand_tag}.zip"
            if selective:
                ps_script = (
                    f"$ErrorActionPreference='Stop'; "
                    f"Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem; "
                    f"$z = Join-Path $env:TEMP 'ja_mfg_{clean_name}_{rand_tag}.zip'; "
                    f"if (Test-Path -LiteralPath $z) {{ Remove-Item -LiteralPath $z -Force }}; "
                    f"$base = [System.IO.Path]::GetFullPath('{win_path}'); "
                    f"$parent = [System.IO.Path]::GetDirectoryName($base); "
                    f"$arch = [System.IO.Compression.ZipFile]::Open($z, 'Create'); "
                    f"try {{ "
                    f"Get-ChildItem -LiteralPath ('\\\\?\\' + $base) -Recurse -File -Force | Where-Object {{ "
                    f"$_.FullName -notmatch '\\\\(serial_logs|sysinfo|connection_configs)\\\\' -and "
                    f"$_.Name -notmatch '(\\.journal\\.sqlite|results\\.html|results\\.tap|\\.pcap)$' "
                    f"}} | ForEach-Object {{ "
                    f"$cleanFull = $_.FullName -replace '^\\\\\\\\\\?\\\\',''; "
                    f"$rel = $cleanFull.Substring($parent.Length).TrimStart('\\').Replace('\\','/'); "
                    f"[System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($arch, $_.FullName, $rel, 'Fastest') | Out-Null "
                    f"}} "
                    f"}} finally {{ $arch.Dispose() }}; "
                    f"Write-Output $z"
                )
            else:
                ps_script = (
                    f"$ErrorActionPreference='Stop'; "
                    f"$z = Join-Path $env:TEMP 'ja_mfg_{clean_name}_{rand_tag}.zip'; "
                    f"Compress-Archive -LiteralPath '{win_path}' -DestinationPath $z -Force; "
                    f"Write-Output $z"
                )
            b64_compress = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
            cleanup_ps = f"Remove-Item -LiteralPath (Join-Path $env:TEMP 'ja_mfg_{clean_name}_{rand_tag}.zip') -Force -ErrorAction SilentlyContinue"
            b64_cleanup = base64.b64encode(cleanup_ps.encode("utf-16le")).decode("ascii")
            compress_cmd = f"powershell -NoProfile -NonInteractive -EncodedCommand {b64_compress}"
            cleanup_cmd = f"powershell -NoProfile -NonInteractive -EncodedCommand {b64_cleanup}"

        try:
            _, stdout, stderr = self._ssh_client.exec_command(compress_cmd, timeout=min(60, self.timeout * 3))
            exit_status = stdout.channel.recv_exit_status()
            out_text = stdout.read().decode("utf-8", errors="replace").strip()
            if exit_status != 0:
                return None

            sftp = self._ssh_client.open_sftp()
            try:
                actual_remote_zip = remote_temp_zip
                if self.remote_os == "windows":
                    lines = [ln.strip() for ln in out_text.splitlines() if ln.strip()]
                    if lines:
                        actual_remote_zip = normalize_remote_path(lines[-1])
                        if not actual_remote_zip.startswith("/"):
                            actual_remote_zip = "/" + actual_remote_zip

                progress = TransferProgress(entry.name) if self.show_progress else None
                try:
                    self._download_file_with_retry(
                        sftp,
                        actual_remote_zip,
                        long_local_zip_path,
                        callback=progress.update if progress else None,
                    )
                finally:
                    if progress:
                        progress.finish()
            finally:
                sftp.close()
                self._ssh_client.exec_command(cleanup_cmd)

            return local_zip_path
        except Exception:
            try:
                self._ssh_client.exec_command(cleanup_cmd)
            except Exception:
                pass
            return None

    def _download_file_with_retry(
        self,
        sftp: "paramiko.SFTPClient",
        remote_file: str,
        local_file: str,
        callback=None,
        max_retries: int = config.SFTP_MAX_RETRIES,
    ) -> None:
        for attempt in range(1, max_retries + 1):
            try:
                sftp.get(remote_file, local_file, callback=callback)
                return
            except (paramiko.SSHException, socket.timeout, socket.error, OSError) as exc:
                if attempt == max_retries:
                    raise DownloadError(f"Tải '{remote_file}' thất bại sau {max_retries} lần thử: {exc}") from exc
                time.sleep(1.0 * attempt)

    def _download_dir_recursive(
        self,
        sftp: "paramiko.SFTPClient",
        remote_dir: str,
        local_dir: Path,
        selective: bool = False,
    ) -> None:
        safe_mkdir(local_dir)
        norm_remote_dir = normalize_remote_path(remote_dir)

        for item in sftp.listdir_attr(norm_remote_dir):
            fname = item.filename
            remote_item_path = f"{norm_remote_dir.rstrip('/')}/{fname}"
            local_item_path = local_dir / fname

            if stat.S_ISLNK(item.st_mode):
                continue
            if stat.S_ISDIR(item.st_mode):
                if selective and fname in SELECTIVE_SKIP_DIRS:
                    continue
                self._download_dir_recursive(sftp, remote_item_path, local_item_path, selective=selective)
            elif stat.S_ISREG(item.st_mode):
                if selective and fname.endswith(SELECTIVE_SKIP_SUFFIXES):
                    continue
                self._download_file_with_retry(sftp, remote_item_path, to_long_path(local_item_path))

    @staticmethod
    def _build_linux_find_command(remote_base_path: str, serial_number: str) -> str:
        args = [
            "find",
            remote_base_path,
            "-mindepth", "1",
            "-maxdepth", "1",
            "-iname", f"*{serial_number}*",
            "-printf", "%f\\t%T@\\t%y\\n",
        ]
        return " ".join(shlex.quote(arg) for arg in args)

    @staticmethod
    def _build_windows_find_command(remote_base_path: str, serial_number: str) -> str:
        import base64
        win_base = remote_base_path.replace("/", "\\")
        ps_cmd = (
            f"Get-ChildItem -LiteralPath '{win_base}' -Depth 1 -Force -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.Name -like '*{serial_number}*' }} | "
            f"ForEach-Object {{ "
            f"$t = ([DateTimeOffset]$_.LastWriteTime).ToUnixTimeSeconds(); "
            f"$k = if ($_.PSIsContainer) {{ 'd' }} else {{ 'f' }}; "
            f"$p = $_.FullName.Replace('\\','/'); "
            f"Write-Output \"$($_.Name)`t$t`t$k`t$p\" "
            f"}}"
        )
        b64 = base64.b64encode(ps_cmd.encode("utf-16le")).decode("ascii")
        return f"powershell -NoProfile -NonInteractive -EncodedCommand {b64}"

    @staticmethod
    def _parse_find_output(output: str, remote_base_path: str) -> List[RemoteLogEntry]:
        entries: List[RemoteLogEntry] = []
        clean_base = remote_base_path.rstrip("/")
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            name, mtime_str, type_char = parts[0], parts[1], parts[2]
            full_remote = parts[3].strip() if len(parts) >= 4 and parts[3].strip() else f"{clean_base}/{name}"
            entry_type = "dir" if type_char == "d" else "file"
            try:
                mtime_epoch = float(mtime_str)
            except ValueError:
                continue
            entries.append(
                RemoteLogEntry(
                    name=name,
                    remote_path=normalize_remote_path(full_remote),
                    mtime_epoch=mtime_epoch,
                    entry_type=entry_type,
                )
            )
        return entries
