"""Cycle-time metadata, report validation, diagnostics and CSV export."""

import csv
import difflib
import hashlib
import json
import os
import re

from .console_style import Color
from .log_io import from_long_path, get_log_package_pn, to_long_path, write_extracted_file


def format_seconds_short(total_seconds):
    """Format seconds into compact Xh Ym Zs or Ym Zs string."""
    if total_seconds is None:
        return "-"
    try:
        sec = int(round(float(total_seconds)))
    except Exception:
        return "-"
    if sec < 0:
        return "-"
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m:02d}m {s:02d}s"

def parse_duration_string(dur_str):
    """
    Parse '0 days 2 hours 31 minutes 43 seconds' into (total_seconds, short_str).
    """
    if not dur_str:
        return None, "-"
    d = h = m = s = 0
    m_d = re.search(r'(\d+)\s*days?', dur_str)
    m_h = re.search(r'(\d+)\s*hours?', dur_str)
    m_m = re.search(r'(\d+)\s*minutes?', dur_str)
    m_s = re.search(r'(\d+)\s*seconds?', dur_str)
    if m_d: d = int(m_d.group(1))
    if m_h: h = int(m_h.group(1))
    if m_m: m = int(m_m.group(1))
    if m_s: s = int(m_s.group(1))
    total_sec = d * 86400 + h * 3600 + m * 60 + s
    if total_sec == 0 and not any([m_d, m_h, m_m, m_s]):
        return None, dur_str.strip()
    return total_sec, format_seconds_short(total_sec)

def extract_cycle_time_metadata(working_unit_root, test_results_dir=None, folder_name=""):
    """
    Extract comprehensive Cycle Time and Test Metadata from a log unit:
    - Reads top-level <unit>.log, ctp_log_metadata.yaml, and job-*/results.json
    """
    meta = {
        "script_name": "-",
        "part_number": "-",
        "station_id": "-",
        "employee_id": "-",
        "local_start_time": "-",
        "local_end_time": "-",
        "test_duration_raw": "-",
        "cycle_time_seconds": None,
        "cycle_time_short": "-",
        "avocado_seconds": None,
        "avocado_short": "-",
        "pass_steps": 0,
        "fail_steps": 0,
        "error_steps": 0,
        "skip_steps": 0,
        "total_steps": 0,
        "test_status": "UNKNOWN"
    }

    # Fallback PN from folder_name (e.g. jbod_cto_test_uut0_W47DG_SGF...)
    if package_pn := get_log_package_pn(folder_name):
        meta["part_number"] = package_pn

    long_root = to_long_path(working_unit_root)
    if not os.path.isdir(long_root):
        return meta

    # 1. Check ctp_log_metadata.yaml
    yaml_path = os.path.join(working_unit_root, "ctp_log_metadata.yaml")
    if os.path.exists(to_long_path(yaml_path)):
        try:
            with open(to_long_path(yaml_path), 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith("HOST_NAME:"):
                        meta["station_id"] = line.split(":", 1)[1].strip()
                    elif line.startswith("TEST_NAME:"):
                        meta["script_name"] = line.split(":", 1)[1].strip()
                    elif line.startswith("START_TIME:") and meta["local_start_time"] == "-":
                        meta["local_start_time"] = line.split(":", 1)[1].strip()[:19]
        except Exception:
            pass

    # 2. Check top-level .log file (excluding mesdetails.log)
    try:
        log_candidates = [
            os.path.join(working_unit_root, fn)
            for fn in os.listdir(long_root)
            if fn.lower().endswith('.log') and fn.lower() not in ('mesdetails.log', 'job.log')
        ]
    except Exception:
        log_candidates = []

    for log_p in log_candidates:
        try:
            with open(to_long_path(log_p), 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if "Input Dict -" in line and "{" in line:
                        dict_part = line[line.find("{"):]
                        m_upn = re.search(r"'uut_pn'\s*:\s*'([^']+)'", dict_part)
                        if m_upn and m_upn.group(1):
                            meta["part_number"] = m_upn.group(1)
                        m_emp = re.search(r"'employee_id'\s*:\s*'([^']+)'", dict_part)
                        if m_emp and m_emp.group(1):
                            meta["employee_id"] = m_emp.group(1)
                    elif "Local start time:" in line:
                        m_st = re.search(r"Local start time:\s*([0-9-]+\s+[0-9:]+)", line)
                        if m_st:
                            meta["local_start_time"] = m_st.group(1)
                    elif "Local end time:" in line:
                        m_et = re.search(r"Local end time:\s*([0-9-]+\s+[0-9:]+)", line)
                        if m_et:
                            meta["local_end_time"] = m_et.group(1)
                    elif "Test duration:" in line:
                        m_dur = re.search(r"Test duration:\s*(.+)$", line)
                        if m_dur:
                            raw_d = m_dur.group(1).strip()
                            meta["test_duration_raw"] = raw_d
                            sec, short_s = parse_duration_string(raw_d)
                            meta["cycle_time_seconds"] = sec
                            meta["cycle_time_short"] = short_s
                    elif "with stationId " in line:
                        m_sta = re.search(r"with stationId\s+([A-Za-z0-9_-]+)", line)
                        if m_sta:
                            meta["station_id"] = m_sta.group(1)
                    elif "| Script " in line:
                        m_sc = re.search(r"Script\s+(\S+)\s+(started|passed|failed)", line)
                        if m_sc:
                            meta["script_name"] = m_sc.group(1)
                            if m_sc.group(2) == "passed":
                                meta["test_status"] = "PASS"
                            elif m_sc.group(2) == "failed":
                                meta["test_status"] = "FAIL"
        except Exception:
            pass

    # 3. Check results.json in job-* or parent of test-results
    results_json_paths = []
    if test_results_dir:
        cand_rj = os.path.join(os.path.dirname(test_results_dir), "results.json")
        if os.path.exists(to_long_path(cand_rj)):
            results_json_paths.append(cand_rj)
    if not results_json_paths:
        for root, dirs, files in os.walk(long_root):
            if "results.json" in files:
                results_json_paths.append(from_long_path(os.path.join(root, "results.json")))
                break

    if results_json_paths:
        try:
            with open(to_long_path(results_json_paths[0]), 'r', encoding='utf-8', errors='ignore') as f:
                rj_data = json.load(f)
            av_time = rj_data.get("time")
            if av_time is not None:
                meta["avocado_seconds"] = round(float(av_time), 2)
                meta["avocado_short"] = format_seconds_short(av_time)
                if meta["cycle_time_seconds"] is None:
                    meta["cycle_time_seconds"] = int(round(float(av_time)))
                    meta["cycle_time_short"] = meta["avocado_short"]
            meta["pass_steps"] = int(rj_data.get("pass", 0))
            meta["fail_steps"] = int(rj_data.get("failures", 0))
            meta["error_steps"] = int(rj_data.get("errors", 0))
            meta["skip_steps"] = int(rj_data.get("skip", 0))
            meta["total_steps"] = int(rj_data.get("total", 0))
            if meta["test_status"] == "UNKNOWN":
                if meta["fail_steps"] > 0 or meta["error_steps"] > 0:
                    meta["test_status"] = "FAIL"
                elif meta["pass_steps"] > 0:
                    meta["test_status"] = "PASS"
        except Exception:
            pass

    return meta

def validate_extracted_reports(unit_type, saved_paths):
    """
    Sanity & Completeness Guard:
    1. Verify expected number of files and non-zero size for all 7 product families.
    2. Scan extracted content for any VPD/FW mismatch or FAIL status lines.
    Returns: (is_valid, warnings_list)
    """
    warnings = []
    expected_counts = {
        "Chassis 4U": 6,
        "Chassis 5U": 2,
        "IO": 2,
        "IO P61070": 2,
        "Chas S1H41": 2,
        "Chas S1H42": 2,
        "Chas S1H44": 2,
        "Chas S1H47": 2,
        "Chas S1H48": 2,
        "Chas S3T80": 2,
        "Chassis": 1,
        "IOM RPC73": 1,
        "PSU 2U": 1,
        "PSU 5U": 1,
        "PSU": 1
    }
    exp_cnt = expected_counts.get(unit_type, 1)
    if len(saved_paths) < exp_cnt:
        warnings.append(f"Thiếu file báo cáo: tạo được {len(saved_paths)}/{exp_cnt} file")

    for p in saved_paths:
        long_p = to_long_path(p)
        fname = os.path.basename(p)
        if not os.path.exists(long_p):
            warnings.append(f"{fname}: File không tồn tại")
            continue
        sz = os.path.getsize(long_p)
        if sz == 0:
            warnings.append(f"{fname}: File rỗng (0 bytes)")
            continue
        try:
            with open(long_p, 'r', encoding='utf-8', errors='ignore') as f:
                for line_no, line in enumerate(f, 1):
                    low = line.lower()
                    if re.search(r'result:\s*mismatch', low) or re.search(r'->\s*mismatch', low):
                        warnings.append(f"{fname} (Dòng {line_no}): {line.strip()}")
                    elif '| fail |' in low:
                        warnings.append(f"{fname} (Dòng {line_no}): {line.strip()}")
                    elif '|1117|mismatch:' in low or 'fw mismatch:' in low or 'vpd rendering failed' in low:
                        warnings.append(f"{fname} (Dòng {line_no}): {line.strip()}")
        except Exception:
            pass

    return (len(warnings) == 0), warnings

def analyze_test_failures(working_unit_root, test_results_dir=None, out_dir=None, warnings=None, force_write=False):
    """
    Failure Root-Cause Analyzer:
    Inspects results.json and step debug.log files to pinpoint failed steps and error lines.
    Writes ERROR_SUMMARY.txt if failures/warnings exist or if force_write=True.
    Returns list of diagnostic strings.
    """
    diag_lines = []
    failed_steps = []

    rj_path = None
    if test_results_dir:
        cand = os.path.join(os.path.dirname(test_results_dir), "results.json")
        if os.path.exists(to_long_path(cand)):
            rj_path = cand
    if not rj_path and working_unit_root and os.path.isdir(to_long_path(working_unit_root)):
        for root, dirs, files in os.walk(to_long_path(working_unit_root)):
            if "results.json" in files:
                rj_path = from_long_path(os.path.join(root, "results.json"))
                break

    if rj_path:
        try:
            with open(to_long_path(rj_path), 'r', encoding='utf-8', errors='ignore') as f:
                rj = json.load(f)
            for t in rj.get("tests", []):
                st = t.get("status", "")
                if st in ("FAIL", "ERROR"):
                    failed_steps.append(t)
        except Exception:
            pass

    if not failed_steps and not warnings and not force_write:
        return []

    diag_lines.append("================================================================================")
    diag_lines.append("CHẨN ĐOÁN NHANH NGUYÊN NHÂN LỖI / CẢNH BÁO (DIAGNOSTIC SUMMARY)")
    diag_lines.append("================================================================================")

    if warnings:
        diag_lines.append(f"\n[!] CẢNH BÁO MISMATCH / TOÀN VẸN BÁO CÁO ({len(warnings)} cảnh báo):")
        for w in warnings:
            diag_lines.append(f"  - {w}")

    if failed_steps:
        diag_lines.append(f"\n[!] PHÁT HIỆN {len(failed_steps)} TEST STEP BỊ FAIL/ERROR TRONG RESULTS.JSON:")
        for idx, step in enumerate(failed_steps, 1):
            step_id = step.get("id", "Unknown")
            status = step.get("status", "FAIL")
            reason = step.get("fail_reason") or "Không có mô tả ngắn"
            dur = round(float(step.get("time", 0)), 2)
            diag_lines.append(f"\n  {idx}. Step: {step_id}")
            diag_lines.append(f"     Trạng thái : {status} (Thời gian chạy: {dur}s)")
            diag_lines.append(f"     Lý do lỗi  : {reason}")

            # Locate step debug.log inside test_results_dir
            if test_results_dir and os.path.isdir(to_long_path(test_results_dir)):
                step_num_m = re.match(r'^(\d+)-', str(step_id))
                if step_num_m:
                    prefix = f"{step_num_m.group(1)}-"
                    for d in os.listdir(to_long_path(test_results_dir)):
                        if d.startswith(prefix):
                            dbg_p = os.path.join(test_results_dir, d, "debug.log")
                            if os.path.exists(to_long_path(dbg_p)):
                                err_snippets = []
                                with open(to_long_path(dbg_p), 'r', encoding='utf-8', errors='ignore') as df:
                                    for l in df:
                                        if any(k in l for k in ("| ERROR", "FAIL", "Exception", "AssertionError", "mismatch", "Error:")):
                                            err_snippets.append(l.rstrip('\r\n'))
                                if err_snippets:
                                    diag_lines.append("     Chi tiết log lỗi cuối cùng trong debug.log:")
                                    for el in err_snippets[-15:]:
                                        diag_lines.append(f"       {el}")
                            break
    elif force_write and not warnings:
        diag_lines.append("\n[OK] Không phát hiện bước kiểm thử FAIL hay cảnh báo Mismatch nào.")

    if out_dir:
        err_file = os.path.join(out_dir, "ERROR_SUMMARY.txt")
        write_extracted_file(err_file, [l + "\n" for l in diag_lines], trim_last_newline=True)

    return diag_lines

def compare_with_golden_sample(generated_dir, sample_dir):
    """
    Golden Sample Diff Verifier:
    Compares extracted report files in generated_dir against sample_dir byte-for-byte (SHA256)
    and line-by-line (difflib) if any discrepancy exists.
    Returns: (all_matched, comparison_results)
    """
    gen_abs = os.path.abspath(generated_dir.strip(' "\' \t\r\n'))
    smp_abs = os.path.abspath(sample_dir.strip(' "\' \t\r\n'))

    if not os.path.isdir(to_long_path(gen_abs)):
        raise FileNotFoundError(f"Thư mục báo cáo không tồn tại: {gen_abs}")
    if not os.path.isdir(to_long_path(smp_abs)):
        raise FileNotFoundError(f"Thư mục mẫu (Sample) không tồn tại: {smp_abs}")

    sample_files = sorted([
        f for f in os.listdir(to_long_path(smp_abs))
        if os.path.isfile(to_long_path(os.path.join(smp_abs, f))) and f.lower().endswith(('.txt', '.md'))
    ])

    print(f"\n{Color.BRIGHT_CYAN}┌──────────────────────────────────────────────────────────────────────────────────────────────────┐{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}│{Color.RESET}                       {Color.BOLD}{Color.WHITE}BẢNG ĐỐI SOÁT MẪU CHUẨN (GOLDEN SAMPLE VERIFICATION){Color.RESET}                       {Color.BRIGHT_CYAN}│{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}├────────────────────────────────────────┬──────────────┬──────────────┬───────────┬───────────────┤{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}Tên File Báo Cáo                       {Color.RESET}│ {Color.BOLD}Kích Thước   {Color.RESET}│ {Color.BOLD}Số Dòng      {Color.RESET}│ {Color.BOLD}SHA256    {Color.RESET}│ {Color.BOLD}Kết Quả       {Color.RESET}{Color.BRIGHT_CYAN}│{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}├────────────────────────────────────────┼──────────────┼──────────────┼───────────┼───────────────┤{Color.RESET}")

    all_matched = True
    comp_results = []

    for fname in sample_files:
        sp = os.path.join(smp_abs, fname)
        gp = os.path.join(gen_abs, fname)
        fname_disp = (fname[:35] + "..." if len(fname) > 38 else fname).ljust(38)

        if not os.path.exists(to_long_path(gp)):
            all_matched = False
            print(f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.WHITE}{fname_disp}{Color.RESET} │ {'MISSING'.ljust(12)} │ {'-'.ljust(12)} │ {'-'.ljust(9)} │ {Color.BRIGHT_RED}MISSING      {Color.RESET} {Color.BRIGHT_CYAN}│{Color.RESET}")
            comp_results.append({"file": fname, "match": False, "reason": "Missing in generated output"})
            continue

        with open(to_long_path(sp), 'rb') as sf:
            s_bytes = sf.read()
        with open(to_long_path(gp), 'rb') as gf:
            g_bytes = gf.read()

        s_hash = hashlib.sha256(s_bytes).hexdigest()
        g_hash = hashlib.sha256(g_bytes).hexdigest()
        s_lines = s_bytes.decode('utf-8', errors='replace').splitlines()
        g_lines = g_bytes.decode('utf-8', errors='replace').splitlines()

        exact_match = (s_hash == g_hash)
        if not exact_match:
            all_matched = False

        sz_disp = f"{len(g_bytes)} B".ljust(12)
        ln_disp = f"{len(g_lines)}/{len(s_lines)}".ljust(12)
        hash_disp = g_hash[:9]
        res_disp = f"{Color.BRIGHT_GREEN}100% MATCH   {Color.RESET}" if exact_match else f"{Color.BRIGHT_RED}DIFF FOUND   {Color.RESET}"

        print(f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.WHITE}{fname_disp}{Color.RESET} │ {Color.GRAY}{sz_disp}{Color.RESET} │ {Color.YELLOW}{ln_disp}{Color.RESET} │ {Color.GRAY}{hash_disp}{Color.RESET} │ {res_disp} {Color.BRIGHT_CYAN}│{Color.RESET}")
        comp_results.append({
            "file": fname,
            "match": exact_match,
            "gen_size": len(g_bytes),
            "sample_size": len(s_bytes),
            "gen_lines": len(g_lines),
            "sample_lines": len(s_lines),
            "sha256": g_hash
        })

        if not exact_match:
            diff = list(difflib.unified_diff(s_lines, g_lines, fromfile=f"Sample/{fname}", tofile=f"Generated/{fname}", lineterm=""))
            if diff:
                print(f"{Color.YELLOW}  ⚠ Chi tiết dòng khác biệt trong {fname} (tối đa 15 dòng đầu):{Color.RESET}")
                for dl in diff[:15]:
                    color = Color.GREEN if dl.startswith('+') else (Color.RED if dl.startswith('-') else Color.GRAY)
                    print(f"    {color}{dl}{Color.RESET}")
            elif s_bytes != g_bytes:
                print(f"{Color.YELLOW}  ⚠ Nội dung văn bản khớp nhưng khác kiểu xuống dòng (CRLF vs LF) hoặc ký tự cuối file.{Color.RESET}")

    print(f"{Color.BRIGHT_CYAN}└────────────────────────────────────────┴──────────────┴──────────────┴───────────┴───────────────┘{Color.RESET}")
    if all_matched and sample_files:
        print(f"{Color.BRIGHT_GREEN}✔ XÁC MINH THÀNH CÔNG: Tất cả {len(sample_files)}/{len(sample_files)} file báo cáo khớp 100% Byte-for-Byte (SHA256 Verified)!{Color.RESET}\n")
    else:
        print(f"{Color.BRIGHT_RED}✖ XÁC MINH THẤT BẠI: Có sự khác biệt giữa báo cáo trích xuất và thư mục mẫu chuẩn.{Color.RESET}\n")

    return all_matched, comp_results


def export_cycle_time_summary_csv(results, output_csv_path):
    """
    Export batch extraction and cycle time metadata to Cycle_Time_Summary.csv (UTF-8 with BOM for Excel).
    """
    if not results:
        return None
    abs_csv = os.path.abspath(output_csv_path)
    parent = os.path.dirname(abs_csv)
    if parent:
        os.makedirs(to_long_path(parent), exist_ok=True)

    headers = [
        "STT", "Target_SN", "Product_Family", "Part_Number", "Controller",
        "Station_ID", "Employee_ID", "Script_Name",
        "Start_Time", "End_Time",
        "Cycle_Time_Short", "Cycle_Time_Seconds", "Cycle_Time_Raw",
        "Avocado_Short", "Avocado_Seconds",
        "Total_Steps", "Pass_Steps", "Fail_Steps", "Error_Steps", "Skip_Steps",
        "Test_Status", "Extraction_Status", "Warnings", "Output_Directory"
    ]
    try:
        with open(to_long_path(abs_csv), "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for idx, item in enumerate(results, 1):
                meta = item.get("metadata") or {}
                warnings_list = item.get("warnings") or []
                writer.writerow([
                    idx,
                    item.get("sn", "N/A"),
                    item.get("unit_type", "-"),
                    meta.get("part_number", "N/A"),
                    item.get("controller", "-"),
                    meta.get("station_id", "N/A"),
                    meta.get("employee_id", "N/A"),
                    meta.get("script_name", "N/A"),
                    meta.get("local_start_time", "N/A"),
                    meta.get("local_end_time", "N/A"),
                    meta.get("cycle_time_short", item.get("cycle_time", "N/A")),
                    meta.get("cycle_time_seconds", 0),
                    meta.get("test_duration_raw", "N/A"),
                    meta.get("avocado_short", "N/A"),
                    meta.get("avocado_seconds", 0.0),
                    meta.get("total_steps", 0),
                    meta.get("pass_steps", 0),
                    meta.get("fail_steps", 0),
                    meta.get("error_steps", 0),
                    meta.get("skip_steps", 0),
                    meta.get("test_status", "N/A"),
                    item.get("status", "N/A"),
                    " | ".join(warnings_list) if warnings_list else "OK",
                    item.get("out_dir", "-")
                ])
        print(f"{Color.BRIGHT_GREEN}📊 Đã xuất bảng tổng hợp Cycle Time CSV tại:{Color.RESET} {Color.BOLD}{Color.WHITE}{from_long_path(abs_csv)}{Color.RESET}")
        return abs_csv
    except Exception as e:
        print(f"{Color.YELLOW}⚠ Không thể ghi file CSV tổng hợp ({abs_csv}): {e}{Color.RESET}")
        return None
