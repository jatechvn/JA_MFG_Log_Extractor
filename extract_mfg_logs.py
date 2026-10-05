import os
import sys
import re
import csv
import argparse
import glob
import tarfile
import ast

APP_NAME = "JA_MFG_Log_Extractor"
APP_TITLE = "CÔNG CỤ TRÍCH XUẤT LOG TỰ ĐỘNG (IO, CHASSIS & PSU UNITS)"
APP_VERSION = "1.3.0"
APP_BUILD = "1"

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
    parent_dir = os.path.dirname(unit_root)

    if not output_base:
        output_base = parent_dir
    
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

def detect_sns_from_folder(folder_path):
    """
    Extract Serial Numbers (SAF..., SGF..., or FVB...) found in input folder name.
    """
    folder_name = os.path.basename(folder_path.rstrip('\\/'))
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
    Handles:
    - input_dir/latest/test-results
    - input_dir/job-*/test-results
    - input_dir/test-results
    - input_dir (if input_dir is already test-results)
    - Recursive search for test-results inside input_dir
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
    Given an input directory (which may be unit root, latest, job-*, or test-results),
    resolve and return the top-level raw log folder (unit root).
    """
    abs_input = os.path.abspath(input_dir.strip(' "\' \t\r\n'))
    try:
        tr = find_test_results_dir(abs_input)
        unit_root = os.path.dirname(tr)
        if os.path.basename(unit_root) == 'latest' or os.path.basename(unit_root).startswith('job-'):
            unit_root = os.path.dirname(unit_root)
        return unit_root
    except Exception:
        return abs_input

def process_single_extraction(input_dir_raw, target_sn_raw, output_base_raw):
    """
    Core extraction function for a single unit. Returns a result dict.
    """
    input_dir = os.path.abspath(input_dir_raw.strip(' "\' \t\r\n'))
    target_sn = target_sn_raw.strip(' "\' \t\r\n')
    is_chassis_4u = target_sn.startswith("FVB")
    is_chassis_2u = target_sn.startswith("SGF")
    is_chassis = is_chassis_2u or is_chassis_4u

    unit_root = get_log_unit_root(input_dir)
    parent_dir = os.path.dirname(unit_root)

    # Smart default output base dir if not provided: default to parent of input folder
    if not output_base_raw:
        output_base_raw = parent_dir

    if is_chassis_4u:
        print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS 4U]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng sản phẩm: {Color.MAGENTA}Chassis 4U (Juno){Color.RESET}")
        out_dir, saved_paths = extract_chassis_4u_logs(input_dir, target_sn, output_base_raw)
        print(f"{Color.BRIGHT_GREEN}✔ Đã tạo {len(saved_paths)} file báo cáo Chassis 4U tại:{Color.RESET}")
        print(f"  {Color.BOLD}{Color.WHITE}➜ {out_dir}{Color.RESET}")

        return {
            "sn": target_sn,
            "unit_type": "Chassis 4U",
            "controller": "-",
            "status": "SUCCESS",
            "error": None,
            "out_dir": out_dir,
            "paths": saved_paths
        }

    out_dir, chassis_file_path = resolve_output_paths(output_base_raw, target_sn, is_chassis, unit_root=unit_root)

    # Find test-results directory inside input_dir (handles job-*, latest, or direct test-results)
    test_results_dir = find_test_results_dir(input_dir)

    saved_paths = []

    if is_chassis_2u:
        print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ CHASSIS 2U]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng sản phẩm: {Color.MAGENTA}Chassis (SGF){Color.RESET}")
        vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
        vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
        print(f"{Color.BLUE}📂 Log nguồn:{Color.RESET} {Color.GRAY}{vpd_log_path}{Color.RESET}")
        
        clean_lines = clean_log_lines(vpd_log_path)
        extracted_lines = extract_chassis_vpd(clean_lines)

        write_extracted_file(chassis_file_path, extracted_lines, trim_last_newline=True)
        saved_paths.append(chassis_file_path)
        print(f"{Color.BRIGHT_GREEN}✔ Đã tạo file báo cáo Chassis ({len(extracted_lines)} dòng) tại:{Color.RESET}")
        print(f"  {Color.BOLD}{Color.WHITE}➜ {chassis_file_path}{Color.RESET}")
        
        return {
            "sn": target_sn,
            "unit_type": "Chassis",
            "controller": "-",
            "status": "SUCCESS",
            "error": None,
            "out_dir": out_dir,
            "paths": saved_paths
        }
    else:
        folder_name = os.path.basename(input_dir.rstrip('\\/'))
        is_psu = target_sn.startswith("PM") or "DYJW5" in folder_name or "0R4C4" in folder_name or check_is_psu(test_results_dir, folder_name)
        is_rpc73 = check_is_iom_rpc73(test_results_dir)

        if is_psu:
            psu_short, psu_full = detect_psu_model_info(test_results_dir, folder_name)
            out_lines, unit_id = extract_psu_logs(test_results_dir, target_sn)
            pcm_name = "PCM 1" if unit_id == "psu0" else "PCM 2"
            print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ {psu_short.upper()}]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng sản phẩm: {Color.MAGENTA}{psu_full}{Color.RESET} │ Unit: {Color.YELLOW}{unit_id} ({pcm_name}){Color.RESET}")

            psu_report_name = "Controller FW, Drive FW, Serial Number Tracking & Test History.txt"
            psu_out_path = os.path.join(out_dir, psu_report_name)
            write_extracted_file(psu_out_path, out_lines, trim_last_newline=True)
            saved_paths.append(psu_out_path)
            print(f"{Color.BRIGHT_GREEN}✔ Đã lưu {psu_report_name} ({len(out_lines)} dòng) tại:{Color.RESET}")
            print(f"  {Color.BOLD}{Color.WHITE}➜ {psu_out_path}{Color.RESET}")

            return {
                "sn": target_sn,
                "unit_type": psu_short,
                "controller": unit_id,
                "status": "SUCCESS",
                "error": None,
                "out_dir": out_dir,
                "paths": saved_paths
            }
        elif is_rpc73:
            vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
            vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
            detected_ctrl = detect_rpc73_controller_from_vpd(clean_log_lines(vpd_log_path), target_sn)
            controller = detected_ctrl if detected_ctrl else determine_controller(folder_name, target_sn)

            print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ IOM RPC73]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng sản phẩm: {Color.MAGENTA}IOM RPC73{Color.RESET} │ Controller: {Color.YELLOW}{controller}{Color.RESET}")

            rpc73_lines = extract_iom_rpc73(test_results_dir, target_sn, controller)
            fw_vpd_out_path = os.path.join(out_dir, "FW_VPD.txt")
            write_extracted_file(fw_vpd_out_path, rpc73_lines, trim_last_newline=True)
            saved_paths.append(fw_vpd_out_path)
            print(f"{Color.BRIGHT_GREEN}✔ Đã lưu FW_VPD.txt ({len(rpc73_lines)} dòng) tại:{Color.RESET}")
            print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_vpd_out_path}{Color.RESET}")

            return {
                "sn": target_sn,
                "unit_type": "IOM RPC73",
                "controller": controller,
                "status": "SUCCESS",
                "error": None,
                "out_dir": out_dir,
                "paths": saved_paths
            }
        else:
            controller = determine_controller(folder_name, target_sn)
            print(f"\n{Color.BRIGHT_CYAN}⚡ [XỬ LÝ IO]{Color.RESET} Target SN: {Color.BOLD}{Color.WHITE}{target_sn}{Color.RESET} │ Dòng sản phẩm: {Color.MAGENTA}IO (SAF){Color.RESET} │ Controller: {Color.YELLOW}{controller}{Color.RESET}")

            # 1. Process FW.txt
            fw_step_dir = find_step_dir(test_results_dir, "check_and_load_fw_test")
            fw_log_path = os.path.join(fw_step_dir, "debug.log")
            print(f"{Color.BLUE}📂 [FW Log]:{Color.RESET} {Color.GRAY}{fw_log_path}{Color.RESET}")
            fw_clean_lines = clean_log_lines(fw_log_path)
            fw_extracted = extract_fw(fw_clean_lines, controller)

            fw_out_path = os.path.join(out_dir, "FW.txt")
            write_extracted_file(fw_out_path, fw_extracted, trim_last_newline=True)
            saved_paths.append(fw_out_path)
            print(f"{Color.BRIGHT_GREEN}✔ Đã lưu FW.txt ({len(fw_extracted)} dòng) tại:{Color.RESET}")
            print(f"  {Color.BOLD}{Color.WHITE}➜ {fw_out_path}{Color.RESET}")

            # 2. Process VPD.txt
            vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
            vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
            print(f"{Color.BLUE}📂 [VPD Log]:{Color.RESET} {Color.GRAY}{vpd_log_path}{Color.RESET}")
            vpd_clean_lines = clean_log_lines(vpd_log_path)
            vpd_extracted = extract_vpd(vpd_clean_lines, controller)

            vpd_out_path = os.path.join(out_dir, "VPD.txt")
            write_extracted_file(vpd_out_path, vpd_extracted, trim_last_newline=True)
            saved_paths.append(vpd_out_path)
            print(f"{Color.BRIGHT_GREEN}✔ Đã lưu VPD.txt ({len(vpd_extracted)} dòng) tại:{Color.RESET}")
            print(f"  {Color.BOLD}{Color.WHITE}➜ {vpd_out_path}{Color.RESET}")

            return {
                "sn": target_sn,
                "unit_type": "IO",
                "controller": controller,
                "status": "SUCCESS",
                "error": None,
                "out_dir": out_dir,
                "paths": saved_paths
            }


def get_script_dir():
    """
    Get absolute directory path where extract_mfg_logs.py (or frozen executable) is located.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))

def generate_sample_csv(output_csv_path="mau_danh_sach_log.csv"):
    """
    Generate a template CSV file for batch log processing in the script's directory.
    """
    if not os.path.isabs(output_csv_path):
        script_dir = get_script_dir()
        abs_csv = os.path.join(script_dir, output_csv_path)
    else:
        abs_csv = os.path.abspath(output_csv_path)

    sample_content = [
        ["LogPath", "TargetSN", "OutputBaseDir (De trong = Mac dinh thu muc me cua LogPath)"],
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
    Parse CSV or TXT file into list of batch items: (log_path, target_sn, output_base_dir)
    """
    abs_path = os.path.abspath(csv_path.strip(' "\' \t\r\n'))
    if not os.path.exists(to_long_path(abs_path)):
        raise FileNotFoundError(f"File CSV không tồn tại: {from_long_path(abs_path)}")

    batch_items = []
    with open(to_long_path(abs_path), 'r', encoding='utf-8-sig', errors='ignore') as f:
        # Detect delimiter (, or ;)
        first_line = f.readline()
        f.seek(0)
        delimiter = ';' if ';' in first_line and ',' not in first_line else ','
        
        reader = csv.reader(f, delimiter=delimiter)
        header = None
        for row in reader:
            if not row or not any(field.strip() for field in row):
                continue
            # Skip header line if present
            if header is None and ("logpath" in row[0].lower() or "link" in row[0].lower() or "path" in row[0].lower()):
                header = row
                continue
            
            log_path = row[0].strip(' "\' \t\r\n') if len(row) > 0 else ""
            target_sn = row[1].strip(' "\' \t\r\n') if len(row) > 1 else ""
            output_base = row[2].strip(' "\' \t\r\n') if len(row) > 2 else ""

            if log_path:
                batch_items.append((log_path, target_sn, output_base))

    return batch_items

def scan_parent_folder_for_logs(parent_folder):
    """
    Scan parent folder for subdirectories containing raw test logs (job-* and test-results/).
    Returns list of items: (log_path, target_sn, output_base)
    """
    abs_parent = os.path.abspath(parent_folder.strip(' "\' \t\r\n'))
    if not os.path.exists(to_long_path(abs_parent)):
        raise FileNotFoundError(f"Thư mục không tồn tại: {from_long_path(abs_parent)}")

    found_items = []
    
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
        for root, dirs, files in os.walk(to_long_path(abs_parent)):
            if 'test-results' in dirs:
                parent_of_tr = from_long_path(root)
                if os.path.basename(parent_of_tr) in ['latest'] or os.path.basename(parent_of_tr).startswith('job-'):
                    unit_dir = os.path.dirname(parent_of_tr)
                else:
                    unit_dir = parent_of_tr
                
                if unit_dir not in target_dirs:
                    target_dirs.append(unit_dir)

    for log_dir in target_dirs:
        detected_sns = detect_sns_from_folder(log_dir)
        if not detected_sns:
            continue

        unit_root = get_log_unit_root(log_dir)
        default_base = os.path.dirname(unit_root)

        # For IO units with 2 SNs, process both ctrla and ctrlb automatically!
        if len(detected_sns) == 2 and not (detected_sns[0].startswith("SGF") or detected_sns[0].startswith("FVB")):
            found_items.append((log_dir, detected_sns[0], default_base))
            found_items.append((log_dir, detected_sns[1], default_base))
        else:
            for sn in detected_sns:
                found_items.append((log_dir, sn, default_base))

    return found_items

def print_batch_summary_table(results):
    """
    Print nicely formatted ANSI summary table of batch extraction results.
    """
    print(f"\n{Color.BRIGHT_CYAN}┌──────────────────────────────────────────────────────────────────────────────────────────────────┐{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}│{Color.RESET}                           {Color.BOLD}{Color.WHITE}BẢNG TỔNG HỢP KẾT QUẢ TRÍCH XUẤT BATCH{Color.RESET}                          {Color.BRIGHT_CYAN}       │{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}├────┬──────────────────┬────────────┬────────────┬────────────┬───────────────────────────────────┤{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}│{Color.RESET} {Color.BOLD}STT{Color.RESET}│ {Color.BOLD}Target SN        {Color.RESET}│  {Color.BOLD}Dòng SP   {Color.RESET}│ {Color.BOLD}Controller {Color.RESET}│ {Color.BOLD}Trạng thái {Color.RESET}│ {Color.BOLD}Thư mục lưu                       {Color.RESET}{Color.BRIGHT_CYAN}│{Color.RESET}")
    print(f"{Color.BRIGHT_CYAN}├────┼──────────────────┼────────────┼────────────┼────────────┼───────────────────────────────────┤{Color.RESET}")

    success_count = 0
    fail_count = 0

    for idx, item in enumerate(results, 1):
        sn = item.get("sn", "UNKNOWN")
        unit_type = item.get("unit_type", "-")
        controller = item.get("controller", "-")
        status = item.get("status", "FAIL")
        out_dir = item.get("out_dir", "-")

        if len(out_dir) > 33:
            out_dir_disp = "..." + out_dir[-30:]
        else:
            out_dir_disp = out_dir.ljust(33)

        if status == "SUCCESS":
            success_count += 1
            status_disp = f"{Color.BRIGHT_GREEN}SUCCESS     {Color.RESET}"
        else:
            fail_count += 1
            status_disp = f"{Color.BRIGHT_RED}FAIL        {Color.RESET}"

        sn_disp = sn.ljust(16)
        unit_disp = unit_type.ljust(9)
        ctrl_disp = controller.ljust(10)

        print(f"{Color.BRIGHT_CYAN}│{Color.RESET} {str(idx).ljust(3)}│ {Color.BOLD}{Color.WHITE}{sn_disp}{Color.RESET} │ {Color.MAGENTA}{unit_disp}{Color.RESET} │ {Color.YELLOW}{ctrl_disp}{Color.RESET} │{status_disp}│ {Color.GRAY}{out_dir_disp}{Color.RESET}{Color.BRIGHT_CYAN} │{Color.RESET}")

    print(f"{Color.BRIGHT_CYAN}└────┴──────────────────┴────────────┴────────────┴────────────┴───────────────────────────────────┘{Color.RESET}")
    print(f"\n{Color.BOLD}Thống kê:{Color.RESET} Tổng số: {len(results)} │ {Color.BRIGHT_GREEN}Thành công: {success_count}{Color.RESET} │ {Color.BRIGHT_RED}Thất bại: {fail_count}{Color.RESET}\n")

def run_batch_extraction(batch_items):
    """
    Run extraction loop over a list of batch items.
    """
    results = []
    total = len(batch_items)
    print(f"\n{Color.BRIGHT_YELLOW}🚀 Bắt đầu trích xuất hàng loạt ({total} mục trong danh sách)...{Color.RESET}")
    print(f"{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")

    for idx, (log_path, target_sn, output_base) in enumerate(batch_items, 1):
        print(f"\n{Color.BRIGHT_CYAN}[{idx}/{total}]{Color.RESET} Đang xử lý log: {Color.GRAY}{log_path}{Color.RESET}")
        
        # If target_sn is empty, auto-detect from folder
        if not target_sn:
            sns = detect_sns_from_folder(log_path)
            target_sn = sns[0] if sns else ""

        if not target_sn:
            print(f"  {Color.RED}✖ Không thể nhận diện Target SN cho thư mục này. Bỏ qua.{Color.RESET}")
            results.append({
                "sn": "N/A",
                "unit_type": "-",
                "controller": "-",
                "status": "FAIL",
                "error": "Missing Target SN",
                "out_dir": "-"
            })
            continue

        try:
            res = process_single_extraction(log_path, target_sn, output_base)
            results.append(res)
        except Exception as e:
            print(f"  {Color.RED}✖ Lỗi khi trích xuất SN {target_sn}: {e}{Color.RESET}")
            results.append({
                "sn": target_sn,
                "unit_type": "Chassis 4U" if target_sn.startswith("FVB") else ("Chassis" if target_sn.startswith("SGF") else ("PSU" if target_sn.startswith("PM") else "IO")),
                "controller": "-",
                "status": "FAIL",
                "error": str(e),
                "out_dir": "-"
            })

    print_batch_summary_table(results)

def get_single_key_choice(prompt_text, valid_keys, default_key="1"):
    """
    Displays prompt_text and gets a single key choice instantly on Windows without waiting for Enter.
    If Enter (\r or \n) is pressed, returns default_key.
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
                elif ch == '\x03': # Ctrl+C
                    print()
                    raise KeyboardInterrupt
        except Exception:
            pass
    
    # Fallback to standard input() if non-win32 or msvcrt fails
    inp = input().strip(' "\' \t\r\n')
    return inp if inp in valid_keys else default_key

def main():
    parser = argparse.ArgumentParser(description="Trích xuất log sản xuất tự động cho IO (FW.txt, VPD.txt) và Chassis (<SN>.txt).")
    parser.add_argument("--input-dir", required=False, default=None, help="Path to raw test log directory.")
    parser.add_argument("--target-sn", required=False, default=None, help="Target serial number (e.g. SAFVN... or SGFVN...).")
    parser.add_argument("--output-dir", required=False, default=None, help="Path to output base directory.")
    parser.add_argument("--batch-dir", required=False, default=None, help="Path to parent folder containing multiple raw log subfolders.")
    parser.add_argument("--csv-file", required=False, default=None, help="Path to CSV/TXT file containing list of logs.")
    parser.add_argument("--generate-csv-template", action="store_true", help="Generate sample CSV input file.")
    parser.add_argument("--in-terminal", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.generate_csv_template:
        generate_sample_csv("mau_danh_sach_log.csv")
        return

    # Non-interactive CLI flags for batch execution
    if args.csv_file:
        batch_items = parse_csv_file(args.csv_file)
        run_batch_extraction(batch_items)
        return

    if args.batch_dir:
        batch_items = scan_parent_folder_for_logs(args.batch_dir)
        run_batch_extraction(batch_items)
        return

    # Non-interactive single unit mode
    if args.input_dir and args.target_sn:
        res = process_single_extraction(args.input_dir, args.target_sn, args.output_dir)
        print_batch_summary_table([res])
        return

    # Interactive Menu Selection
    print_header()
    print(f"{Color.BRIGHT_YELLOW}Vui lòng chọn chế độ làm việc:{Color.RESET}")
    print(f"   {Color.CYAN}[1]{Color.RESET} Trích xuất 1 thư mục log đơn lẻ (Single Folder Mode)")
    print(f"   {Color.CYAN}[2]{Color.RESET} Quét và trích xuất hàng loạt từ thư mục gốc (Batch Subfolders Scan)")
    print(f"   {Color.CYAN}[3]{Color.RESET} Đọc danh sách trích xuất từ file CSV / TXT (Batch CSV Import)")
    print(f"   {Color.CYAN}[4]{Color.RESET} Tạo file CSV mẫu (mau_danh_sach_log.csv)\n")

    prompt_str = f"   {Color.CYAN}👉 Chọn nhanh số (1-4) hoặc nhấn Enter để chọn [1]: {Color.RESET}"
    mode_choice = get_single_key_choice(prompt_str, ["1", "2", "3", "4"], default_key="1")

    if mode_choice == "4":
        generate_sample_csv("mau_danh_sach_log.csv")
        return
    elif mode_choice == "3":
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Batch CSV Mode] Đọc danh sách từ file CSV/TXT:{Color.RESET}")
        csv_file_path = input(f"   {Color.CYAN}👉 Nhập đường dẫn file CSV/TXT (Mặc định: mau_danh_sach_log.csv): {Color.RESET}").strip(' "\' \t\r\n')
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
        run_batch_extraction(batch_items)
        return
    elif mode_choice == "2":
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Batch Subfolders Scan] Quét hàng loạt từ thư mục gốc:{Color.RESET}")
        parent_dir = input(f"   {Color.CYAN}👉 Nhập đường dẫn thư mục gốc chứa nhiều log: {Color.RESET}").strip(' "\' \t\r\n')
        while not parent_dir or not os.path.exists(parent_dir):
            print(f"   {Color.RED}✖ Thư mục không tồn tại. Vui lòng nhập lại!{Color.RESET}")
            parent_dir = input(f"   {Color.CYAN}👉 Nhập đường dẫn thư mục gốc: {Color.RESET}").strip(' "\' \t\r\n')

        batch_items = scan_parent_folder_for_logs(parent_dir)
        if not batch_items:
            print(f"\n{Color.RED}✖ Không tìm thấy thư mục log hợp lệ nào trong {parent_dir}{Color.RESET}\n")
            return
        run_batch_extraction(batch_items)
        return
    else:
        # Mode 1: Single Folder Mode
        print(f"\n{Color.BRIGHT_YELLOW}📌 [Single Folder Mode] Trích xuất đơn lẻ 1 thư mục log:{Color.RESET}\n")

        while True:
            prompt_str = f"{Color.BRIGHT_YELLOW}📌 [1/3] Nhập đường dẫn thư mục log đầu vào (Input Dir):{Color.RESET}\n   {Color.CYAN}👉 {Color.RESET}"
            input_dir_raw = input(prompt_str).strip(' "\' \t\r\n')
            if input_dir_raw and os.path.exists(input_dir_raw):
                break
            print(f"   {Color.RED}✖ Thư mục không tồn tại. Vui lòng kiểm tra lại đường dẫn!{Color.RESET}\n")

        input_dir = os.path.abspath(input_dir_raw.strip(' "\' \t\r\n'))
        detected_sns = detect_sns_from_folder(input_dir)

        if detected_sns:
            if len(detected_sns) == 1 or detected_sns[0].startswith("SGF"):
                sn_item = detected_sns[0]
                unit_tag = "Chassis 4U" if sn_item.startswith("FVB") else ("Chassis" if sn_item.startswith("SGF") else ("PSU" if sn_item.startswith("PM") else "IO"))
                print(f"\n{Color.BRIGHT_YELLOW}⚡ [TỰ ĐỘNG CHỌN SN {unit_tag.upper()}]:{Color.RESET} {Color.BOLD}{Color.WHITE}{sn_item}{Color.RESET}")
                target_sn_raw = sn_item
            else:
                print(f"\n{Color.BRIGHT_YELLOW}📌 [2/3] Phát hiện Serial Number trong tên thư mục. Vui lòng chọn:{Color.RESET}")
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
                target_sn_raw = input(prompt_str).strip(' "\' \t\r\n')
                if target_sn_raw:
                    break
                print(f"   {Color.RED}✖ Target SN không được để trống. Vui lòng nhập lại!{Color.RESET}\n")

        target_sn = target_sn_raw.strip(' "\' \t\r\n')
        unit_root = get_log_unit_root(input_dir)
        default_output_base = os.path.dirname(unit_root)

        target_default_dir = default_output_base if os.path.basename(default_output_base.rstrip('\\/')) == target_sn else os.path.join(default_output_base, target_sn)
        prompt_str = f"\n{Color.BRIGHT_YELLOW}📌 [3/3] Nhập thư mục xuất báo cáo (Mặc định: {target_default_dir}):{Color.RESET}\n   {Color.CYAN}👉 Nhấn Enter để dùng mặc định hoặc dán đường dẫn khác: {Color.RESET}"
        output_dir_raw = input(prompt_str).strip(' "\' \t\r\n')
        if not output_dir_raw:
            output_dir_raw = default_output_base
            print(f"   {Color.GREEN}➜ Đã chọn mặc định: {target_default_dir}{Color.RESET}")

        print(f"\n{Color.GRAY}─────────────────────────────────────────────────────────────────────────────{Color.RESET}")
        res = process_single_extraction(input_dir, target_sn, output_dir_raw)
        print_batch_summary_table([res])

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Color.YELLOW}[!] Thao tác đã bị hủy bởi người dùng (Ctrl+C).{Color.RESET}\n")
        sys.exit(0)
