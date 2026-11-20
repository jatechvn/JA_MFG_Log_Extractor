"""Report parsers for standard IO controllers and Chassis 2U."""


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
