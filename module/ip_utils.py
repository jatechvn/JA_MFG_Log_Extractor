"""Tiện ích chuẩn hoá IP nhập từ người dùng và sơ đồ IP các Line trạm test (Line 3, Line 2, Line 1).

Cho phép:
- Chọn từ sơ đồ 3 Line (`172.19.116.121` .. `172.19.116.199`)
- Gõ tắt 1 octet cuối theo sơ đồ (VD: '.174' hoặc '174' -> '172.19.116.174')
- Gõ tắt 2 octet cuối (VD: '116.174' hoặc '116174' -> '172.19.116.174')
- Gõ IP đầy đủ bất kỳ (VD: '172.19.116.174', '172.21.168.241', ...)
"""
import ipaddress
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_STATION_OCTET3 = "116"

# Sơ đồ 3 Line (10 hàng x 2 cột mỗi Line) theo đúng bố cục thực tế tại xưởng:
# Mỗi phần tử là (octet_4, style)
# style: "pink" | "green" | "blue" | "amber" | "dim" (inactive/xám mờ)
STATION_LINES: List[Dict[str, Any]] = [
    {
        "name": "Line 3",
        "active_Summary": "20/20",
        "rows": [
            ((188, "pink"), (189, "pink")),
            ((199, "pink"), (198, "green")),
            ((187, "blue"), (197, "green")),
            ((191, "pink"), (190, "green")),
            ((180, "green"), (181, "green")),
            ((174, "green"), (184, "green")),
            ((185, "pink"), (186, "green")),
            ((172, "green"), (182, "green")),
            ((192, "green"), (194, "green")),
            ((193, "green"), (195, "green")),
        ],
    },
    {
        "name": "Line 2",
        "active_Summary": "16/20",
        "rows": [
            ((160, "amber"), (159, "amber")),
            ((158, "amber"), (157, "amber")),
            ((156, "amber"), (155, "dim")),
            ((154, "dim"), (153, "dim")),
            ((152, "amber"), (151, "amber")),
            ((150, "pink"), (149, "amber")),
            ((148, "amber"), (147, "dim")),
            ((146, "amber"), (145, "amber")),
            ((144, "amber"), (143, "blue")),
            ((142, "pink"), (141, "green")),
        ],
    },
    {
        "name": "Line 1",
        "active_Summary": "16/20",
        "rows": [
            ((140, "dim"), (139, "dim")),
            ((138, "dim"), (137, "dim")),
            ((136, "amber"), (135, "amber")),
            ((134, "amber"), (133, "amber")),
            ((132, "amber"), (131, "amber")),
            ((130, "amber"), (129, "amber")),
            ((128, "amber"), (127, "amber")),
            ((126, "amber"), (125, "amber")),
            ((124, "amber"), (123, "amber")),
            ((122, "amber"), (121, "amber")),
        ],
    },
]


def get_station_lookup(ip_prefix: Optional[str] = None, octet3: str = DEFAULT_STATION_OCTET3) -> Dict[int, Dict[str, Any]]:
    """Trả về bảng tra cứu nhanh theo octet thứ 4 (121..199) trong sơ đồ trạm test."""
    if ip_prefix is None:
        from . import config
        ip_prefix = config.DEFAULT_IP_PREFIX
    lookup: Dict[int, Dict[str, Any]] = {}
    for line_idx, line_info in enumerate(STATION_LINES):
        line_name = line_info["name"]
        summary = line_info["active_Summary"]
        for row_idx, pair in enumerate(line_info["rows"]):
            for sub_col_idx, (oct4, style) in enumerate(pair):
                lookup[oct4] = {
                    "octet": oct4,
                    "full_ip": f"{ip_prefix}.{octet3}.{oct4}",
                    "line": line_name,
                    "line_summary": summary,
                    "style": style,
                    "active": style != "dim",
                    "line_idx": line_idx,
                    "row_idx": row_idx,
                    "sub_col_idx": sub_col_idx,
                    "grid_col": line_idx * 2 + sub_col_idx,
                }
    return lookup


def get_station_line_info(ip_or_raw: str, ip_prefix: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Tra cứu thông tin Line (Line 1 / Line 2 / Line 3) của một địa chỉ IP nếu thuộc sơ đồ."""
    if ip_prefix is None:
        from . import config
        ip_prefix = config.DEFAULT_IP_PREFIX
    try:
        full_ip = expand_ip(ip_or_raw, ip_prefix=ip_prefix)
    except Exception:
        return None
    parts = full_ip.split(".")
    if len(parts) == 4 and f"{parts[0]}.{parts[1]}" == ip_prefix and parts[2] == DEFAULT_STATION_OCTET3:
        try:
            oct4 = int(parts[3])
            return get_station_lookup(ip_prefix=ip_prefix).get(oct4)
        except ValueError:
            return None
    return None


def normalize_ip(raw_ip: str, prefix: str, default_octet3: str = DEFAULT_STATION_OCTET3) -> str:
    """Tự hoàn thiện IP rút gọn thành IP đầy đủ dựa trên `prefix` (vd '172.19').

    Hỗ trợ 3 kiểu gõ tắt:
    - '.174' hoặc '174' (1 octet cuối trên sơ đồ Line 1/2/3) -> '172.19.116.174'
    - '116.174' (2 octet cuối, có dấu chấm) -> '172.19.116.174'
    - '116191' hoặc '11624' (gõ liền không dấu chấm) -> hiểu 3 ký tự đầu là
      octet thứ 3, phần còn lại là octet thứ 4 -> '172.19.116.191' /
      '172.19.116.24'.

    Đã nhập đủ 4 octet hoặc định dạng khác (hostname, IP mạng khác...) thì
    giữ nguyên, không đoán thêm.
    """
    raw_ip = raw_ip.strip()

    # Kiểu 1: '.174' hoặc '174' (1 octet cuối của dải 172.19.116.xxx)
    single_octet_candidate = raw_ip[1:] if raw_ip.startswith(".") else raw_ip
    if single_octet_candidate.isdigit() and 1 <= len(single_octet_candidate) <= 3:
        oct_val = int(single_octet_candidate)
        if 1 <= oct_val <= 254:
            return f"{prefix}.{default_octet3}.{oct_val}"

    parts = raw_ip.split(".")

    # Kiểu 2: '116.174' (2 octet cuối)
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return f"{prefix}.{raw_ip}"

    # Kiểu 3: '116174' (4-6 chữ số liền)
    if raw_ip.isdigit() and 4 <= len(raw_ip) <= 6:
        octet3, octet4 = raw_ip[:3], raw_ip[3:]
        if octet4 and 0 <= int(octet3) <= 255 and 0 <= int(octet4) <= 255:
            return f"{prefix}.{octet3}.{octet4}"

    return raw_ip


def expand_ip(raw_ip: str, ip_prefix: Optional[str] = None) -> str:
    """Chuẩn hoá IP rút gọn (1 octet cuối, 2 octet cuối hoặc 4-6 chữ số liền) và kiểm tra tính hợp lệ IPv4."""
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
            f"Hãy nhập theo sơ đồ (VD: .174, 174), 2 octet cuối (VD: 116.174, 116174) hoặc IP đầy đủ (VD: 172.19.116.174)."
        ) from exc
