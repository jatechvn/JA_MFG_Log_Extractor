#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Khung Mẫu Ứng Dụng CLI Python Chuyên Nghiệp (Professional CLI App Framework)
Bao gồm:
- Hỗ trợ màu ANSI chuẩn trên Windows CMD/PowerShell.
- Chọn nhanh 1 phím bằng msvcrt (không cần bấm Enter).
- Tự động định vị thư mục chứa script (không bị lệch sang C:\Users\<User>).
- 4 Chế độ làm việc: Đơn lẻ, Quét Batch thư mục, Đọc file CSV, Tạo CSV mẫu.
- Bắt lỗi từng item độc lập (không sập cả lượt batch).
- Bảng tổng hợp báo cáo trực quan.
"""

import os
import sys
import re
import csv
import argparse

# 1. Enable ANSI escape sequences on Windows console
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
            sys.stdin.reconfigure(encoding='utf-8')
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # ENABLE_PROCESSED_OUTPUT (1) | ENABLE_WRAP_AT_EOL_OUTPUT (2) | ENABLE_VIRTUAL_TERMINAL_PROCESSING (4)
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

# 2. ANSI Color Palette
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[96m"
    BRIGHT_CYAN = "\033[1;96m"
    GREEN = "\033[92m"
    BRIGHT_GREEN = "\033[1;92m"
    YELLOW = "\033[93m"
    BRIGHT_YELLOW = "\033[1;93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    RED = "\033[91m"
    BRIGHT_RED = "\033[1;91m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

# 3. Path & Helper Utilities
def get_script_dir():
    """Lấy đường dẫn thư mục tuyệt đối chứa script/exe hiện tại."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))

def get_single_key_choice(prompt_text, valid_keys, default_key="1"):
    """
    Bắt phím bấm đơn lẻ lập tức trên Windows mà không cần nhấn Enter.
    """
    print(prompt_text, end="", flush=True)
    if sys.platform == 'win32':
        try:
            import msvcrt
            while True:
                ch = msvcrt.getwch()
                if ch in ('\r', '\n'):
                    print(f"{default_key}")
                    return default_key
                elif ch in valid_keys:
                    print(f"{ch}")
                    return ch
                elif ch == '\x03':  # Ctrl+C
                    print()
                    raise KeyboardInterrupt
        except Exception:
            pass

    inp = input().strip(' "\' \t\r\n')
    return inp if inp in valid_keys else default_key

def print_header():
    """In khung tiêu đề giao diện."""
    print(f"\n{Color.BRIGHT_CYAN}┌─────────────────────────────────────────────────────────────────────┐{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}│{Color.RESET}            {Color.BOLD}{Color.WHITE}TÊN CÔNG CỤ / SCRIPT CỦA BẠN (CLI FRAMEWORK){Color.RESET}            {Color.BRIGHT_CYAN}│{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}└─────────────────────────────────────────────────────────────────────┘{Color.RESET}\n")

# 4. Core Business Logic (Tùy chỉnh phần này theo bài toán của bạn)
def process_single_item(input_path_raw, target_name_raw, output_dir_raw):
    """
    Hàm xử lý cho 1 đối tượng duy nhất. Trả về dict kết quả báo cáo.
    """
    input_path = os.path.abspath(input_path_raw.strip(' "\' \t\r\n'))
    target_name = target_name_raw.strip(' "\' \t\r\n') if target_name_raw else "DEFAULT_ITEM"
    
    # Định vị thư mục lưu mặc định nếu người dùng để trống
    script_dir = get_script_dir()
    output_dir = os.path.abspath(output_dir_raw.strip(' "\' \t\r\n')) if output_dir_raw else os.path.join(script_dir, "output")

    os.makedirs(output_dir, exist_ok=True)

    # -------------------------------------------------------------
    # TODO: VIẾT MÃ XỬ LÝ CHÍNH CỦA BẠN Ở ĐÂY (Vd: đọc file, parse log, xuất báo cáo)
    # -------------------------------------------------------------
    print(f"{Color.BRIGHT_CYAN}⚡ [ĐANG XỬ LÝ]{Color.RESET} Target: {Color.BOLD}{Color.WHITE}{target_name}{Color.RESET}")
    print(f"  {Color.BLUE}📂 File nguồn:{Color.RESET} {Color.GRAY}{input_path}{Color.RESET}")

    saved_file = os.path.join(output_dir, f"report_{target_name}.txt")
    with open(saved_file, "w", encoding="utf-8") as f:
        f.write(f"Báo cáo kết quả cho {target_name}\nNguồn: {input_path}\n")

    print(f"  {Color.BRIGHT_GREEN}✔ Đã lưu kết quả tại:{Color.RESET} {Color.WHITE}➜ {saved_file}{Color.RESET}")

    return {
        "name": target_name,
        "type": "SAMPLE_TYPE",
        "status": "SUCCESS",
        "error": None,
        "out_dir": output_dir
    }

# 5. Batch & CSV Processing Logic
def generate_sample_csv(output_filename="mau_danh_sach.csv"):
    """Tạo file CSV mẫu tại cùng thư mục chứa script."""
    if not os.path.isabs(output_filename):
        script_dir = get_script_dir()
        abs_csv = os.path.join(script_dir, output_filename)
    else:
        abs_csv = os.path.abspath(output_filename)

    sample_content = [
        ["InputPath", "TargetName", "OutputDir"],
        [r"D:\PATH\TO\SAMPLE_FILE_1.log", "ITEM_01", r"D:\PATH\TO\OUTPUT"],
        [r"D:\PATH\TO\SAMPLE_FILE_2.log", "ITEM_02", r"D:\PATH\TO\OUTPUT"]
    ]
    with open(abs_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(sample_content)

    print(f"\n{Color.BRIGHT_GREEN}✔ Đã tạo thành công file CSV mẫu tại:{Color.RESET}\n  {Color.BOLD}{Color.WHITE}➜ {abs_csv}{Color.RESET}\n")
    return abs_csv

def parse_csv_file(csv_path):
    """Đọc danh sách từ file CSV hoặc TXT."""
    abs_path = os.path.abspath(csv_path.strip(' "\' \t\r\n'))
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"File CSV không tồn tại: {abs_path}")

    batch_items = []
    with open(abs_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        first_line = f.readline()
        f.seek(0)
        delimiter = ';' if ';' in first_line and ',' not in first_line else ','
        reader = csv.reader(f, delimiter=delimiter)
        header = None

        for row in reader:
            if not row or not any(field.strip() for field in row):
                continue
            if header is None and ("path" in row[0].lower() or "input" in row[0].lower() or "link" in row[0].lower()):
                header = row
                continue

            inp_path = row[0].strip(' "\' \t\r\n') if len(row) > 0 else ""
            target_name = row[1].strip(' "\' \t\r\n') if len(row) > 1 else ""
            out_dir = row[2].strip(' "\' \t\r\n') if len(row) > 2 else ""

            if inp_path:
                batch_items.append((inp_path, target_name, out_dir))

    return batch_items

def print_batch_summary_table(results):
    """In bảng tổng hợp kết quả chạy Batch."""
    print(f"\n{Color.BRIGHT_CYAN}┌─────────────────────────────────────────────────────────────────────────────────────────────┐{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}│{Color.RESET}                          {Color.BOLD}{Color.WHITE}BẢNG TỔNG HỢP KẾT QUẢ XỬ LÝ BATCH{Color.RESET}                            {Color.BRIGHT_CYAN}│{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}├────┬──────────────────┬───────────┬────────────┬────────────────────────────────────────────────┤{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}STT{Color.RESET}│ {Color.BOLD}Target Name      {Color.RESET}│ {Color.BOLD}Phân Loại  {Color.RESET}│ {Color.BOLD}Trạng Thái {Color.RESET}│ {Color.BOLD}Thư mục lưu                                      {Color.RESET}{Color.BRIGHT_CYAN}│{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}├────┼──────────────────┼───────────┼────────────┼────────────────────────────────────────────────┤{Color.RESET}")

    success_count = 0
    fail_count = 0

    for idx, item in enumerate(results, 1):
        name = item.get("name", "UNKNOWN").ljust(16)
        item_type = item.get("type", "-").ljust(10)
        status = item.get("status", "FAIL")
        out_dir = item.get("out_dir", "-")
        out_disp = ("..." + out_dir[-42:]) if len(out_dir) > 45 else out_dir.ljust(45)

        if status == "SUCCESS":
            success_count += 1
            status_disp = f"{Color.BRIGHT_GREEN}SUCCESS   {Color.RESET}"
        else:
            fail_count += 1
            status_disp = f"{Color.BRIGHT_RED}FAIL      {Color.RESET}"

        print(f"{Color.BRIGHT_CYAN}│{Color.RESET} {str(idx).ljust(3)}│ {Color.BOLD}{Color.WHITE}{name}{Color.RESET}│ {Color.MAGENTA}{item_type}{Color.RESET}│ {status_disp}│ {Color.GRAY}{out_disp}{Color.RESET}{Color.BRIGHT_CYAN}│{Color.RESET}")

    print(f"{Color.BRIGHT_CYAN}└────┴──────────────────┴───────────┴────────────┴────────────────────────────────────────────────┘{Color.RESET}")
    print(f"\n{Color.BOLD}Thống kê:{Color.RESET} Tổng số: {len(results)} │ {Color.BRIGHT_GREEN}Thành công: {success_count}{Color.RESET} │ {Color.BRIGHT_RED}Thất bại: {fail_count}{Color.RESET}\n")

def run_batch_execution(batch_items):
    """Chạy vòng lặp cách ly lỗi cho từng item trong danh sách."""
    results = []
    total = len(batch_items)
    print(f"\n{Color.BRIGHT_YELLOW}🚀 Bắt đầu xử lý hàng loạt ({total} mục trong danh sách)...{Color.RESET}")
    print(f"{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")

    for idx, (inp_path, target_name, out_dir) in enumerate(batch_items, 1):
        print(f"\n{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} Đang xử lý: {Color.GRAY}{inp_path}{Color.RESET}")
        try:
            res = process_single_item(inp_path, target_name, out_dir)
            results.append(res)
        except Exception as e:
            print(f"  {Color.RED}✖ Lỗi khi xử lý {target_name}: {e}{Color.RESET}")
            results.append({
                "name": target_name if target_name else "N/A",
                "type": "ERROR",
                "status": "FAIL",
                "error": str(e),
                "out_dir": "-"
            })

    print_batch_summary_table(results)

# 6. Main Entry Point & Command Line Parsing
def main():
    parser = argparse.ArgumentParser(description="Mô tả công cụ của bạn.")
    parser.add_argument("--input", required=False, default=None, help="Đường dẫn file/folder đầu vào.")
    parser.add_argument("--name", required=False, default=None, help="Tên hoặc nhãn định danh.")
    parser.add_argument("--output", required=False, default=None, help="Thư mục xuất kết quả.")
    parser.add_argument("--batch-dir", required=False, default=None, help="Thư mục gốc quét hàng loạt.")
    parser.add_argument("--csv-file", required=False, default=None, help="File CSV danh sách đầu vào.")
    parser.add_argument("--generate-csv-template", action="store_true", help="Tạo file CSV mẫu.")

    args = parser.parse_args()

    if args.generate_csv_template:
        generate_sample_csv("mau_danh_sach.csv")
        return

    if args.csv_file:
        batch_items = parse_csv_file(args.csv_file)
        run_batch_execution(batch_items)
        return

    if args.input:
        res = process_single_item(args.input, args.name, args.output)
        print_batch_summary_table([res])
        return

    # Giao diện Chọn Chế độ Tương tác
    print_header()
    print(f"{Color.BRIGHT_YELLOW}Vui lòng chọn chế độ làm việc:{Color.RESET}")
    print(f"   {Color.CYAN}[1]{Color.RESET} Trực tiếp 1 đối tượng (Single Mode)")
    print(f"   {Color.CYAN}[2]{Color.RESET} Quét hàng loạt từ thư mục gốc (Batch Folder Scan)")
    print(f"   {Color.CYAN}[3]{Color.RESET} Đọc danh sách từ file CSV / TXT (Batch CSV Import)")
    print(f"   {Color.CYAN}[4]{Color.RESET} Tạo file CSV mẫu (mau_danh_sach.csv)\n")

    prompt_str = f"   {Color.CYAN}👉 Chọn nhanh số (1-4) hoặc nhấn Enter để chọn [1]: {Color.RESET}"
    mode_choice = get_single_key_choice(prompt_str, ["1", "2", "3", "4"], default_key="1")

    if mode_choice == "4":
        generate_sample_csv("mau_danh_sach.csv")
        return
    elif mode_choice == "3":
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Batch CSV Mode] Đọc danh sách từ file CSV/TXT:{Color.RESET}")
        csv_path = input(f"   {Color.CYAN}👉 Nhập đường dẫn file CSV/TXT (Mặc định: mau_danh_sach.csv): {Color.RESET}").strip(' "\' \t\r\n')
        if not csv_path:
            script_dir = get_script_dir()
            csv_path = os.path.join(script_dir, "mau_danh_sach.csv")
            if not os.path.exists(csv_path):
                generate_sample_csv(csv_path)

        batch_items = parse_csv_file(csv_path)
        run_batch_execution(batch_items)
        return
    elif mode_choice == "2":
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Batch Folder Scan] Quét hàng loạt thư mục gốc:{Color.RESET}")
        parent_dir = input(f"   {Color.CYAN}👉 Nhập đường dẫn thư mục gốc: {Color.RESET}").strip(' "\' \t\r\n')
        while not parent_dir or not os.path.exists(parent_dir):
            print(f"   {Color.RED}✖ Thư mục không tồn tại. Vui lòng nhập lại!{Color.RESET}")
            parent_dir = input(f"   {Color.CYAN}👉 Nhập đường dẫn thư mục gốc: {Color.RESET}").strip(' "\' \t\r\n')

        # Đọc danh sách các subfolder trong parent_dir
        batch_items = [(os.path.join(parent_dir, d), d, "") for d in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, d))]
        run_batch_execution(batch_items)
        return
    else:
        # Chế độ 1: Single Mode
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Single Mode] Xử lý đơn lẻ 1 mục:{Color.RESET}\n")

        while True:
            prompt_str = f"{Color.BRIGHT_YELLOW}📌 [1/2] Nhập đường dẫn đầu vào (Input Path):{Color.RESET}\n   {Color.CYAN}👉 {Color.RESET}"
            inp_raw = input(prompt_str).strip(' "\' \t\r\n')
            if inp_raw and os.path.exists(inp_raw):
                break
            print(f"   {Color.RED}✖ Đường dẫn không tồn tại. Vui lòng kiểm tra lại!{Color.RESET}\n")

        prompt_str = f"\n{Color.BRIGHT_YELLOW}📌 [2/2] Nhập thư mục xuất kết quả (Nhấn Enter để chọn mặc định):{Color.RESET}\n   {Color.CYAN}👉 {Color.RESET}"
        out_raw = input(prompt_str).strip(' "\' \t\r\n')

        print(f"\n{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")
        res = process_single_item(inp_raw, os.path.basename(inp_raw), out_raw)
        print_batch_summary_table([res])

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Color.YELLOW}[!] Thao tác đã bị hủy bởi người dùng (Ctrl+C).{Color.RESET}\n")
        sys.exit(0)
