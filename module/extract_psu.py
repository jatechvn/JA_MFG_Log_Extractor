"""PSU 2U (DYJW5) and 5U (0R4C4) identification and report extraction."""

import ast
import os
import re

from .log_io import find_step_dir, to_long_path


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
    - Section 3 (Step 7): VPD 60 (psu0) or VPD 61 (psu1) hex dump:
        * PSU 2U (DYJW5): 0000: to 00a0: + blank line + 0360: to 0390: (117 lines total)
        * PSU 5U (0R4C4): 0000: to 0090: + blank line + 0360: to 0390: (116 lines total)
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

    # Section 3: VPD 60 / 61 hex from Step 7
    # - PSU 5U (0R4C4): 0000: to 0090: + blank line + 0360: to 0390: (116 lines total)
    # - PSU 2U (DYJW5): 0000: to 00a0: + blank line + 0360: to 0390: (117 lines total)
    is_psu_5u = any("0R4C4" in l or "PWR SPLY,5U" in l for l in s7)
    upper_hex_end = 0xa0 if is_psu_5u else 0xb0
    last_upper_addr = "0090" if is_psu_5u else "00a0"

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
            m = re.search(r'\|0509\|([0-9a-fA-F]{4}:.+)$', l)
            if m:
                hex_part = m.group(1).rstrip()
                addr = hex_part[:4].lower()
                if addr in [f"{x:04x}" for x in range(0, upper_hex_end, 0x10)]:
                    s3_lines.append(hex_part)
                    if addr == last_upper_addr:
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
