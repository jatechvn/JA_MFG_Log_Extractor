# -*- coding: utf-8 -*-
"""Tiện ích xử lý đường dẫn tương thích đa nền tảng (Windows & Linux).

Giải quyết vấn đề giới hạn 260 ký tự (MAX_PATH) trên Windows:
- Tự động chuyển đổi đường dẫn sang Extended-Length Path (\\\\?\\) trên Windows.
- Cung cấp safe_mkdir và safe_remove cho thư mục có độ sâu lớn.
- Chuẩn hóa đường dẫn từ xa (SFTP) cho cả Linux lẫn Windows.
"""

import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Union


def to_long_path(path: Union[str, Path]) -> str:
    """Chuyển đổi đường dẫn tuyệt đối sang định dạng Extended-Length Path trên Windows.

    - Nếu chạy trên Linux/macOS: giữ nguyên đường dẫn chuỗi.
    - Nếu chạy trên Windows:
      * 'D:\\folder\\file' -> '\\\\?\\D:\\folder\\file'
      * '\\\\server\\share' (UNC) -> '\\\\?\\UNC\\server\\share'
      * Đã có tiền tố '\\\\?\\' thì giữ nguyên.
    """
    path_str = str(path)
    if not path_str:
        return path_str

    if sys.platform != "win32":
        return path_str

    if path_str.startswith("\\\\?\\"):
        return path_str

    abs_path = os.path.abspath(path_str)
    if abs_path.startswith("\\\\?\\"):
        return abs_path

    if abs_path.startswith("\\\\"):
        # UNC path: \\server\share -> \\?\UNC\server\share
        return "\\\\?\\UNC\\" + abs_path[2:]

    # Local drive path: D:\path -> \\?\D:\path
    return "\\\\?\\" + abs_path


def safe_mkdir(path: Union[str, Path]) -> Path:
    """Tạo thư mục an toàn, hỗ trợ đường dẫn vượt quá 260 ký tự trên Windows."""
    long_p = to_long_path(path)
    os.makedirs(long_p, exist_ok=True)
    return Path(path)


def _handle_remove_readonly(func, path, exc_info):
    """Callback xử lý file read-only khi shutil.rmtree gặp lỗi permission."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def safe_remove(path: Union[str, Path]) -> None:
    """Xóa file hoặc thư mục an toàn ngay cả khi đường dẫn rất dài hoặc chứa file read-only."""
    long_p = to_long_path(path)
    if not os.path.exists(long_p):
        return

    if os.path.isdir(long_p):
        try:
            shutil.rmtree(long_p, onerror=_handle_remove_readonly)
        except TypeError:
            # Python 3.12+ hỗ trợ on_exc
            shutil.rmtree(long_p, on_exc=lambda fn, p, exc: _handle_remove_readonly(fn, p, None))
    else:
        try:
            os.chmod(long_p, stat.S_IWRITE)
        except OSError:
            pass
        os.unlink(long_p)


def normalize_remote_path(path: str) -> str:
    """Chuẩn hóa đường dẫn từ xa để dùng với SFTP (OpenSSH trên cả Linux và Windows).

    SFTP luôn ưu tiên dấu gạch chéo xuôi '/', loại bỏ dấu gạch chéo ngược '\\'.
    Ví dụ: 'D:\\logs\\test' -> 'D:/logs/test'.
    """
    if not path:
        return ""
    normalized = path.replace("\\", "/").strip()
    # Rút gọn các dấu gạch chéo liên tiếp (trừ trường hợp UNC //)
    while "//" in normalized and not normalized.startswith("//"):
        normalized = normalized.replace("//", "/")
    return normalized


def check_disk_space(target_path: Union[str, Path], min_bytes: int = 1024 * 1024 * 1024) -> tuple[bool, int, int]:
    """Kiểm tra dung lượng đĩa trống tại thư mục target_path.

    Trả về: (đủ_dung_lượng: bool, dung_lượng_trống_bytes: int, tổng_dung_lượng_bytes: int).
    """
    try:
        check_dir = os.path.abspath(str(target_path))
        # Nếu thư mục chưa tồn tại, kiểm tra thư mục cha
        while not os.path.exists(check_dir) and os.path.dirname(check_dir) != check_dir:
            check_dir = os.path.dirname(check_dir)
        usage = shutil.disk_usage(check_dir)
        return (usage.free >= min_bytes, usage.free, usage.total)
    except Exception:
        # Nếu không lấy được dung lượng (vd phân vùng đặc biệt), coi như hợp lệ
        return (True, 0, 0)

