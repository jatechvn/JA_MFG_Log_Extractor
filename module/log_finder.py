# -*- coding: utf-8 -*-
"""Business logic thuần: mô hình hoá kết quả tìm log, bảng 5 cột chống vỡ và xử lý lựa chọn của người dùng.

Không phụ thuộc paramiko/SSH -> dễ test độc lập.
"""
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Tuple


_START_TS_IN_NAME_RE = re.compile(r"(?:^|[_-])(20\d{6})[-_](\d{6})(?:\.[A-Za-z0-9]+)?$")


class _TableColor:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GRAY = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_CYAN = "\033[96m"
    WHITE = "\033[97m"


def extract_start_time_from_name(name: str) -> Optional[str]:
    """Trích xuất chuỗi thời gian bắt đầu 'YYYY-MM-DD HH:MM:SS' từ hậu tố tên gói log
    (ví dụ: '..._20261007-134726' -> '2026-10-07 13:47:26').
    """
    if not name:
        return None
    m = _START_TS_IN_NAME_RE.search(name.strip())
    if not m:
        return None
    d_part, t_part = m.group(1), m.group(2)
    try:
        dt = datetime.strptime(f"{d_part}{t_part}", "%Y%m%d%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def extract_start_epoch_from_name(name: str) -> Optional[float]:
    """Trích xuất epoch thời gian bắt đầu từ tên gói log nếu có."""
    if not name:
        return None
    m = _START_TS_IN_NAME_RE.search(name.strip())
    if not m:
        return None
    d_part, t_part = m.group(1), m.group(2)
    try:
        dt = datetime.strptime(f"{d_part}{t_part}", "%Y%m%d%H%M%S")
        return dt.timestamp()
    except (ValueError, OSError):
        return None


@dataclass(frozen=True)
class RemoteLogEntry:
    """Một thư mục (hoặc file rời) log trên máy đích khớp với SN cần tìm.

    - mtime_epoch: Thời điểm kết thúc ghi log / đẩy lên MES (lấy từ mtime mới nhất của
      file .log / ctp_log_metadata.yaml / mesdetails.log bên trong gói log).
    - start_time_epoch: Thời điểm bắt đầu ghi log (nếu có; tự động trích xuất từ tên
      gói log _YYYYMMDD-HHMMSS nếu không truyền).
    - test_result: Kết quả test ('PASS', 'FAIL', 'RUN', hoặc '-').
    """

    name: str
    remote_path: str
    mtime_epoch: float
    entry_type: str  # "dir" hoặc "file"
    test_result: str = "-"
    start_time_epoch: Optional[float] = None

    @property
    def mtime_str(self) -> str:
        """Chuỗi thời gian kết thúc ghi log (đẩy lên MES)."""
        return datetime.fromtimestamp(self.mtime_epoch).strftime("%Y-%m-%d %H:%M:%S")

    @property
    def end_time_str(self) -> str:
        """Chuỗi thời gian kết thúc ghi log (đẩy lên MES)."""
        return self.mtime_str

    @property
    def start_time_str(self) -> str:
        """Chuỗi thời gian bắt đầu ghi log (ưu tiên start_time_epoch -> hậu tố tên gói -> mtime_str)."""
        if self.start_time_epoch is not None and self.start_time_epoch > 0:
            return datetime.fromtimestamp(self.start_time_epoch).strftime("%Y-%m-%d %H:%M:%S")
        from_name = extract_start_time_from_name(self.name)
        if from_name:
            return from_name
        return self.mtime_str


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


def _display_width(text: str) -> int:
    """Ước lượng độ rộng hiển thị trên terminal của văn bản (không chứa mã màu ANSI)."""
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ("W", "F") else 1
    return width


def _pad_display(text: str, width: int) -> str:
    """Đệm khoảng trắng bên phải để đạt đúng độ rộng hiển thị `width`."""
    return text + " " * max(0, width - _display_width(text))


def _truncate_display(text: str, width: int, keep_tail: bool = False) -> str:
    """Cắt bớt văn bản nếu vượt độ rộng hiển thị `width`, chèn '...'."""
    if _display_width(text) <= width:
        return text
    budget = max(0, width - 3)
    if keep_tail:
        out = ""
        for ch in reversed(text):
            if _display_width(ch + out) > budget:
                break
            out = ch + out
        return "..." + out
    out = ""
    for ch in text:
        if _display_width(out + ch) > budget:
            break
        out += ch
    return out + "..."


def _build_border(widths: Sequence[int], left: str, mid: str, right: str) -> str:
    segments = ["─" * (w + 2) for w in widths]
    return f"{_TableColor.BRIGHT_CYAN}{left}" + mid.join(segments) + f"{right}{_TableColor.RESET}"


def _build_row(cells: Sequence[Tuple[str, int]], colors: Optional[Sequence[Optional[str]]] = None) -> str:
    colors = colors or [None] * len(cells)
    parts = []
    for (raw, width), color in zip(cells, colors):
        padded = _pad_display(raw, width)
        parts.append(f"{color}{padded}{_TableColor.RESET}" if color else padded)
    sep = f" {_TableColor.BRIGHT_CYAN}│{_TableColor.RESET} "
    return f"{_TableColor.BRIGHT_CYAN}│{_TableColor.RESET} " + sep.join(parts) + f" {_TableColor.BRIGHT_CYAN}│{_TableColor.RESET}"


def _wrap_display(text: str, width: int) -> List[str]:
    """Wrap narrow-terminal output by display cells, preserving all text."""
    lines = []
    current = ""
    for ch in text:
        if current and _display_width(current + ch) > width:
            lines.append(current)
            current = ""
        current += ch
    if current:
        lines.append(current)
    return lines


_ENTRIES_COLUMNS = [
    ("STT", 3),
    ("Kết quả", 7),
    ("Bắt đầu ghi log", 19),
    ("Kết thúc (Đẩy MES)", 19),
    ("Tên gói log (Thư mục / Tệp tin)", 72),
]


def format_entries_table_colored(entries: Sequence[RemoteLogEntry]) -> str:
    """Trả về bảng box-drawing 5 cột có tô màu PASS/FAIL và thời gian bắt đầu / đẩy MES.

    Bảng tự điều chỉnh theo độ rộng terminal:
    - Không dùng emoji/dingbat trong ô bảng để tránh lệch độ rộng 1/2 cột giữa CMD/PowerShell/WT.
    - Tự động co giãn cột Tên gói log theo tên dài nhất và kích thước cửa sổ terminal.
    """
    if not entries:
        return f"{_TableColor.BRIGHT_YELLOW}(Không tìm thấy mục nào khớp điều kiện){_TableColor.RESET}"

    min_name_col = _display_width(_ENTRIES_COLUMNS[4][0])
    max_entry_name = max((_display_width(e.name) for e in entries), default=min_name_col)
    name_col_width = max(min_name_col, min(max_entry_name, 80))

    fixed_columns = list(_ENTRIES_COLUMNS[:4])
    fixed_columns[0] = ("STT", max(3, len(str(len(entries)))))
    fixed_cols_width = sum(w for _, w in fixed_columns) + 16
    name_title = _ENTRIES_COLUMNS[4][0]
    if sys.stdout.isatty():
        term_cols = shutil.get_terminal_size((140, 30)).columns
        available_width = max(2, term_cols - 1)
        avail_for_name = available_width - fixed_cols_width
        if avail_for_name < min_name_col:
            name_title = "Tên gói log"
            min_name_col = _display_width(name_title)
        if avail_for_name < min_name_col:
            # Dates stay complete when even five compact columns cannot fit.
            lines = []
            for idx, entry in enumerate(entries, start=1):
                for text in (
                    f"{idx}. [{entry.test_result or '-'}] {entry.name}",
                    f"Bắt đầu: {entry.start_time_str}",
                    f"Kết thúc: {entry.end_time_str}",
                ):
                    lines.extend(_wrap_display(text, available_width))
                lines.append("")
            return "\n".join(lines).rstrip()
        name_col_width = min(name_col_width, avail_for_name)

    columns = fixed_columns + [(name_title, name_col_width)]
    widths = [w for _, w in columns]
    lines = [
        _build_border(widths, "┌", "┬", "┐"),
        _build_row([(title, w) for title, w in columns], colors=[_TableColor.BOLD] * len(columns)),
        _build_border(widths, "├", "┼", "┤"),
    ]

    for idx, entry in enumerate(entries, start=1):
        res_upper = (getattr(entry, "test_result", "-") or "-").strip().upper()
        if res_upper == "PASS":
            res_raw, res_color = " PASS", f"{_TableColor.BOLD}{_TableColor.BRIGHT_GREEN}"
        elif res_upper == "FAIL":
            res_raw, res_color = " FAIL", f"{_TableColor.BOLD}{_TableColor.BRIGHT_RED}"
        elif res_upper == "RUN":
            res_raw, res_color = " RUN", f"{_TableColor.BOLD}{_TableColor.BRIGHT_YELLOW}"
        else:
            res_raw, res_color = "  -", _TableColor.GRAY

        name_color = (
            f"{_TableColor.BOLD}{_TableColor.BRIGHT_CYAN}"
            if entry.entry_type == "dir"
            else f"{_TableColor.BOLD}{_TableColor.WHITE}"
        )
        name_raw = _truncate_display(entry.name, name_col_width, keep_tail=True)

        start_str = getattr(entry, "start_time_str", "-")
        end_str = getattr(entry, "end_time_str", entry.mtime_str)

        lines.append(
            _build_row(
                [
                    (str(idx), widths[0]),
                    (res_raw, widths[1]),
                    (start_str, widths[2]),
                    (end_str, widths[3]),
                    (name_raw, widths[4]),
                ],
                colors=[None, res_color, _TableColor.WHITE, _TableColor.BRIGHT_YELLOW, name_color],
            )
        )

    lines.append(_build_border(widths, "└", "┴", "┘"))
    return "\n".join(lines)


def format_entries_table(entries: List[RemoteLogEntry]) -> str:
    """Trả về bảng liệt kê có đánh số (văn bản thuần)."""
    if not entries:
        return "(không có mục nào)"

    lines = [
        f"{'STT':<4} {'Kết quả':<7} {'Bắt đầu ghi log':<20} {'Kết thúc (Đẩy MES)':<20} {'Loại':<7} {'Tên'}"
    ]
    for idx, entry in enumerate(entries, start=1):
        kind = "Thư mục" if entry.entry_type == "dir" else "File"
        res = entry.test_result or "-"
        lines.append(
            f"{idx:<4} {res:<7} {entry.start_time_str:<20} {entry.end_time_str:<20} {kind:<7} {entry.name}"
        )
    return "\n".join(lines)


def parse_selection(raw_input: str, entries: List[RemoteLogEntry]) -> List[RemoteLogEntry]:
    """Phân giải chuỗi người dùng nhập ("all"/"a", "latest"/"l", "pass"/"p", "fail"/"f",
    "1", "1,3,4", "1-3, 5") thành danh sách entry đã chọn (không trùng lặp, giữ đúng thứ tự chọn).
    """
    cleaned = raw_input.strip().lower()
    if not entries or not cleaned:
        return []
    if cleaned in ("all", "a", "*"):
        return list(entries)
    if cleaned in ("l", "latest"):
        return [entries[0]]
    if cleaned in ("p", "pass"):
        return [e for e in entries if e.test_result.upper() == "PASS"]
    if cleaned in ("f", "fail"):
        return [e for e in entries if e.test_result.upper() == "FAIL"]

    selected: List[RemoteLogEntry] = []
    seen_indices = set()
    for token in cleaned.split(","):
        token = token.strip()
        if not token:
            continue
        if token in ("p", "pass"):
            for idx, entry in enumerate(entries, start=1):
                if entry.test_result.upper() == "PASS" and idx not in seen_indices:
                    seen_indices.add(idx)
                    selected.append(entry)
            continue
        if token in ("f", "fail"):
            for idx, entry in enumerate(entries, start=1):
                if entry.test_result.upper() == "FAIL" and idx not in seen_indices:
                    seen_indices.add(idx)
                    selected.append(entry)
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
