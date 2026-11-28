"""Coordinate local, remote and batch report extraction."""

import os
import queue
import re
import shutil
import sys
import tempfile
import threading

from .console_style import Color
from .extract_basic import extract_chassis_vpd, extract_fw, extract_vpd
from .extract_chassis_5u import check_is_chassis_5u_dell, extract_chassis_5u_dell_logs
from .extract_juno import extract_chassis_4u_logs
from .extract_p61070 import (
    P61070_CLI_REPORT_NAME,
    P61070_RAW_REPORT_NAME,
    check_is_p61070,
    extract_p61070_logs,
)
from .extract_s1h41 import (
    S1H41_CLI_REPORT_NAME,
    S1H41_RAW_REPORT_NAME,
    check_is_s1h41,
    extract_s1h41_logs,
)
from .extract_s1h42 import (
    S1H42_CLI_REPORT_NAME,
    S1H42_RAW_REPORT_NAME,
    check_is_s1h42,
    extract_s1h42_logs,
)
from .extract_s1h44 import (
    S1H44_CLI_REPORT_NAME,
    S1H44_RAW_REPORT_NAME,
    check_is_s1h44,
    extract_s1h44_logs,
)
from .extract_s1h47 import (
    S1H47_CLI_REPORT_NAME,
    S1H47_RAW_REPORT_NAME,
    check_is_s1h47,
    extract_s1h47_logs,
)
from .extract_s1h48 import (
    S1H48_CLI_REPORT_NAME,
    S1H48_RAW_REPORT_NAME,
    check_is_s1h48,
    extract_s1h48_logs,
)
from .extract_s3t80 import (
    S3T80_CLI_REPORT_NAME,
    S3T80_RAW_REPORT_NAME,
    check_is_s3t80,
    extract_s3t80_logs,
)
from .extract_psu import check_is_psu, detect_psu_model_info, extract_psu_logs
from .extract_rpc73 import check_is_iom_rpc73, detect_rpc73_controller_from_vpd, extract_iom_rpc73
from .log_io import (
    clean_log_lines,
    find_step_dir,
    find_test_results_dir,
    from_long_path,
    get_default_downloads_dir,
    get_default_reports_dir,
    get_log_package_pn,
    get_log_unit_root,
    prepare_log_input_source,
    resolve_output_paths,
    strip_archive_ext,
    to_long_path,
    write_extracted_file,
)
from .reporting import (
    analyze_test_failures,
    export_cycle_time_summary_csv,
    extract_cycle_time_metadata,
    validate_extracted_reports,
)


_PRINT_LOCK = threading.Lock()


def determine_controller(folder_name, target_sn):
    """
    Determine whether target_sn corresponds to ctrla or ctrlb
    based on serial numbers found in folder name.
    """
    sn_matches = re.findall(r'S[AG]F[A-Z0-9]+', folder_name)
    if target_sn in sn_matches:
        idx = sn_matches.index(target_sn)
        return 'ctrla' if idx == 0 else 'ctrlb'

    sn_matches = re.findall(r'[A-Z0-9]{14,}', folder_name)
    if target_sn in sn_matches:
        idx = sn_matches.index(target_sn)
        return 'ctrla' if idx == 0 else 'ctrlb'

    raise ValueError(f"Target SN '{target_sn}' not found in folder name '{folder_name}' to determine controller.")


def process_single_extraction(input_dir_raw, target_sn_raw, output_base_raw, quiet=False, diagnose=False):
    """
    Core extraction function for a single unit (supports both directories and .zip/.tar.gz archives).
    Returns a comprehensive result dict including Cycle Time metadata and sanity validation warnings.
    """
    target_sn = target_sn_raw.strip(' "\' \t\r\n')
    logs_buffer = []

    def log_print(msg):
        if quiet:
            logs_buffer.append(msg)
        else:
            with _PRINT_LOCK:
                print(msg)

    with prepare_log_input_source(input_dir_raw) as (working_input_dir, logical_unit_root, folder_name):
        if not output_base_raw:
            output_base_raw = get_default_reports_dir()

        test_results_dir = find_test_results_dir(working_input_dir)
        actual_working_root = get_log_unit_root(working_input_dir)
        cycle_meta = extract_cycle_time_metadata(actual_working_root, test_results_dir, folder_name)

        is_chassis_4u = target_sn.startswith("FVB")
        part_number = cycle_meta['part_number'].strip().upper()
        is_chassis_s1h41 = check_is_s1h41(folder_name, part_number)
        is_chassis_s1h42 = check_is_s1h42(folder_name, part_number)
        is_chassis_s1h44 = check_is_s1h44(folder_name, part_number)
        is_chassis_s1h47 = check_is_s1h47(folder_name, part_number)
        is_chassis_s1h48 = check_is_s1h48(folder_name, part_number)
        is_chassis_s3t80 = check_is_s3t80(folder_name, part_number)
        is_chassis_5u_dell = not is_chassis_s1h41 and not is_chassis_s1h42 and not is_chassis_s1h44 and not is_chassis_s1h47 and not is_chassis_s1h48 and not is_chassis_s3t80 and (part_number == "7PNTN" or (
            (target_sn.startswith("SGF") or "W47DG" in folder_name or "5U_Dell" in folder_name or "5U84" in folder_name)
            and check_is_chassis_5u_dell(test_results_dir, folder_name, part_number)
        ))
        is_chassis_2u = not is_chassis_s1h41 and not is_chassis_s1h42 and not is_chassis_s1h44 and not is_chassis_s1h47 and not is_chassis_s1h48 and not is_chassis_s3t80 and target_sn.startswith("SGF") and not is_chassis_5u_dell
        is_chassis = is_chassis_2u or is_chassis_4u or is_chassis_5u_dell or is_chassis_s1h41 or is_chassis_s1h42 or is_chassis_s1h44 or is_chassis_s1h47 or is_chassis_s1h48 or is_chassis_s3t80

        unit_type = "-"
        controller = "-"
        saved_paths = []
        out_dir = "-"

        if is_chassis_4u:
            unit_type = "Chassis 4U"
            log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS 4U]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}Chassis 4U (Juno){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")
            out_dir, saved_paths = extract_chassis_4u_logs(working_input_dir, target_sn, output_base_raw)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã tạo {len(saved_paths)} file báo cáo Chassis 4U tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {out_dir}{Color.RESET}")

        elif is_chassis_5u_dell:
            unit_type = "Chassis 5U"
            pn_label = "7PNTN" if part_number == "7PNTN" else "W47DG"
            log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS 5U DELL]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}Chassis 5U Dell ({pn_label}){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")
            out_dir, saved_paths = extract_chassis_5u_dell_logs(working_input_dir, target_sn, output_base_raw, part_number=part_number)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã tạo {len(saved_paths)} file báo cáo Chassis 5U Dell tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {out_dir}{Color.RESET}")

        elif is_chassis_s1h41:
            cli_lines, raw_lines = extract_s1h41_logs(test_results_dir, target_sn)
            out_dir, _ = resolve_output_paths(output_base_raw, target_sn, is_chassis=False, unit_root=logical_unit_root)
            unit_type = "Chas S1H41"
            controller = "-"
            log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS HPE MSA S1H41-62001]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}Chas S1H41 (MSA 2070 FC LFF){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

            fw_out_path = os.path.join(out_dir, S1H41_CLI_REPORT_NAME)
            write_extracted_file(fw_out_path, cli_lines, trim_last_newline=True)
            saved_paths.append(fw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S1H41_CLI_REPORT_NAME} ({len(cli_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_out_path}{Color.RESET}")

            raw_out_path = os.path.join(out_dir, S1H41_RAW_REPORT_NAME)
            write_extracted_file(raw_out_path, raw_lines, trim_last_newline=True)
            saved_paths.append(raw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S1H41_RAW_REPORT_NAME} ({len(raw_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {raw_out_path}{Color.RESET}")

        elif is_chassis_s3t80:
            cli_lines, raw_lines = extract_s3t80_logs(test_results_dir, target_sn)
            out_dir, _ = resolve_output_paths(output_base_raw, target_sn, is_chassis=False, unit_root=logical_unit_root)
            unit_type = "Chas S3T80"
            controller = "-"
            log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS HPE MSA S3T80-62001]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}Chas S3T80 (MSA 2070 32Gb FC SFF){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

            fw_out_path = os.path.join(out_dir, S3T80_CLI_REPORT_NAME)
            write_extracted_file(fw_out_path, cli_lines, trim_last_newline=True)
            saved_paths.append(fw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S3T80_CLI_REPORT_NAME} ({len(cli_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_out_path}{Color.RESET}")

            raw_out_path = os.path.join(out_dir, S3T80_RAW_REPORT_NAME)
            write_extracted_file(raw_out_path, raw_lines, trim_last_newline=True)
            saved_paths.append(raw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S3T80_RAW_REPORT_NAME} ({len(raw_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {raw_out_path}{Color.RESET}")

        elif is_chassis_s1h42:
            cli_lines, raw_lines = extract_s1h42_logs(test_results_dir, target_sn)
            out_dir, _ = resolve_output_paths(output_base_raw, target_sn, is_chassis=False, unit_root=logical_unit_root)
            unit_type = "Chas S1H42"
            controller = "-"
            log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS HPE MSA S1H42-62001]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}Chas S1H42 (MSA 2070 16Gb FC SFF){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

            fw_out_path = os.path.join(out_dir, S1H42_CLI_REPORT_NAME)
            write_extracted_file(fw_out_path, cli_lines, trim_last_newline=True)
            saved_paths.append(fw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S1H42_CLI_REPORT_NAME} ({len(cli_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_out_path}{Color.RESET}")

            raw_out_path = os.path.join(out_dir, S1H42_RAW_REPORT_NAME)
            write_extracted_file(raw_out_path, raw_lines, trim_last_newline=True)
            saved_paths.append(raw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S1H42_RAW_REPORT_NAME} ({len(raw_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {raw_out_path}{Color.RESET}")

        elif is_chassis_s1h44:
            cli_lines, raw_lines = extract_s1h44_logs(test_results_dir, target_sn)
            out_dir, _ = resolve_output_paths(output_base_raw, target_sn, is_chassis=False, unit_root=logical_unit_root)
            unit_type = "Chas S1H44"
            controller = "-"
            log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS HPE MSA S1H44-62001]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}Chas S1H44 (MSA 2070 10/25GbE iSCSI SFF){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

            fw_out_path = os.path.join(out_dir, S1H44_CLI_REPORT_NAME)
            write_extracted_file(fw_out_path, cli_lines, trim_last_newline=True)
            saved_paths.append(fw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S1H44_CLI_REPORT_NAME} ({len(cli_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_out_path}{Color.RESET}")

            raw_out_path = os.path.join(out_dir, S1H44_RAW_REPORT_NAME)
            write_extracted_file(raw_out_path, raw_lines, trim_last_newline=True)
            saved_paths.append(raw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S1H44_RAW_REPORT_NAME} ({len(raw_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {raw_out_path}{Color.RESET}")

        elif is_chassis_s1h47:
            cli_lines, raw_lines = extract_s1h47_logs(test_results_dir, target_sn)
            out_dir, _ = resolve_output_paths(output_base_raw, target_sn, is_chassis=False, unit_root=logical_unit_root)
            unit_type = "Chas S1H47"
            controller = "-"
            log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS HPE MSA S1H47-62001]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}Chas S1H47 (MSA 2070 12Gb SAS LFF){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

            fw_out_path = os.path.join(out_dir, S1H47_CLI_REPORT_NAME)
            write_extracted_file(fw_out_path, cli_lines, trim_last_newline=True)
            saved_paths.append(fw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S1H47_CLI_REPORT_NAME} ({len(cli_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_out_path}{Color.RESET}")

            raw_out_path = os.path.join(out_dir, S1H47_RAW_REPORT_NAME)
            write_extracted_file(raw_out_path, raw_lines, trim_last_newline=True)
            saved_paths.append(raw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S1H47_RAW_REPORT_NAME} ({len(raw_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {raw_out_path}{Color.RESET}")

        elif is_chassis_s1h48:
            cli_lines, raw_lines = extract_s1h48_logs(test_results_dir, target_sn)
            out_dir, _ = resolve_output_paths(output_base_raw, target_sn, is_chassis=False, unit_root=logical_unit_root)
            unit_type = "Chas S1H48"
            controller = "-"
            log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS HPE MSA S1H48-62001]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}Chas S1H48 (MSA 2070 12Gb SAS SFF){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

            fw_out_path = os.path.join(out_dir, S1H48_CLI_REPORT_NAME)
            write_extracted_file(fw_out_path, cli_lines, trim_last_newline=True)
            saved_paths.append(fw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S1H48_CLI_REPORT_NAME} ({len(cli_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_out_path}{Color.RESET}")

            raw_out_path = os.path.join(out_dir, S1H48_RAW_REPORT_NAME)
            write_extracted_file(raw_out_path, raw_lines, trim_last_newline=True)
            saved_paths.append(raw_out_path)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {S1H48_RAW_REPORT_NAME} ({len(raw_lines)} dòng) tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {raw_out_path}{Color.RESET}")

        else:
            out_dir, chassis_file_path = resolve_output_paths(output_base_raw, target_sn, is_chassis, unit_root=logical_unit_root)

            if is_chassis_2u:
                unit_type = "Chassis"
                log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS 2U]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}Chassis (SGF){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")
                vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
                vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
                log_print(f"{Color.BLUE}📂 Log nguồn:{Color.RESET} {Color.GRAY}{vpd_log_path}{Color.RESET}")

                clean_lines = clean_log_lines(vpd_log_path)
                extracted_lines = extract_chassis_vpd(clean_lines)

                write_extracted_file(chassis_file_path, extracted_lines, trim_last_newline=True)
                saved_paths.append(chassis_file_path)
                log_print(f"{Color.BRIGHT_GREEN}✔ Đã tạo file báo cáo Chassis ({len(extracted_lines)} dòng) tại:{Color.RESET}")
                log_print(f"  {Color.BOLD}{Color.WHITE}➜ {chassis_file_path}{Color.RESET}")
            else:
                is_p61070 = check_is_p61070(folder_name, part_number)
                is_psu = not is_p61070 and (target_sn.startswith("PM") or "DYJW5" in folder_name or "0R4C4" in folder_name or check_is_psu(test_results_dir, folder_name))
                is_rpc73 = not is_p61070 and check_is_iom_rpc73(test_results_dir)

                if is_p61070:
                    cli_lines, raw_lines, controller = extract_p61070_logs(test_results_dir, target_sn)
                    unit_type = "IO P61070"
                    log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ HPE MSA P61070-001]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}IO P61070 (MSA 2070 FC){Color.RESET} │ Controller: {Color.YELLOW}{controller}{Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

                    fw_out_path = os.path.join(out_dir, P61070_CLI_REPORT_NAME)
                    write_extracted_file(fw_out_path, cli_lines, trim_last_newline=True)
                    saved_paths.append(fw_out_path)
                    log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {P61070_CLI_REPORT_NAME} ({len(cli_lines)} dòng) tại:{Color.RESET}")
                    log_print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_out_path}{Color.RESET}")

                    raw_out_path = os.path.join(out_dir, P61070_RAW_REPORT_NAME)
                    write_extracted_file(raw_out_path, raw_lines, trim_last_newline=True)
                    saved_paths.append(raw_out_path)
                    log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {P61070_RAW_REPORT_NAME} ({len(raw_lines)} dòng) tại:{Color.RESET}")
                    log_print(f"  {Color.BOLD}{Color.WHITE}➜ {raw_out_path}{Color.RESET}")
                elif is_psu:
                    psu_short, psu_full = detect_psu_model_info(test_results_dir, folder_name)
                    out_lines, unit_id = extract_psu_logs(test_results_dir, target_sn)
                    unit_type = psu_short
                    controller = unit_id
                    pcm_name = "PCM 1" if unit_id == "psu0" else "PCM 2"
                    log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ {psu_short.upper()}]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}{psu_full}{Color.RESET} │ Unit: {Color.YELLOW}{unit_id} ({pcm_name}){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

                    psu_report_name = "Controller FW, Drive FW, Serial Number Tracking & Test History.txt"
                    psu_out_path = os.path.join(out_dir, psu_report_name)
                    write_extracted_file(psu_out_path, out_lines, trim_last_newline=True)
                    saved_paths.append(psu_out_path)
                    log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {psu_report_name} ({len(out_lines)} dòng) tại:{Color.RESET}")
                    log_print(f"  {Color.BOLD}{Color.WHITE}➜ {psu_out_path}{Color.RESET}")
                elif is_rpc73:
                    vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
                    vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
                    detected_ctrl = detect_rpc73_controller_from_vpd(clean_log_lines(vpd_log_path), target_sn)
                    controller = detected_ctrl if detected_ctrl else determine_controller(folder_name, target_sn)
                    if package_pn := get_log_package_pn(folder_name):
                        part_number = package_pn
                        cycle_meta["part_number"] = package_pn
                    unit_type = f"IOM {part_number}" if part_number not in ("", "-") else "IOM"

                    log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ {unit_type}]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}{unit_type}{Color.RESET} │ Controller: {Color.YELLOW}{controller}{Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

                    rpc73_lines = extract_iom_rpc73(test_results_dir, target_sn, controller, part_number=part_number)
                    fw_vpd_out_path = os.path.join(out_dir, "FW_VPD.txt")
                    # New validation layouts include a CRLF after the final separator.
                    write_extracted_file(fw_vpd_out_path, rpc73_lines, trim_last_newline=not rpc73_lines[-1].startswith('|4021|'))
                    saved_paths.append(fw_vpd_out_path)
                    log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu FW_VPD.txt ({len(rpc73_lines)} dòng) tại:{Color.RESET}")
                    log_print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_vpd_out_path}{Color.RESET}")
                else:
                    controller = determine_controller(folder_name, target_sn)
                    unit_type = "IO"
                    log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ IO]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}IO (SAF){Color.RESET} │ Controller: {Color.YELLOW}{controller}{Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

                    fw_step_dir = find_step_dir(test_results_dir, "check_and_load_fw_test")
                    fw_log_path = os.path.join(fw_step_dir, "debug.log")
                    log_print(f"{Color.BLUE}📂 [FW Log]:{Color.RESET} {Color.GRAY}{fw_log_path}{Color.RESET}")
                    fw_clean_lines = clean_log_lines(fw_log_path)
                    fw_extracted = extract_fw(fw_clean_lines, controller)

                    fw_out_path = os.path.join(out_dir, "FW.txt")
                    write_extracted_file(fw_out_path, fw_extracted, trim_last_newline=True)
                    saved_paths.append(fw_out_path)
                    log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu FW.txt ({len(fw_extracted)} dòng) tại:{Color.RESET}")
                    log_print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_out_path}{Color.RESET}")

                    vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
                    vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
                    log_print(f"{Color.BLUE}📂 [VPD Log]:{Color.RESET} {Color.GRAY}{vpd_log_path}{Color.RESET}")
                    vpd_clean_lines = clean_log_lines(vpd_log_path)
                    vpd_extracted = extract_vpd(vpd_clean_lines, controller)

                    vpd_out_path = os.path.join(out_dir, "VPD.txt")
                    write_extracted_file(vpd_out_path, vpd_extracted, trim_last_newline=True)
                    saved_paths.append(vpd_out_path)
                    log_print(f"{Color.BRIGHT_GREEN}✔ Đã lưu VPD.txt ({len(vpd_extracted)} dòng) tại:{Color.RESET}")
                    log_print(f"  {Color.BOLD}{Color.WHITE}➜ {vpd_out_path}{Color.RESET}")

        # Sanity & Completeness Validation
        is_valid, warnings = validate_extracted_reports(unit_type, saved_paths)
        if warnings:
            log_print(f"{Color.BRIGHT_YELLOW}⚠ Phát hiện {len(warnings)} cảnh báo Mismatch / Toàn vẹn trong báo cáo:{Color.RESET}")
            for w in warnings[:5]:
                log_print(f"  {Color.YELLOW}• {w}{Color.RESET}")

        # Failure Root-Cause Analyzer
        diag_lines = analyze_test_failures(actual_working_root, test_results_dir, out_dir=out_dir, warnings=warnings, force_write=diagnose)
        if diag_lines and (warnings or cycle_meta["test_status"] == "FAIL" or diagnose):
            log_print(f"{Color.YELLOW}📋 Đã lưu tóm tắt chẩn đoán tại: {os.path.join(out_dir, 'ERROR_SUMMARY.txt')}{Color.RESET}")

        return {
            "sn": target_sn,
            "unit_type": unit_type,
            "controller": controller,
            "status": "SUCCESS",
            "error": "; ".join(warnings) if warnings else None,
            "warnings": warnings,
            "out_dir": out_dir,
            "paths": saved_paths,
            "cycle_time": cycle_meta.get("cycle_time_short", "N/A"),
            "metadata": cycle_meta,
            "cycle_meta": cycle_meta
        }


def detect_sns_from_folder(folder_path):
    """
    Extract Serial Numbers (SAF..., SGF..., FVB..., or PM...) found in input folder or archive name.
    """
    raw_name = os.path.basename(folder_path.rstrip('\\/'))
    folder_name = strip_archive_ext(raw_name)
    matches = re.findall(r'S[AG]F[A-Z0-9]+', folder_name)
    if not matches:
        matches = re.findall(r'FVB[A-Z0-9]{6,12}', folder_name)
    if not matches:
        matches = re.findall(r'PM[A-Z0-9]{10,}', folder_name)
    if not matches:
        matches = re.findall(r'[A-Z0-9]{14,}', folder_name)
    pkg_pn = get_log_package_pn(folder_name)
    if not matches and pkg_pn in ("P61070-001", "S1H41-62001", "S1H42-62001", "S1H44-62001", "S1H47-62001", "S1H48-62001", "S3T80-62001"):
        m_after = re.search(r'_' + re.escape(pkg_pn) + r'_(.+)$', folder_name, re.IGNORECASE)
        if m_after:
            tail = re.sub(r'_\d{8}-\d{6}.*$', '', m_after.group(1))
            for tok in tail.split('_'):
                tok_up = tok.strip().upper()
                if re.fullmatch(r'(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{8,14}', tok_up):
                    matches.append(tok_up)

    unique_sns = []
    for sn in matches:
        if sn not in unique_sns:
            unique_sns.append(sn)
    return unique_sns


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
    *,
    read_input,
    show_summary,
):
    """
    Connect directly or via Indirect Bridge (172.21.168.241 -> 172.19.*.*) to a remote test station,
    search for logs matching raw_sn (supports multiple comma-separated SNs), perform Selective Fast Fetch
    into a temporary directory, extract reports into <App_Dir>/reports/<Target_SN>/, and clean up.
    Supports reusing an existing ssh_service and --list-only mode.
    """
    from pathlib import Path
    from module import config as m_config
    from module.bridge import build_bridge_settings, should_use_bridge
    from module.ip_utils import expand_ip, get_station_line_info
    from module.log_finder import (
        filter_entries,
        format_entries_table_colored,
        parse_selection,
        parse_sn_list,
    )
    from module.remote_fetcher import SshLogService
    from module.smart_actions import RecentHistoryManager, export_retry_csv

    host = expand_ip(raw_ip, ip_prefix=m_config.DEFAULT_IP_PREFIX)
    station_info = get_station_line_info(host, ip_prefix=m_config.DEFAULT_IP_PREFIX)
    station_tag = f" [{station_info['line']} • .{station_info['octet']}]" if station_info else ""
    sn_list = parse_sn_list(raw_sn)
    if not sn_list:
        raise ValueError("Danh sách Serial Number (SN) trống.")

    output_base = output_base_raw if output_base_raw else get_default_reports_dir()
    port = int(ssh_port) if ssh_port else m_config.DEFAULT_SSH_PORT

    bridge_settings = build_bridge_settings(
        mode=connection_mode,
        transport=bridge_transport,
        host=bridge_host,
        username=bridge_user,
        password=bridge_password,
    )

    will_use_bridge = should_use_bridge(host, port, bridge_settings)
    route_desc = (
        f"Gián tiếp qua Bridge {bridge_settings.host} ({bridge_settings.transport})"
        if will_use_bridge
        else "Trực tiếp (Direct)"
    )

    print(f"\n{Color.BRIGHT_CYAN}🌐 [KẾT NỐI TRẠM TEST TỪ XA]{Color.RESET}")
    print(f"   ├─ {Color.GRAY}Máy đích (Target IP) :{Color.RESET} {Color.BOLD}{Color.WHITE}{host}:{port}{Color.RESET}{Color.BRIGHT_GREEN}{station_tag}{Color.RESET} (nhập: {raw_ip})")
    print(f"   ├─ {Color.GRAY}Phương thức kết nối  :{Color.RESET} {Color.BRIGHT_YELLOW}{route_desc}{Color.RESET}")
    print(f"   ├─ {Color.GRAY}Serial Number cần tìm:{Color.RESET} {Color.BOLD}{Color.CYAN}{', '.join(sn_list)}{Color.RESET}")
    print(f"   └─ {Color.GRAY}Thư mục lưu báo cáo  :{Color.RESET} {Color.WHITE}{output_base}{Color.RESET}")

    owns_service = ssh_service is None
    service = ssh_service or SshLogService(
        host=host,
        username=ssh_user,
        password=ssh_password,
        port=port,
        timeout=m_config.SSH_CONNECT_TIMEOUT_SEC,
        bridge_settings=bridge_settings,
        show_progress=not (not sys.stdout.isatty()),
    )

    all_results = []
    try:
        if owns_service or not getattr(service, "is_connected", False):
            print(f"\n   {Color.YELLOW}⏳ Đang thiết lập phiên SSH tới {host}...{Color.RESET}")
            service.connect()
            print(
                f"   {Color.BRIGHT_GREEN}✔ Đã kết nối thành công!{Color.RESET} "
                f"(OS: {Color.BOLD}{service.remote_os.upper()}{Color.RESET} │ User: {Color.CYAN}{service.username}{Color.RESET})"
            )
        else:
            print(
                f"\n   {Color.BRIGHT_GREEN}⚡ Tái sử dụng phiên SSH đang mở tới {host}!{Color.RESET} "
                f"(OS: {Color.BOLD}{service.remote_os.upper()}{Color.RESET} │ User: {Color.CYAN}{service.username}{Color.RESET})"
            )

        for sn_idx, sn_query in enumerate(sn_list, 1):
            print(f"\n{Color.BRIGHT_CYAN}🔎 [{sn_idx}/{len(sn_list)}] Đang tìm log cho SN '{sn_query}' trên {host}...{Color.RESET}")
            entries, found_in_path = service.find_matching_entries(remote_path, sn_query)
            filtered = filter_entries(entries, max_days=max_days, latest_n=latest_n)

            if not filtered:
                msg = f"Không tìm thấy log nào khớp với '{sn_query}' trên {host} (đã quét {found_in_path})"
                print(f"   {Color.RED}✖ {msg}{Color.RESET}")
                all_results.append({
                    "sn": sn_query,
                    "source_target": host,
                    "output_base": output_base,
                    "unit_type": "-",
                    "controller": "-",
                    "status": "FAIL",
                    "error": msg,
                    "out_dir": "-",
                    "cycle_time": "N/A",
                    "metadata": {},
                    "warnings": [],
                })
                continue

            print(f"   {Color.GREEN}✔ Tìm thấy {len(filtered)} bộ log tại {found_in_path}:{Color.RESET}")
            for line in format_entries_table_colored(filtered).splitlines():
                print(f"   {line}")

            if list_only:
                all_results.append({
                    "sn": sn_query,
                    "source_target": host,
                    "output_base": output_base,
                    "unit_type": "LIST-ONLY",
                    "controller": f"{len(filtered)} gói",
                    "status": "SUCCESS",
                    "error": "",
                    "out_dir": found_in_path,
                    "cycle_time": filtered[0].end_time_str,
                    "metadata": {"test_result": filtered[0].test_result},
                    "warnings": [],
                })
                continue

            if latest_n is not None or len(filtered) == 1 or not interactive or not sys.stdin.isatty():
                selected_entries = filtered if latest_n is not None else [filtered[0]]
                if len(filtered) > 1 and latest_n is None:
                    print(f"   {Color.BRIGHT_YELLOW}⚡ Tự động chọn bộ log mới nhất: {selected_entries[0].name}{Color.RESET}")
            else:
                sel_prompt = (
                    f"\n   {Color.CYAN}👉 Chọn STT cần trích xuất (VD: 1, 1-3), 'P' (chỉ PASS), 'F' (chỉ FAIL), "
                    f"'L' (mới nhất), 'A' (tất cả); Enter = [1] mới nhất: {Color.RESET}"
                )
                while True:
                    raw_sel = read_input(sel_prompt, default="1") or "1"
                    selected_entries = parse_selection(raw_sel, filtered)
                    if selected_entries:
                        break
                    print(f"   {Color.YELLOW}⚠ Không có gói log nào khớp lựa chọn '{raw_sel.strip()}'. Vui lòng chọn lại.{Color.RESET}")

            keep_dir = (Path(get_default_downloads_dir()) / host) if keep_raw_zip else None

            for entry_i, entry in enumerate(selected_entries):
                fetch_mode_str = "Full Archive (--keep-raw-zip)" if keep_raw_zip else "Selective Fast Fetch (chỉ tải file phân tích)"
                print(f"\n   {Color.BRIGHT_CYAN}⬇ Đang tải log '{entry.name}' [{fetch_mode_str}]...{Color.RESET}")
                tmp_dir = tempfile.mkdtemp(prefix="ja_mfg_remote_")
                try:
                    local_log_path, saved_raw_path = service.fetch_selective_log_to_temp(
                        entry,
                        Path(tmp_dir),
                        keep_raw_zip_dir=keep_dir,
                    )
                    if saved_raw_path is not None:
                        print(f"   {Color.GREEN}💾 Đã lưu bản .zip gốc tại: {saved_raw_path}{Color.RESET}")

                    detected_sns = detect_sns_from_folder(entry.name)
                    target_sns_to_run = []
                    q_up = sn_query.upper()
                    for d_sn in detected_sns:
                        if q_up == d_sn.upper() or q_up in d_sn.upper():
                            target_sns_to_run.append(d_sn)
                    if not target_sns_to_run:
                        if detected_sns and len(detected_sns) == 1:
                            target_sns_to_run = [detected_sns[0]]
                        elif detected_sns and not q_up.startswith(("SAF", "SGF", "FVB", "PM")):
                            target_sns_to_run = list(detected_sns)
                        else:
                            target_sns_to_run = [sn_query.upper()]

                    # If multiple entries were selected for the same SN, append timestamp tag to older runs
                    ts_match = re.search(r"(\d{8}-\d{6})", entry.name)
                    ts_suffix = f"_{ts_match.group(1)}" if (len(selected_entries) > 1 and entry_i > 0 and ts_match) else (
                        f"_run{entry_i + 1}" if (len(selected_entries) > 1 and entry_i > 0) else ""
                    )

                    for t_sn in target_sns_to_run:
                        if ts_suffix:
                            eff_out_base = os.path.join(output_base, f"{t_sn}{ts_suffix}")
                        else:
                            eff_out_base = output_base
                        try:
                            res = process_single_extraction(
                                str(local_log_path),
                                t_sn,
                                eff_out_base,
                                quiet=False,
                                diagnose=diagnose,
                            )
                            res["source_target"] = host
                            res["output_base"] = output_base
                            all_results.append(res)
                        except Exception as exc:
                            print(f"   {Color.RED}✖ Lỗi khi trích xuất '{entry.name}' (SN {t_sn}): {exc}{Color.RESET}")
                            all_results.append({
                                "sn": t_sn,
                                "source_target": host,
                                "output_base": output_base,
                                "unit_type": "-",
                                "controller": "-",
                                "status": "FAIL",
                                "error": str(exc),
                                "out_dir": "-",
                                "cycle_time": "N/A",
                                "metadata": {},
                                "warnings": [],
                            })
                finally:
                    shutil.rmtree(to_long_path(tmp_dir), ignore_errors=True)
    finally:
        if owns_service:
            service.disconnect()

    if not list_only:
        try:
            max_hist = int(m_config.LOCAL_SETTINGS.get("ui", {}).get("max_recent_history", 5))
            hist_mgr = RecentHistoryManager(m_config.HISTORY_FILE, max_items=max_hist)
            first_valid_out = next((r.get("out_dir") for r in all_results if r.get("out_dir") and r.get("out_dir") != "-"), output_base)
            hist_mgr.record_session([host], sn_list, last_target_path=first_valid_out)
        except Exception:
            pass

    if export_csv and all_results and not list_only:
        show_summary(all_results)
        csv_target = custom_csv_path if custom_csv_path else os.path.join(output_base, "Cycle_Time_Summary.csv")
        export_cycle_time_summary_csv(all_results, csv_target)
        retry_path = export_retry_csv(all_results, output_base)
        if retry_path:
            print(f"   {Color.YELLOW}📋 Đã xuất danh sách lỗi để chạy lại tại: {from_long_path(str(retry_path))}{Color.RESET}")

    return all_results


def is_remote_ip_target(raw_value):
    """
    Check if raw_value represents a remote test station IP / shorthand (e.g. '116.174', '116182', '172.19.116.174')
    rather than a local directory or archive path.
    """
    if not raw_value:
        return False
    cleaned = raw_value.strip(' "\' \t\r\n')
    if not cleaned or os.path.exists(to_long_path(cleaned)):
        return False
    if any(ch in cleaned for ch in ("\\", "/", ":")):
        return False
    try:
        from module import config as m_config
        from module.ip_utils import expand_ip
        expand_ip(cleaned, ip_prefix=m_config.DEFAULT_IP_PREFIX)
        return True
    except Exception:
        return False


def run_batch_extraction(
    batch_items, max_workers=4, export_csv=True, diagnose=False, *, extract_remote, show_summary
):
    """
    Run extraction over a list of batch items (supports both Remote IP+SN items and Local Folder/Archive items).
    Includes per-host SSH session reuse + Fail-Fast for unreachable remote hosts + retry_failed.csv export.
    """
    from module import config as m_config
    from module.bridge import build_bridge_settings
    from module.ip_utils import expand_ip
    from module.remote_fetcher import SshLogService
    from module.smart_actions import export_retry_csv

    total = len(batch_items)
    if total == 0:
        print(f"\n{Color.YELLOW}⚠ Danh sách trích xuất trống.{Color.RESET}")
        return []

    effective_workers = min(max(1, int(max_workers or 1)), total)
    mode_tag = f"Đa luồng ({effective_workers} workers)" if effective_workers > 1 else "Tuần tự (1 worker)"
    print(f"\n{Color.BRIGHT_YELLOW}🚀 Bắt đầu trích xuất hàng loạt ({total} mục - {mode_tag})...{Color.RESET}")
    print(f"{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")

    indexed_results = [None] * total
    host_locks = {}
    host_services = {}
    failed_hosts = {}
    host_cache_lock = threading.Lock()

    def _get_host_lock(host_ip):
        with host_cache_lock:
            if host_ip not in host_locks:
                host_locks[host_ip] = threading.Lock()
            return host_locks[host_ip]

    def _worker_task(idx, item):
        log_path, target_sn, output_base = item
        if not output_base:
            output_base = get_default_reports_dir()

        if is_remote_ip_target(log_path):
            if not target_sn:
                with _PRINT_LOCK:
                    print(f"\n{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} {Color.RED}✖ Thiếu Serial Number cho trạm test IP: {log_path}{Color.RESET}")
                return idx, {
                    "sn": "N/A",
                    "source_target": log_path,
                    "output_base": output_base,
                    "unit_type": "-",
                    "controller": "-",
                    "status": "FAIL",
                    "error": "Missing Target SN for remote IP",
                    "out_dir": "-",
                    "cycle_time": "N/A",
                    "metadata": {},
                    "warnings": []
                }
            try:
                host_ip = expand_ip(log_path, ip_prefix=m_config.DEFAULT_IP_PREFIX)
            except Exception as exc:
                return idx, {
                    "sn": target_sn,
                    "source_target": log_path,
                    "output_base": output_base,
                    "unit_type": "-",
                    "controller": "-",
                    "status": "FAIL",
                    "error": str(exc),
                    "out_dir": "-",
                    "cycle_time": "N/A",
                    "metadata": {},
                    "warnings": []
                }

            h_lock = _get_host_lock(host_ip)
            with h_lock:
                if host_ip in failed_hosts:
                    err_msg = f"Fail-Fast (máy {host_ip} không phản hồi): {failed_hosts[host_ip]}"
                    with _PRINT_LOCK:
                        print(f"{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} {Color.RED}⚡ Bỏ qua nhanh ({host_ip} - {target_sn}): {err_msg}{Color.RESET}")
                    return idx, {
                        "sn": target_sn,
                        "source_target": host_ip,
                        "output_base": output_base,
                        "unit_type": "-",
                        "controller": "-",
                        "status": "FAIL",
                        "error": err_msg,
                        "out_dir": "-",
                        "cycle_time": "N/A",
                        "metadata": {},
                        "warnings": []
                    }

                svc = host_services.get(host_ip)
                if svc is None or not getattr(svc, "is_connected", False):
                    bridge_settings = build_bridge_settings()
                    svc = SshLogService(
                        host=host_ip,
                        port=m_config.DEFAULT_SSH_PORT,
                        timeout=m_config.SSH_CONNECT_TIMEOUT_SEC,
                        bridge_settings=bridge_settings,
                        show_progress=False,
                    )
                    try:
                        svc.connect()
                        host_services[host_ip] = svc
                    except Exception as conn_exc:
                        failed_hosts[host_ip] = str(conn_exc)
                        with _PRINT_LOCK:
                            print(f"{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} {Color.RED}✖ Không thể kết nối máy {host_ip} ({target_sn}): {conn_exc}{Color.RESET}")
                        return idx, {
                            "sn": target_sn,
                            "source_target": host_ip,
                            "output_base": output_base,
                            "unit_type": "-",
                            "controller": "-",
                            "status": "FAIL",
                            "error": str(conn_exc),
                            "out_dir": "-",
                            "cycle_time": "N/A",
                            "metadata": {},
                            "warnings": []
                        }

                try:
                    rem_results = extract_remote(
                        raw_ip=host_ip,
                        raw_sn=target_sn,
                        output_base_raw=output_base,
                        latest_n=1,
                        diagnose=diagnose,
                        interactive=False,
                        export_csv=False,
                        ssh_service=svc,
                    )
                    res_item = rem_results[0] if rem_results else {
                        "sn": target_sn,
                        "source_target": host_ip,
                        "output_base": output_base,
                        "unit_type": "-",
                        "controller": "-",
                        "status": "FAIL",
                        "error": "No result returned",
                        "out_dir": "-",
                        "cycle_time": "N/A",
                        "metadata": {},
                        "warnings": []
                    }
                    return idx, res_item
                except Exception as e:
                    with _PRINT_LOCK:
                        print(f"{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} {Color.RED}✖ Lỗi kết nối/trích xuất từ xa ({host_ip} - {target_sn}): {e}{Color.RESET}")
                    return idx, {
                        "sn": target_sn,
                        "source_target": host_ip,
                        "output_base": output_base,
                        "unit_type": "-",
                        "controller": "-",
                        "status": "FAIL",
                        "error": str(e),
                        "out_dir": "-",
                        "cycle_time": "N/A",
                        "metadata": {},
                        "warnings": []
                    }

        if not target_sn:
            sns = detect_sns_from_folder(log_path)
            target_sn = sns[0] if sns else ""

        if not target_sn:
            with _PRINT_LOCK:
                print(f"\n{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} {Color.RED}✖ Không thể nhận diện Target SN cho: {log_path}{Color.RESET}")
            return idx, {
                "sn": "N/A",
                "source_target": log_path,
                "output_base": output_base,
                "unit_type": "-",
                "controller": "-",
                "status": "FAIL",
                "error": "Missing Target SN",
                "out_dir": "-",
                "cycle_time": "N/A",
                "metadata": {},
                "warnings": []
            }

        try:
            use_quiet = effective_workers > 1
            res = process_single_extraction(log_path, target_sn, output_base, quiet=use_quiet, diagnose=diagnose)
            res["source_target"] = log_path
            res["output_base"] = output_base
            with _PRINT_LOCK:
                print(f"{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} {Color.BRIGHT_GREEN}✔ Hoàn tất SN {res['sn']}{Color.RESET} ({res['unit_type']} - {res['controller']}) │ Cycle Time: {Color.BRIGHT_CYAN}{res.get('cycle_time', 'N/A')}{Color.RESET} ➜ {Color.GRAY}{res['out_dir']}{Color.RESET}")
                for w in res.get("warnings", []):
                    print(f"      {Color.YELLOW}⚠ Cảnh báo: {w}{Color.RESET}")
            return idx, res
        except Exception as e:
            with _PRINT_LOCK:
                print(f"{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} {Color.RED}✖ Lỗi khi trích xuất SN {target_sn}: {e}{Color.RESET}")
            return idx, {
                "sn": target_sn,
                "source_target": log_path,
                "output_base": output_base,
                "unit_type": "Chassis 4U" if target_sn.startswith("FVB") else ("Chassis 5U" if ("W47DG" in log_path or "5U_Dell" in log_path or "5U84" in log_path) else ("Chassis" if target_sn.startswith("SGF") else ("PSU" if target_sn.startswith("PM") else ("Chas S1H41" if check_is_s1h41(os.path.basename(log_path.rstrip("\\/"))) else ("Chas S1H42" if check_is_s1h42(os.path.basename(log_path.rstrip("\\/"))) else ("Chas S1H44" if check_is_s1h44(os.path.basename(log_path.rstrip("\\/"))) else ("Chas S1H47" if check_is_s1h47(os.path.basename(log_path.rstrip("\\/"))) else ("Chas S1H48" if check_is_s1h48(os.path.basename(log_path.rstrip("\\/"))) else ("Chas S3T80" if check_is_s3t80(os.path.basename(log_path.rstrip("\\/"))) else ("IO P61070" if check_is_p61070(os.path.basename(log_path.rstrip("\\/"))) else "IO")))))))))),
                "controller": "-",
                "status": "FAIL",
                "error": str(e),
                "out_dir": "-",
                "cycle_time": "N/A",
                "metadata": {},
                "warnings": []
            }

    try:
        if effective_workers == 1:
            for idx, item in enumerate(batch_items, 1):
                print(f"\n{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} Đang xử lý: {Color.GRAY}{item[0]}{Color.RESET}")
                _, res = _worker_task(idx, item)
                indexed_results[idx - 1] = res
        else:
            work_q = queue.Queue()
            for idx, item in enumerate(batch_items, 1):
                work_q.put((idx, item))

            def _thread_runner():
                while True:
                    try:
                        idx, item = work_q.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        r_idx, res = _worker_task(idx, item)
                        indexed_results[r_idx - 1] = res
                    finally:
                        work_q.task_done()

            threads = []
            for _ in range(effective_workers):
                t = threading.Thread(target=_thread_runner, daemon=True)
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
    finally:
        for svc in host_services.values():
            try:
                svc.disconnect()
            except Exception:
                pass

    results = [r for r in indexed_results if r is not None]
    show_summary(results)

    if export_csv and results:
        first_out = next((r.get("out_dir") for r in results if r.get("out_dir") and r.get("out_dir") != "-"), None)
        if first_out:
            csv_dir = os.path.dirname(first_out.rstrip("\\/"))
        else:
            csv_dir = get_default_reports_dir()
        export_cycle_time_summary_csv(results, os.path.join(csv_dir, "Cycle_Time_Summary.csv"))
        retry_path = export_retry_csv(results, csv_dir)
        if retry_path:
            print(f"   {Color.YELLOW}📋 Đã xuất danh sách lỗi để chạy lại tại: {from_long_path(str(retry_path))}{Color.RESET}")

    return results
