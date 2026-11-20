"""Interactive menu, terminal rendering and Windows input helpers."""

import os
import re
import subprocess
import sys

from .console_style import Color
from .extract_p61070 import check_is_p61070
from .extract_s1h41 import check_is_s1h41
from .extract_s3t80 import check_is_s3t80
from .extraction_workflows import detect_sns_from_folder, process_single_extraction
from .log_io import from_long_path, get_default_reports_dir, get_script_dir, to_long_path
from .reporting import compare_with_golden_sample


def print_header(title, version):
    title_str = f"{title} - v{version}"
    print(f"\n{Color.BRIGHT_CYAN}┌─────────────────────────────────────────────────────────────────────┐{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}{Color.WHITE}{title_str.center(67)}{Color.RESET} {Color.BRIGHT_CYAN}│{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}└─────────────────────────────────────────────────────────────────────┘{Color.RESET}\n")


def print_batch_summary_table(results):
    """
    Print nicely formatted ANSI summary table of batch extraction results including Cycle Time.
    """
    title_text = "BẢNG TỔNG HỢP KẾT QUẢ TRÍCH XUẤT & CYCLE TIME".center(109)
    print(f"\n{Color.BRIGHT_CYAN}┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}│{Color.RESET}{Color.BOLD}{Color.WHITE}{title_text}{Color.RESET}{Color.BRIGHT_CYAN}│{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}├─────┬──────────────────┬────────────┬────────────┬─────────────┬────────────┬───────────────────────────────┤{Color.RESET}")
    print(
        f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}{'STT':<3}{Color.RESET} "
        f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}{'Target SN':<16}{Color.RESET} "
        f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}{'Dòng SP':<10}{Color.RESET} "
        f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}{'Controller':<10}{Color.RESET} "
        f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}{'Cycle Time':<11}{Color.RESET} "
        f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}{'Trạng thái':<10}{Color.RESET} "
        f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}{'Thư mục lưu':<29}{Color.RESET} {Color.BRIGHT_CYAN}│{Color.RESET}"
    )
    print(f"{Color.BRIGHT_CYAN}├─────┼──────────────────┼────────────┼────────────┼─────────────┼────────────┼───────────────────────────────┤{Color.RESET}")

    success_count = 0
    warn_count = 0
    fail_count = 0

    for idx, item in enumerate(results, 1):
        sn = str(item.get("sn", "UNKNOWN"))
        unit_type = str(item.get("unit_type", "-"))
        controller = str(item.get("controller", "-"))
        cycle_time = str(item.get("cycle_time", "N/A"))
        status = item.get("status", "FAIL")
        out_dir = str(item.get("out_dir", "-"))
        warnings = item.get("warnings", [])

        if len(out_dir) > 29:
            out_dir_disp = "..." + out_dir[-26:]
        else:
            out_dir_disp = out_dir.ljust(29)

        if status == "SUCCESS":
            success_count += 1
            if warnings:
                warn_count += 1
                status_disp = f"{Color.BRIGHT_YELLOW}{'WARN (OK)':<10}{Color.RESET}"
            else:
                status_disp = f"{Color.BRIGHT_GREEN}{'SUCCESS':<10}{Color.RESET}"
        else:
            fail_count += 1
            status_disp = f"{Color.BRIGHT_RED}{'FAIL':<10}{Color.RESET}"

        idx_disp = str(idx)[:3].ljust(3)
        sn_disp = sn[:16].ljust(16)
        unit_disp = unit_type[:10].ljust(10)
        ctrl_disp = controller[:10].ljust(10)
        ct_disp = cycle_time[:11].ljust(11)

        print(
            f"{Color.BRIGHT_CYAN}│{Color.RESET} {idx_disp} "
            f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}{Color.WHITE}{sn_disp}{Color.RESET} "
            f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.MAGENTA}{unit_disp}{Color.RESET} "
            f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.YELLOW}{ctrl_disp}{Color.RESET} "
            f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BRIGHT_CYAN}{ct_disp}{Color.RESET} "
            f"{Color.BRIGHT_CYAN}│{Color.RESET} {status_disp} "
            f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.GRAY}{out_dir_disp}{Color.RESET} {Color.BRIGHT_CYAN}│{Color.RESET}"
        )

    print(f"{Color.BRIGHT_CYAN}└─────┴──────────────────┴────────────┴────────────┴─────────────┴────────────┴───────────────────────────────┘{Color.RESET}")
    warn_str = f" │ {Color.BRIGHT_YELLOW}Cảnh báo: {warn_count}{Color.RESET}" if warn_count > 0 else ""
    print(f"\n{Color.BOLD}Thống kê:{Color.RESET} Tổng số: {len(results)} │ {Color.BRIGHT_GREEN}Thành công: {success_count}{Color.RESET}{warn_str} │ {Color.BRIGHT_RED}Thất bại: {fail_count}{Color.RESET}\n")


def open_native_path_dialog(mode="folder", title="Chọn đường dẫn"):
    """
    Open native Windows FolderBrowserDialog or OpenFileDialog via PowerShell .NET System.Windows.Forms.
    Compatible with Windows Embedded Python (no tkinter required).
    mode: 'folder', 'archive_or_csv', 'csv'
    """
    if sys.platform != "win32":
        return ""
    safe_title = title.replace("'", "''")
    if mode == "csv":
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.OpenFileDialog; "
            f"$f.Title = '{safe_title}'; "
            "$f.Filter = 'CSV/TXT Files (*.csv;*.txt)|*.csv;*.txt|All Files (*.*)|*.*'; "
            "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.FileName }"
        )
    elif mode == "file":
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.OpenFileDialog; "
            f"$f.Title = '{safe_title}'; "
            "$f.Filter = 'Log Archives (*.zip;*.tar.gz;*.tgz;*.tar.xz)|*.zip;*.gz;*.tgz;*.xz|All Files (*.*)|*.*'; "
            "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.FileName }"
        )
    else:
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$f.Description = '{safe_title}'; "
            "$f.ShowNewFolderButton = $true; "
            "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }"
        )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        selected = proc.stdout.strip()
        return selected
    except Exception:
        return ""


def get_clipboard_text():
    """
    Read plain Unicode text from the Windows Clipboard (fast ctypes Win32 API with PowerShell fallback).
    """
    if sys.platform == "win32":
        try:
            import ctypes
            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            user32.OpenClipboard.restype = ctypes.c_int
            user32.GetClipboardData.argtypes = [ctypes.c_uint]
            user32.GetClipboardData.restype = ctypes.c_void_p
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = ctypes.c_int
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalUnlock.restype = ctypes.c_int

            if user32.OpenClipboard(None):
                try:
                    handle = user32.GetClipboardData(CF_UNICODETEXT)
                    if handle:
                        ptr = kernel32.GlobalLock(handle)
                        if ptr:
                            try:
                                text = ctypes.wstring_at(ptr)
                                if text:
                                    return text.strip()
                            finally:
                                kernel32.GlobalUnlock(handle)
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass

        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=3,
            )
            return proc.stdout.strip()
        except Exception:
            pass
    return ""


def get_sn_from_clipboard(allow_multiple=True):
    """
    Extract valid Serial Number(s) from the system clipboard.
    Prioritizes standard MFG SN patterns (SAF..., SGF..., FVB..., PM...),
    with fallback to clean alphanumeric SN tokens.
    """
    raw_clip = get_clipboard_text()
    if not raw_clip:
        return ""

    # 1. Check for known MFG Serial Number patterns first
    pattern = r'(SAF[A-Z0-9]{8,}|SGF[A-Z0-9]{8,}|FVB[A-Z0-9]{6,}|PM[A-Z0-9]{10,})'
    matches = re.findall(pattern, raw_clip.upper())
    if matches:
        unique_sns = []
        for m in matches:
            if m not in unique_sns:
                unique_sns.append(m)
        return ", ".join(unique_sns) if allow_multiple else unique_sns[0]

    # 2. Fallback: accept clean alphanumeric token(s) if clipboard doesn't look like a file path or long text
    cleaned = raw_clip.strip(' "\' \t\r\n')
    if not cleaned or len(cleaned) > 120 or any(ch in cleaned for ch in ("\\", "/", ":")):
        return ""
    tokens = [t.strip() for t in re.split(r'[,;\s]+', cleaned) if t.strip()]
    if tokens and all(re.match(r'^[A-Za-z0-9_-]{4,32}$', t) for t in tokens):
        unique_tokens = []
        for t in tokens:
            t_up = t.upper()
            if t_up not in unique_tokens:
                unique_tokens.append(t_up)
        return ", ".join(unique_tokens) if allow_multiple else unique_tokens[0]

    return ""


def safe_input(prompt_text="", default=""):
    """
    Safely reads input from stdin, returning default on EOFError or exception.
    Prevents crashing when running in non-interactive/automated/remote pipes.
    """
    try:
        val = input(prompt_text)
        return val.strip(' "\' \t\r\n')
    except (EOFError, Exception):
        print()
        return default


def prompt_path_with_browse(prompt_text, dialog_mode="folder", dialog_title="Chọn thư mục log", allow_file_shortcut=True):
    """
    Prompts user for a path. If user enters 'B' (Folder Browse) or 'F' (File/Archive Browse),
    opens the native Windows GUI dialog and returns the selected path.
    """
    val = safe_input(prompt_text)
    if val.upper() == "B":
        print(f"   {Color.GRAY}📂 Đang mở hộp thoại chọn thư mục Windows...{Color.RESET}")
        chosen = open_native_path_dialog(mode=dialog_mode, title=dialog_title)
        if chosen:
            print(f"   {Color.GREEN}➜ Đã chọn: {chosen}{Color.RESET}")
        return chosen
    if allow_file_shortcut and val.upper() == "F":
        print(f"   {Color.GRAY}🗜  Đang mở hộp thoại chọn file nén (.zip / .tar.gz)...{Color.RESET}")
        chosen = open_native_path_dialog(mode="file", title="Chọn file nén log (.zip / .tar.gz)")
        if chosen:
            print(f"   {Color.GREEN}➜ Đã chọn: {chosen}{Color.RESET}")
        return chosen
    return val


def get_single_key_choice(prompt_text, valid_keys, default_key="1"):
    """
    Displays prompt_text and gets a single key choice instantly on Windows without waiting for Enter.
    If Enter (\r or \n) is pressed, returns default_key.
    Gracefully handles non-TTY, pipes, and remote sessions (SSH, WinRM).
    """
    print(prompt_text, end="", flush=True)
    if sys.platform == 'win32' and sys.stdin.isatty():
        try:
            import msvcrt
            while True:
                ch = msvcrt.getwch()
                if ch in ('\r', '\n'):
                    print(f"{default_key}")
                    return default_key
                elif ch in valid_keys or ch.upper() in valid_keys:
                    matched = ch if ch in valid_keys else ch.upper()
                    print(f"{matched}")
                    return matched
                elif ch == '\x03': # Ctrl+C
                    print()
                    raise KeyboardInterrupt
        except KeyboardInterrupt:
            raise
        except Exception:
            pass

    # Fallback to stdin for non-win32, non-tty pipes, or remote sessions
    try:
        if not sys.stdin.isatty():
            line = sys.stdin.readline()
            if not line:
                print(f"{default_key} (auto)")
                return default_key
            inp = line.strip(' "\' \t\r\n')
            if inp in valid_keys:
                return inp
            if inp.upper() in valid_keys:
                return inp.upper()
            return default_key
        inp = input().strip(' "\' \t\r\n')
        if inp in valid_keys:
            return inp
        if inp.upper() in valid_keys:
            return inp.upper()
        return default_key
    except (EOFError, Exception):
        print(f"{default_key}")
        return default_key


def prompt_post_extraction_actions(last_out_dir=None):
    """
    Interactive post-action bar:
      [O] Open output folder in Windows Explorer
      [C] Copy output path to Clipboard
      [R] Return to main menu
      [Q/Enter] Exit
    Returns True if user wants to return to main menu, False otherwise.
    """
    if last_out_dir == "__RETURN_MENU__":
        return True
    if last_out_dir == "__QUIT__":
        return False
    if not sys.stdin.isatty():
        return False

    from module.smart_actions import open_output_target, set_clipboard_text

    print(f"{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")
    if last_out_dir and last_out_dir != "-" and os.path.exists(to_long_path(last_out_dir)):
        while True:
            prompt_str = (
                f"   {Color.CYAN}[O]{Color.RESET} 📂 Mở thư mục kết quả  │  "
                f"{Color.CYAN}[C]{Color.RESET} 📋 Copy đường dẫn  │  "
                f"{Color.CYAN}[R]{Color.RESET} 🏠 Về Menu chính  │  "
                f"{Color.CYAN}[Enter/Q]{Color.RESET} Thoát: "
            )
            choice = get_single_key_choice(prompt_str, ["O", "C", "R", "Q"], default_key="Q")
            if choice == "O":
                if open_output_target(last_out_dir, select_file=False):
                    print(f"   {Color.GREEN}📂 Đã mở Windows Explorer: {from_long_path(last_out_dir)}{Color.RESET}")
                else:
                    print(f"   {Color.YELLOW}⚠ Không thể mở Explorer cho: {from_long_path(last_out_dir)}{Color.RESET}")
                continue
            if choice == "C":
                clean_p = from_long_path(last_out_dir)
                if set_clipboard_text(clean_p):
                    print(f"   {Color.GREEN}📋 Đã copy đường dẫn vào Clipboard: {clean_p}{Color.RESET}")
                else:
                    print(f"   {Color.YELLOW}⚠ Không thể ghi Clipboard.{Color.RESET}")
                continue
            return choice == "R"
    else:
        prompt_str = f"   {Color.CYAN}[R]{Color.RESET} 🏠 Về Menu chính  │  {Color.CYAN}[Enter/Q]{Color.RESET} Thoát: "
        choice = get_single_key_choice(prompt_str, ["R", "Q"], default_key="Q")
        return choice == "R"


def _format_station_cell(oct4, style, is_selected=False):
    """
    Format a single 8-character station cell (e.g. '[ .188 ]' or highlighted '[>.174<]').
    Uses pure ASCII width (8 visible chars) so all 3 Line boxes align 100% across fonts.
    """
    style_colors = {
        "pink": "\033[95m",     # Bright Magenta / Pink
        "green": "\033[92m",    # Bright Green / Teal
        "blue": "\033[96m",     # Bright Cyan / Blue
        "amber": "\033[93m",    # Bright Yellow / Amber
        "dim": "\033[90m",      # Dark Gray (inactive)
    }
    fg = style_colors.get(style, Color.WHITE)
    if is_selected:
        return f"\033[7m\033[1m{Color.BRIGHT_CYAN}[>.{oct4:03d}<]{Color.RESET}"
    return f"{fg}[ .{oct4:03d} ]{Color.RESET}"


def render_station_ip_map_lines(highlight_octet=None):
    """
    Build the 14-line visual 3-Column Station IP Diagram (Line 3 | Line 2 | Line 1)
    matching the factory layout (172.19.116.121 .. 172.19.116.199).
    """
    from module.ip_utils import STATION_LINES

    top_border = (
        f"   {Color.GRAY}╭─────────────────────╮  ╭─────────────────────╮  ╭─────────────────────╮{Color.RESET}"
    )
    hdr_parts = []
    for line_info in STATION_LINES:
        name = line_info["name"]
        summary = line_info["active_Summary"]
        hdr_parts.append(
            f"{Color.GRAY}│{Color.RESET}  {Color.BOLD}{Color.BRIGHT_CYAN}{name:<6}{Color.RESET}       "
            f"{Color.BRIGHT_GREEN}{summary:>5}{Color.RESET} {Color.GRAY}│{Color.RESET}"
        )
    header_line = "   " + "  ".join(hdr_parts)
    mid_border = (
        f"   {Color.GRAY}├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤{Color.RESET}"
    )

    lines = [top_border, header_line, mid_border]
    num_rows = len(STATION_LINES[0]["rows"])
    for r_idx in range(num_rows):
        row_cells = []
        for l_idx in range(len(STATION_LINES)):
            (oct_left, style_left), (oct_right, style_right) = STATION_LINES[l_idx]["rows"][r_idx]
            c_left = _format_station_cell(oct_left, style_left, is_selected=(highlight_octet == oct_left))
            c_right = _format_station_cell(oct_right, style_right, is_selected=(highlight_octet == oct_right))
            row_cells.append(f"{Color.GRAY}│{Color.RESET}  {c_left} {c_right}  {Color.GRAY}│{Color.RESET}")
        lines.append("   " + "  ".join(row_cells))

    bot_border = (
        f"   {Color.GRAY}╰─────────────────────╯  ╰─────────────────────╯  ╰─────────────────────╯{Color.RESET}"
    )
    lines.append(bot_border)
    return lines


def prompt_ip_with_station_map(ip_prefix="172.19", bridge_host="172.21.168.241"):
    """
    Interactive IP selector combining:
      1. Visual 3-Column Station IP Diagram (Line 3 | Line 2 | Line 1) with arrow-key (↑↓←→) navigation + Enter.
      2. Automatic Clipboard IP detection (auto-positions cursor on the map or pre-fills manual IP) + Recent IP history.
      3. Instant manual typing (type '.174', '174', '116.174', '172.19.116.174', etc. at any time + Enter).
      4. Graceful fallback for non-TTY / piped stdin.
    """
    from module import config as m_config
    from module.ip_utils import STATION_LINES, DEFAULT_STATION_OCTET3, expand_ip, get_station_line_info
    from module.smart_actions import RecentHistoryManager, detect_clipboard_ip

    # Build 10x6 grid of octets across Line 3 (cols 0-1), Line 2 (cols 2-3), Line 1 (cols 4-5)
    grid_rows = len(STATION_LINES[0]["rows"])
    grid_cols = len(STATION_LINES) * 2
    grid_octets = []
    for r in range(grid_rows):
        row_list = []
        for l_idx in range(len(STATION_LINES)):
            row_list.append(STATION_LINES[l_idx]["rows"][r][0][0])
            row_list.append(STATION_LINES[l_idx]["rows"][r][1][0])
        grid_octets.append(row_list)

    recent_ips = []
    try:
        max_hist = int(m_config.LOCAL_SETTINGS.get("ui", {}).get("max_recent_history", 5))
        recent_ips = RecentHistoryManager(m_config.HISTORY_FILE, max_items=max_hist).get_recent_ips()
    except Exception:
        recent_ips = []

    clip_ip = None
    if m_config.LOCAL_SETTINGS.get("ui", {}).get("enable_clipboard_hint", True):
        clip_ip = detect_clipboard_ip(get_clipboard_text(), default_prefix=ip_prefix)

    print(
        f"{Color.BRIGHT_YELLOW}📌 [1/3] Chọn IP trên Sơ đồ ({Color.WHITE}↑↓←→{Color.BRIGHT_YELLOW} + {Color.WHITE}Enter{Color.BRIGHT_YELLOW}) "
        f"hoặc Nhập thủ công ({Color.WHITE}.174{Color.BRIGHT_YELLOW}, {Color.WHITE}174{Color.BRIGHT_YELLOW}, {Color.WHITE}116.174{Color.BRIGHT_YELLOW}, {Color.WHITE}{ip_prefix}.116.174{Color.BRIGHT_YELLOW}):{Color.RESET}"
    )
    if recent_ips:
        print(f"   {Color.GRAY}🕒 IP gần đây: {', '.join(recent_ips)}{Color.RESET}")
    if clip_ip:
        st_clip = get_station_line_info(clip_ip, ip_prefix=ip_prefix)
        clip_badge = f" ({st_clip['line']} • .{st_clip['octet']})" if st_clip else ""
        print(f"   {Color.BRIGHT_GREEN}📋 Phát hiện IP trong Clipboard: {Color.BOLD}{Color.WHITE}{clip_ip}{Color.RESET}{Color.BRIGHT_GREEN}{clip_badge} (Nhấn Enter để chọn ngay){Color.RESET}")

    if not (sys.platform == "win32" and sys.stdin.isatty()):
        for l_str in render_station_ip_map_lines(highlight_octet=None):
            print(l_str)
        raw_val = safe_input(f"   {Color.CYAN}👉 Nhập IP máy test: {Color.RESET}")
        return raw_val if raw_val else (clip_ip or "")

    import msvcrt

    # Default highlight position: Clipboard station -> most recent station -> .174 (Line 3, row 5, col 0)
    cur_r, cur_c = 5, 0
    manual_buf = ""
    if clip_ip:
        st_clip = get_station_line_info(clip_ip, ip_prefix=ip_prefix)
        if st_clip:
            cur_r, cur_c = st_clip["row_idx"], st_clip["grid_col"]
        else:
            manual_buf = clip_ip
    elif recent_ips:
        st_rec = get_station_line_info(recent_ips[0], ip_prefix=ip_prefix)
        if st_rec:
            cur_r, cur_c = st_rec["row_idx"], st_rec["grid_col"]

    def _resolve_highlighted_octet():
        if manual_buf.strip():
            info = get_station_line_info(manual_buf.strip(), ip_prefix=ip_prefix)
            if info:
                return info["octet"]
            return None
        return grid_octets[cur_r][cur_c]

    def _build_frame():
        hl_oct = _resolve_highlighted_octet()
        frame = render_station_ip_map_lines(highlight_octet=hl_oct)
        if manual_buf:
            preview_str = ""
            try:
                resolved = expand_ip(manual_buf, ip_prefix=ip_prefix)
                st_info = get_station_line_info(resolved, ip_prefix=ip_prefix)
                line_badge = f" ({st_info['line']})" if st_info else " (IP thủ công)"
                preview_str = f" {Color.GRAY}➜ {Color.BRIGHT_GREEN}{resolved}{line_badge}{Color.RESET}"
            except Exception:
                preview_str = f" {Color.GRAY}(đang nhập...){Color.RESET}"
            frame.append(
                f"   {Color.GRAY}[Esc: Chọn lại trên sơ đồ │ Enter: Xác nhận]{Color.RESET}"
            )
            frame.append(
                f"   {Color.CYAN}👉 Nhập IP thủ công:{Color.RESET} {Color.BOLD}{Color.WHITE}{manual_buf}{Color.RESET}{preview_str}"
            )
        else:
            sel_oct = grid_octets[cur_r][cur_c]
            sel_ip = f"{ip_prefix}.{DEFAULT_STATION_OCTET3}.{sel_oct}"
            st_info = get_station_line_info(sel_ip, ip_prefix=ip_prefix)
            line_name = st_info["line"] if st_info else "Line"
            state_note = "" if (not st_info or st_info["active"]) else f" {Color.YELLOW}(ô xám trên sơ đồ){Color.RESET}"
            frame.append(
                f"   {Color.GRAY}[Mũi tên ↑↓←→: Di chuyển trên sơ đồ │ Gõ số/chữ: Nhập IP thủ công │ Enter: Chọn]{Color.RESET}"
            )
            frame.append(
                f"   {Color.CYAN}👉 Đang chọn:{Color.RESET} {Color.BOLD}{Color.BRIGHT_GREEN}.{sel_oct}{Color.RESET} "
                f"{Color.WHITE}({sel_ip} — {Color.BRIGHT_CYAN}{line_name}{Color.WHITE}){Color.RESET}{state_note}"
            )
        return frame

    initial_frame = _build_frame()
    total_frame_lines = len(initial_frame)
    for line in initial_frame:
        print(line)

    def _redraw():
        new_frame = _build_frame()
        sys.stdout.write(f"\033[{total_frame_lines}A")
        for line in new_frame:
            sys.stdout.write(f"\r\033[2K{line}\n")
        sys.stdout.flush()

    while True:
        ch = msvcrt.getwch()
        if ch == "\x03":  # Ctrl+C
            print()
            raise KeyboardInterrupt
        if ch in ("\x00", "\xe0"):
            ext = msvcrt.getwch()
            if ext == "H":  # Up
                cur_r = (cur_r - 1) % grid_rows
                manual_buf = ""
                _redraw()
            elif ext == "P":  # Down
                cur_r = (cur_r + 1) % grid_rows
                manual_buf = ""
                _redraw()
            elif ext == "K":  # Left
                cur_c = (cur_c - 1) % grid_cols
                manual_buf = ""
                _redraw()
            elif ext == "M":  # Right
                cur_c = (cur_c + 1) % grid_cols
                manual_buf = ""
                _redraw()
            continue

        if ch in ("\r", "\n"):
            if manual_buf.strip():
                return manual_buf.strip()
            sel_oct = grid_octets[cur_r][cur_c]
            return f".{sel_oct}"

        if ch == "\x1b":  # Esc clears manual buffer back to map selector
            if manual_buf:
                manual_buf = ""
                _redraw()
            continue

        if ch == "\x08":  # Backspace
            if manual_buf:
                manual_buf = manual_buf[:-1]
                info = get_station_line_info(manual_buf, ip_prefix=ip_prefix) if manual_buf else None
                if info:
                    cur_r, cur_c = info["row_idx"], info["grid_col"]
                _redraw()
            continue

        if ch.isprintable():
            manual_buf += ch
            info = get_station_line_info(manual_buf, ip_prefix=ip_prefix)
            if info:
                cur_r, cur_c = info["row_idx"], info["grid_col"]
            _redraw()


def run_remote_interactive_mode(*, extract_remote):
    """
    Interactive Mode [1]: Connect to remote test station via IP + SN (Indirect Bridge 172.21.168.241 -> 172.19.*.*)
    and extract reports directly into <App_Dir>/reports/<Target_SN>/.
    Supports continuous same-host loop (reusing active SSH session), switching IP, opening Explorer [O], and copying path [C].
    """
    from module import config as m_config
    from module.bridge import build_bridge_settings
    from module.ip_utils import expand_ip, get_station_line_info
    from module.remote_fetcher import SshLogService
    from module.smart_actions import (
        RecentHistoryManager,
        open_output_target,
        resolve_best_report_target,
        set_clipboard_text,
    )

    print(f"\n{Color.BRIGHT_YELLOW}📌 [Remote IP + SN Mode] Trích xuất trực tiếp từ Trạm Test (Bridge {m_config.LOCAL_SETTINGS['bridge']['host']} ➜ {m_config.DEFAULT_IP_PREFIX}.*.*):{Color.RESET}\n")

    active_service = None
    active_host = None
    output_dir_raw = None

    try:
        while True:
            # Step 1: Select or reuse IP
            if not active_host:
                while True:
                    raw_ip = prompt_ip_with_station_map(
                        ip_prefix=m_config.DEFAULT_IP_PREFIX,
                        bridge_host=m_config.LOCAL_SETTINGS["bridge"]["host"],
                    )
                    if not raw_ip:
                        if not sys.stdin.isatty():
                            return None
                        print(f"   {Color.RED}✖ IP không được để trống. Vui lòng nhập lại!{Color.RESET}\n")
                        continue
                    try:
                        full_ip = expand_ip(raw_ip, ip_prefix=m_config.DEFAULT_IP_PREFIX)
                        st_info = get_station_line_info(full_ip, ip_prefix=m_config.DEFAULT_IP_PREFIX)
                        line_tag = f" ({st_info['line']} • .{st_info['octet']})" if st_info else " (IP thủ công)"
                        print(f"   {Color.GREEN}➜ Đã chốt IP máy đích: {Color.BOLD}{Color.WHITE}{full_ip}{Color.RESET}{Color.BRIGHT_CYAN}{line_tag}{Color.RESET}")
                        active_host = full_ip
                        break
                    except Exception as exc:
                        if not sys.stdin.isatty():
                            print(f"   {Color.RED}✖ {exc}{Color.RESET}")
                            return None
                        print(f"   {Color.RED}✖ {exc}. Vui lòng nhập lại!{Color.RESET}\n")
            else:
                st_info = get_station_line_info(active_host, ip_prefix=m_config.DEFAULT_IP_PREFIX)
                line_tag = f" ({st_info['line']} • .{st_info['octet']})" if st_info else ""
                print(f"\n{Color.BRIGHT_GREEN}🔗 Đang giữ kết nối máy test: {Color.BOLD}{Color.WHITE}{active_host}{Color.RESET}{Color.BRIGHT_CYAN}{line_tag}{Color.RESET}")

            # Step 2: Prompt SN (with Clipboard & Recent SN hints)
            recent_sns = []
            try:
                max_hist = int(m_config.LOCAL_SETTINGS.get("ui", {}).get("max_recent_history", 5))
                recent_sns = RecentHistoryManager(m_config.HISTORY_FILE, max_items=max_hist).get_recent_sns()
            except Exception:
                recent_sns = []

            while True:
                clip_preview = get_sn_from_clipboard(allow_multiple=True)
                clip_hint = (
                    f"Nhấn Enter để lấy từ Clipboard: {Color.BOLD}{Color.WHITE}{clip_preview}{Color.RESET}{Color.GRAY}"
                    if clip_preview
                    else "Nhấn Enter để tự động lấy SN từ Clipboard"
                )
                recent_sn_line = f"   {Color.GRAY}🕒 SN gần đây: {', '.join(recent_sns)}{Color.RESET}\n" if recent_sns else ""
                sn_prompt = (
                    f"\n{Color.BRIGHT_YELLOW}📌 [2/3] Nhập Serial Number cần tìm (hỗ trợ nhiều SN cách nhau dấu phẩy, VD: SN1, SN2):{Color.RESET}\n"
                    f"{recent_sn_line}"
                    f"   {Color.GRAY}({clip_hint}){Color.RESET}\n"
                    f"   {Color.CYAN}👉 {Color.RESET}"
                )
                raw_sn = safe_input(sn_prompt)
                if not raw_sn:
                    raw_sn = get_sn_from_clipboard(allow_multiple=True)
                    if raw_sn:
                        print(f"   {Color.GREEN}📋 Đã tự động lấy SN từ Clipboard: {Color.BOLD}{Color.WHITE}{raw_sn}{Color.RESET}")
                if raw_sn:
                    break
                if not sys.stdin.isatty():
                    return None
                print(f"   {Color.RED}✖ Serial Number trống (Clipboard cũng không có SN hợp lệ). Vui lòng nhập hoặc copy SN!{Color.RESET}")

            # Step 3: Output directory (ask once per session)
            default_reports = get_default_reports_dir()
            if not output_dir_raw:
                out_prompt = (
                    f"\n{Color.BRIGHT_YELLOW}📌 [3/3] Nhập thư mục lưu báo cáo (Mặc định: {default_reports}):{Color.RESET}\n"
                    f"   {Color.CYAN}👉 Nhấn Enter dùng mặc định, gõ [B] chọn thư mục, hoặc dán đường dẫn khác: {Color.RESET}"
                )
                output_dir_raw = prompt_path_with_browse(
                    out_prompt,
                    dialog_mode="folder",
                    dialog_title="Chọn thư mục lưu báo cáo đầu ra",
                    allow_file_shortcut=False,
                )
                if not output_dir_raw:
                    output_dir_raw = default_reports
                    print(f"   {Color.GREEN}➜ Đã chọn mặc định: {default_reports}{Color.RESET}")

            # Ensure active_service is connected for active_host
            if active_service is None or active_service.host != active_host:
                if active_service is not None:
                    active_service.disconnect()
                bridge_settings = build_bridge_settings()
                active_service = SshLogService(
                    host=active_host,
                    port=m_config.DEFAULT_SSH_PORT,
                    timeout=m_config.SSH_CONNECT_TIMEOUT_SEC,
                    bridge_settings=bridge_settings,
                    show_progress=not (not sys.stdout.isatty()),
                )

            results = []
            try:
                results = extract_remote(
                    raw_ip=active_host,
                    raw_sn=raw_sn,
                    output_base_raw=output_dir_raw,
                    interactive=True,
                    export_csv=True,
                    ssh_service=active_service,
                )
            except Exception as exc:
                print(f"\n{Color.RED}✖ Lỗi khi trích xuất từ xa: {exc}{Color.RESET}\n")
                if active_service is not None:
                    active_service.disconnect()
                    active_service = None

            best_target, select_file = resolve_best_report_target(results, output_dir_raw or default_reports)
            target_str = from_long_path(str(best_target)) if best_target else from_long_path(output_dir_raw or default_reports)

            if not sys.stdin.isatty():
                return target_str

            if m_config.LOCAL_SETTINGS.get("ui", {}).get("auto_open_single", False) and best_target:
                open_output_target(best_target, select_file=select_file)

            # Interactive loop menu after remote extraction
            while True:
                print(f"\n{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")
                print(f"   {Color.BRIGHT_YELLOW}⚡ Thao tác nhanh (Báo cáo: {Color.WHITE}{target_str}{Color.BRIGHT_YELLOW}):{Color.RESET}")
                print(f"   {Color.CYAN}[O]{Color.RESET} 📂 Mở ngay thư mục báo cáo vừa trích xuất  │  {Color.CYAN}[C]{Color.RESET} 📋 Copy đường dẫn vào Clipboard")
                print(f"   {Color.CYAN}[1]{Color.RESET} 🔎 Tìm & trích xuất tiếp SN khác trên cùng máy ({Color.BRIGHT_GREEN}{active_host}{Color.RESET})")
                print(f"   {Color.CYAN}[2]{Color.RESET} 🌐 Đổi sang IP máy test khác               │  {Color.CYAN}[R]{Color.RESET} 🏠 Về Menu chính  │  {Color.CYAN}[Enter/Q]{Color.RESET} 🚪 Thoát")
                act_prompt = f"   {Color.CYAN}👉 Chọn nhanh [O/C/1/2/R/Q] (Enter = Thoát): {Color.RESET}"
                act = get_single_key_choice(act_prompt, ["O", "C", "1", "2", "R", "Q"], default_key="Q")

                if act == "O":
                    if open_output_target(target_str, select_file=False):
                        print(f"   {Color.GREEN}📂 Đã mở Windows Explorer: {target_str}{Color.RESET}")
                    else:
                        print(f"   {Color.YELLOW}⚠ Không thể mở Explorer cho: {target_str}{Color.RESET}")
                    continue
                if act == "C":
                    if set_clipboard_text(target_str):
                        print(f"   {Color.GREEN}📋 Đã copy đường dẫn vào Clipboard: {target_str}{Color.RESET}")
                    else:
                        print(f"   {Color.YELLOW}⚠ Không thể ghi Clipboard.{Color.RESET}")
                    continue
                if act == "1":
                    # Continue outer loop with same active_host and active_service
                    break
                if act == "2":
                    if active_service is not None:
                        active_service.disconnect()
                        active_service = None
                    active_host = None
                    break
                if act == "R":
                    return "__RETURN_MENU__"
                return "__QUIT__"
    finally:
        if active_service is not None:
            active_service.disconnect()


def run_interactive_menu_once(
    *, show_header, run_remote, run_batch_extraction, generate_sample_csv,
    parse_csv_file, scan_parent_folder_for_logs, run_cycle_time_analysis,
):
    """
    Runs one cycle of the interactive CLI menu. Returns last output directory for post-action handling.
    """
    from module.smart_actions import open_output_target

    show_header()
    print(f"{Color.BRIGHT_YELLOW}Vui lòng chọn chế độ làm việc:{Color.RESET}")
    print(f"   {Color.CYAN}[1]{Color.RESET} 🌐 Trích xuất trực tiếp từ Trạm Test qua IP + SN (Indirect Bridge 172.21.168.241 ➜ 172.19.*.*)")
    print(f"   {Color.CYAN}[2]{Color.RESET} 📂 Trích xuất 1 thư mục / file nén log trên máy (Single Folder / Archive Mode)")
    print(f"   {Color.CYAN}[3]{Color.RESET} 🚀 Quét và trích xuất hàng loạt từ thư mục gốc (Batch Subfolders & Archives)")
    print(f"   {Color.CYAN}[4]{Color.RESET} 📋 Đọc danh sách trích xuất từ file CSV / TXT (Hỗ trợ cả IP Trạm Test & Đường dẫn Local)")
    print(f"   {Color.CYAN}[5]{Color.RESET} 📝 Tạo file CSV mẫu (mau_danh_sach_log.csv)")
    print(f"   {Color.CYAN}[6]{Color.RESET} ⏱  Phân tích nhanh Cycle Time & Chẩn đoán lỗi (Cycle Time & Failure Analyzer)")
    print(f"   {Color.CYAN}[7]{Color.RESET} 🔍 Đối chiếu kết quả với thư mục Golden Sample (Golden Sample Diff Verifier)")
    print(f"   {Color.CYAN}[O]{Color.RESET} 📂 Mở nhanh thư mục báo cáo ({from_long_path(get_default_reports_dir())})\n")

    prompt_str = f"   {Color.CYAN}👉 Chọn nhanh số (1-7, O) hoặc nhấn Enter để chọn [1]: {Color.RESET}"
    mode_choice = get_single_key_choice(prompt_str, ["1", "2", "3", "4", "5", "6", "7", "O"], default_key="1")

    if mode_choice == "O":
        rep_dir = get_default_reports_dir()
        os.makedirs(to_long_path(rep_dir), exist_ok=True)
        if open_output_target(rep_dir, select_file=False):
            print(f"\n   {Color.GREEN}📂 Đã mở thư mục báo cáo: {from_long_path(rep_dir)}{Color.RESET}")
        return "__RETURN_MENU__"

    if mode_choice == "1":
        return run_remote()

    elif mode_choice == "5":
        generate_sample_csv("mau_danh_sach_log.csv")
        return get_script_dir()

    elif mode_choice == "4":
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Batch CSV Mode] Đọc danh sách từ file CSV/TXT (Hỗ trợ IP & Local Path):{Color.RESET}")
        csv_file_path = prompt_path_with_browse(
            f"   {Color.CYAN}👉 Nhập đường dẫn file CSV/TXT, gõ [B] mở hộp thoại chọn file, hoặc Enter dùng mặc định (mau_danh_sach_log.csv): {Color.RESET}",
            dialog_mode="csv",
            dialog_title="Chọn file danh sách CSV / TXT",
            allow_file_shortcut=False,
        )
        if not csv_file_path:
            script_dir = get_script_dir()
            csv_file_path = os.path.join(script_dir, "mau_danh_sach_log.csv")
            if not os.path.exists(csv_file_path):
                generate_sample_csv(csv_file_path)
        elif not os.path.isabs(csv_file_path):
            script_dir = get_script_dir()
            possible_path = os.path.join(script_dir, csv_file_path)
            if os.path.exists(possible_path):
                csv_file_path = possible_path

        batch_items = parse_csv_file(csv_file_path)
        results = run_batch_extraction(batch_items)
        first_out = next((r.get("out_dir") for r in results if r.get("out_dir") and r.get("out_dir") != "-"), get_default_reports_dir())
        return first_out

    elif mode_choice == "3":
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Batch Subfolders Scan] Quét hàng loạt từ thư mục gốc:{Color.RESET}")
        parent_dir = prompt_path_with_browse(
            f"   {Color.CYAN}👉 Nhập đường dẫn thư mục gốc (hoặc gõ [B] để mở hộp thoại chọn thư mục): {Color.RESET}",
            dialog_mode="folder",
            dialog_title="Chọn thư mục gốc chứa các thư mục/file nén log",
            allow_file_shortcut=False,
        )
        while not parent_dir or not os.path.exists(to_long_path(parent_dir)):
            if not sys.stdin.isatty():
                print(f"   {Color.RED}✖ Thư mục không tồn tại hoặc không hợp lệ: '{parent_dir}'{Color.RESET}")
                return None
            print(f"   {Color.RED}✖ Thư mục không tồn tại. Vui lòng nhập lại!{Color.RESET}")
            parent_dir = prompt_path_with_browse(
                f"   {Color.CYAN}👉 Nhập đường dẫn thư mục gốc (hoặc gõ [B] để chọn): {Color.RESET}",
                dialog_mode="folder",
                dialog_title="Chọn thư mục gốc chứa các thư mục/file nén log",
                allow_file_shortcut=False,
            )

        batch_items = scan_parent_folder_for_logs(parent_dir)
        if not batch_items:
            print(f"\n{Color.RED}✖ Không tìm thấy thư mục hoặc file nén log hợp lệ nào trong {parent_dir}{Color.RESET}\n")
            return None
        results = run_batch_extraction(batch_items)
        return get_default_reports_dir() if results else None

    elif mode_choice == "6":
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Cycle Time & Failure Analyzer] Phân tích thời gian test & chẩn đoán lỗi:{Color.RESET}")
        target_path = prompt_path_with_browse(
            f"   {Color.CYAN}👉 Nhập đường dẫn thư mục / file nén log (hoặc gõ [B] chọn thư mục, [F] chọn file .zip): {Color.RESET}",
            dialog_mode="folder",
            dialog_title="Chọn thư mục log cần phân tích Cycle Time",
            allow_file_shortcut=True,
        )
        while not target_path or not os.path.exists(to_long_path(target_path)):
            if not sys.stdin.isatty():
                print(f"   {Color.RED}✖ Đường dẫn không tồn tại: '{target_path}'{Color.RESET}")
                return None
            print(f"   {Color.RED}✖ Đường dẫn không tồn tại. Vui lòng nhập lại!{Color.RESET}")
            target_path = prompt_path_with_browse(
                f"   {Color.CYAN}👉 Nhập đường dẫn (hoặc [B] chọn thư mục, [F] chọn file .zip): {Color.RESET}",
                dialog_mode="folder",
                dialog_title="Chọn thư mục log cần phân tích Cycle Time",
                allow_file_shortcut=True,
            )

        items = scan_parent_folder_for_logs(target_path)
        if not items:
            items = [(target_path, "", get_default_reports_dir())]
        run_cycle_time_analysis(items, diagnose=True)
        return get_default_reports_dir()

    elif mode_choice == "7":
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Golden Sample Diff Verifier] Đối chiếu 100% Byte-for-Byte với thư mục mẫu:{Color.RESET}")
        ext_dir = prompt_path_with_browse(
            f"   {Color.CYAN}👉 [1/2] Nhập thư mục báo cáo vừa trích xuất (hoặc gõ [B] để chọn): {Color.RESET}",
            dialog_mode="folder",
            dialog_title="Chọn thư mục báo cáo đã trích xuất",
            allow_file_shortcut=False,
        )
        if not ext_dir or not os.path.exists(to_long_path(ext_dir)):
            print(f"   {Color.RED}✖ Thư mục báo cáo không tồn tại: '{ext_dir}'{Color.RESET}")
            return None
        sample_dir = prompt_path_with_browse(
            f"   {Color.CYAN}👉 [2/2] Nhập thư mục Golden Sample chuẩn (hoặc gõ [B] để chọn): {Color.RESET}",
            dialog_mode="folder",
            dialog_title="Chọn thư mục Golden Sample chuẩn",
            allow_file_shortcut=False,
        )
        if not sample_dir or not os.path.exists(to_long_path(sample_dir)):
            print(f"   {Color.RED}✖ Thư mục Golden Sample không tồn tại: '{sample_dir}'{Color.RESET}")
            return None
        compare_with_golden_sample(ext_dir, sample_dir)
        return ext_dir

    else:
        # Mode 2: Single Folder / Archive Mode
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Single Folder / Archive Mode] Trích xuất đơn lẻ 1 thư mục hoặc file nén (.zip/.tar.gz):{Color.RESET}\n")

        while True:
            prompt_str = (
                f"{Color.BRIGHT_YELLOW}📌 [1/3] Nhập đường dẫn thư mục log hoặc file nén (.zip/.tar.gz):{Color.RESET}\n"
                f"   {Color.GRAY}(Mẹo: Gõ [B] để chọn thư mục hoặc [F] để chọn file nén bằng cửa sổ Windows){Color.RESET}\n"
                f"   {Color.CYAN}👉 {Color.RESET}"
            )
            input_dir_raw = prompt_path_with_browse(
                prompt_str,
                dialog_mode="folder",
                dialog_title="Chọn thư mục log đầu vào",
                allow_file_shortcut=True,
            )
            if input_dir_raw and os.path.exists(to_long_path(input_dir_raw)):
                break
            if not sys.stdin.isatty():
                print(f"   {Color.RED}✖ Đường dẫn không tồn tại hoặc không hợp lệ: '{input_dir_raw}'{Color.RESET}")
                return None
            print(f"   {Color.RED}✖ Đường dẫn không tồn tại. Vui lòng kiểm tra lại!{Color.RESET}\n")

        input_dir = os.path.abspath(input_dir_raw.strip(' "\' \t\r\n'))
        detected_sns = detect_sns_from_folder(input_dir)

        if detected_sns:
            if len(detected_sns) == 1 or detected_sns[0].startswith("SGF"):
                sn_item = detected_sns[0]
                unit_tag = "Chassis 4U" if sn_item.startswith("FVB") else ("Chassis 5U" if ("W47DG" in input_dir or "5U_Dell" in input_dir or "5U84" in input_dir) else ("Chassis" if sn_item.startswith("SGF") else ("PSU" if sn_item.startswith("PM") else ("Chas S1H41" if check_is_s1h41(os.path.basename(input_dir.rstrip("\\/"))) else ("Chas S3T80" if check_is_s3t80(os.path.basename(input_dir.rstrip("\\/"))) else ("IO P61070" if check_is_p61070(os.path.basename(input_dir.rstrip("\\/"))) else "IO"))))))
                print(f"\n{Color.BRIGHT_YELLOW}⚡ [TỰ ĐỘNG CHỌN SN {unit_tag.upper()}]:{Color.RESET} {Color.BOLD}{Color.WHITE}{sn_item}{Color.RESET}")
                target_sn_raw = sn_item
            else:
                clip_sn = get_sn_from_clipboard(allow_multiple=False)
                default_choice = 1
                print(f"\n{Color.BRIGHT_YELLOW}📌 [2/3] Phát hiện Serial Number trong tên thư mục/file. Vui lòng chọn:{Color.RESET}")
                for idx, sn in enumerate(detected_sns, 1):
                    if sn.startswith("PM"):
                        ctrl_tag = f" ({'psu0 / PCM 1' if idx == 1 else 'psu1 / PCM 2'})"
                    elif not sn.startswith("SGF") and not sn.startswith("FVB"):
                        ctrl_tag = f" ({'ctrla' if idx == 1 else 'ctrlb'})"
                    else:
                        ctrl_tag = ""
                    clip_badge = ""
                    if clip_sn and clip_sn.upper() == sn.upper():
                        default_choice = idx
                        clip_badge = f" {Color.BRIGHT_GREEN}📋 [Khớp Clipboard]{Color.RESET}"
                    print(f"   {Color.CYAN}[{idx}]{Color.RESET} {Color.BOLD}{Color.WHITE}{sn}{Color.RESET}{Color.GRAY}{ctrl_tag}{Color.RESET}{clip_badge}")

                default_sn = detected_sns[default_choice - 1]
                prompt_str = f"   {Color.CYAN}👉 Chọn nhanh số (1-{len(detected_sns)}) hoặc nhấn Enter để chọn [{default_choice}] ({default_sn}): {Color.RESET}"
                valid_keys = [str(i) for i in range(1, len(detected_sns) + 1)]
                choice_str = get_single_key_choice(prompt_str, valid_keys, default_key=str(default_choice))

                if choice_str.isdigit() and 1 <= int(choice_str) <= len(detected_sns):
                    target_sn_raw = detected_sns[int(choice_str) - 1]
                else:
                    target_sn_raw = default_sn
        else:
            while True:
                clip_preview = get_sn_from_clipboard(allow_multiple=False)
                clip_hint = (
                    f"Nhấn Enter để lấy từ Clipboard: {Color.BOLD}{Color.WHITE}{clip_preview}{Color.RESET}{Color.GRAY}"
                    if clip_preview
                    else "Nhấn Enter để tự động lấy SN từ Clipboard"
                )
                prompt_str = (
                    f"\n{Color.BRIGHT_YELLOW}📌 [2/3] Nhập Target Serial Number (VD: SAFVN... hoặc SGFVN...):{Color.RESET}\n"
                    f"   {Color.GRAY}({clip_hint}){Color.RESET}\n"
                    f"   {Color.CYAN}👉 {Color.RESET}"
                )
                target_sn_raw = safe_input(prompt_str)
                if not target_sn_raw:
                    target_sn_raw = get_sn_from_clipboard(allow_multiple=False)
                    if target_sn_raw:
                        print(f"   {Color.GREEN}📋 Đã tự động lấy SN từ Clipboard: {Color.BOLD}{Color.WHITE}{target_sn_raw}{Color.RESET}")
                if target_sn_raw:
                    break
                if not sys.stdin.isatty():
                    print(f"   {Color.RED}✖ Target SN không được để trống.{Color.RESET}")
                    return None
                print(f"   {Color.RED}✖ Target SN trống (Clipboard cũng không có SN hợp lệ). Vui lòng nhập lại!{Color.RESET}\n")

        target_sn = target_sn_raw.strip(' "\' \t\r\n')
        default_output_base = get_default_reports_dir()

        target_default_dir = os.path.join(default_output_base, target_sn)
        prompt_str = (
            f"\n{Color.BRIGHT_YELLOW}📌 [3/3] Nhập thư mục xuất báo cáo (Mặc định: {target_default_dir}):{Color.RESET}\n"
            f"   {Color.CYAN}👉 Nhấn Enter dùng mặc định, gõ [B] chọn thư mục, hoặc dán đường dẫn khác: {Color.RESET}"
        )
        output_dir_raw = prompt_path_with_browse(
            prompt_str,
            dialog_mode="folder",
            dialog_title="Chọn thư mục lưu báo cáo đầu ra",
            allow_file_shortcut=False,
        )
        if not output_dir_raw:
            output_dir_raw = default_output_base
            print(f"   {Color.GREEN}➜ Đã chọn mặc định: {target_default_dir}{Color.RESET}")

        print(f"\n{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")
        res = process_single_extraction(input_dir, target_sn, output_dir_raw)
        print_batch_summary_table([res])
        return res.get("out_dir")
