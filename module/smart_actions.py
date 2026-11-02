# -*- coding: utf-8 -*-
"""Các tính năng thông minh hỗ trợ kỹ thuật viên cho JA_MFG_Log_Extractor v1.7.0:
1. Đọc/ghi Clipboard đa nền tảng (ctypes Win32 API trên Windows) để nhận diện IP / Serial Number
   hoặc copy nhanh đường dẫn thư mục báo cáo.
2. Lưu & gợi ý lịch sử 5 IP máy test và 5 Serial Number gần nhất (reports/recent_history.json).
3. Mở nhanh thư mục báo cáo (reports/<Target_SN>) hoặc highlight file trong Windows Explorer.
4. Xuất tự động reports/retry_failed.csv cho các mục FAIL trong phiên chạy Batch / Multi-SN.
"""

import csv
from datetime import datetime
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple, Union

from .ip_utils import normalize_ip
from .log_finder import parse_sn_list
from .path_utils import to_long_path, to_standard_path


_SN_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.\-]{4,36}$")


def get_clipboard_text() -> str:
    """Đọc nội dung văn bản thuần từ Clipboard hệ thống (không làm treo hay lộ lỗi)."""
    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            user32.OpenClipboard.restype = ctypes.c_int
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = ctypes.c_int
            user32.GetClipboardData.argtypes = [ctypes.c_uint]
            user32.GetClipboardData.restype = ctypes.c_void_p

            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalUnlock.restype = ctypes.c_int

            cf_unicodetext = 13
            if not user32.OpenClipboard(None):
                return ""
            try:
                handle = user32.GetClipboardData(cf_unicodetext)
                if not handle:
                    return ""
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return ""
                try:
                    text = ctypes.wstring_at(ptr)
                    return text or ""
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        except Exception:
            return ""

    if sys.platform == "darwin":
        try:
            proc = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                timeout=0.5,
                check=False,
            )
            return proc.stdout if proc.returncode == 0 else ""
        except Exception:
            return ""

    for cmd in (["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=0.5,
                check=False,
            )
            if proc.returncode == 0:
                return proc.stdout
        except Exception:
            continue
    return ""


def set_clipboard_text(text: str) -> bool:
    """Ghi chuỗi văn bản vào Clipboard hệ thống."""
    if not text:
        return False

    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            user32.OpenClipboard.restype = ctypes.c_int
            user32.EmptyClipboard.argtypes = []
            user32.EmptyClipboard.restype = ctypes.c_int
            user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
            user32.SetClipboardData.restype = ctypes.c_void_p
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = ctypes.c_int

            kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
            kernel32.GlobalAlloc.restype = ctypes.c_void_p
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalUnlock.restype = ctypes.c_int
            kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
            kernel32.GlobalFree.restype = ctypes.c_void_p

            cf_unicodetext = 13
            gmem_moveable = 0x0002

            encoded = text.encode("utf-16-le") + b"\x00\x00"
            if not user32.OpenClipboard(None):
                return False
            try:
                user32.EmptyClipboard()
                h_mem = kernel32.GlobalAlloc(gmem_moveable, len(encoded))
                if not h_mem:
                    return False
                ptr = kernel32.GlobalLock(h_mem)
                if not ptr:
                    kernel32.GlobalFree(h_mem)
                    return False
                try:
                    ctypes.memmove(ptr, encoded, len(encoded))
                finally:
                    kernel32.GlobalUnlock(h_mem)
                if not user32.SetClipboardData(cf_unicodetext, h_mem):
                    kernel32.GlobalFree(h_mem)
                    return False
                return True
            finally:
                user32.CloseClipboard()
        except Exception:
            return False

    if sys.platform == "darwin":
        try:
            proc = subprocess.run(
                ["pbcopy"],
                input=text,
                text=True,
                timeout=0.5,
                check=False,
            )
            return proc.returncode == 0
        except Exception:
            return False

    for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        try:
            proc = subprocess.run(
                cmd,
                input=text,
                text=True,
                timeout=0.5,
                check=False,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            continue
    return False


def detect_clipboard_ip(clip_text: str, default_prefix: str = "172.19") -> Optional[str]:
    """Nhận diện địa chỉ IP máy test hợp lệ trong Clipboard (full IPv4, viết tắt 2 octet, hoặc .xxx trên sơ đồ).
    Trả về IP đã chuẩn hóa (vd '172.19.116.174') hoặc None nếu nội dung không phải IP.
    """
    if not clip_text:
        return None
    cleaned = clip_text.strip()
    if not cleaned or len(cleaned) > 45 or "\n" in cleaned or "\r" in cleaned:
        return None
    # Không tự đoán số nguyên ngắn 1..3 chữ số không có dấu chấm trong clipboard là IP
    if cleaned.isdigit() and len(cleaned) <= 3:
        return None

    candidate = normalize_ip(cleaned, default_prefix)
    try:
        ip_obj = ipaddress.ip_address(candidate)
        if ip_obj.version == 4:
            return str(ip_obj)
    except ValueError:
        pass
    return None


def detect_clipboard_sn(clip_text: str, default_prefix: str = "172.19") -> Optional[str]:
    """Nhận diện 1 hoặc nhiều Serial Number hợp lệ trong Clipboard (hỗ trợ cả copy từ Excel có xuống dòng).
    Từ chối IP, đường dẫn file, URL hoặc văn bản thông thường.
    """
    if not clip_text:
        return None
    cleaned = clip_text.strip()
    if not cleaned or len(cleaned) > 200:
        return None

    normalized_lines = ", ".join(line.strip() for line in cleaned.splitlines() if line.strip())
    if not normalized_lines:
        return None

    if detect_clipboard_ip(normalized_lines, default_prefix) is not None:
        return None
    if any(marker in normalized_lines for marker in ("://", "\\", "/", "@", "=")):
        return None

    tokens = parse_sn_list(normalized_lines)
    if not tokens or len(tokens) > 10:
        return None

    for tok in tokens:
        if " " in tok or not _SN_TOKEN_RE.match(tok):
            return None
        has_alpha = any(ch.isalpha() for ch in tok)
        has_digit = any(ch.isdigit() for ch in tok)
        if not (has_alpha and has_digit):
            return None

    return ", ".join(tokens)


def resolve_best_report_target(
    results: Sequence[Dict],
    default_reports_dir: Union[str, Path],
) -> Tuple[Optional[Path], bool]:
    """Xác định đường dẫn báo cáo tối ưu nhất để mở sau khi trích xuất:
    - Nếu chỉ có 1 thư mục báo cáo (<reports>/<Target_SN>) hợp lệ -> trả về (Path(out_dir), False).
    - Nếu có nhiều thư mục báo cáo -> trả về (Path(default_reports_dir), False).
    - Nếu không có mục nào có out_dir hợp lệ -> trả về (Path(default_reports_dir), False) nếu tồn tại.
    """
    std_base = Path(to_standard_path(default_reports_dir))
    if not results:
        return (std_base, False) if os.path.exists(to_long_path(std_base)) else (None, False)

    valid_dirs: List[Path] = []
    seen_dirs = set()

    for item in results:
        out_dir_str = item.get("out_dir")
        if out_dir_str and out_dir_str != "-":
            std_d = to_standard_path(out_dir_str)
            if std_d not in seen_dirs and os.path.exists(to_long_path(std_d)):
                seen_dirs.add(std_d)
                valid_dirs.append(Path(std_d))

    if len(valid_dirs) == 1:
        return valid_dirs[0], False

    if len(valid_dirs) > 1:
        if os.path.exists(to_long_path(std_base)):
            return std_base, False
        return valid_dirs[0], False

    if os.path.exists(to_long_path(std_base)):
        return std_base, False
    return None, False


resolve_best_open_target = resolve_best_report_target


def open_output_target(target_path: Union[str, Path], select_file: bool = False) -> bool:
    """Mở thư mục báo cáo hoặc highlight file trong trình quản lý file của hệ điều hành."""
    if not target_path:
        return False

    std_path = to_standard_path(target_path)
    long_path = to_long_path(std_path)
    if not os.path.exists(long_path):
        return False

    is_file = os.path.isfile(long_path)

    try:
        if sys.platform == "win32":
            if select_file and is_file:
                subprocess.Popen(["explorer.exe", f"/select,{std_path}"])
                return True
            target_dir = os.path.dirname(std_path) if is_file else std_path
            if hasattr(os, "startfile"):
                os.startfile(target_dir)
            else:
                subprocess.Popen(["explorer.exe", target_dir])
            return True

        if sys.platform == "darwin":
            cmd = ["open", "-R", std_path] if (select_file and is_file) else [
                "open",
                os.path.dirname(std_path) if is_file else std_path,
            ]
            subprocess.Popen(cmd)
            return True

        target_dir = os.path.dirname(std_path) if is_file else std_path
        subprocess.Popen(["xdg-open", target_dir])
        return True
    except Exception:
        return False


open_download_target = open_output_target


def export_retry_csv(results: Sequence[Dict], output_dir: Union[str, Path]) -> Optional[Path]:
    """Xuất danh sách các mục FAIL ra file retry_failed.csv trong output_dir để chạy lại dễ dàng."""
    failed_rows = []
    for r in results or []:
        if r.get("status") == "FAIL":
            src = r.get("source_target") or r.get("host") or r.get("log_path") or ""
            sn = r.get("sn") or ""
            out_base = r.get("output_base") or ""
            if src or (sn and sn != "N/A"):
                failed_rows.append((src, sn, out_base))

    if not failed_rows:
        return None

    out_dir_path = Path(to_standard_path(output_dir))
    retry_file = out_dir_path / "retry_failed.csv"
    try:
        os.makedirs(to_long_path(out_dir_path), exist_ok=True)
        with open(to_long_path(retry_file), "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["LogPath", "TargetSN", "OutputBaseDir"])
            for src, sn, out_base in failed_rows:
                writer.writerow([src, sn, out_base])
        return retry_file
    except OSError:
        return None


class RecentHistoryManager:
    """Quản lý lịch sử IP máy test và Serial Number tra cứu gần đây (reports/recent_history.json).
    Đảm bảo không bao giờ lưu tài khoản hay mật khẩu.
    """

    def __init__(self, history_file: Path, max_items: int = 5) -> None:
        self.history_file = Path(history_file)
        self.max_items = max(1, int(max_items))

    def load(self) -> Dict:
        """Đọc lịch sử từ đĩa, trả về cấu trúc mặc định nếu file chưa tồn tại hoặc lỗi."""
        default_data = {
            "recent_ips": [],
            "recent_sns": [],
            "last_target_path": "",
            "updated_at": "",
        }
        if not self.history_file.is_file():
            return default_data
        try:
            raw = json.loads(self.history_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return default_data
            ips = [str(x).strip() for x in raw.get("recent_ips", []) if str(x).strip()]
            sns = [str(x).strip() for x in raw.get("recent_sns", []) if str(x).strip()]
            last_target = str(raw.get("last_target_path", "") or "").strip()
            return {
                "recent_ips": ips[: self.max_items],
                "recent_sns": sns[: self.max_items],
                "last_target_path": last_target,
                "updated_at": str(raw.get("updated_at", "") or ""),
            }
        except Exception:
            return default_data

    def get_recent_ips(self) -> List[str]:
        return self.load()["recent_ips"]

    def get_recent_sns(self) -> List[str]:
        return self.load()["recent_sns"]

    def record_session(
        self,
        ips: Sequence[str],
        sns: Sequence[str],
        last_target_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """Cập nhật IP và SN vừa tra cứu lên đầu danh sách lịch sử."""
        data = self.load()
        recent_ips: List[str] = list(data["recent_ips"])
        recent_sns: List[str] = list(data["recent_sns"])

        for ip in reversed([str(x).strip() for x in ips if str(x).strip()]):
            if ip in recent_ips:
                recent_ips.remove(ip)
            recent_ips.insert(0, ip)

        for sn in reversed([str(x).strip() for x in sns if str(x).strip()]):
            if sn in recent_sns:
                recent_sns.remove(sn)
            recent_sns.insert(0, sn)

        updated = {
            "recent_ips": recent_ips[: self.max_items],
            "recent_sns": recent_sns[: self.max_items],
            "last_target_path": (
                to_standard_path(last_target_path)
                if last_target_path
                else data.get("last_target_path", "")
            ),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            self.history_file.write_text(
                json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
