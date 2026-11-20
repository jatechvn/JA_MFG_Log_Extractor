"""IOM RPC73 and 9D57G canister FW/VPD parsing."""

import os
import re

from .log_io import clean_log_lines, find_step_dir, to_long_path


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

_RPC73_REVISION_HEADER = re.compile(r'^\|3898\|Checking (ctrl[ab]) customer VPD \(ID = 49\)')


def extract_rpc73_revision_vpd(lines, target_sn, *, full_validation=False):
    """Pair the target serial's VPD 49 dump with its selected validation layout."""
    end_field = 'fru_description' if full_validation else 'revision'
    starts = [i for i, row in enumerate(lines) if row.startswith('|0608|VPD 49 (1) - Canister Customer')]
    offsets = (*range(0, 0xb0, 0x10), 0x360, 0x370)
    expected_serial = target_sn.upper().encode('ascii', errors='replace')
    for start, end in zip(starts, starts[1:] + [len(lines)]):
        dump = {}
        for i in range(start + 2, end):
            match = re.match(r'^\|0509\|([0-9a-fA-F]{4}):((?: [0-9a-fA-F]{2}){16})\s', lines[i])
            if not match:
                break
            offset = int(match[1], 16)
            if offset in offsets:
                dump[offset] = (lines[i].rstrip('\r\n'), bytes.fromhex(match[2]))
        if not {0x20, 0x30, 0x40}.issubset(dump):
            continue
        # Read the entire 32-byte serial field starting at 0x28.
        serial = (dump[0x20][1][8:] + dump[0x30][1] + dump[0x40][1][:8]).split(b'\0', 1)[0]
        if serial.upper() != expected_serial:
            continue
        if not lines[start + 1].startswith('|0609|Header:') or set(dump) != set(offsets):
            raise ValueError(f"IOM RPC73 Step 07: incomplete VPD 49 hex dump for {target_sn}")
        boundary = next((i for i in range(start + 2, end) if lines[i].startswith(('|3896|Reading customer VPD', '|3898|Checking '))), None)
        match = _RPC73_REVISION_HEADER.match(lines[boundary]) if boundary is not None else None
        if not match:
            raise ValueError(f"IOM RPC73 Step 07: missing VPD 49 validation for {target_sn}")
        controller = match[1]
        in_end_field = False
        validated_serial = False
        in_serial = False
        for j in range(boundary + 1, end):
            row = lines[j]
            if row.startswith(('|3896|Reading customer VPD', '|3898|Checking ')):
                break
            if row.startswith('|3908|name: '):
                in_end_field = row.startswith(f'|3908|name: {end_field},')
                in_serial = row.startswith('|3908|name: serial_number,')
            if in_serial and re.fullmatch(r'\|4001\|\s*got:\s*\[' + re.escape(target_sn) + r'\]\s*', row, re.IGNORECASE):
                validated_serial = True
            if in_end_field and row.startswith('|4021|') and lines[j - 1].startswith('|4004|result:'):
                if not validated_serial:
                    raise ValueError(f"IOM RPC73 Step 07: VPD 49 validation serial does not match {target_sn}")
                hex_rows = [lines[start].rstrip('\r\n'), lines[start + 1].rstrip('\r\n')]
                hex_rows.extend(dump[offset][0] for offset in offsets)
                return controller, hex_rows, [line.rstrip('\r\n') for line in lines[boundary:j + 1]]
        raise ValueError(f"IOM RPC73 Step 07: incomplete VPD 49 {end_field} validation for {target_sn}")
    raise ValueError(f"IOM RPC73 Step 07: VPD 49 dump not found for {target_sn}")


def detect_rpc73_controller_from_vpd(s7_lines, target_sn):
    """
    Determine if target_sn corresponds to ctrla or ctrlb by searching VPD 49 hex blocks.
    """
    if any(_RPC73_REVISION_HEADER.match(row) for row in s7_lines):
        return extract_rpc73_revision_vpd(s7_lines, target_sn)[0]
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

def extract_iom_rpc73(test_results_dir, target_sn, controller, *, part_number=""):
    """
    Extract combined FW_VPD.txt report for IOM RPC73 units.
    - Section 1 (Step 2): Canister firmware (9 lines)
    - Section 2 (Step 2): FW match for controller (30 lines)
    - Section 3 (Step 7): VPD 49 hex dump (15 lines)
    - Section 4 (Step 7): Customer VPD validation through fru_description
      for PN RPC73 and 9D57G in the newer validation layout.
    """
    fw_step_dir = find_rpc73_fw_step_dir(test_results_dir)
    fw_log_path = os.path.join(fw_step_dir, "debug.log")
    s2_lines = clean_log_lines(fw_log_path)

    vpd_step_dir = find_step_dir(test_results_dir, "vpd_validation")
    vpd_log_path = os.path.join(vpd_step_dir, "debug.log")
    s7_lines = clean_log_lines(vpd_log_path)
    revision_layout = any(_RPC73_REVISION_HEADER.match(row) for row in s7_lines)
    if revision_layout:
        controller, new_dump, new_validation = extract_rpc73_revision_vpd(
            s7_lines, target_sn, full_validation=part_number in ("RPC73", "9D57G"),
        )

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

    if revision_layout:
        sec3, sec4 = new_dump, new_validation

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
