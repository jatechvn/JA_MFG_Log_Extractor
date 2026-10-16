"""Các exception nghiệp vụ riêng, tránh để lỗi thư viện (paramiko/scp) rò rỉ
lên tầng trên và giúp main.py xử lý/log theo từng loại lỗi rõ ràng."""


class SshConnectionError(Exception):
    """Không thiết lập được kết nối SSH tới máy đích (sai IP, sai user/pass, timeout...)."""


class RemoteCommandError(Exception):
    """Lệnh liệt kê log trên máy đích thực thi thất bại (sai đường dẫn, quyền truy cập...)."""


class DownloadError(Exception):
    """Tải log về máy cục bộ thất bại (mất kết nối giữa chừng, hết dung lượng đĩa...)."""
