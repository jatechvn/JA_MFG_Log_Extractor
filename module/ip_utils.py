"""Tiện ích chuẩn hoá IP nhập từ người dùng: cho phép gõ tắt 2 octet cuối,
hoặc gõ liền không dấu chấm."""
import ipaddress
from typing import Optional


def normalize_ip(raw_ip: str, prefix: str) -> str:
    """Tự hoàn thiện IP rút gọn thành IP đầy đủ dựa trên `prefix` (vd '172.19').

    Hỗ trợ 2 kiểu gõ tắt:
    - '116.174' (2 octet cuối, có dấu chấm) -> '172.19.116.174'
    - '116191' hoặc '11624' (gõ liền không dấu chấm) -> hiểu 3 ký tự đầu là
      octet thứ 3, phần còn lại là octet thứ 4 -> '172.19.116.191' /
      '172.19.116.24'. Chỉ áp dụng khi cả 2 phần tách ra đều là octet hợp lệ
      (0-255), tránh đoán bậy với chuỗi số không phải IP.

    Đã nhập đủ 4 octet hoặc định dạng khác (hostname, IP mạng khác...) thì
    giữ nguyên, không đoán thêm.
    """
    raw_ip = raw_ip.strip()
    parts = raw_ip.split(".")

    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return f"{prefix}.{raw_ip}"

    if raw_ip.isdigit() and 4 <= len(raw_ip) <= 6:
        octet3, octet4 = raw_ip[:3], raw_ip[3:]
        if octet4 and 0 <= int(octet3) <= 255 and 0 <= int(octet4) <= 255:
            return f"{prefix}.{octet3}.{octet4}"

    return raw_ip


def expand_ip(raw_ip: str, ip_prefix: Optional[str] = None) -> str:
    """Chuẩn hoá IP rút gọn (2 octet cuối hoặc 4-6 chữ số liền) và kiểm tra tính hợp lệ IPv4."""
    if not raw_ip or not raw_ip.strip():
        raise ValueError("Địa chỉ IP không được để trống.")
    if ip_prefix is None:
        from . import config
        ip_prefix = config.DEFAULT_IP_PREFIX
    candidate = normalize_ip(raw_ip, ip_prefix)
    try:
        addr = ipaddress.ip_address(candidate)
        if addr.version != 4:
            raise ValueError(f"Địa chỉ IP không phải IPv4 hợp lệ: '{raw_ip}'")
        return str(addr)
    except ValueError as exc:
        raise ValueError(
            f"Địa chỉ IP không hợp lệ: '{raw_ip}' (sau chuẩn hoá: '{candidate}'). "
            f"Hãy nhập IP đầy đủ (VD: 172.19.116.174) hoặc 2 octet cuối (VD: 116.174 / 116174)."
        ) from exc
