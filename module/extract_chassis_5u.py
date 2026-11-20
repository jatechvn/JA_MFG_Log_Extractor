"""Dell 5U chassis FW/VPD extraction for W47DG and 7PNTN."""

import os
import re

from .log_io import (
    find_step_dir,
    find_test_results_dir,
    get_default_reports_dir,
    get_log_package_pn,
    get_log_unit_root,
    to_long_path,
    write_extracted_file,
)


def check_is_chassis_5u_dell(test_results_dir, folder_name="", part_number=""):
    """
    Check if a log corresponds to Dell 5U chassis (W47DG, 7PNTN, or 5U84).
    """
    pn = part_number.strip().upper() or get_log_package_pn(folder_name)
    if pn in ("7PNTN", "W47DG") or "W47DG" in folder_name or "5U_Dell" in folder_name or "5U84" in folder_name:
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


def extract_chassis_5u_midplane_validation(lines, part_number="W47DG"):
    """Read one complete Midplane status block from vpd_validation (Step 07)."""
    markers = ("Midplane VPD structure", "Midplane VPD CRC", "Midplane CPLD")
    for i, line in enumerate(lines):
        if '|0250|Midplane VPD structure' not in line:
            continue
        block = lines[i:i + 3]
        if len(block) == 3 and all(
            f'|0250|{marker}' in row for marker, row in zip(markers, block)
        ):
            return [row[row.index('|0250|'):].rstrip('\r\n') for row in block]
    raise ValueError(f"{part_number}: incomplete Midplane status block in Step 07 vpd_validation; Step 02 is not a valid fallback.")


def strip_5u_log_code(line):
    """Remove one leading log code, leaving payload separators intact."""
    return re.sub(r'^\|\d{4}\|', '', line, count=1)


def extract_7pntn_fan_fw(lines, midplane):
    """Read all five controller pairs from the selected Step 07 snapshot."""
    fields = {}
    in_snapshot = False
    for i, line in enumerate(lines):
        if '|0250|Midplane VPD structure' in line:
            if in_snapshot:
                break
            in_snapshot = len(lines) >= i + 3 and all(
                lines[i + offset].endswith(row) for offset, row in enumerate(midplane)
            )
        if not in_snapshot:
            continue
        match = re.search(r'\|0250\|(Fan Controller ([0-4]) (config|deviceFW)\s*:\s*\S.*)$', line)
        if match:
            key = (int(match[2]), match[3])
            if key in fields and fields[key] != match[1]:
                raise ValueError(f"7PNTN Step 07: conflicting Fan Controller {key[0]} {key[1]}")
            fields[key] = match[1]
    expected = [(i, field) for i in range(5) for field in ('config', 'deviceFW')]
    for i, field in expected:
        if (i, field) not in fields:
            raise ValueError(f"7PNTN Step 07: missing Fan Controller {i} {field}")
    return [fields[key] for key in expected]


def extract_7pntn_wwn(lines, match_idx, block):
    """Match the preceding WWN read to the two TWI outputs and validations."""
    addresses = []
    for bus, output, validation in zip((2, 1), block[1:3], block[3:5]):
        prefix = rf'TWI bus {bus} vpd_type 2: \[([0-9a-fA-F]{{16}})\]'
        command = re.fullmatch(prefix + r'\s*', output)
        checked = re.fullmatch(prefix + r'\s*; want: \[([0-9a-fA-F]{16})\]\s*-> match\s*', validation)
        if not command or not checked:
            raise ValueError(f"7PNTN Step 07: invalid WWN validation for TWI bus {bus}")
        addresses.extend(value.lower() for value in (command[1], *checked.groups()))
    if len(set(addresses)) != 1:
        raise ValueError("7PNTN Step 07: WWN mismatch between TWI buses or expected values")
    # Stop at an earlier type-2 validation result so a prior pass cannot fill a gap.
    for i in range(match_idx - 1, -1, -1):
        if re.search(r'\|3673\|TWI bus [12] vpd_type 2:.*->', lines[i]):
            break
        if re.search(r'\|\d{4}\|WWN:', lines[i]):
            value = re.search(r'\|\d{4}\|(WWN: ([0-9a-fA-F]{16}))$', lines[i])
            read = re.search(r'\|\d{4}\|(get_wwn: WWN = ([0-9a-fA-F]{16}))$', lines[i - 1]) if i else None
            if value and read and value[2].lower() == read[2].lower() == addresses[0]:
                return [read[1], value[1]]
            raise ValueError("7PNTN Step 07: WWN read pair is incomplete or does not match TWI validation")
        if re.search(r'\|\d{4}\|get_wwn: WWN =', lines[i]):
            raise ValueError("7PNTN Step 07: incomplete WWN read pair")
    raise ValueError("7PNTN Step 07: missing get_wwn/WWN pair for set_midplanevpd 2")


def extract_7pntn_fan_vpd(lines):
    """Read the first six left-column rows of each Step 06 Fan VPD block."""
    blocks = {}
    for i, line in enumerate(lines):
        header = line.split(' | ', 1)[0].rstrip()
        match = re.match(r'^VPD (12[2-6]) \(0\) - Fan Controller VPD (\d+) - ', header)
        if not match:
            continue
        vpd_id = int(match[1])
        if int(match[2]) != vpd_id - 121:
            raise ValueError(f"7PNTN Step 06: Fan Controller number does not match VPD {vpd_id}")
        block = [header]
        for row_no, offset in enumerate(range(0, 0x60, 0x10), 1):
            row = lines[i + row_no][:72] if i + row_no < len(lines) else ''
            if not re.match(rf'^{offset:04x}:(?: [0-9a-fA-F]{{2}}){{16}}  ', row, re.IGNORECASE):
                raise ValueError(f"7PNTN Step 06: VPD {vpd_id} missing or invalid offset {offset:04x}")
            block.append(row.rstrip())
        if vpd_id in blocks and block != blocks[vpd_id]:
            raise ValueError(f"7PNTN Step 06: conflicting Fan Controller blocks for VPD {vpd_id}")
        blocks[vpd_id] = block
    for vpd_id in range(122, 127):
        if vpd_id not in blocks:
            raise ValueError(f"7PNTN Step 06: missing Fan Controller VPD {vpd_id}")
    return [blocks[vpd_id] for vpd_id in range(122, 127)]


def extract_7pntn_customer_validation(lines):
    """Render only the Customer VPD 18 fields required by the 7PNTN report."""
    identity = ('part_number', 'serial_number', 'revision', 'customer_pn', 'customer_sn', 'customer_rev')
    layout = ('FRUID Ver', 'oem_id', 'config_selector', 'reserved')
    required = (*identity, *layout, 'fru_description')
    header = []
    fields = {}
    current = None
    for line in lines:
        match = re.search(r'\|(\d{4})\|(.*)$', line)
        if not match:
            continue
        code, payload = match.groups()
        row = match[0]
        if not header:
            if code == '3893' and payload.startswith('Checking chassis customer VPD (ID = 18)'):
                header.append(row)
            continue
        if code in ('3891', '3893'):
            break
        if len(header) < 3 and code in ('3894', '3895'):
            header.append(row)
            continue
        if code == '3903':
            name = re.match(r'name: ([^,]+),', payload)
            current = name[1] if name and name[1] in required else None
            if current:
                if current in fields:
                    raise ValueError(f"7PNTN Step 07: duplicate Customer VPD 18 field {current}")
                fields[current] = []
        if current:
            fields[current].append(row)
            if code == '4010':
                if current == 'fru_description':
                    break
                current = None

    if [row[:6] for row in header] != ['|3893|', '|3894|', '|3895|']:
        raise ValueError("7PNTN Step 07: missing Customer VPD 18 validation header")
    for name in required:
        block = fields.get(name, [])
        if [row[:6] for row in block[-2:]] != ['|3993|', '|4010|']:
            raise ValueError(f"7PNTN Step 07: missing or incomplete Customer VPD 18 field {name}")
    return [row for name in identity for row in fields[name]] + [''] + header + [
        row for name in layout for row in fields[name]
    ] + [''] + fields['fru_description']


def extract_chassis_5u_dell_logs(input_dir, target_sn, output_base, part_number=""):
    """
    Extract Chassis 5U Dell report files, with the 7PNTN layout when selected:
    1. FW.txt:
       - Midplane VPD structure, CRC, CPLD from Step 07 vpd_validation only
       - Sled 1/2 Element 0-3 Firmware (8 lines)
       - Expander SAS addresses sorted exp:0 to exp:7 (8 lines from Step 07)
    2. VPD.txt:
       - Section 1 (Step 07): VPD 16 Midplane A hex dump (7PNTN ends at 0090:)
       - Section 2 (Step 07): VPD 18 Midplane Customer A hex dump (7PNTN keeps 0000: to 00a0: and 0360:/0370:)
       - Sections 3-10 (Step 06): exp:0..7 VPD 48 Canister hex dumps (sorted exp:0..7)
       - Sections 11-17 (Step 07): Midplane VPD verification for set_midplanevpd 2..8
       - Section 18 (Step 07): Customer VPD validation table (part_number down to fru_description match)
    """
    abs_input = os.path.abspath(input_dir.strip(' "\' \t\r\n'))
    test_results_dir = find_test_results_dir(abs_input)
    pn = part_number.strip().upper() or get_log_package_pn(os.path.basename(get_log_unit_root(abs_input)))
    is_7pntn = pn == "7PNTN"
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

    # 1. Generate FW.txt. Preserve existing Sled FW selection from Step 02.
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

    # Midplane status must reflect validation, never the pre-write Step 02 state.
    fw_b1 = extract_chassis_5u_midplane_validation(s07_lines, part_number="7PNTN" if is_7pntn else "W47DG")

    # Expander SAS addresses from Step 07
    exp_sas_dict = {}
    for l in s07_lines:
        m = re.search(r'(\|3673\|)(exp:\d+:\s+vpd_type 2:\s+\[[0-9a-fA-F]+\])', l)
        if m:
            exp_id = re.search(r'exp:(\d+)', m.group(2)).group(1)
            exp_sas_dict[int(exp_id)] = m.group(1) + m.group(2)
    fw_b3 = [exp_sas_dict[k] for k in sorted(exp_sas_dict.keys())]

    fan_fw = extract_7pntn_fan_fw(s07_lines, fw_b1) if is_7pntn else []
    if is_7pntn and (len(fw_b2) != 8 or set(exp_sas_dict) != set(range(8))):
        raise ValueError("7PNTN FW: missing Sled firmware (Step 02) or expander SAS (Step 07)")
    fw_all_lines = fw_b1 + [""] + fan_fw + fw_b2 + [""] + fw_b3
    if is_7pntn:
        fw_all_lines = [strip_5u_log_code(line) for line in fw_all_lines]
    fw_out_path = os.path.join(output_dir, "FW.txt")

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
                if l.strip().startswith('0090:' if is_7pntn else '00c0:'):
                    break

    vpd_b2 = []
    in_b2 = False
    for l in s07_lines:
        if '|3891|Reading customer VPD (ID = 18)' in l:
            if is_7pntn and in_b2:
                break
            idx = l.find('|3891|')
            vpd_b2.append(l[idx:].rstrip())
            in_b2 = True
            continue
        if in_b2:
            m = re.search(r'\|(\d{4})\|(.*)$', l)
            if m:
                clean_l = f'|{m.group(1)}|{m.group(2)}'.rstrip()
                if is_7pntn:
                    if m.group(1) in ('3891', '3893'):
                        break
                    hex_row = re.match(r'^\|0509\|([0-9a-fA-F]{4}):', clean_l)
                    if hex_row and not (int(hex_row[1], 16) <= 0xa0 or int(hex_row[1], 16) in (0x360, 0x370)):
                        continue
                vpd_b2.append(clean_l)
                if ('|0509|0370:' if is_7pntn else '|0509|00b0:') in clean_l:
                    break

    exp_vpd_dict = {}
    for i, l in enumerate(s06_lines):
        if 'VPD 48 (1) - Canister' in l and '|' in l and l.startswith('exp:'):
            exp_id = int(l.split(':')[1])
            hdr = l.split(' | ', 1)[0].rstrip() if is_7pntn else l[:65]
            n_lines = 8 if exp_id == 0 and not is_7pntn else 6
            hex_lines = []
            for j in range(i + 1, i + 1 + n_lines):
                if is_7pntn:
                    offset = (j - i - 1) * 0x10
                    if j >= len(s06_lines) or not re.match(rf'^{offset:04x}:(?: [0-9a-fA-F]{{2}}){{16}}  ', s06_lines[j]):
                        raise ValueError(f"7PNTN Step 06: Canister VPD 48 exp:{exp_id} missing or invalid offset {offset:04x}")
                    hex_lines.append(s06_lines[j][:72].rstrip())
                else:
                    hex_lines.append(s06_lines[j][6:71])
            exp_vpd_dict[exp_id] = [hdr] + hex_lines
    exp_vpd_list = [exp_vpd_dict[k] for k in sorted(exp_vpd_dict.keys())]
    if is_7pntn:
        for vpd_id, block, prefix, expected in (
            (16, vpd_b1, '', range(0, 0xa0, 0x10)),
            (18, vpd_b2, '|0509|', (*range(0, 0xb0, 0x10), 0x360, 0x370)),
        ):
            offsets = [m[1].lower() for row in block if (m := re.match(re.escape(prefix) + r'([0-9a-fA-F]{4}):', row))]
            if offsets != [f'{offset:04x}' for offset in expected]:
                raise ValueError(f"7PNTN Step 07: VPD {vpd_id} missing or invalid hex offsets")
        if set(exp_vpd_dict) != set(range(8)):
            raise ValueError("7PNTN Step 06: missing or invalid Canister VPD 48 expander blocks")

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
        if is_7pntn and (match_idx is None or match_idx + 1 >= len(s07_lines)):
            raise ValueError(f"7PNTN Step 07: missing validation for set_midplanevpd {vpd_type}")
        for j in range(match_idx - 1, max(0, match_idx - 20), -1):
            if out_cmd_marker in s07_lines[j]:
                cmd_idx = j
                break
        if is_7pntn and (cmd_idx is None or cmd_idx + 2 >= match_idx):
            raise ValueError(f"7PNTN Step 07: missing command output for set_midplanevpd {vpd_type}")

        blk_lines = []
        hdr_l = s07_lines[cmd_idx]
        blk_lines.append(hdr_l[hdr_l.find('|0509|'):])
        blk_lines.append(s07_lines[cmd_idx + 1])
        blk_lines.append(s07_lines[cmd_idx + 2])
        l4 = s07_lines[match_idx]
        l5 = s07_lines[match_idx + 1]
        blk_lines.append(l4[l4.find('|3673|'):])
        blk_lines.append(l5[l5.find('|3673|'):])
        if is_7pntn:
            blk_lines = [strip_5u_log_code(row) for row in blk_lines]
            if not all(re.match(rf'^TWI bus {bus} vpd_type {vpd_type}:', row)
                       for bus, row in zip((2, 1, 2, 1), blk_lines[1:])) or not blk_lines[-1].rstrip().endswith('-> match'):
                raise ValueError(f"7PNTN Step 07: incomplete TWI validation for set_midplanevpd {vpd_type}")
            if vpd_type == 2:
                blk_lines[3:3] = extract_7pntn_wwn(s07_lines, match_idx, blk_lines)
        midplane_blocks.append(blk_lines)

    if is_7pntn:
        vpd_b18 = extract_7pntn_customer_validation(s07_lines)
    else:
        vpd_b18 = []
        in_b18 = False
        for l in s07_lines:
            if '|3903|name: part_number, size: 32' in l:
                in_b18 = True
            if in_b18:
                m = re.search(r'\|(\d{4})\|(.*)$', l)
                if m:
                    vpd_b18.append(m[0])
                    if m.group(1) == '3993' and 'fru_description' in '\n'.join(vpd_b18[-10:]):
                        break

    all_vpd_sections = [vpd_b1, vpd_b2] + exp_vpd_list + midplane_blocks + [vpd_b18]
    if is_7pntn:
        all_vpd_sections.extend(extract_7pntn_fan_vpd(s06_lines))
    vpd_full_text = '\n\n'.join('\n'.join(sec) for sec in all_vpd_sections)
    vpd_lines_out = [l + '\n' for l in vpd_full_text.splitlines()]
    vpd_out_path = os.path.join(output_dir, "VPD.txt")
    write_extracted_file(fw_out_path, [l + "\n" for l in fw_all_lines], trim_last_newline=True)
    saved_paths.append(fw_out_path)
    write_extracted_file(vpd_out_path, vpd_lines_out, trim_last_newline=True)
    saved_paths.append(vpd_out_path)

    return output_dir, saved_paths
