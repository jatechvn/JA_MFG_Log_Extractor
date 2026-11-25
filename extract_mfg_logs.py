import os
import sys
import csv
import json
import argparse

# Preserve the original entrypoint imports for existing callers.
from module.cli_ui import (
    print_header as _print_header,
    print_batch_summary_table,
    open_native_path_dialog,
    get_clipboard_text,
    get_sn_from_clipboard,
    safe_input,
    prompt_path_with_browse,
    get_single_key_choice,
    prompt_post_extraction_actions,
    _format_station_cell,
    render_station_ip_map_lines,
    prompt_ip_with_station_map,
    run_remote_interactive_mode as _run_remote_interactive_mode,
    run_interactive_menu_once as _run_interactive_menu_once,
)
from module.console_style import Color
from module.extract_basic import extract_chassis_vpd, extract_fw, extract_vpd
from module.extract_chassis_5u import (
    check_is_chassis_5u_dell,
    find_chassis_5u_fw_step_dir,
    extract_chassis_5u_midplane_validation,
    strip_5u_log_code,
    extract_7pntn_fan_fw,
    extract_7pntn_wwn,
    extract_7pntn_fan_vpd,
    extract_7pntn_customer_validation,
    extract_chassis_5u_dell_logs,
)
from module.extract_juno import extract_chassis_4u_logs
from module.extract_p61070 import (
    P61070_PART_NUMBER,
    P61070_CLI_REPORT_NAME,
    P61070_RAW_REPORT_NAME,
    check_is_p61070,
    detect_p61070_controller,
    extract_p61070_logs,
    render_p61070_cli_report,
    render_p61070_raw_report,
)
from module.extract_s1h41 import (
    S1H41_PART_NUMBER,
    S1H41_CLI_REPORT_NAME,
    S1H41_RAW_REPORT_NAME,
    check_is_s1h41,
    validate_s1h41_target_sn,
    extract_s1h41_logs,
    render_s1h41_cli_report,
    render_s1h41_raw_report,
)
from module.extract_s1h42 import (
    S1H42_PART_NUMBER,
    S1H42_CLI_REPORT_NAME,
    S1H42_RAW_REPORT_NAME,
    check_is_s1h42,
    validate_s1h42_target_sn,
    extract_s1h42_logs,
    render_s1h42_cli_report,
    render_s1h42_raw_report,
)
from module.extract_s3t80 import (
    S3T80_PART_NUMBER,
    S3T80_CLI_REPORT_NAME,
    S3T80_RAW_REPORT_NAME,
    check_is_s3t80,
    validate_s3t80_target_sn,
    extract_s3t80_logs,
    render_s3t80_cli_report,
    render_s3t80_raw_report,
)
from module.extract_psu import (
    check_is_psu,
    check_is_psu_dyjw5,
    detect_psu_model_info,
    detect_psu_unit_id,
    extract_psu_dyjw5,
    extract_psu_logs,
)
from module.extract_rpc73 import (
    _RPC73_REVISION_HEADER,
    check_is_iom_rpc73,
    find_rpc73_fw_step_dir,
    extract_rpc73_revision_vpd,
    detect_rpc73_controller_from_vpd,
    extract_iom_rpc73,
)
from module.extraction_workflows import (
    _PRINT_LOCK,
    detect_sns_from_folder,
    determine_controller,
    is_remote_ip_target,
    process_remote_extraction as _process_remote_extraction,
    process_single_extraction,
    run_batch_extraction as _run_batch_extraction,
)
from module.log_io import (
    to_long_path,
    from_long_path,
    get_script_dir,
    get_log_package_pn,
    get_default_reports_dir,
    get_default_downloads_dir,
    find_step_dir,
    clean_log_lines,
    write_extracted_file,
    resolve_output_paths,
    is_archive_path,
    strip_archive_ext,
    find_test_results_dir,
    get_log_unit_root,
    _should_extract_archive_member,
    prepare_log_input_source,
)
from module.reporting import (
    format_seconds_short,
    parse_duration_string,
    extract_cycle_time_metadata,
    validate_extracted_reports,
    analyze_test_failures,
    compare_with_golden_sample,
    export_cycle_time_summary_csv,
)


APP_NAME = "JA_MFG_Log_Extractor"
APP_TITLE = "CÔNG CỤ TRÍCH XUẤT LOG TỰ ĐỘNG (IO, CHASSIS & PSU UNITS)"
APP_VERSION = "1.8.1"
APP_BUILD = "0"

# Enable ANSI escape sequences on Windows console
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

def print_header():
    """Display the CLI banner with the current app metadata."""
    return _print_header(APP_TITLE, APP_VERSION)

def generate_sample_csv(output_csv_path="mau_danh_sach_log.csv"):
    """
    Generate a template CSV file for batch log processing in the script's directory.
    Supports both Remote IP (via Bridge 172.21.168.241) and Local Folder/Archive paths.
    """
    if not os.path.isabs(output_csv_path):
        script_dir = get_script_dir()
        abs_csv = os.path.join(script_dir, output_csv_path)
    else:
        abs_csv = os.path.abspath(output_csv_path)

    sample_content = [
        ["LogPath_Or_IP", "TargetSN", "OutputBaseDir (De trong = Mac dinh <App_Dir>/reports)"],
        ["116.172", "PMV1104546G0017", ""],
        ["116.174", "SGFVN2633836284", ""],
        [r"D:\JA_TESTER\LOGS_ANL\5U_Dell\jbod_cto_test_uut0_W47DG_SGFVN26418364D7_20261008-124933", "SGFVN26418364D7", ""],
        [r"D:\JA_TESTER\LOGS_ANL\5U_PSU\jbod_cto_test_uut0_0R4C4_PMV1104546G0016_PMV1104546G0017_20261005-134529", "PMV1104546G0016", ""],
        [r"D:\JA_TESTER\LOGS_ANL\2U_PSU\jbod_cto_test_uut0_DYJW5_PMV1104029G007D_PMV1104029G007K_20261003-142309", "PMV1104029G007D", ""],
        [r"D:\JA_TESTER\LOGS_ANL\4U_Juno\FVBTL0000E_RAW\juno_fin2_test_uut0_J024X1-995_FVBTL0000E_20260912-154742", "FVBTL0000E", ""],
        [r"D:\JA_TESTER\LOGS_ANL\2U24\jbod_cto_test_uut0_NP0W0_SGFVN2632836201_20260808-164852", "SGFVN2632836201", ""],
        [r"D:\JA_TESTER\LOGS_ANL\IO\rbod_fin2_test_uut0_TD214_SAFVN2628836122_SAFVN262883610F_20260717-053125", "SAFVN262883610F", ""]
    ]
    with open(abs_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(sample_content)
    print(f"\n{Color.BRIGHT_GREEN}✔ Đã tạo thành công file CSV mẫu tại:{Color.RESET}\n  {Color.BOLD}{Color.WHITE}➜ {abs_csv}{Color.RESET}\n")
    return abs_csv

def parse_csv_file(csv_path):
    """
    Parse CSV or TXT file into list of batch items: (log_path_or_ip, target_sn, output_base_dir)
    """
    abs_path = os.path.abspath(csv_path.strip(' "\' \t\r\n'))
    if not os.path.exists(to_long_path(abs_path)):
        raise FileNotFoundError(f"File CSV không tồn tại: {from_long_path(abs_path)}")

    batch_items = []
    with open(to_long_path(abs_path), 'r', encoding='utf-8-sig', errors='ignore') as f:
        first_line = f.readline()
        f.seek(0)
        delimiter = ';' if ';' in first_line and ',' not in first_line else ','
        
        reader = csv.reader(f, delimiter=delimiter)
        header = None
        for row in reader:
            if not row or not any(field.strip() for field in row):
                continue
            first_col_low = row[0].strip().lower()
            if first_col_low.startswith("#"):
                continue
            if header is None and any(k in first_col_low for k in ("logpath", "link", "path", "ip", "host", "machine")):
                header = row
                continue
            
            log_path = row[0].strip(' "\' \t\r\n') if len(row) > 0 else ""
            target_sn = row[1].strip(' "\' \t\r\n') if len(row) > 1 else ""
            output_base = row[2].strip(' "\' \t\r\n') if len(row) > 2 else ""

            if log_path:
                batch_items.append((log_path, target_sn, output_base))

    return batch_items

def scan_parent_folder_for_logs(parent_folder, default_output_base=None):
    """
    Scan parent folder for subdirectories or standalone archives containing raw test logs.
    Returns list of items: (log_path, target_sn, output_base)
    By default, output_base points to <App_Dir>/reports.
    """
    abs_parent = os.path.abspath(parent_folder.strip(' "\' \t\r\n'))
    if not os.path.exists(to_long_path(abs_parent)):
        raise FileNotFoundError(f"Thư mục hoặc file không tồn tại: {from_long_path(abs_parent)}")

    found_items = []

    if is_archive_path(abs_parent):
        target_dirs = [abs_parent]
    else:
        def check_is_direct_log_unit(path):
            abs_p = os.path.abspath(path)
            long_p = to_long_path(abs_p)
            if os.path.basename(abs_p) == 'test-results' and os.path.isdir(long_p):
                return True
            if os.path.isdir(os.path.join(long_p, 'test-results')):
                return True
            if os.path.isdir(os.path.join(long_p, 'latest', 'test-results')):
                return True
            try:
                for item in os.listdir(long_p):
                    if item.startswith('job-') and os.path.isdir(os.path.join(long_p, item, 'test-results')):
                        return True
            except Exception:
                pass
            return False

        if check_is_direct_log_unit(abs_parent):
            target_dirs = [abs_parent]
        else:
            target_dirs = []
            archive_candidates = []
            for root, dirs, files in os.walk(to_long_path(abs_parent)):
                if 'test-results' in dirs:
                    parent_of_tr = from_long_path(root)
                    if os.path.basename(parent_of_tr) in ['latest'] or os.path.basename(parent_of_tr).startswith('job-'):
                        unit_dir = os.path.dirname(parent_of_tr)
                    else:
                        unit_dir = parent_of_tr
                    
                    if unit_dir not in target_dirs:
                        target_dirs.append(unit_dir)
                for fname in files:
                    full_f = os.path.join(from_long_path(root), fname)
                    if is_archive_path(full_f) and detect_sns_from_folder(full_f):
                        archive_candidates.append(full_f)

            unpacked_basenames = {os.path.basename(d.rstrip('\\/')).lower() for d in target_dirs}
            for arch in archive_candidates:
                stem_bname = os.path.basename(strip_archive_ext(arch)).lower()
                if stem_bname not in unpacked_basenames and arch not in target_dirs:
                    target_dirs.append(arch)

    default_base = default_output_base if default_output_base else get_default_reports_dir()

    for log_dir in target_dirs:
        detected_sns = detect_sns_from_folder(log_dir)
        if not detected_sns:
            continue

        # For IO/PSU units with 2 SNs, process both units automatically!
        if len(detected_sns) == 2 and not (detected_sns[0].startswith("SGF") or detected_sns[0].startswith("FVB")):
            found_items.append((log_dir, detected_sns[0], default_base))
            found_items.append((log_dir, detected_sns[1], default_base))
        else:
            for sn in detected_sns:
                found_items.append((log_dir, sn, default_base))

    return found_items


def run_cycle_time_analysis(batch_items, output_csv_path=None, diagnose=False):
    """
    Fast Cycle Time & Test Metadata analysis across one or more log folders/archives
    without extracting full FW/VPD reports.
    Saves Cycle_Time_Summary.csv into <App_Dir>/reports/Cycle_Time_Summary.csv by default.
    """
    results = []
    seen_units = set()
    reports_root = get_default_reports_dir()
    print(f"\n{Color.BRIGHT_YELLOW}⏱  Đang phân tích Cycle Time & Test Metadata...{Color.RESET}")
    print(f"{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")

    for log_path, target_sn, output_base in batch_items:
        unit_key = os.path.abspath(log_path)
        if unit_key in seen_units:
            continue
        seen_units.add(unit_key)

        try:
            with prepare_log_input_source(log_path) as (working_dir, logical_root, logical_name):
                try:
                    tr_dir = find_test_results_dir(working_dir)
                except Exception:
                    tr_dir = None
                meta = extract_cycle_time_metadata(working_dir, tr_dir, folder_name=logical_name)
                sns = detect_sns_from_folder(logical_root)
                sn_disp = ", ".join(sns) if sns else (target_sn or logical_name)
                first_sn = sns[0] if sns else (target_sn or "")
                unit_type = (
                    "Chassis 4U" if first_sn.startswith("FVB") else
                    ("Chassis 5U" if ("W47DG" in logical_root or "5U_Dell" in logical_root or "5U84" in logical_root or str(meta.get("part_number", "")).strip().upper() in ("W47DG", "7PNTN")) else
                     ("Chassis" if first_sn.startswith("SGF") else
                      ("PSU" if first_sn.startswith("PM") else
                       ("Chas S1H41" if check_is_s1h41(logical_name, meta.get("part_number", "")) else
                        ("Chas S1H42" if check_is_s1h42(logical_name, meta.get("part_number", "")) else
                         ("Chas S3T80" if check_is_s3t80(logical_name, meta.get("part_number", "")) else
                          ("IO P61070" if check_is_p61070(logical_name, meta.get("part_number", "")) else "IO")))))))
                )
                print(f"\n  {Color.BRIGHT_CYAN}● Log Unit:{Color.RESET} {Color.WHITE}{logical_name}{Color.RESET}")
                print(f"    ├─ {Color.GRAY}SN / Part Number :{Color.RESET} {Color.BOLD}{sn_disp}{Color.RESET} (PN: {meta['part_number']})")
                print(f"    ├─ {Color.GRAY}Station / User   :{Color.RESET} {meta['station_id']} / {meta['employee_id']} ({meta['script_name']})")
                print(f"    ├─ {Color.GRAY}Start -> End     :{Color.RESET} {meta['local_start_time']}  ➜  {meta['local_end_time']}")
                print(f"    ├─ {Color.GRAY}Total Cycle Time :{Color.RESET} {Color.BRIGHT_GREEN}{meta['cycle_time_short']}{Color.RESET} ({meta['test_duration_raw']} | {meta['cycle_time_seconds']}s)")
                print(f"    ├─ {Color.GRAY}Avocado Active   :{Color.RESET} {Color.BRIGHT_CYAN}{meta['avocado_short']}{Color.RESET} ({meta['avocado_seconds']}s)")
                status_color = Color.BRIGHT_GREEN if meta['test_status'] == "PASS" else Color.BRIGHT_RED
                print(f"    └─ {Color.GRAY}Test Steps       :{Color.RESET} {status_color}{meta['test_status']}{Color.RESET} (Total: {meta['total_steps']} | Pass: {meta['pass_steps']} | Fail: {meta['fail_steps']} | Skip: {meta['skip_steps']})")

                diag_target_dir = os.path.join(output_base if output_base else reports_root, first_sn or logical_name)
                if diagnose or meta["test_status"] == "FAIL":
                    diag_lines = analyze_test_failures(working_dir, tr_dir, out_dir=diag_target_dir, warnings=[], force_write=diagnose)
                    if diag_lines:
                        print(f"    {Color.BRIGHT_RED}🔍 Đã tạo báo cáo chẩn đoán lỗi:{Color.RESET} {Color.WHITE}{os.path.join(diag_target_dir, 'ERROR_SUMMARY.txt')}{Color.RESET}")

                results.append({
                    "sn": sn_disp,
                    "unit_type": unit_type,
                    "controller": meta["test_status"],
                    "status": "SUCCESS" if meta["cycle_time_seconds"] > 0 or meta["avocado_seconds"] > 0 else "FAIL",
                    "out_dir": diag_target_dir if os.path.exists(to_long_path(diag_target_dir)) else reports_root,
                    "cycle_time": meta["cycle_time_short"],
                    "metadata": meta,
                    "warnings": []
                })
        except Exception as e:
            print(f"  {Color.RED}✖ Lỗi phân tích Cycle Time cho {log_path}: {e}{Color.RESET}")

    if results:
        print_batch_summary_table(results)
        if not output_csv_path:
            output_csv_path = os.path.join(reports_root, "Cycle_Time_Summary.csv")
        export_cycle_time_summary_csv(results, output_csv_path)
    return results


def process_remote_extraction(
    raw_ip,
    raw_sn,
    output_base_raw=None,
    latest_n=None,
    max_days=None,
    remote_path=None,
    ssh_user=None,
    ssh_password=None,
    ssh_port=None,
    connection_mode=None,
    bridge_host=None,
    bridge_user=None,
    bridge_password=None,
    bridge_transport=None,
    keep_raw_zip=False,
    diagnose=False,
    interactive=False,
    export_csv=True,
    custom_csv_path=None,
    list_only=False,
    ssh_service=None,
):
    """Run remote extraction with the CLI's input and summary functions."""
    return _process_remote_extraction(
        raw_ip=raw_ip,
        raw_sn=raw_sn,
        output_base_raw=output_base_raw,
        latest_n=latest_n,
        max_days=max_days,
        remote_path=remote_path,
        ssh_user=ssh_user,
        ssh_password=ssh_password,
        ssh_port=ssh_port,
        connection_mode=connection_mode,
        bridge_host=bridge_host,
        bridge_user=bridge_user,
        bridge_password=bridge_password,
        bridge_transport=bridge_transport,
        keep_raw_zip=keep_raw_zip,
        diagnose=diagnose,
        interactive=interactive,
        export_csv=export_csv,
        custom_csv_path=custom_csv_path,
        list_only=list_only,
        ssh_service=ssh_service,
        read_input=safe_input,
        show_summary=print_batch_summary_table,
    )


def run_batch_extraction(batch_items, max_workers=4, export_csv=True, diagnose=False):
    """Run the batch workflow through the CLI's remote handler and summary."""
    return _run_batch_extraction(
        batch_items,
        max_workers=max_workers,
        export_csv=export_csv,
        diagnose=diagnose,
        extract_remote=process_remote_extraction,
        show_summary=print_batch_summary_table,
    )


def run_remote_interactive_mode():
    """Run the remote menu with the CLI's extraction adapter."""
    return _run_remote_interactive_mode(extract_remote=process_remote_extraction)


def run_interactive_menu_once():
    """Connect one interactive menu pass to the CLI actions."""
    return _run_interactive_menu_once(
        show_header=print_header,
        run_remote=run_remote_interactive_mode,
        run_batch_extraction=run_batch_extraction,
        generate_sample_csv=generate_sample_csv,
        parse_csv_file=parse_csv_file,
        scan_parent_folder_for_logs=scan_parent_folder_for_logs,
        run_cycle_time_analysis=run_cycle_time_analysis,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Trích xuất log sản xuất tự động cho IO (FW.txt, VPD.txt), PSU, và Chassis (<SN>.txt) qua Indirect Bridge (172.21.168.241 -> 172.19.*.*) hoặc Local kèm phân tích Cycle Time."
    )
    parser.add_argument("--ip", required=False, default=None, help="Remote test station IP or 2-octet shorthand (e.g. 116.174, 116182, 172.19.116.174, 172.21.168.241).")
    parser.add_argument("--sn", required=False, default=None, help="Serial number(s) to search on remote test station (comma-separated, e.g. SN1,SN2).")
    parser.add_argument("--latest", type=int, required=False, default=None, help="Automatically pick the N newest matching logs on remote host (e.g. --latest 1).")
    parser.add_argument("--days", type=float, required=False, default=None, help="Filter remote logs modified within the last N days.")
    parser.add_argument("--remote-path", required=False, default=None, help="Remote base path to scan (default auto-detects /CTP/logs/test/ or D:/).")
    parser.add_argument("--ssh-user", required=False, default=None, help="Override SSH username.")
    parser.add_argument("--ssh-password", required=False, default=None, help="Override SSH password.")
    parser.add_argument("--ssh-port", type=int, required=False, default=None, help="Override SSH port (default: 22).")
    parser.add_argument("--connection", choices=["auto", "direct", "bridge"], required=False, default=None, help="Connection mode: auto, direct, or bridge.")
    parser.add_argument("--bridge-host", required=False, default=None, help="Override jump-host bridge IP (default from config.json: 172.21.168.241).")
    parser.add_argument("--bridge-user", required=False, default=None, help="Override bridge username.")
    parser.add_argument("--bridge-password", required=False, default=None, help="Override bridge password.")
    parser.add_argument("--bridge-transport", choices=["auto", "ssh", "winrm"], required=False, default=None, help="Bridge transport protocol: auto, ssh, or winrm.")
    parser.add_argument("--keep-raw-zip", action="store_true", help="Also retain the full raw .zip log archive in <App_Dir>/downloads/<IP>/.")
    parser.add_argument("--list-only", action="store_true", help="Only list matching remote log packages with PASS/FAIL & MES end time without downloading/extracting.")
    parser.add_argument("--input-dir", required=False, default=None, help="Path to local raw test log directory or archive (.zip/.tar.gz/.tar.xz).")
    parser.add_argument("--target-sn", required=False, default=None, help="Target serial number (e.g. SAFVN..., SGFVN..., FVB..., PM...).")
    parser.add_argument("--output-dir", required=False, default=None, help="Path to output base directory (default: <App_Dir>/reports).")
    parser.add_argument("--batch-dir", required=False, default=None, help="Path to parent folder containing multiple raw log subfolders/archives.")
    parser.add_argument("--csv-file", required=False, default=None, help="Path to CSV/TXT file containing list of logs (supports both Remote IP and Local Path).")
    parser.add_argument("--generate-csv-template", action="store_true", help="Generate sample CSV input file.")
    parser.add_argument("--cycle-time", action="store_true", help="Analyze and export Cycle Time & Test Metadata only.")
    parser.add_argument("--diagnose", action="store_true", help="Force root-cause failure diagnosis (ERROR_SUMMARY.txt) when FAIL steps exist.")
    parser.add_argument("--verify-sample", required=False, default=None, help="Compare extracted output folder against a Golden Sample folder byte-for-byte.")
    parser.add_argument("--workers", type=int, default=4, help="Number of worker threads for batch extraction (default: 4).")
    parser.add_argument("--export-summary-csv", required=False, default=None, help="Custom path to export Cycle_Time_Summary.csv.")
    parser.add_argument("--in-terminal", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.generate_csv_template:
        generate_sample_csv("mau_danh_sach_log.csv")
        return

    # Standalone Golden Sample verification without extraction
    if args.verify_sample and args.output_dir and not args.input_dir and not args.ip:
        all_ok, _ = compare_with_golden_sample(args.output_dir, args.verify_sample)
        if not all_ok:
            sys.exit(1)
        return

    # Remote IP + SN Extraction Mode (Direct or via Indirect Bridge 172.21.168.241 -> 172.19.*.*)
    if args.ip:
        raw_sn = args.sn or args.target_sn
        if not raw_sn:
            print(f"{Color.RED}✖ Vui lòng truyền --sn (hoặc --target-sn) khi kết nối tới trạm test --ip {args.ip}.{Color.RESET}")
            sys.exit(1)
        try:
            results = process_remote_extraction(
                raw_ip=args.ip,
                raw_sn=raw_sn,
                output_base_raw=args.output_dir,
                latest_n=args.latest,
                max_days=args.days,
                remote_path=args.remote_path,
                ssh_user=args.ssh_user,
                ssh_password=args.ssh_password,
                ssh_port=args.ssh_port,
                connection_mode=args.connection,
                bridge_host=args.bridge_host,
                bridge_user=args.bridge_user,
                bridge_password=args.bridge_password,
                bridge_transport=args.bridge_transport,
                keep_raw_zip=args.keep_raw_zip,
                diagnose=args.diagnose,
                interactive=(args.latest is None and not args.list_only and sys.stdin.isatty()),
                export_csv=not args.list_only,
                custom_csv_path=args.export_summary_csv,
                list_only=args.list_only,
            )
        except Exception as exc:
            print(f"{Color.RED}✖ Lỗi kết nối/trích xuất từ xa: {exc}{Color.RESET}")
            sys.exit(1)

        if not results or any(r.get("status") != "SUCCESS" for r in results):
            sys.exit(1)
        if args.verify_sample and results:
            all_ok, _ = compare_with_golden_sample(results[0]["out_dir"], args.verify_sample)
            if not all_ok:
                sys.exit(1)
        return

    # Fast Cycle Time analysis mode
    if args.cycle_time:
        target = args.batch_dir or args.input_dir
        if not target:
            print(f"{Color.RED}✖ Vui lòng truyền --input-dir hoặc --batch-dir khi dùng --cycle-time.{Color.RESET}")
            sys.exit(1)
        items = scan_parent_folder_for_logs(target, default_output_base=args.output_dir)
        if not items:
            items = [(target, args.target_sn or args.sn or "", args.output_dir or get_default_reports_dir())]
        run_cycle_time_analysis(items, output_csv_path=args.export_summary_csv, diagnose=args.diagnose)
        return

    # Non-interactive CLI flags for batch execution
    if args.csv_file:
        batch_items = parse_csv_file(args.csv_file)
        if args.output_dir:
            batch_items = [(lp, tsn, ob or args.output_dir) for lp, tsn, ob in batch_items]
        results = run_batch_extraction(batch_items, max_workers=args.workers, export_csv=(not args.export_summary_csv), diagnose=args.diagnose)
        if args.export_summary_csv:
            export_cycle_time_summary_csv(results, args.export_summary_csv)
        return

    if args.batch_dir:
        batch_items = scan_parent_folder_for_logs(args.batch_dir, default_output_base=args.output_dir)
        results = run_batch_extraction(batch_items, max_workers=args.workers, export_csv=(not args.export_summary_csv), diagnose=args.diagnose)
        if args.export_summary_csv:
            export_cycle_time_summary_csv(results, args.export_summary_csv)
        return

    # Non-interactive single unit mode (supports auto-detecting target_sn if omitted)
    if args.input_dir:
        target_sn = args.target_sn or args.sn
        if not target_sn:
            sns = detect_sns_from_folder(args.input_dir)
            if sns:
                target_sn = sns[0]
        if not target_sn:
            print(f"{Color.RED}✖ Không thể tự động nhận diện Target SN từ '{args.input_dir}'. Vui lòng truyền --target-sn.{Color.RESET}")
            sys.exit(1)
        res = process_single_extraction(args.input_dir, target_sn, args.output_dir, diagnose=args.diagnose)
        print_batch_summary_table([res])
        if args.export_summary_csv:
            export_cycle_time_summary_csv([res], args.export_summary_csv)
        if args.verify_sample:
            all_ok, _ = compare_with_golden_sample(res["out_dir"], args.verify_sample)
            if not all_ok:
                sys.exit(1)
        return

    # Interactive Menu Loop
    while True:
        last_out_dir = run_interactive_menu_once()
        if not prompt_post_extraction_actions(last_out_dir):
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Color.YELLOW}[!] Thao tác đã bị hủy bởi người dùng (Ctrl+C).{Color.RESET}\n")
        sys.exit(0)

