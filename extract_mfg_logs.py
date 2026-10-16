import os
import sys
import re
import csv
import json
import argparse
import glob
import tarfile
import zipfile
import shutil
import tempfile
import hashlib
import difflib
import threading
import queue
import subprocess
import contextlib
import ast

APP_NAME = "JA_MFG_Log_Extractor"
APP_TITLE = "CÔNG CỤ TRÍCH XUẤT LOG TỰ ĐỘNG (IO, CHASSIS & PSU UNITS)"
APP_VERSION = "1.6.0"
APP_BUILD = "1"

_PRINT_LOCK = threading.Lock()

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

def to_long_path(path):
    """
    Convert a path to Windows extended-length path (\\\\?\\...) if running on Windows.
    Bypasses the 260-character MAX_PATH limit.
    """
    if sys.platform == 'win32' and path:
        abs_p = os.path.abspath(path)
        if not abs_p.startswith('\\\\?\\') and not abs_p.startswith('\\\\.\\'):
            if abs_p.startswith('\\\\'):
                return '\\\\?\\UNC\\' + abs_p[2:]
            return '\\\\?\\' + abs_p
        return abs_p
    return os.path.abspath(path) if path else path

def from_long_path(path):
    """Strip \\\\?\\ or \\\\?\\UNC\\ prefix if present for clean display to user."""
    if path and isinstance(path, str):
        if path.startswith('\\\\?\\UNC\\'):
            return '\\\\' + path[8:]
        if path.startswith('\\\\?\\'):
            return path[4:]
    return path

def get_script_dir():
    """
    Get absolute directory path where extract_mfg_logs.py (or frozen executable) is located.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))

def get_default_reports_dir():
    """
    Return the centralized reports directory inside the app folder (<App_Dir>/reports).
    """
    rep_dir = os.path.join(get_script_dir(), "reports")
    os.makedirs(to_long_path(rep_dir), exist_ok=True)
    return rep_dir

def get_default_downloads_dir():
    """
    Return the centralized downloads directory inside the app folder (<App_Dir>/downloads).
    """
    dl_dir = os.path.join(get_script_dir(), "downloads")
    os.makedirs(to_long_path(dl_dir), exist_ok=True)
    return dl_dir

def find_step_dir(test_results_dir, pattern):
    """
    Find the directory inside test-results matching pattern.
    If multiple match, pick the one with the highest step number prefix.
    """
    long_tr = to_long_path(test_results_dir)
    if not os.path.exists(long_tr):
        raise FileNotFoundError(f"Directory not found: {from_long_path(test_results_dir)}")

    matching_dirs = []
    for item in os.listdir(long_tr):
        full_path = os.path.join(test_results_dir, item)
        if os.path.isdir(to_long_path(full_path)) and pattern in item:
            match = re.match(r'^(\d+)-', item)
            step_num = int(match.group(1)) if match else 0
            matching_dirs.append((step_num, full_path))

    if not matching_dirs:
        raise FileNotFoundError(f"No test step directory matching '{pattern}' in {from_long_path(test_results_dir)}")

    matching_dirs.sort(key=lambda x: x[0], reverse=True)
    return matching_dirs[0][1]

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

def clean_log_lines(filepath):
    """
    Read debug.log and replace 'YYYY-MM-DD...(|XXXX|)' prefix with '$1'.
    """
    long_p = to_long_path(filepath)
    if not os.path.exists(long_p):
        raise FileNotFoundError(f"Log file not found: {from_long_path(filepath)}")

    with open(long_p, 'r', encoding='utf-8', errors='ignore') as f:
        raw_lines = f.readlines()

    clean_lines = [re.sub(r'^\d{4}-\d{2}-\d{2}.*?(\|\d+\|)', r'\1', l) for l in raw_lines]
    return clean_lines

def extract_fw(clean_lines, controller):
    """
    Extract FW.txt content for controller (ctrla or ctrlb).
    """
    start_marker = f"|0586|Component FW {controller}:rfwd not in enclosure object."
    end_marker = f"|0586|Component FW {controller}:kmip_bundle_version not in enclosure object."

    start_idx = None
    end_idx = None

    for i, line in enumerate(clean_lines):
        if start_marker in line and start_idx is None:
            start_idx = i
        if end_marker in line and start_idx is not None:
            end_idx = i
            break

    if start_idx is None or end_idx is None:
        raise ValueError(f"Could not find start/end FW markers for {controller} in log lines.")

    return clean_lines[start_idx : end_idx + 1]

def extract_vpd(clean_lines, controller):
    """
    Extract VPD.txt content for controller (ctrla or ctrlb).
    Part 1: from '|0180|Sending GEM cmd set_ebodvpd 1...' up to '|3671|vpd_type 13:...'
    Part 2: from '|3887|Checking <ctrl> customer VPD (ID = 49)...' down to the closing separator line.
    """
    b2_marker = f"VPD validation passed for component {controller}"
    b2_idx = None
    for i, l in enumerate(clean_lines):
        if b2_marker in l:
            b2_idx = i
            break

    if b2_idx is None:
        raise ValueError(f"Could not find B2 anchor '{b2_marker}' in VPD log lines.")

    part1_end = None
    for i in range(b2_idx - 1, -1, -1):
        if '|3671|vpd_type 13:' in clean_lines[i]:
            part1_end = i
            break

    if part1_end is None:
        raise ValueError("Could not find Part 1 end line '|3671|vpd_type 13:' in VPD log lines.")

    batt_idx = None
    for i in range(part1_end - 1, -1, -1):
        if '|0250|Battery 2 firmware' in clean_lines[i]:
            batt_idx = i
            break

    if batt_idx is not None:
        part1_start = batt_idx + 1
    else:
        part1_start = None
        for i in range(part1_end - 1, -1, -1):
            if '|0180|Sending GEM cmd set_ebodvpd' in clean_lines[i]:
                part1_start = i

    if part1_start is None:
        raise ValueError("Could not find Part 1 start line in VPD log lines.")

    part1_lines = clean_lines[part1_start : part1_end + 1]

    b4_marker = f"Checking {controller} customer VPD (ID = 49) ..."
    b4_idx = None
    for i in range(b2_idx, len(clean_lines)):
        if b4_marker in clean_lines[i]:
            b4_idx = i
            break

    if b4_idx is None:
        raise ValueError(f"Could not find B4 anchor '{b4_marker}' in VPD log lines.")

    part2_start = b4_idx
    part2_end = None

    for i in range(part2_start, len(clean_lines)):
        if '|3987|result: match' in clean_lines[i] and i + 1 < len(clean_lines):
            if '|4004|-----------------------------------------------------------------------------' in clean_lines[i + 1]:
                window = "".join(clean_lines[max(part2_start, i - 10) : i + 1])
                if 'fru_description' in window or 'FRU Description' in window:
                    part2_end = i + 1
                    break

    if part2_end is None:
        for i in range(part2_start, len(clean_lines)):
            if '|4098|' in clean_lines[i] or 'VPD rendering failed' in clean_lines[i]:
                part2_end = i
                break
    if part2_end is None:
        last_sep = [i for i in range(part2_start, len(clean_lines)) if '|4004|---' in clean_lines[i]]
        if last_sep:
            part2_end = last_sep[-1]

    if part2_end is None:
        raise ValueError("Could not find Part 2 end line for customer VPD in VPD log lines.")

    part2_lines = clean_lines[part2_start : part2_end + 1]

    return part1_lines + ['\n'] + part2_lines

def extract_chassis_vpd(clean_lines):
    """
    Extract Chassis report file (<target_sn>.txt) from vpd_validation step clean log lines.
    """
    step1_matches = [i for i, l in enumerate(clean_lines) if '|0250|Midplane VPD structure' in l and i > 400]
    if not step1_matches:
        step1_matches = [i for i, l in enumerate(clean_lines) if '|0250|Midplane VPD structure' in l]
    if not step1_matches:
        raise ValueError("Could not find '|0250|Midplane VPD structure' in log lines.")
    step1_start = step1_matches[0]
    step1_lines = clean_lines[step1_start : step1_start + 3]

    step2_matches = [i for i, l in enumerate(clean_lines) if 'Midplane Customer A' in l and '|0608|' in l]
    if not step2_matches:
        raise ValueError("Could not find Step 2 marker '|0608|...Midplane Customer A' in log lines.")
    step2_start = step2_matches[0]
    step2_end_matches = [i for i in range(step2_start, len(clean_lines)) if '|0509|00a0:' in clean_lines[i] or 'z.....' in clean_lines[i]]
    if not step2_end_matches:
        raise ValueError("Could not find Step 2 end marker '|0509|00a0:' in log lines.")
    step2_end = step2_end_matches[0]
    step2_lines = clean_lines[step2_start : step2_end + 1]

    step3_matches = [i for i in range(step2_end, len(clean_lines)) if '|0509|0360:' in clean_lines[i]]
    if not step3_matches:
        raise ValueError("Could not find Step 3 marker '|0509|0360:' in log lines.")
    step3_start = step3_matches[0]
    step3_lines = clean_lines[step3_start : step3_start + 2]

    step4_matches = [i for i, l in enumerate(clean_lines) if 'Checking chassis customer VPD' in l]
    if not step4_matches:
        raise ValueError("Could not find Step 4 marker 'Checking chassis customer VPD' in log lines.")
    step4_start = step4_matches[0]
    step4_end = None
    for i in range(step4_start, len(clean_lines)):
        if '|3987|result: match' in clean_lines[i] and i + 1 < len(clean_lines):
            if '|4004|-----------------------------------------------------------------------------' in clean_lines[i + 1]:
                window = "".join(clean_lines[max(step4_start, i - 10) : i + 1])
                if 'fru_description' in window or 'FRU Description' in window:
                    step4_end = i + 1
                    break

    if step4_end is None:
        for i in range(step4_start, len(clean_lines)):
            if '|4098|' in clean_lines[i] or 'VPD rendering failed' in clean_lines[i]:
                step4_end = i
                break
    if step4_end is None:
        last_sep = [i for i in range(step4_start, len(clean_lines)) if '|4004|---' in clean_lines[i]]
        if last_sep:
            step4_end = last_sep[-1]

    if step4_end is None:
        raise ValueError("Could not find Step 4 end line for chassis customer VPD.")

    step4_lines = clean_lines[step4_start : step4_end + 1]

    return step1_lines + ['\n'] + step2_lines + step3_lines + ['\n'] + step4_lines

def extract_chassis_4u_logs(input_dir, target_sn, output_base):
    """
    Extract Chassis 4U (4U Juno) report files:
    FW.txt, GETVPD.txt, VER.txt, VPD.txt, Provisioning State.txt, Restore Default.txt
    """
    abs_input = os.path.abspath(input_dir.strip(' "\' \t\r\n'))
    test_results_dir = find_test_results_dir(abs_input)
    unit_root = os.path.dirname(test_results_dir)
    if os.path.basename(unit_root) == 'latest' or os.path.basename(unit_root).startswith('job-'):
        unit_root = os.path.dirname(unit_root)
    if not output_base:
        output_base = get_default_reports_dir()
    
    clean_base = output_base.strip(' "\' \t\r\n')
    abs_base = os.path.abspath(clean_base)

    if os.path.basename(abs_base.rstrip('\\/')) == target_sn:
        output_dir = abs_base
    else:
        output_dir = os.path.join(abs_base, target_sn)
    
    os.makedirs(to_long_path(output_dir), exist_ok=True)

    saved_paths = []

    # 1. Process FW.txt
    fw_step_dirs = [d for d in os.listdir(to_long_path(test_results_dir)) if 'check_and_load_fw_test' in d and 'test_check_fw_versions' in d]
    if fw_step_dirs:
        fw_debug_log = os.path.join(test_results_dir, fw_step_dirs[0], 'debug.log')
        if os.path.exists(to_long_path(fw_debug_log)):
            with open(to_long_path(fw_debug_log), 'r', encoding='utf-8', errors='ignore') as f:
                raw_lines = f.readlines()

            def clean_4u_log_line(line):
                if '|Received:' in line:
                    line = re.sub(r'^.*?\|Received:\s*', '', line)
                line = re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\|.*?\|\d+\|', '', line)
                line = re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*', '', line)
                return line

            start_idx = None
            for i, l in enumerate(raw_lines):
                if 'Hook post_sequence_hook' in l:
                    start_idx = i
                    break

            end_idx = None
            if start_idx is not None:
                for i in range(start_idx, len(raw_lines)):
                    cl = clean_4u_log_line(raw_lines[i])
                    if re.search(r'exos-.*?:~\$\s*$', cl):
                        end_idx = i
                        break

            if start_idx is not None and end_idx is not None:
                out_lines = []
                for i in range(start_idx, end_idx + 1):
                    if raw_lines[i] == '\n':
                        continue
                    cl = clean_4u_log_line(raw_lines[i])
                    out_lines.append(cl)

                for l in raw_lines:
                    if '|0030|Test Passed' in l:
                        cl = re.sub(r'^\d{4}-\d{2}-\d{2}.*?(\|\d+\|)', r'\1', l)
                        out_lines.append(cl)
                        break

                fw_out_path = os.path.join(output_dir, 'FW.txt')
                write_extracted_file(fw_out_path, out_lines, trim_last_newline=True)
                saved_paths.append(fw_out_path)

    # 2 & 3. Process GETVPD.txt & VER.txt from enc_logs
    enc_dir = os.path.join(unit_root, 'enc_logs')
    log_content = None
    if os.path.exists(to_long_path(enc_dir)):
        extracted_log_path = glob.glob(to_long_path(os.path.join(enc_dir, 'obmcdump_*', 'uut_list_utility_logs.log')))
        if extracted_log_path:
            with open(to_long_path(extracted_log_path[0]), 'r', encoding='utf-8', errors='ignore') as f:
                log_content = f.read()
        else:
            tar_files = glob.glob(to_long_path(os.path.join(enc_dir, '*tar.xz'))) + glob.glob(to_long_path(os.path.join(enc_dir, '*.tar.gz')))
            for tar_path in tar_files:
                try:
                    with tarfile.open(to_long_path(tar_path), 'r:*') as tar:
                        for member in tar.getmembers():
                            if member.name.endswith('uut_list_utility_logs.log'):
                                f = tar.extractfile(member)
                                if f:
                                    log_content = f.read().decode('utf-8', errors='ignore')
                                    break
                except Exception:
                    pass
                if log_content:
                    break

    if log_content:
        blocks = re.split(r'(?=Command identifier:)', log_content)
        folder_name = os.path.basename(unit_root)
        date_match = re.search(r'(\d{4})(\d{2})(\d{2})', folder_name)
        date_str = f'{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}' if date_match else ''

        getvpd_idx = None
        for idx, b in enumerate(blocks):
            if 'Command Executed: getvpd' in b and (not date_str or date_str in b):
                getvpd_idx = idx
                break
        if getvpd_idx is None:
            for idx, b in enumerate(blocks):
                if 'Command Executed: getvpd' in b:
                    getvpd_idx = idx
                    break

        ver_idx = None
        if getvpd_idx is not None:
            getvpd_block = blocks[getvpd_idx]
            lines = [l + '\n' for l in getvpd_block.rstrip('\r\n').splitlines()]
            getvpd_out_path = os.path.join(output_dir, 'GETVPD.txt')
            write_extracted_file(getvpd_out_path, lines, trim_last_newline=True)
            saved_paths.append(getvpd_out_path)

            # Pair ver block with matching timestamp or adjacent block in the same test cycle
            ts_match = re.search(r'Command identifier:\s*gemcli_getvpd_test_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})', getvpd_block)
            if ts_match:
                ts_prefix = ts_match.group(1)
                for idx in range(getvpd_idx + 1, len(blocks)):
                    if 'Command Executed: ver' in blocks[idx] and f'gemcli_ver_test_{ts_prefix}' in blocks[idx]:
                        ver_idx = idx
                        break

            if ver_idx is None:
                for idx in range(getvpd_idx + 1, min(getvpd_idx + 10, len(blocks))):
                    if 'Command Executed: getvpd' in blocks[idx]:
                        break
                    if 'Command Executed: ver' in blocks[idx]:
                        ver_idx = idx
                        break

            if ver_idx is None:
                for b in blocks:
                    if 'Command Executed: ver' in b and 'USM Version' in b and 'Ops Panel Version' in b:
                        ver_block = b
                        break

            if ver_idx is not None:
                ver_block = blocks[ver_idx]
                lines = [l + '\n' for l in ver_block.rstrip('\r\n').splitlines()]
                ver_out_path = os.path.join(output_dir, 'VER.txt')
                write_extracted_file(ver_out_path, lines, trim_last_newline=True)
                saved_paths.append(ver_out_path)

    # Helper function to preserve |XXXX| line-number block while stripping date/thread prefix
    def clean_with_line_block(line):
        m = re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\|.*?\|(\d{4})\|(.*)$', line)
        if m:
            return f'|{m.group(1)}|{m.group(2)}\n'
        return line

    # 4. Process VPD.txt from vpd_validation
    vpd_step_dirs = [d for d in os.listdir(to_long_path(test_results_dir)) if 'vpd_validation' in d and 'test_vpd_validation' in d]
    if not vpd_step_dirs:
        vpd_step_dirs = [d for d in os.listdir(to_long_path(test_results_dir)) if 'vpd_validation' in d]

    if vpd_step_dirs:
        vpd_debug_log = os.path.join(test_results_dir, vpd_step_dirs[0], 'debug.log')
        if os.path.exists(to_long_path(vpd_debug_log)):
            with open(to_long_path(vpd_debug_log), 'r', encoding='utf-8', errors='ignore') as f:
                raw_lines = f.readlines()

            start_idx = None
            for i, l in enumerate(raw_lines):
                if '|          name           | Oper  | CTP status |' in l:
                    start_idx = i
                    break

            end_idx = None
            if start_idx is not None:
                for i in range(len(raw_lines) - 1, start_idx - 1, -1):
                    if 'Skipping VPD Check on Validate for ManufacturingDateTime' in raw_lines[i]:
                        end_idx = i
                        break

            if start_idx is not None and end_idx is not None:
                out_lines = [clean_with_line_block(raw_lines[i]) for i in range(start_idx, end_idx + 1)]
                vpd_out_path = os.path.join(output_dir, 'VPD.txt')
                write_extracted_file(vpd_out_path, out_lines, trim_last_newline=True)
                saved_paths.append(vpd_out_path)

    # 6. Process Restore Default.txt from juno_restore_default
    restore_step_dirs = [d for d in os.listdir(to_long_path(test_results_dir)) if 'restore_default' in d and 'test_restore_default' in d]
    if not restore_step_dirs:
        restore_step_dirs = [d for d in os.listdir(to_long_path(test_results_dir)) if 'restore_default' in d]

    if restore_step_dirs:
        restore_debug_log = os.path.join(test_results_dir, restore_step_dirs[0], 'debug.log')
        if os.path.exists(to_long_path(restore_debug_log)):
            with open(to_long_path(restore_debug_log), 'r', encoding='utf-8', errors='ignore') as f:
                raw_lines = f.readlines()

            start_idx = None
            for i, l in enumerate(raw_lines):
                if 'Verify Factory reset flag state' in l:
                    start_idx = i
                    break

            end_idx = None
            if start_idx is not None:
                for i in range(start_idx, len(raw_lines)):
                    if 'Factory reset successful using Restore Default command' in raw_lines[i]:
                        end_idx = i
                        break

            if start_idx is not None and end_idx is not None:
                out_lines = [clean_with_line_block(raw_lines[i]) for i in range(start_idx, end_idx + 1)]
                restore_out_path = os.path.join(output_dir, 'Restore Default.txt')
                write_extracted_file(restore_out_path, out_lines, trim_last_newline=True)
                saved_paths.append(restore_out_path)

    # 5. Process Provisioning State.txt
    job_log_path = os.path.join(os.path.dirname(test_results_dir), 'job.log')
    if os.path.exists(to_long_path(job_log_path)):
        with open(to_long_path(job_log_path), 'r', encoding='utf-8', errors='ignore') as f:
            raw_lines = f.readlines()

        start_idx = None
        for i, l in enumerate(raw_lines):
            if 'Slot A, Provisioned State: expander_0, development' in l:
                start_idx = i
                break

        end_idx = None
        if start_idx is not None:
            for i in range(start_idx, len(raw_lines)):
                if 'expander_5   development Before Provisioning' in raw_lines[i]:
                    end_idx = i
                    break

        if start_idx is not None and end_idx is not None:
            def clean_job_log_line(line):
                return re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+\s+.*?\|\s*', '', line)

            out_lines = [clean_job_log_line(raw_lines[i]) for i in range(start_idx, end_idx + 1)]
            out_lines[-1] = out_lines[-1].rstrip() + '\n'

            prov_out_path = os.path.join(output_dir, 'Provisioning State.txt')
            write_extracted_file(prov_out_path, out_lines, trim_last_newline=True)
            saved_paths.append(prov_out_path)

    expected_files = {
        'FW.txt', 'GETVPD.txt', 'VER.txt', 'VPD.txt',
        'Provisioning State.txt', 'Restore Default.txt',
    }
    missing_files = expected_files - {os.path.basename(path) for path in saved_paths}
    if missing_files:
        raise ValueError(
            'Incomplete Chassis 4U extraction; missing reports: '
            + ', '.join(sorted(missing_files))
        )
    return output_dir, saved_paths

def check_is_chassis_5u_dell(test_results_dir, folder_name=""):
    """
    Check if an input log directory corresponds to Dell 5U Chassis (PN W47DG / 5U84).
    """
    if "W47DG" in folder_name or "5U_Dell" in folder_name or "5U84" in folder_name:
        return True
    if test_results_dir:
        try:
            vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
            vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
            if os.path.exists(to_long_path(vpd_log_path)):
                with open(to_long_path(vpd_log_path), 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(50000)
                if "W47DG" in content or "5U84ENC" in content or "5U84NPCM" in content or "ASSY,CHAS,RKMNT,5U" in content:
                    return True
        except Exception:
            pass
    return False

def find_chassis_5u_fw_step_dir(test_results_dir):
    """
    Locate the check_and_load_fw_test step containing 'Midplane VPD structure' and 'Sled 1 Element 0 Firmware' (typically Step 02).
    """
    long_tr = to_long_path(test_results_dir)
    fw_dirs = [d for d in os.listdir(long_tr) if os.path.isdir(to_long_path(os.path.join(test_results_dir, d))) and 'check_and_load_fw_test' in d]
    fw_dirs.sort(key=lambda item: int(re.match(r'^(\d+)-', item).group(1)) if re.match(r'^(\d+)-', item) else 0)
    for d in fw_dirs:
        full_p = os.path.join(test_results_dir, d)
        log_p = os.path.join(full_p, "debug.log")
        if os.path.exists(to_long_path(log_p)):
            with open(to_long_path(log_p), 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if "Midplane VPD structure" in content and "Sled 1 Element 0 Firmware" in content:
                return full_p
    return find_step_dir(test_results_dir, "check_and_load_fw_test")

def extract_chassis_5u_dell_logs(input_dir, target_sn, output_base):
    """
    Extract Chassis 5U Dell (PN W47DG) report files:
    1. FW.txt:
       - Midplane VPD structure, CRC, CPLD (from Step 02, fallback Step 07)
       - Sled 1/2 Element 0-3 Firmware (8 lines)
       - Expander SAS addresses sorted exp:0 to exp:7 (8 lines from Step 07)
    2. VPD.txt:
       - Section 1 (Step 07): VPD 16 Midplane A hex dump (0000: to 00c0:)
       - Section 2 (Step 07): VPD 18 Midplane Customer A hex dump (0000: to 00b0:)
       - Sections 3-10 (Step 06): exp:0..7 VPD 48 Canister hex dumps (sorted exp:0..7)
       - Sections 11-17 (Step 07): Midplane VPD verification for set_midplanevpd 2..8
       - Section 18 (Step 07): Customer VPD validation table (part_number down to fru_description match)
    """
    abs_input = os.path.abspath(input_dir.strip(' "\' \t\r\n'))
    test_results_dir = find_test_results_dir(abs_input)
    if not output_base:
        output_base = get_default_reports_dir()
    
    clean_base = output_base.strip(' "\' \t\r\n')
    abs_base = os.path.abspath(clean_base)

    if os.path.basename(abs_base.rstrip('\\/')) == target_sn:
        output_dir = abs_base
    else:
        output_dir = os.path.join(abs_base, target_sn)
    
    os.makedirs(to_long_path(output_dir), exist_ok=True)
    saved_paths = []

    # Find step directories
    fw_step_dir = find_chassis_5u_fw_step_dir(test_results_dir)
    fw_log_path = os.path.join(fw_step_dir, "debug.log")

    s06_dir = find_step_dir(test_results_dir, "write_vpd")
    s06_log_path = os.path.join(s06_dir, "debug.log")

    s07_dir = find_step_dir(test_results_dir, "vpd_validation")
    s07_log_path = os.path.join(s07_dir, "debug.log")

    with open(to_long_path(fw_log_path), 'r', encoding='utf-8', errors='ignore') as f:
        fw_lines = [l.rstrip('\r\n') for l in f]

    with open(to_long_path(s06_log_path), 'r', encoding='utf-8', errors='ignore') as f:
        s06_lines = [l.rstrip('\r\n') for l in f]

    with open(to_long_path(s07_log_path), 'r', encoding='utf-8', errors='ignore') as f:
        s07_lines = [l.rstrip('\r\n') for l in f]

    # 1. Generate FW.txt
    candidates = []
    for i in range(len(fw_lines)):
        l = fw_lines[i]
        if '|0250|Midplane VPD structure' in l and i + 35 < len(fw_lines):
            nearby = ''.join(fw_lines[i:i+35])
            if 'Sled 1 Element 0 Firmware' in nearby and '6.0.0.54' in nearby:
                c_b1 = []
                for j in range(i, i+5):
                    if any(k in fw_lines[j] for k in ['Midplane VPD structure', 'Midplane VPD CRC', 'Midplane CPLD']):
                        c_b1.append(fw_lines[j][fw_lines[j].find('|0250|'):])
                c_b2 = []
                for j in range(i, i+35):
                    if 'Sled ' in fw_lines[j] and 'Element ' in fw_lines[j]:
                        c_b2.append(fw_lines[j][fw_lines[j].find('|0250|'):])
                candidates.append((c_b1, c_b2))

    fw_b1 = []
    fw_b2 = []
    for c_b1, c_b2 in candidates:
        if any('0x13' in l for l in c_b1):
            fw_b1 = c_b1
            fw_b2 = c_b2
            break
    if not fw_b1 and candidates:
        fw_b1, fw_b2 = candidates[0]

    # Fallback to Step 07 if Step 02 did not have candidate
    if not fw_b1:
        for i in range(len(s07_lines)):
            l = s07_lines[i]
            if '|0250|Midplane VPD structure' in l and i + 35 < len(s07_lines):
                for j in range(i, i+5):
                    if any(k in s07_lines[j] for k in ['Midplane VPD structure', 'Midplane VPD CRC', 'Midplane CPLD']):
                        fw_b1.append(s07_lines[j][s07_lines[j].find('|0250|'):])
                for j in range(i, i+35):
                    if 'Sled ' in s07_lines[j] and 'Element ' in s07_lines[j]:
                        fw_b2.append(s07_lines[j][s07_lines[j].find('|0250|'):])
                break

    # Expander SAS addresses from Step 07
    exp_sas_dict = {}
    for l in s07_lines:
        m = re.search(r'(\|3673\|)(exp:\d+:\s+vpd_type 2:\s+\[[0-9a-fA-F]+\])', l)
        if m:
            exp_id = re.search(r'exp:(\d+)', m.group(2)).group(1)
            exp_sas_dict[int(exp_id)] = m.group(1) + m.group(2)
    fw_b3 = [exp_sas_dict[k] for k in sorted(exp_sas_dict.keys())]

    fw_all_lines = fw_b1 + [""] + fw_b2 + [""] + fw_b3
    fw_out_path = os.path.join(output_dir, "FW.txt")
    write_extracted_file(fw_out_path, [l + "\n" for l in fw_all_lines], trim_last_newline=True)
    saved_paths.append(fw_out_path)

    # 2. Generate VPD.txt
    vpd_b1 = []
    in_b1 = False
    for l in s07_lines:
        if 'VPD 16 (1) - Midplane A' in l and ('+' in l or '|' in l):
            vpd_b1.append(l[:72].rstrip())
            in_b1 = True
            continue
        if in_b1:
            if re.search(r'^[0-9a-fA-F]{4}:', l.strip()):
                vpd_b1.append(l[:72].rstrip())
                if l.strip().startswith('00c0:'):
                    break

    vpd_b2 = []
    in_b2 = False
    for l in s07_lines:
        if 'Reading customer VPD (ID = 18)' in l:
            idx = l.find('|3891|')
            vpd_b2.append(l[idx:].rstrip())
            in_b2 = True
            continue
        if in_b2:
            m = re.search(r'\|(\d{4})\|(.*)$', l)
            if m:
                clean_l = f'|{m.group(1)}|{m.group(2)}'.rstrip()
                vpd_b2.append(clean_l)
                if '|0509|00b0:' in clean_l:
                    break

    exp_vpd_dict = {}
    for i, l in enumerate(s06_lines):
        if 'VPD 48 (1) - Canister' in l and '|' in l and l.startswith('exp:'):
            exp_id = int(l.split(':')[1])
            hdr = l[:65]
            n_lines = 8 if exp_id == 0 else 6
            hex_lines = []
            for j in range(i + 1, i + 1 + n_lines):
                hex_lines.append(s06_lines[j][6:71])
            exp_vpd_dict[exp_id] = [hdr] + hex_lines
    exp_vpd_list = [exp_vpd_dict[k] for k in sorted(exp_vpd_dict.keys())]

    midplane_blocks = []
    for vpd_type in range(2, 9):
        match_marker = f'|3673|TWI bus 2 vpd_type {vpd_type}:'
        match_idx = None
        for i, l in enumerate(s07_lines):
            if match_marker in l and '-> match' in l:
                match_idx = i
                break

        out_cmd_marker = f'|0509|Output of cmd "set_midplanevpd {vpd_type}" is'
        cmd_idx = None
        for j in range(match_idx - 1, max(0, match_idx - 20), -1):
            if out_cmd_marker in s07_lines[j]:
                cmd_idx = j
                break

        blk_lines = []
        hdr_l = s07_lines[cmd_idx]
        blk_lines.append(hdr_l[hdr_l.find('|0509|'):])
        blk_lines.append(s07_lines[cmd_idx + 1])
        blk_lines.append(s07_lines[cmd_idx + 2])
        l4 = s07_lines[match_idx]
        l5 = s07_lines[match_idx + 1]
        blk_lines.append(l4[l4.find('|3673|'):])
        blk_lines.append(l5[l5.find('|3673|'):])
        midplane_blocks.append(blk_lines)

    vpd_b18 = []
    in_b18 = False
    for i, l in enumerate(s07_lines):
        if '|3903|name: part_number, size: 32' in l:
            in_b18 = True
        if in_b18:
            m = re.search(r'\|(\d{4})\|(.*)$', l)
            if m:
                vpd_b18.append(f'|{m.group(1)}|{m.group(2)}')
                if m.group(1) == '3993' and 'fru_description' in '\n'.join(vpd_b18[-10:]):
                    break

    all_vpd_sections = [vpd_b1, vpd_b2] + exp_vpd_list + midplane_blocks + [vpd_b18]
    vpd_full_text = '\n\n'.join('\n'.join(sec) for sec in all_vpd_sections)
    vpd_lines_out = [l + '\n' for l in vpd_full_text.splitlines()]
    vpd_out_path = os.path.join(output_dir, "VPD.txt")
    write_extracted_file(vpd_out_path, vpd_lines_out, trim_last_newline=True)
    saved_paths.append(vpd_out_path)

    return output_dir, saved_paths

def check_is_iom_rpc73(test_results_dir):
    """
    Check if an IO log directory is for IOM RPC73:
    In step vpd_validation, the block '|0608|VPD 49 (1) - Canister Customer' contains 'RPC73'.
    """
    try:
        vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
        vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
        if os.path.exists(to_long_path(vpd_log_path)):
            with open(to_long_path(vpd_log_path), 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if "VPD 49 (1) - Canister Customer" in content and "RPC73" in content:
                return True
    except Exception:
        pass
    return False

def find_rpc73_fw_step_dir(test_results_dir):
    """
    Locate the check_and_load_fw_test step containing 'Canister firmware' (Step 02).
    """
    long_tr = to_long_path(test_results_dir)
    fw_dirs = [d for d in os.listdir(long_tr) if os.path.isdir(to_long_path(os.path.join(test_results_dir, d))) and 'check_and_load_fw_test' in d]
    fw_dirs.sort(key=lambda item: int(re.match(r'^(\d+)-', item).group(1)) if re.match(r'^(\d+)-', item) else 0)
    for d in fw_dirs:
        full_p = os.path.join(test_results_dir, d)
        log_p = os.path.join(full_p, "debug.log")
        if os.path.exists(to_long_path(log_p)):
            with open(to_long_path(log_p), 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if "Canister firmware" in content:
                return full_p
    return find_step_dir(test_results_dir, "check_and_load_fw_test")

def detect_rpc73_controller_from_vpd(s7_lines, target_sn):
    """
    Determine if target_sn corresponds to ctrla or ctrlb by searching VPD 49 hex blocks.
    """
    vpd49_starts = [i for i, l in enumerate(s7_lines) if '|0608|VPD 49 (1) - Canister Customer' in l]
    for start_idx in vpd49_starts:
        block_snippet = ''.join(s7_lines[start_idx:start_idx+15])
        if target_sn in block_snippet:
            for j in range(start_idx-1, max(0, start_idx-25), -1):
                if 'ctrla customer VPD' in s7_lines[j] or 'device /dev/sg1' in s7_lines[j]:
                    return 'ctrla'
                if 'ctrlb customer VPD' in s7_lines[j] or 'device /dev/sg2' in s7_lines[j]:
                    return 'ctrlb'
            return 'ctrla' if start_idx == vpd49_starts[0] else 'ctrlb'
    return None

def extract_iom_rpc73(test_results_dir, target_sn, controller):
    """
    Extract combined FW_VPD.txt report for IOM RPC73 units.
    - Section 1 (Step 2): Canister firmware (9 lines)
    - Section 2 (Step 2): FW match for controller (30 lines)
    - Section 3 (Step 7): VPD 49 hex dump (15 lines)
    - Section 4 (Step 7): Customer VPD validation table (83 lines)
    """
    fw_step_dir = find_rpc73_fw_step_dir(test_results_dir)
    fw_log_path = os.path.join(fw_step_dir, "debug.log")
    s2_lines = clean_log_lines(fw_log_path)

    vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
    vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
    s7_lines = clean_log_lines(vpd_log_path)

    # Device to controller mapping in Step 2
    dev_to_ctrl = {}
    cur_dev = None
    for l in s2_lines:
        m_dev = re.search(r'Device:\s*(sg\d+)', l)
        if m_dev: cur_dev = m_dev.group(1)
        m_ctrl = re.search(r'Controller ID:\s*([AB])', l)
        if m_ctrl and cur_dev:
            c = 'ctrla' if m_ctrl.group(1) == 'A' else 'ctrlb'
            dev_to_ctrl[cur_dev] = c

    # 1. Section 1: Canister firmware (9 lines)
    sec1 = []
    canister_occurrences = []
    for i, l in enumerate(s2_lines):
        if re.match(r'^\|0250\|Canister firmware\s*:', l):
            target_ctrl = None
            for j in range(i-1, max(0, i-30), -1):
                m_dev = re.search(r'/dev/(sg\d+)', s2_lines[j])
                if m_dev:
                    target_ctrl = dev_to_ctrl.get(m_dev.group(1))
                    break
            canister_occurrences.append((target_ctrl, s2_lines[i:i+9]))

    for c, blk in canister_occurrences:
        if c == controller:
            sec1 = [line.rstrip('\r\n') for line in blk]
            break
    if not sec1 and canister_occurrences:
        idx = 0 if controller == 'ctrla' else -1
        sec1 = [line.rstrip('\r\n') for line in canister_occurrences[idx][1]]

    # 2. Section 2: FW match for controller (30 lines)
    sec2 = []
    start_sec2 = None
    for i, l in enumerate(s2_lines):
        if f'|0573|FW match: Component: {controller}' in l:
            start_sec2 = i
            break
    if start_sec2 is not None:
        for i in range(start_sec2, len(s2_lines)):
            l = s2_lines[i].rstrip('\r\n')
            if '|0573|FW match: Component:' in l and controller not in l:
                break
            if '|0589|Files to load:' in l or '|0586|Component FW' in l or '|1117|mismatch:' in l:
                break
            sec2.append(l)

    # 3. Section 3: VPD 49 hex dump (15 lines)
    sec3 = []
    vpd49_starts = [i for i, l in enumerate(s7_lines) if '|0608|VPD 49 (1) - Canister Customer' in l]
    for start_idx in vpd49_starts:
        ctx_ctrl = None
        for j in range(start_idx-1, max(0, start_idx-25), -1):
            if 'ctrla customer VPD' in s7_lines[j] or 'device /dev/sg1' in s7_lines[j]:
                ctx_ctrl = 'ctrla'; break
            if 'ctrlb customer VPD' in s7_lines[j] or 'device /dev/sg2' in s7_lines[j]:
                ctx_ctrl = 'ctrlb'; break
        block_snippet = ''.join(s7_lines[start_idx:start_idx+15])
        if target_sn in block_snippet or ctx_ctrl == controller:
            p1 = []
            for i in range(start_idx, min(start_idx + 30, len(s7_lines))):
                p1.append(s7_lines[i].rstrip('\r\n'))
                if '00a0:' in s7_lines[i]: break
            p2 = []
            for i in range(start_idx, min(start_idx + 150, len(s7_lines))):
                l_str = s7_lines[i].rstrip('\r\n')
                if '0360:' in l_str or '0370:' in l_str:
                    p2.append(l_str)
                    if '0370:' in l_str: break
            sec3 = p1 + p2
            break

    # 4. Section 4: Customer VPD validation table (83 lines)
    sec4 = []
    start_sec4 = None
    for i, l in enumerate(s7_lines):
        if f'|3893|Checking {controller} customer VPD (ID = 49) ...' in l:
            start_sec4 = i
            break
    if start_sec4 is not None:
        in_fru = False
        for i in range(start_sec4, len(s7_lines)):
            l = s7_lines[i].rstrip('\r\n')
            sec4.append(l)
            if 'name: fru_description' in l or 'FRU Description' in l:
                in_fru = True
            if in_fru and 'result: match' in l:
                break

    # Combine all 4 sections with blank line delimiters
    result = []
    result.extend([l + '\n' for l in sec1])
    result.append('\n')
    while sec2 and sec2[-1] == '':
        sec2.pop()
    result.extend([l + '\n' for l in sec2])
    result.append('\n')
    result.extend([l + '\n' for l in sec3])
    result.append('\n')
    result.extend([l + '\n' for l in sec4])
    return result

def check_is_psu(test_results_dir, folder_name=""):
    """
    Check if a test log directory is for a PSU unit (2U DYJW5, 5U 0R4C4, etc.):
    Folder name contains DYJW5, 0R4C4, or Step 07/06 contains PSMI/PCM/DYJW5/0R4C4.
    """
    if "DYJW5" in folder_name or "0R4C4" in folder_name:
        return True
    try:
        vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
        vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
        if os.path.exists(to_long_path(vpd_log_path)):
            with open(to_long_path(vpd_log_path), 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(30000)
            if ("DYJW5" in content or "0R4C4" in content or "PWR SPLY" in content) and ("psu0" in content or "PCM 1" in content or "PSMI" in content):
                return True
    except Exception:
        pass
    return False

check_is_psu_dyjw5 = check_is_psu

def detect_psu_model_info(test_results_dir, folder_name=""):
    """
    Detect PSU model and return (short_tag, full_display_name).
    Examples:
      ("PSU 5U", "PSU 5U (0R4C4)")
      ("PSU 2U", "PSU 2U (DYJW5)")
    """
    if "0R4C4" in folder_name:
        return "PSU 5U", "PSU 5U (0R4C4)"
    if "DYJW5" in folder_name:
        return "PSU 2U", "PSU 2U (DYJW5)"

    try:
        vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
        vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
        if os.path.exists(to_long_path(vpd_log_path)):
            with open(to_long_path(vpd_log_path), 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(30000)
            if "0R4C4" in content or "PWR SPLY,5U" in content:
                return "PSU 5U", "PSU 5U (0R4C4)"
            if "DYJW5" in content or "PWR SPLY,2U" in content:
                return "PSU 2U", "PSU 2U (DYJW5)"
    except Exception:
        pass

    return "PSU", "PSU"

def detect_psu_unit_id(s7_lines, target_sn):
    """
    Detect whether target_sn belongs to psu0 (PCM 1) or psu1 (PCM 2).
    Returns 'psu0' or 'psu1'.
    """
    for line in s7_lines:
        if "PARAMS (key=sn_pn_dict" in line:
            m = re.search(r'=>\s*"(.*)"', line)
            if m:
                dict_str = m.group(1).replace("\\'", "'")
                try:
                    d = ast.literal_eval(dict_str)
                    for k in ["psu0", "psu1"]:
                        if target_sn in str(d.get(k, "")):
                            return k
                except Exception:
                    pass
    # Fallback to validation block search
    psu1_start = None
    for i, line in enumerate(s7_lines):
        if "Checking psu1 customer VPD" in line:
            psu1_start = i
            break
    if psu1_start is not None:
        psu1_content = "\n".join(s7_lines[psu1_start:])
        if target_sn in psu1_content:
            return "psu1"
    return "psu0"

def extract_psu_logs(test_results_dir, target_sn):
    """
    Extract 'Controller FW, Drive FW, Serial Number Tracking & Test History.txt' for PSU units (2U & 5U).
    - Section 1 (Step 6/7): PCM 1 & 2 firmware, VPD structure, and VPD CRC (6 lines)
    - Section 2 (Step 6): VPD 40 (psu0) or VPD 41 (psu1) hex dump (0000: to 0050:)
    - Section 3 (Step 7): VPD 60 (psu0) or VPD 61 (psu1) hex dump (0000: to 0090: + blank line + 0360: to 0390:)
    - Section 4 (Step 7): Customer VPD validation table (84 lines)
    """
    s6_dir = find_step_dir(test_results_dir, "write_vpd")
    s7_dir = find_step_dir(test_results_dir, "vpd_validation")

    with open(to_long_path(os.path.join(s6_dir, "debug.log")), 'r', encoding='utf-8', errors='ignore') as f:
        s6 = [l.rstrip('\r\n') for l in f]

    with open(to_long_path(os.path.join(s7_dir, "debug.log")), 'r', encoding='utf-8', errors='ignore') as f:
        s7 = [l.rstrip('\r\n') for l in f]

    unit_id = detect_psu_unit_id(s7, target_sn)
    pcm_num = "1" if unit_id == "psu0" else "2"
    vpd_raw_id = "40" if unit_id == "psu0" else "41"
    vpd_cust_id = "60" if unit_id == "psu0" else "61"

    # Section 1: PCM firmware & VPD CRC (6 lines)
    pcm_fw = []
    for l in s6:
        if "|0250|PCM " in l:
            idx = l.find("|0250|PCM ")
            pcm_fw.append(l[idx:])
            if len(pcm_fw) == 6:
                break

    # Section 2: VPD 40 / 41 from Step 6 diff table (0000: to 0050:)
    s2_lines = []
    target_v4x_hdr = f"VPD {vpd_raw_id} (1) - PSMI PCM {pcm_num} A"
    in_v4x = False
    for l in s6:
        if target_v4x_hdr in l and ("|" in l or "+" in l):
            parts = re.split(r'\s+[|+]\s+', l)
            s2_lines.append(parts[0].strip())
            in_v4x = True
            continue
        if in_v4x:
            if re.search(r'^\d{4}:', l.strip()):
                parts = re.split(r'\s+[|+]\s+', l)
                s2_lines.append(parts[0].rstrip())
                if parts[0].startswith("0050:"):
                    break

    # Section 3: VPD 60 / 61 hex from Step 7 (0000: to 0090: + blank line + 0360: to 0390:)
    s3_lines = []
    target_v6x_hdr_marker = f"|0608|VPD {vpd_cust_id} (1) - PSMI PCM {pcm_num} Customer"
    in_v6x = False
    cust_header = ""
    for l in s7:
        if target_v6x_hdr_marker in l:
            idx = l.find(f"VPD {vpd_cust_id} (1)")
            cust_header = l[idx:].strip()
            s3_lines.append(cust_header)
            in_v6x = True
            continue
        if in_v6x:
            m = re.search(r'\|0509\|(\d{4}:.+)$', l)
            if m:
                hex_part = m.group(1).rstrip()
                addr = hex_part[:4]
                if addr in [f"{x:04x}" for x in range(0, 0xa0, 0x10)]:
                    s3_lines.append(hex_part)
                    if addr == "0090":
                        s3_lines.append("")
                elif addr in ["0360", "0370", "0380", "0390"]:
                    s3_lines.append(hex_part)
                    if addr == "0390":
                        break

    # Section 4: Customer VPD validation table from Step 7
    s4_lines = [cust_header]
    in_val = False
    val_marker = f"|3893|Checking {unit_id} customer VPD"
    for l in s7:
        if val_marker in l:
            idx = l.find(f"|3893|Checking {unit_id}")
            s4_lines.append(l[idx:])
            in_val = True
            continue
        if in_val:
            m = re.search(r'\|(\d{4})\|(.*)$', l)
            if m:
                s4_lines.append(f"|{m.group(1)}|{m.group(2)}")
                if m.group(1) == "3993" and "fru_description" in "\n".join(s4_lines[-10:]):
                    break

    # Combine with blank lines
    combined = pcm_fw + [""] + s2_lines + [""] + s3_lines + [""] + s4_lines
    out_lines = [l + "\n" for l in combined]
    return out_lines, unit_id

extract_psu_dyjw5 = extract_psu_logs

def write_extracted_file(filepath, lines, trim_last_newline=True):

    """
    Write extracted lines to file preserving Windows CRLF line endings.
    """
    if not lines:
        return

    long_p = to_long_path(filepath)
    os.makedirs(os.path.dirname(long_p), exist_ok=True)
    with open(long_p, 'w', encoding='utf-8', newline='\r\n') as f:
        for i, line in enumerate(lines):
            if i == len(lines) - 1 and trim_last_newline:
                f.write(line.rstrip('\r\n'))
            else:
                f.write(line)

def resolve_output_paths(base_output_dir, target_sn, is_chassis, unit_root=None):
    """
    Resolve target output directory and output file paths.
    """
    if not base_output_dir:
        base_output_dir = get_default_reports_dir()
    clean_base = base_output_dir.strip(' "\' \t\r\n')
    
    if clean_base.lower().endswith('.txt'):
        out_dir = os.path.dirname(os.path.abspath(clean_base))
        if is_chassis:
            return out_dir, os.path.abspath(clean_base)
        else:
            return out_dir, None

    abs_base = os.path.abspath(clean_base)
    if os.path.basename(abs_base.rstrip('\\/')) == target_sn:
        target_dir = abs_base
    else:
        target_dir = os.path.join(abs_base, target_sn)

    os.makedirs(to_long_path(target_dir), exist_ok=True)
    
    if is_chassis:
        chassis_file = os.path.join(target_dir, f"{target_sn}.txt")
        return target_dir, chassis_file
    else:
        return target_dir, None

def is_archive_path(path):
    """Return True if path points to a supported archive (.zip, .tar.gz, .tgz, .tar.xz)."""
    if not path:
        return False
    low = path.strip(' "\' \t\r\n').lower()
    return low.endswith(('.zip', '.tar.gz', '.tgz', '.tar.xz'))

def strip_archive_ext(filename):
    """Strip archive extension (.zip, .tar.gz, .tgz, .tar.xz) from filename."""
    for ext in ('.tar.gz', '.tar.xz', '.tgz', '.zip'):
        if filename.lower().endswith(ext):
            return filename[:-len(ext)]
    return filename

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
    
    unique_sns = []
    for sn in matches:
        if sn not in unique_sns:
            unique_sns.append(sn)
    return unique_sns

def print_header():
    title_str = f"{APP_TITLE} - v{APP_VERSION}"
    print(f"\n{Color.BRIGHT_CYAN}┌─────────────────────────────────────────────────────────────────────┐{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}{Color.WHITE}{title_str.center(67)}{Color.RESET} {Color.BRIGHT_CYAN}│{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}└─────────────────────────────────────────────────────────────────────┘{Color.RESET}\n")

def find_test_results_dir(input_dir):
    """
    Locate the 'test-results' directory inside input_dir regardless of nesting level.
    """
    abs_input = os.path.abspath(input_dir.strip(' "\' \t\r\n'))
    long_input = to_long_path(abs_input)

    if os.path.basename(abs_input.rstrip('\\/')) == 'test-results' and os.path.isdir(long_input):
        return abs_input

    direct_tr = os.path.join(abs_input, 'test-results')
    if os.path.isdir(to_long_path(direct_tr)):
        return direct_tr

    latest_tr = os.path.join(abs_input, 'latest', 'test-results')
    if os.path.isdir(to_long_path(latest_tr)):
        return latest_tr

    if os.path.isdir(long_input):
        try:
            for item in os.listdir(long_input):
                full_item = os.path.join(abs_input, item)
                if item.startswith('job-'):
                    tr = os.path.join(full_item, 'test-results')
                    if os.path.isdir(to_long_path(tr)):
                        return tr
        except Exception:
            pass

    for root, dirs, files in os.walk(long_input):
        if 'test-results' in dirs:
            return from_long_path(os.path.join(root, 'test-results'))

    raise FileNotFoundError(f"Không tìm thấy thư mục 'test-results' trong {from_long_path(input_dir)}")

def get_log_unit_root(input_dir):
    """
    Given an input directory (which may be unit root, latest, job-*, test-results, or archive file),
    resolve and return the top-level raw log folder (unit root).
    """
    abs_input = os.path.abspath(input_dir.strip(' "\' \t\r\n'))
    if os.path.isfile(to_long_path(abs_input)) and is_archive_path(abs_input):
        return os.path.join(os.path.dirname(abs_input), strip_archive_ext(os.path.basename(abs_input)))
    try:
        tr = find_test_results_dir(abs_input)
        unit_root = os.path.dirname(tr)
        if os.path.basename(unit_root) == 'latest' or os.path.basename(unit_root).startswith('job-'):
            unit_root = os.path.dirname(unit_root)
        return unit_root
    except Exception:
        return abs_input

def _should_extract_archive_member(member_name):
    """
    Selective filter for archive members: skip heavy serial_logs, sysinfo, sqlite, html
    while keeping all test-results debug.log, enc_logs, results.json/xml, job.log, and top-level logs.
    """
    norm = member_name.replace('\\', '/')
    low = norm.lower()
    if '/serial_logs/' in low or low.startswith('serial_logs/'):
        return False
    if '/sysinfo/' in low or low.startswith('sysinfo/'):
        return False
    if '/connection_configs/' in low or low.startswith('connection_configs/'):
        return False
    if low.endswith(('.journal.sqlite', 'results.html', 'results.tap', '.pyc')):
        return False
    return True

@contextlib.contextmanager
def prepare_log_input_source(input_path_raw):
    """
    Context manager that accepts either a folder path or an archive (.zip, .tar.gz, .tgz, .tar.xz).
    If an archive is provided, selectively extracts needed files to a fast temporary directory
    and cleans up automatically upon exit.
    Yields: (working_input_dir, logical_unit_root, logical_folder_name)
    """
    abs_input = os.path.abspath(input_path_raw.strip(' "\' \t\r\n'))
    long_input = to_long_path(abs_input)

    if os.path.isfile(long_input) and is_archive_path(abs_input):
        tmp_dir = tempfile.mkdtemp(prefix="ja_mfg_zip_")
        logical_name = strip_archive_ext(os.path.basename(abs_input))
        logical_unit_root = os.path.join(os.path.dirname(abs_input), logical_name)
        try:
            low_path = abs_input.lower()
            if low_path.endswith('.zip'):
                with zipfile.ZipFile(long_input, 'r') as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        if _should_extract_archive_member(info.filename):
                            target_p = os.path.join(tmp_dir, *info.filename.replace('\\', '/').split('/'))
                            os.makedirs(to_long_path(os.path.dirname(target_p)), exist_ok=True)
                            with zf.open(info, 'r') as src, open(to_long_path(target_p), 'wb') as dst:
                                shutil.copyfileobj(src, dst)
            else:
                with tarfile.open(long_input, 'r:*') as tf:
                    for member in tf.getmembers():
                        if not member.isfile():
                            continue
                        if _should_extract_archive_member(member.name):
                            target_p = os.path.join(tmp_dir, *member.name.replace('\\', '/').split('/'))
                            os.makedirs(to_long_path(os.path.dirname(target_p)), exist_ok=True)
                            src = tf.extractfile(member)
                            if src:
                                with src, open(to_long_path(target_p), 'wb') as dst:
                                    shutil.copyfileobj(src, dst)

            entries = [d for d in os.listdir(to_long_path(tmp_dir)) if os.path.isdir(to_long_path(os.path.join(tmp_dir, d)))]
            if len(entries) == 1 and entries[0] not in ('test-results', 'latest', 'enc_logs') and not entries[0].startswith('job-'):
                working_dir = os.path.join(tmp_dir, entries[0])
            else:
                working_dir = tmp_dir
            yield working_dir, logical_unit_root, logical_name
        finally:
            shutil.rmtree(to_long_path(tmp_dir), ignore_errors=True)
    else:
        unit_root = get_log_unit_root(abs_input)
        folder_name = os.path.basename(unit_root.rstrip('\\/'))
        yield abs_input, unit_root, folder_name

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
    if folder_name:
        m_pn = re.search(r'_uut\d+_([A-Z0-9-]+)_(?:S[AG]F|FVB|PM)', folder_name)
        if m_pn:
            meta["part_number"] = m_pn.group(1)

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
        if os.path.isfile(to_long_path(os.path.join(smp_abs, f))) and f.lower().endswith('.txt')
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
        is_chassis_5u_dell = (target_sn.startswith("SGF") or "W47DG" in folder_name or "5U_Dell" in folder_name or "5U84" in folder_name) and check_is_chassis_5u_dell(test_results_dir, folder_name)
        is_chassis_2u = target_sn.startswith("SGF") and not is_chassis_5u_dell
        is_chassis = is_chassis_2u or is_chassis_4u or is_chassis_5u_dell

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
            log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS 5U DELL]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}Chassis 5U Dell (W47DG){Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")
            out_dir, saved_paths = extract_chassis_5u_dell_logs(working_input_dir, target_sn, output_base_raw)
            log_print(f"{Color.BRIGHT_GREEN}✔ Đã tạo {len(saved_paths)} file báo cáo Chassis 5U Dell tại:{Color.RESET}")
            log_print(f"  {Color.BOLD}{Color.WHITE}➜ {out_dir}{Color.RESET}")

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
                is_psu = target_sn.startswith("PM") or "DYJW5" in folder_name or "0R4C4" in folder_name or check_is_psu(test_results_dir, folder_name)
                is_rpc73 = check_is_iom_rpc73(test_results_dir)

                if is_psu:
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
                    unit_type = "IOM RPC73"

                    log_print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ IOM RPC73]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng SP: {Color.MAGENTA}IOM RPC73{Color.RESET} │ Controller: {Color.YELLOW}{controller}{Color.RESET} │ Cycle Time: {Color.BRIGHT_YELLOW}{cycle_meta['cycle_time_short']}{Color.RESET}")

                    rpc73_lines = extract_iom_rpc73(test_results_dir, target_sn, controller)
                    fw_vpd_out_path = os.path.join(out_dir, "FW_VPD.txt")
                    write_extracted_file(fw_vpd_out_path, rpc73_lines, trim_last_newline=True)
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
                    ("Chassis 5U" if ("W47DG" in logical_root or "5U_Dell" in logical_root or "5U84" in logical_root or meta.get("part_number") == "W47DG") else
                     ("Chassis" if first_sn.startswith("SGF") else
                      ("PSU" if first_sn.startswith("PM") else "IO")))
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
):
    """
    Connect directly or via Indirect Bridge (172.21.168.241 -> 172.19.*.*) to a remote test station,
    search for logs matching raw_sn (supports multiple comma-separated SNs), perform Selective Fast Fetch
    into a temporary directory, extract reports into <App_Dir>/reports/<Target_SN>/, and clean up.
    """
    from pathlib import Path
    from module import config as m_config
    from module.bridge import build_bridge_settings, should_use_bridge
    from module.ip_utils import expand_ip
    from module.log_finder import (
        filter_entries,
        format_entries_table,
        parse_selection,
        parse_sn_list,
    )
    from module.remote_fetcher import SshLogService

    host = expand_ip(raw_ip, ip_prefix=m_config.DEFAULT_IP_PREFIX)
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
    print(f"   ├─ {Color.GRAY}Máy đích (Target IP) :{Color.RESET} {Color.BOLD}{Color.WHITE}{host}:{port}{Color.RESET} (nhập: {raw_ip})")
    print(f"   ├─ {Color.GRAY}Phương thức kết nối  :{Color.RESET} {Color.BRIGHT_YELLOW}{route_desc}{Color.RESET}")
    print(f"   ├─ {Color.GRAY}Serial Number cần tìm:{Color.RESET} {Color.BOLD}{Color.CYAN}{', '.join(sn_list)}{Color.RESET}")
    print(f"   └─ {Color.GRAY}Thư mục lưu báo cáo  :{Color.RESET} {Color.WHITE}{output_base}{Color.RESET}")

    service = SshLogService(
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
        print(f"\n   {Color.YELLOW}⏳ Đang thiết lập phiên SSH tới {host}...{Color.RESET}")
        service.connect()
        print(
            f"   {Color.BRIGHT_GREEN}✔ Đã kết nối thành công!{Color.RESET} "
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
            for line in format_entries_table(filtered).splitlines():
                print(f"     {line}")

            if latest_n is not None or len(filtered) == 1 or not interactive or not sys.stdin.isatty():
                selected_entries = filtered if latest_n is not None else [filtered[0]]
                if len(filtered) > 1 and latest_n is None:
                    print(f"   {Color.BRIGHT_YELLOW}⚡ Tự động chọn bộ log mới nhất: {selected_entries[0].name}{Color.RESET}")
            else:
                sel_prompt = (
                    f"\n   {Color.CYAN}👉 Chọn STT log cần phân tích (VD: 1, 1-2, l=mới nhất, a=tất cả; Enter = [1] mới nhất): {Color.RESET}"
                )
                raw_sel = safe_input(sel_prompt, default="1") or "1"
                selected_entries = parse_selection(raw_sel, filtered)
                if not selected_entries:
                    selected_entries = [filtered[0]]

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
                            all_results.append(res)
                        except Exception as exc:
                            print(f"   {Color.RED}✖ Lỗi khi trích xuất '{entry.name}' (SN {t_sn}): {exc}{Color.RESET}")
                            all_results.append({
                                "sn": t_sn,
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
        service.disconnect()

    if export_csv and all_results:
        print_batch_summary_table(all_results)
        csv_target = custom_csv_path if custom_csv_path else os.path.join(output_base, "Cycle_Time_Summary.csv")
        export_cycle_time_summary_csv(all_results, csv_target)

    return all_results


def run_batch_extraction(batch_items, max_workers=4, export_csv=True, diagnose=False):
    """
    Run extraction over a list of batch items (supports both Remote IP+SN items and Local Folder/Archive items).
    """
    total = len(batch_items)
    if total == 0:
        print(f"\n{Color.YELLOW}⚠ Danh sách trích xuất trống.{Color.RESET}")
        return []

    effective_workers = min(max(1, int(max_workers or 1)), total)
    mode_tag = f"Đa luồng ({effective_workers} workers)" if effective_workers > 1 else "Tuần tự (1 worker)"
    print(f"\n{Color.BRIGHT_YELLOW}🚀 Bắt đầu trích xuất hàng loạt ({total} mục - {mode_tag})...{Color.RESET}")
    print(f"{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")

    indexed_results = [None] * total

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
                rem_results = process_remote_extraction(
                    raw_ip=log_path,
                    raw_sn=target_sn,
                    output_base_raw=output_base,
                    latest_n=1,
                    diagnose=diagnose,
                    interactive=False,
                    export_csv=False,
                )
                return idx, (rem_results[0] if rem_results else {
                    "sn": target_sn,
                    "unit_type": "-",
                    "controller": "-",
                    "status": "FAIL",
                    "error": "No result returned",
                    "out_dir": "-",
                    "cycle_time": "N/A",
                    "metadata": {},
                    "warnings": []
                })
            except Exception as e:
                with _PRINT_LOCK:
                    print(f"{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} {Color.RED}✖ Lỗi kết nối/trích xuất từ xa ({log_path} - {target_sn}): {e}{Color.RESET}")
                return idx, {
                    "sn": target_sn,
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
                "unit_type": "Chassis 4U" if target_sn.startswith("FVB") else ("Chassis 5U" if ("W47DG" in log_path or "5U_Dell" in log_path or "5U84" in log_path) else ("Chassis" if target_sn.startswith("SGF") else ("PSU" if target_sn.startswith("PM") else "IO"))),
                "controller": "-",
                "status": "FAIL",
                "error": str(e),
                "out_dir": "-",
                "cycle_time": "N/A",
                "metadata": {},
                "warnings": []
            }

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

    results = [r for r in indexed_results if r is not None]
    print_batch_summary_table(results)

    if export_csv and results:
        first_out = next((r.get("out_dir") for r in results if r.get("out_dir") and r.get("out_dir") != "-"), None)
        if first_out:
            csv_dir = os.path.dirname(first_out.rstrip("\\/"))
        else:
            csv_dir = get_default_reports_dir()
        export_cycle_time_summary_csv(results, os.path.join(csv_dir, "Cycle_Time_Summary.csv"))

    return results


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
      [R] Return to main menu
      [Q/Enter] Exit
    Returns True if user wants to return to main menu, False otherwise.
    """
    if not sys.stdin.isatty():
        return False
    print(f"{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")
    if last_out_dir and last_out_dir != "-" and os.path.exists(to_long_path(last_out_dir)):
        prompt_str = (
            f"   {Color.CYAN}[O]{Color.RESET} Mở thư mục kết quả (Explorer)  │  "
            f"{Color.CYAN}[R]{Color.RESET} Về Menu chính  │  "
            f"{Color.CYAN}[Enter/Q]{Color.RESET} Thoát: "
        )
        choice = get_single_key_choice(prompt_str, ["O", "R", "Q"], default_key="Q")
        if choice == "O":
            try:
                target_open = last_out_dir if os.path.isdir(to_long_path(last_out_dir)) else os.path.dirname(last_out_dir)
                os.startfile(from_long_path(target_open))
                print(f"   {Color.GREEN}📂 Đã mở Windows Explorer: {from_long_path(target_open)}{Color.RESET}")
            except Exception as e:
                print(f"   {Color.YELLOW}⚠ Không thể mở Explorer: {e}{Color.RESET}")
            # After opening Explorer, ask if user wants to return to menu or quit
            prompt_str2 = f"   {Color.CYAN}[R]{Color.RESET} Về Menu chính  │  {Color.CYAN}[Enter/Q]{Color.RESET} Thoát: "
            choice2 = get_single_key_choice(prompt_str2, ["R", "Q"], default_key="Q")
            return choice2 == "R"
        return choice == "R"
    else:
        prompt_str = f"   {Color.CYAN}[R]{Color.RESET} Về Menu chính  │  {Color.CYAN}[Enter/Q]{Color.RESET} Thoát: "
        choice = get_single_key_choice(prompt_str, ["R", "Q"], default_key="Q")
        return choice == "R"


def run_remote_interactive_mode():
    """
    Interactive Mode [1]: Connect to remote test station via IP + SN (Indirect Bridge 172.21.168.241 -> 172.19.*.*)
    and extract reports directly into <App_Dir>/reports/<Target_SN>/.
    """
    from module import config as m_config
    from module.ip_utils import expand_ip

    print(f"\n{Color.BRIGHT_YELLOW}📌 [Remote IP + SN Mode] Trích xuất trực tiếp từ Trạm Test (Bridge {m_config.LOCAL_SETTINGS['bridge']['host']} ➜ {m_config.DEFAULT_IP_PREFIX}.*.*):{Color.RESET}\n")

    while True:
        ip_prompt = (
            f"{Color.BRIGHT_YELLOW}📌 [1/3] Nhập IP máy test (VD: 116.174, 116174, 172.19.116.174 hoặc {m_config.LOCAL_SETTINGS['bridge']['host']}):{Color.RESET}\n"
            f"   {Color.CYAN}👉 {Color.RESET}"
        )
        raw_ip = safe_input(ip_prompt)
        if not raw_ip:
            if not sys.stdin.isatty():
                return None
            print(f"   {Color.RED}✖ IP không được để trống. Vui lòng nhập lại!{Color.RESET}\n")
            continue
        try:
            full_ip = expand_ip(raw_ip, ip_prefix=m_config.DEFAULT_IP_PREFIX)
            print(f"   {Color.GREEN}➜ Địa chỉ IP máy đích: {full_ip}{Color.RESET}")
            break
        except Exception as exc:
            if not sys.stdin.isatty():
                print(f"   {Color.RED}✖ {exc}{Color.RESET}")
                return None
            print(f"   {Color.RED}✖ {exc}. Vui lòng nhập lại!{Color.RESET}\n")

    while True:
        sn_prompt = (
            f"\n{Color.BRIGHT_YELLOW}📌 [2/3] Nhập Serial Number cần tìm (hỗ trợ nhiều SN cách nhau dấu phẩy, VD: SN1, SN2):{Color.RESET}\n"
            f"   {Color.CYAN}👉 {Color.RESET}"
        )
        raw_sn = safe_input(sn_prompt)
        if raw_sn:
            break
        if not sys.stdin.isatty():
            return None
        print(f"   {Color.RED}✖ Serial Number không được để trống. Vui lòng nhập lại!{Color.RESET}")

    default_reports = get_default_reports_dir()
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

    try:
        results = process_remote_extraction(
            raw_ip=raw_ip,
            raw_sn=raw_sn,
            output_base_raw=output_dir_raw,
            interactive=True,
            export_csv=True,
        )
        first_out = next((r.get("out_dir") for r in results if r.get("out_dir") and r.get("out_dir") != "-"), default_reports)
        return first_out
    except Exception as exc:
        print(f"\n{Color.RED}✖ Lỗi khi trích xuất từ xa: {exc}{Color.RESET}\n")
        return None


def run_interactive_menu_once():
    """
    Runs one cycle of the interactive CLI menu. Returns last output directory for post-action handling.
    """
    print_header()
    print(f"{Color.BRIGHT_YELLOW}Vui lòng chọn chế độ làm việc:{Color.RESET}")
    print(f"   {Color.CYAN}[1]{Color.RESET} 🌐 Trích xuất trực tiếp từ Trạm Test qua IP + SN (Indirect Bridge 172.21.168.241 ➜ 172.19.*.*)")
    print(f"   {Color.CYAN}[2]{Color.RESET} 📂 Trích xuất 1 thư mục / file nén log trên máy (Single Folder / Archive Mode)")
    print(f"   {Color.CYAN}[3]{Color.RESET} 🚀 Quét và trích xuất hàng loạt từ thư mục gốc (Batch Subfolders & Archives)")
    print(f"   {Color.CYAN}[4]{Color.RESET} 📋 Đọc danh sách trích xuất từ file CSV / TXT (Hỗ trợ cả IP Trạm Test & Đường dẫn Local)")
    print(f"   {Color.CYAN}[5]{Color.RESET} 📝 Tạo file CSV mẫu (mau_danh_sach_log.csv)")
    print(f"   {Color.CYAN}[6]{Color.RESET} ⏱  Phân tích nhanh Cycle Time & Chẩn đoán lỗi (Cycle Time & Failure Analyzer)")
    print(f"   {Color.CYAN}[7]{Color.RESET} 🔍 Đối chiếu kết quả với thư mục Golden Sample (Golden Sample Diff Verifier)\n")

    prompt_str = f"   {Color.CYAN}👉 Chọn nhanh số (1-7) hoặc nhấn Enter để chọn [1]: {Color.RESET}"
    mode_choice = get_single_key_choice(prompt_str, ["1", "2", "3", "4", "5", "6", "7"], default_key="1")

    if mode_choice == "1":
        return run_remote_interactive_mode()

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
                unit_tag = "Chassis 4U" if sn_item.startswith("FVB") else ("Chassis 5U" if ("W47DG" in input_dir or "5U_Dell" in input_dir or "5U84" in input_dir) else ("Chassis" if sn_item.startswith("SGF") else ("PSU" if sn_item.startswith("PM") else "IO")))
                print(f"\n{Color.BRIGHT_YELLOW}⚡ [TỰ ĐỘNG CHỌN SN {unit_tag.upper()}]:{Color.RESET} {Color.BOLD}{Color.WHITE}{sn_item}{Color.RESET}")
                target_sn_raw = sn_item
            else:
                print(f"\n{Color.BRIGHT_YELLOW}📌 [2/3] Phát hiện Serial Number trong tên thư mục/file. Vui lòng chọn:{Color.RESET}")
                for idx, sn in enumerate(detected_sns, 1):
                    if sn.startswith("PM"):
                        ctrl_tag = f" ({'psu0 / PCM 1' if idx == 1 else 'psu1 / PCM 2'})"
                    elif not sn.startswith("SGF") and not sn.startswith("FVB"):
                        ctrl_tag = f" ({'ctrla' if idx == 1 else 'ctrlb'})"
                    else:
                        ctrl_tag = ""
                    print(f"   {Color.CYAN}[{idx}]{Color.RESET} {Color.BOLD}{Color.WHITE}{sn}{Color.RESET}{Color.GRAY}{ctrl_tag}{Color.RESET}")

                default_choice = 1
                prompt_str = f"   {Color.CYAN}👉 Chọn nhanh số (1-{len(detected_sns)}) hoặc nhấn Enter để chọn [{default_choice}] ({detected_sns[0]}): {Color.RESET}"
                valid_keys = [str(i) for i in range(1, len(detected_sns) + 1)]
                choice_str = get_single_key_choice(prompt_str, valid_keys, default_key="1")

                if choice_str.isdigit() and 1 <= int(choice_str) <= len(detected_sns):
                    target_sn_raw = detected_sns[int(choice_str) - 1]
                else:
                    target_sn_raw = detected_sns[0]
        else:
            while True:
                prompt_str = f"\n{Color.BRIGHT_YELLOW}📌 [2/3] Nhập Target Serial Number (VD: SAFVN... hoặc SGFVN...):{Color.RESET}\n   {Color.CYAN}👉 {Color.RESET}"
                target_sn_raw = safe_input(prompt_str)
                if target_sn_raw:
                    break
                if not sys.stdin.isatty():
                    print(f"   {Color.RED}✖ Target SN không được để trống.{Color.RESET}")
                    return None
                print(f"   {Color.RED}✖ Target SN không được để trống. Vui lòng nhập lại!{Color.RESET}\n")

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
                interactive=(args.latest is None and sys.stdin.isatty()),
                export_csv=True,
                custom_csv_path=args.export_summary_csv,
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

