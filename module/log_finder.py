"""Business logic thuần: mô hình hoá kết quả tìm log và xử lý lựa chọn của người dùng.

Không phụ thuộc paramiko/SSH -> dễ test độc lập.
"""
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class RemoteLogEntry:
    """Một thư mục (hoặc file rời) log trên máy đích khớp với SN cần tìm."""

    name: str
    remote_path: str
    mtime_epoch: float
    entry_type: str  # "dir" hoặc "file"

    @property
    def mtime_str(self) -> str:
        return datetime.fromtimestamp(self.mtime_epoch).strftime("%Y-%m-%d %H:%M:%S")


def parse_sn_list(raw_sn: str) -> List[str]:
    """Tách chuỗi nhập nhiều Serial Number (ngăn cách bởi dấu phẩy hoặc chấm phẩy),
    loại bỏ khoảng trắng thừa và giữ nguyên thứ tự không trùng lặp.
    """
    if not raw_sn:
        return []
    tokens = re.split(r"[,;]+", raw_sn)
    result: List[str] = []
    seen = set()
    for tok in tokens:
        cleaned = tok.strip(' "\'\t\r\n')
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def sort_entries_by_time_desc(entries: List[RemoteLogEntry]) -> List[RemoteLogEntry]:
    """Log mới nhất lên đầu để người dùng dễ chọn."""
    return sorted(entries, key=lambda e: e.mtime_epoch, reverse=True)


def filter_entries(
    entries: List[RemoteLogEntry],
    max_days: Optional[float] = None,
    latest_n: Optional[int] = None,
    now_epoch: Optional[float] = None,
) -> List[RemoteLogEntry]:
    """Sắp xếp log mới nhất lên đầu, lọc theo số ngày gần nhất (--days)
    và giới hạn số bản ghi mới nhất (--latest N).
    """
    sorted_list = sort_entries_by_time_desc(entries)
    if max_days is not None and max_days > 0:
        ref_now = now_epoch if now_epoch is not None else time.time()
        cutoff = ref_now - (max_days * 86400.0)
        sorted_list = [e for e in sorted_list if e.mtime_epoch >= cutoff]
    if latest_n is not None and latest_n > 0:
        sorted_list = sorted_list[:latest_n]
    return sorted_list


def format_entries_table(entries: List[RemoteLogEntry]) -> str:
    """Trả về bảng liệt kê có đánh số, dùng để hiển thị cho người dùng chọn."""
    if not entries:
        return "(không có mục nào)"

    lines = [f"{'STT':<4} {'Loại':<8} {'Thời gian':<20} {'Tên'}"]
    for idx, entry in enumerate(entries, start=1):
        kind = "Thư mục" if entry.entry_type == "dir" else "File"
        lines.append(f"{idx:<4} {kind:<8} {entry.mtime_str:<20} {entry.name}")
    return "\n".join(lines)


def parse_selection(raw_input: str, entries: List[RemoteLogEntry]) -> List[RemoteLogEntry]:
    """Phân giải chuỗi người dùng nhập ("all"/"a", "latest"/"l", "1", "1,3,4", "1-3, 5")
    thành danh sách entry đã chọn (không trùng lặp, giữ đúng thứ tự chọn).

    Chỉ số không hợp lệ sẽ bị bỏ qua, không raise để một lựa chọn sai
    không làm crash toàn bộ phiên chọn.
    """
    cleaned = raw_input.strip().lower()
    if not entries or not cleaned:
        return []
    if cleaned in ("all", "a", "*"):
        return list(entries)
    if cleaned in ("l", "latest"):
        return [entries[0]]

    selected: List[RemoteLogEntry] = []
    seen_indices = set()
    for token in cleaned.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            parts = token.split("-", 1)
            left, right = parts[0].strip(), parts[1].strip()
            if left.isdigit() and right.isdigit():
                start_idx, end_idx = int(left), int(right)
                if start_idx > end_idx:
                    start_idx, end_idx = end_idx, start_idx
                for idx in range(start_idx, end_idx + 1):
                    if 1 <= idx <= len(entries) and idx not in seen_indices:
                        seen_indices.add(idx)
                        selected.append(entries[idx - 1])
            continue
        if token.isdigit():
            index = int(token)
            if 1 <= index <= len(entries) and index not in seen_indices:
                seen_indices.add(index)
                selected.append(entries[index - 1])
    return selected

