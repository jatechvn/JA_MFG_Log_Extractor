"""HPE MSA 2070 FC Controller (PN P61070-001) FW & Raw CLI log extraction."""

import ast
import copy
import os
import re
import xml.etree.ElementTree as ET

from .log_io import find_step_dir, get_log_package_pn, to_long_path

P61070_PART_NUMBER = "P61070-001"
P61070_CLI_REPORT_NAME = "FW.txt"
P61070_RAW_REPORT_NAME = "FW_RAW.md"

P61070_MFG_COMMANDS = (
    "show firmware-bundles",
    "show system",
    "show frus detail",
    "show configuration",
)

P61070_ALL_COMMANDS = (
    "show firmware-bundles",
    "show system",
    "show frus detail",
    "show configuration",
    "show certificates",
)

P61070_VERSION_FIELDS = (
    ("Storage Controller CPU Type:", "sc-cpu-type"),
    ("Bundle Version:", "bundle-version"),
    ("Base Bundle Version:", "bundle-base-version"),
    ("Build Date:", "build-date"),
    ("Storage Controller Code Version:", "sc-fw"),
    ("Storage Controller Code Baselevel:", "sc-baselevel"),
    ("ASIC Controller Version:", "sc-fu-version"),
    ("Storage Controller Loader Code Version:", "sc-loader"),
    ("CAPI Version:", "capi-version"),
    ("Management Controller Code Version:", "mc-fw"),
    ("Management Controller Loader Code Version:", "mc-loader"),
    ("Expander Controller Code Version:", "ec-fw"),
    ("CPLD Code Version:", "pld-rev"),
    ("Hardware Version:", "hw-rev"),
    ("Host Interface Module Version:", "him-rev"),
    ("Host Interface Module Model:", "him-model"),
    ("Backplane Type:", "backplane-type"),
    ("Host Interface Hardware (Chip) Version:", "host-channel_revision"),
    ("Disk Interface Hardware (Chip) Version:", "disk-channel_revision"),
    ("SC Boot Memory Reference Code Version:", "mrc-version"),
    ("CTK Version:", "ctk-version"),
    ("MC OS Version:", "mcos-version"),
    ("GEM Version:", "gem-version"),
    ("Help Version:", "pubs-version"),
    ("Translation Version:", "translation-version"),
)

_EXPECTED_FRU_LOCATIONS = {
    "A": "UPPER IOM SLOT",
    "B": "LOWER IOM SLOT",
}


def check_is_p61070(folder_name="", part_number=""):
    """Return True when the package or metadata PN is exactly P61070-001."""
    pn = (part_number or "").strip().upper()
    if not pn or pn == "-":
        pn = get_log_package_pn(folder_name or "")
    return pn == P61070_PART_NUMBER


def _xml_object_to_dict(obj_el):
    """Convert an MSA XML <OBJECT> element recursively into CTP's dict format."""
    item = {"object-name": obj_el.attrib.get("name", "")}
    for prop in obj_el.findall("PROPERTY"):
        name = prop.attrib.get("name", "")
        if name:
            item[name] = prop.text or ""
    for child in obj_el.findall("OBJECT"):
        basetype = child.attrib.get("basetype") or child.attrib.get("name", "")
        if basetype:
            item.setdefault(basetype, []).append(_xml_object_to_dict(child))
    return item


def _parse_xml_response(xml_text):
    """Parse an MSA <RESPONSE> XML payload into top-level grouped object lists."""
    root = ET.fromstring(xml_text)
    result = {}
    for child in root.findall("OBJECT"):
        basetype = child.attrib.get("basetype") or child.attrib.get("name", "")
        if basetype:
            result.setdefault(basetype, []).append(_xml_object_to_dict(child))
    return result


def _has_valid_status(cmd_data):
    """Check whether parsed command output is a dict with a non-empty status response."""
    if not isinstance(cmd_data, dict):
        return False
    statuses = cmd_data.get("status")
    if not isinstance(statuses, list) or not statuses:
        return False
    return any(isinstance(st, dict) and str(st.get("response", "")).strip() for st in statuses)


def _find_matching_step_dirs_desc(test_results_dir, pattern):
    """Return matching step directories inside test_results_dir ordered highest step first."""
    long_tr = to_long_path(test_results_dir)
    if not os.path.isdir(long_tr):
        return []
    candidates = []
    for item in os.listdir(long_tr):
        full_path = os.path.join(test_results_dir, item)
        if os.path.isdir(to_long_path(full_path)) and pattern in item:
            m = re.match(r"^(\d+)-", item)
            step_num = int(m.group(1)) if m else 0
            candidates.append((step_num, full_path))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [path for _, path in candidates]


def find_p61070_mfg_default_log(test_results_dir):
    """Locate the mfg restore default debug.log containing MSA show commands."""
    try:
        step_dir = find_step_dir(test_results_dir, "test_mfg_restore_default_setting")
    except FileNotFoundError:
        step_dir = find_step_dir(test_results_dir, "rbod_test_mfg_default")
    log_path = os.path.join(step_dir, "debug.log")
    if not os.path.isfile(to_long_path(log_path)):
        raise FileNotFoundError(f"P61070-001: missing debug.log in {step_dir}")
    return log_path


def find_p61070_certificates_log(test_results_dir):
    """Locate the post-remove-certs restore_default debug.log containing show certificates XML."""
    search_patterns = ("test_restore_defaults_factory_remove_certs", "restore_default")
    checked = set()
    for pattern in search_patterns:
        for step_dir in _find_matching_step_dirs_desc(test_results_dir, pattern):
            norm_dir = os.path.normpath(step_dir)
            if norm_dir in checked:
                continue
            checked.add(norm_dir)
            log_path = os.path.join(step_dir, "debug.log")
            long_log = to_long_path(log_path)
            if not os.path.isfile(long_log):
                continue
            with open(long_log, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if 'REQUEST="show certificates"' in content:
                return log_path
    raise ValueError("P61070-001: missing 'show certificates' XML response in restore_default steps")


def _extract_command_from_mfg_text(text, cmd):
    """Parse one command block from Step 62 text (dict line first, XML response fallback)."""
    dict_pattern = (
        r"(?:rbod_test_mfg_default\.py\|\d+\||L\d+\s+DEBUG\|\s*)"
        + re.escape(cmd)
        + r":[ \t]*\r?\n(\{[^\r\n]+\})"
    )
    dict_matches = re.findall(dict_pattern, text)
    for raw_dict in reversed(dict_matches):
        try:
            parsed = ast.literal_eval(raw_dict)
        except (SyntaxError, ValueError):
            continue
        if _has_valid_status(parsed):
            return parsed

    xml_pattern = (
        r'<RESPONSE\b[^>]*\bREQUEST="' + re.escape(cmd) + r'"[^>]*>.*?</RESPONSE>'
    )
    xml_matches = re.findall(xml_pattern, text, re.DOTALL)
    for raw_xml in reversed(xml_matches):
        try:
            parsed = _parse_xml_response(raw_xml)
        except ET.ParseError:
            continue
        if _has_valid_status(parsed):
            return parsed

    raise ValueError(f"P61070-001: missing or incomplete '{cmd}' block with status")


def parse_p61070_mfg_default_commands(log_path):
    """Parse all 4 required MSA commands from the mfg_restore_default_setting debug.log."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    parsed = {}
    for cmd in P61070_MFG_COMMANDS:
        parsed[cmd] = _extract_command_from_mfg_text(text, cmd)
    return parsed


def parse_p61070_certificates(log_path):
    """Parse the LAST valid post-reset <RESPONSE REQUEST='show certificates'> XML block."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    xml_matches = re.findall(
        r'<RESPONSE\b[^>]*\bREQUEST="show certificates"[^>]*>.*?</RESPONSE>',
        text,
        re.DOTALL,
    )
    for raw_xml in reversed(xml_matches):
        try:
            parsed = _parse_xml_response(raw_xml)
        except ET.ParseError:
            continue
        certs = parsed.get("certificates")
        if isinstance(certs, list) and certs and _has_valid_status(parsed):
            return parsed
    raise ValueError("P61070-001: missing valid 'show certificates' XML response with status")


def detect_p61070_controller(config_data, frus_data, target_sn):
    """Map target_sn to ('ctrla'|'ctrlb', 'A'|'B') with FRU and redundancy cross-checks."""
    sn_up = (target_sn or "").strip().upper()
    if not sn_up:
        raise ValueError("P61070-001: empty target serial number")

    matched_ctrls = [
        c for c in config_data.get("controllers", [])
        if str(c.get("serial-number", "")).strip().upper() == sn_up
    ]
    if len(matched_ctrls) != 1:
        raise ValueError(
            f"P61070-001: expected exactly 1 controller matching SN '{sn_up}', found {len(matched_ctrls)}"
        )

    ctrl_letter = str(matched_ctrls[0].get("controller-id", "")).strip().upper()
    if ctrl_letter not in ("A", "B"):
        raise ValueError(f"P61070-001: invalid controller-id '{ctrl_letter}' for SN '{sn_up}'")

    matched_frus = [
        f for f in frus_data.get("enclosure-fru", [])
        if str(f.get("name", "")).strip().upper() == "RAID_IOM"
        and str(f.get("serial-number", "")).strip().upper() == sn_up
    ]
    if len(matched_frus) != 1:
        raise ValueError(
            f"P61070-001: expected exactly 1 RAID_IOM FRU for SN '{sn_up}', found {len(matched_frus)}"
        )

    fru_loc = str(matched_frus[0].get("fru-location", "")).strip().upper()
    if fru_loc in _EXPECTED_FRU_LOCATIONS.values() and fru_loc != _EXPECTED_FRU_LOCATIONS[ctrl_letter]:
        raise ValueError(
            f"P61070-001: controller '{ctrl_letter}' contradicts FRU location '{fru_loc}' for SN '{sn_up}'"
        )

    red_key = f"controller-{ctrl_letter.lower()}-serial-number"
    for sys_item in config_data.get("system", []):
        for red in sys_item.get("redundancy", []) if isinstance(sys_item.get("redundancy"), list) else []:
            red_sn = str(red.get(red_key, "")).strip().upper()
            if red_sn and red_sn != sn_up:
                raise ValueError(
                    f"P61070-001: redundancy {red_key} '{red_sn}' contradicts SN '{sn_up}'"
                )

    controller_role = "ctrla" if ctrl_letter == "A" else "ctrlb"
    return controller_role, ctrl_letter


def _filter_by_controller(items, key, ctrl_up):
    """Filter a list of dicts where item[key] matches ctrl_up (case-insensitive)."""
    return [
        copy.deepcopy(item)
        for item in (items or [])
        if isinstance(item, dict) and str(item.get(key, "")).strip().upper() == ctrl_up
    ]


def _sanitize_system_list(sys_list, sibling_letter):
    """Copy system objects while stripping sibling controller serial/status from redundancy."""
    sibling_prefix = f"controller-{sibling_letter.lower()}-"
    cleaned = copy.deepcopy(sys_list)
    for sys_item in cleaned:
        reds = sys_item.get("redundancy")
        if isinstance(reds, list):
            sys_item["redundancy"] = [
                {k: v for k, v in r.items() if not k.lower().startswith(sibling_prefix)}
                for r in reds
                if isinstance(r, dict)
            ]
    return cleaned


def filter_p61070_data(raw_commands, target_sn, ctrl_letter):
    """Filter all 5 commands to target SN/controller and validate required sections before writing."""
    sn_up = target_sn.strip().upper()
    ctrl_up = ctrl_letter.strip().upper()
    sibling_up = "B" if ctrl_up == "A" else "A"

    for cmd in P61070_ALL_COMMANDS:
        if cmd not in raw_commands or not _has_valid_status(raw_commands[cmd]):
            raise ValueError(f"P61070-001: missing required command or status for '{cmd}'")

    # 1. show firmware-bundles
    fw_cmd = raw_commands["show firmware-bundles"]
    fw_bundles = copy.deepcopy(fw_cmd.get("firmware-bundles", []))
    if not fw_bundles:
        raise ValueError("P61070-001: empty firmware-bundles in 'show firmware-bundles'")

    # 2. show system
    sys_cmd = raw_commands["show system"]
    sys_list = _sanitize_system_list(sys_cmd.get("system", []), sibling_up)
    if not sys_list:
        raise ValueError("P61070-001: empty system list in 'show system'")

    # 3. show frus detail
    frus_cmd = raw_commands["show frus detail"]
    target_frus = [
        copy.deepcopy(f)
        for f in frus_cmd.get("enclosure-fru", [])
        if str(f.get("name", "")).strip().upper() == "RAID_IOM"
        and str(f.get("serial-number", "")).strip().upper() == sn_up
    ]
    if len(target_frus) != 1:
        raise ValueError(f"P61070-001: missing RAID_IOM FRU for SN '{sn_up}' in 'show frus detail'")

    # 4. show configuration
    cfg_cmd = raw_commands["show configuration"]
    cfg_sys = _sanitize_system_list(cfg_cmd.get("system", []), sibling_up)
    if not cfg_sys:
        raise ValueError("P61070-001: empty system list in 'show configuration'")

    target_ctrls = [
        copy.deepcopy(c)
        for c in cfg_cmd.get("controllers", [])
        if str(c.get("controller-id", "")).strip().upper() == ctrl_up
        and str(c.get("serial-number", "")).strip().upper() == sn_up
    ]
    if len(target_ctrls) != 1:
        raise ValueError(f"P61070-001: missing controller {ctrl_up} ({sn_up}) in 'show configuration'")

    target_dns = _filter_by_controller(cfg_cmd.get("dns-parameters", []), "controller", ctrl_up)
    target_mgmt = _filter_by_controller(cfg_cmd.get("mgmt-hostnames", []), "controller", ctrl_up)

    ver_by_obj = {
        str(v.get("object-name", "")).strip().lower(): copy.deepcopy(v)
        for v in cfg_cmd.get("versions", [])
        if isinstance(v, dict)
    }
    target_ver_key = f"controller-{ctrl_up.lower()}-versions"
    if target_ver_key not in ver_by_obj:
        raise ValueError(f"P61070-001: missing '{target_ver_key}' in 'show configuration'")
    ordered_versions = [
        ver_by_obj[key]
        for key in ("controller-a-versions", "controller-b-versions")
        if key in ver_by_obj
    ]

    filtered_fru_versions = []
    target_expanders = []
    for fv in cfg_cmd.get("fru-versions", []):
        if not isinstance(fv, dict):
            continue
        exps = _filter_by_controller(fv.get("expander-versions", []), "controller", ctrl_up)
        if exps:
            target_expanders.extend(exps)
            fv_entry = {
                "object-name": fv.get("object-name", "fru-versions"),
            }
            if "enclosure-id" in fv:
                fv_entry["enclosure-id"] = fv["enclosure-id"]
            fv_entry["expander-versions"] = exps
            filtered_fru_versions.append(fv_entry)
    if not target_expanders:
        raise ValueError(f"P61070-001: missing expander-versions for controller {ctrl_up}")

    target_ports = _filter_by_controller(cfg_cmd.get("port", []), "controller", ctrl_up)
    if not target_ports:
        target_ports = _filter_by_controller(target_ctrls[0].get("port", []), "controller", ctrl_up)
    if not target_ports:
        raise ValueError(f"P61070-001: missing ports for controller {ctrl_up}")

    # Trim sibling ports/expanders nested inside controller dict when present? No sibling is inside
    # target_ctrls[0] anyway because target_ctrls[0] is strictly the target controller object.
    cfg_frus = [
        copy.deepcopy(f)
        for f in cfg_cmd.get("enclosure-fru", [])
        if str(f.get("name", "")).strip().upper() == "RAID_IOM"
        and str(f.get("serial-number", "")).strip().upper() == sn_up
    ]
    if len(cfg_frus) != 1:
        raise ValueError(f"P61070-001: missing RAID_IOM FRU for SN '{sn_up}' in 'show configuration'")

    # 5. show certificates
    cert_cmd = raw_commands["show certificates"]
    target_certs = _filter_by_controller(cert_cmd.get("certificates", []), "certificate-controller", ctrl_up)
    if not target_certs:
        raise ValueError(f"P61070-001: missing certificate for controller {ctrl_up}")

    return {
        "show firmware-bundles": {
            "firmware-bundles": fw_bundles,
            "status": copy.deepcopy(fw_cmd["status"]),
        },
        "show system": {
            "system": sys_list,
            "status": copy.deepcopy(sys_cmd["status"]),
        },
        "show frus detail": {
            "enclosure-fru": target_frus,
            "status": copy.deepcopy(frus_cmd["status"]),
        },
        "show configuration": {
            "system": cfg_sys,
            "controllers": target_ctrls,
            "dns-parameters": target_dns,
            "mgmt-hostnames": target_mgmt,
            "versions": ordered_versions,
            "fru-versions": filtered_fru_versions,
            "port": target_ports,
            "enclosure-fru": cfg_frus,
            "status": copy.deepcopy(cfg_cmd["status"]),
        },
        "show certificates": {
            "certificates": target_certs,
            "status": copy.deepcopy(cert_cmd["status"]),
        },
    }


def _kv(label, value):
    """Format 'Label: value' or 'Label:' with no trailing space when value is empty."""
    val = "" if value is None else str(value)
    return f"{label}: {val}" if val != "" else f"{label}:"


def _format_status_lines(status_list):
    """Render MSA status object list as real Success/Info lines from the log."""
    lines = []
    for st in status_list:
        rtype = str(st.get("response-type", "Success")).strip() or "Success"
        resp = str(st.get("response", "")).strip()
        if resp:
            lines.append(f"{rtype}: {resp}")
    return lines


def _format_table_row(cells, widths):
    """Format cells left-aligned with fixed widths, stripping trailing spaces on the last column."""
    parts = []
    for idx, (cell, width) in enumerate(zip(cells, widths)):
        text = "" if cell is None else str(cell)
        if idx == len(cells) - 1:
            parts.append(text)
        else:
            parts.append(text.ljust(width))
    return "".join(parts).rstrip()


def _compute_col_widths(rows, min_widths, gap=3):
    """Compute per-column widths safely exceeding every cell's length by at least `gap`."""
    widths = list(min_widths)
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len("" if cell is None else str(cell)) + gap)
    return widths


def _render_system_info_lines(sys_obj, *, include_scsi=False, underline="------------------"):
    """Render MSA System Information block for show system / show configuration."""
    fields = [
        ("System Name", sys_obj.get("system-name", "")),
        ("System Contact", sys_obj.get("system-contact", "")),
        ("System Location", sys_obj.get("system-location", "")),
        ("System Information", sys_obj.get("system-information", "")),
        ("Vendor Name", sys_obj.get("vendor-name", "")),
        ("Product ID", sys_obj.get("product-id", "")),
        ("Product Brand", sys_obj.get("product-brand", "")),
    ]
    if include_scsi:
        fields.extend([
            ("SCSI Vendor ID", sys_obj.get("scsi-vendor-id", "")),
            ("SCSI Product ID", sys_obj.get("scsi-product-id", "")),
        ])
    fields.extend([
        ("Enclosure Count", sys_obj.get("enclosure-count", "")),
        ("Health", sys_obj.get("health", "")),
        ("Health Reason", sys_obj.get("health-reason", "")),
        ("Other MC Status", sys_obj.get("other-MC-status", "")),
        ("PFU Status", sys_obj.get("pfuStatus", "")),
        ("Security System Management", sys_obj.get("security-system-management", "")),
        ("Supported Locales", sys_obj.get("supported-locales", "")),
    ])
    lines = ["System Information", underline]
    lines.extend(_kv(lbl, val) for lbl, val in fields)
    return lines


def _render_fru_lines(fru, underline="------", include_enclosure_id=True):
    """Render one FRU detail block."""
    fields = [
        ("Name", fru.get("name", "")),
        ("Description", fru.get("description", "")),
        ("Part Number", fru.get("part-number", "")),
        ("Serial Number", fru.get("serial-number", "")),
        ("Revision", fru.get("revision", "")),
        ("Dash Level", fru.get("dash-level", "")),
        ("FRU Shortname", fru.get("fru-shortname", "")),
        ("Manufacturing Date", fru.get("mfg-date", "")),
        ("Manufacturing Location", fru.get("mfg-location", "")),
        ("Manufacturing Vendor ID", fru.get("mfg-vendor-id", "")),
        ("FRU Location", fru.get("fru-location", "")),
        ("FRU Status", fru.get("fru-status", "")),
    ]
    if include_enclosure_id:
        fields.append(("Enclosure ID", fru.get("enclosure-id", "")))
    lines = ["FRU", underline]
    lines.extend(_kv(lbl, val) for lbl, val in fields)
    return lines


def _render_controller_lines(ctrl):
    """Render MSA Controller properties block matching OFAIR Section 4 pages 5-6."""
    fields = [
        ("Controller ID", ctrl.get("controller-id", "")),
        ("Serial Number", ctrl.get("serial-number", "")),
        ("Hardware Version", ctrl.get("hardware-version", "")),
        ("CPLD Version", ctrl.get("cpld-version", "")),
        ("MAC Address", ctrl.get("mac-address", "")),
        ("WWNN", ctrl.get("node-wwn", "")),
        ("IP Address", ctrl.get("ip-address", "")),
        ("IP Subnet Mask", ctrl.get("ip-subnet-mask", "")),
        ("IP Gateway", ctrl.get("ip-gateway", "")),
        ("IP6 Link Local", ctrl.get("ip6-link-local-address", "")),
        ("IP6 Link Local GW", ctrl.get("ip6-link-local-gateway", "")),
        ("Autoconfig", ctrl.get("autoconfig", "")),
        ("DHCPv6", ctrl.get("dhcpv6", "")),
        ("SLAAC IP Address", ctrl.get("slaac-ip", "")),
        ("IP6 Auto Gateway", ctrl.get("ip6-auto-gateway", "")),
        ("Disks", ctrl.get("disks", "")),
        ("Virtual Pools", ctrl.get("number-of-storage-pools", "")),
        ("Disk Groups", ctrl.get("virtual-disks", "")),
        ("System Memory (MB)", ctrl.get("system-memory-size", "")),
        ("Host Ports", ctrl.get("host-ports", "")),
        ("Disk Channels", ctrl.get("drive-channels", "")),
        ("Disk Bus Type", ctrl.get("drive-bus-type", "")),
        ("Status", ctrl.get("status", "")),
        ("Failed Over to This Controller", ctrl.get("failed-over", "")),
        ("Fail Over Reason", ctrl.get("fail-over-reason", "")),
        ("Multi-core", ctrl.get("multicore", "")),
        ("Health", ctrl.get("health", "")),
        ("Health Reason", ctrl.get("health-reason", "")),
        ("Health Recommendation", ctrl.get("health-recommendation", "")),
        ("Position", ctrl.get("position", "")),
        ("Phy Isolation", ctrl.get("phy-isolation", "")),
        ("Controller Redundancy Mode", ctrl.get("redundancy-mode", "")),
        ("Controller Redundancy Status", ctrl.get("redundancy-status", "")),
    ]
    lines = ["Controller", "-------------"]
    lines.extend(_kv(lbl, val) for lbl, val in fields)
    return lines


def _version_value(ver_dict, key):
    """Extract display value for a version row, matching CLI Help Version fallback."""
    val = str(ver_dict.get(key, "")).strip()
    if key == "pubs-version" and not val:
        return "No Help Version"
    return val


def _render_versions_table_cli(versions_list):
    """Render 2-column Controller A & Controller B Versions table with non-colliding padding."""
    ver_by_obj = {str(v.get("object-name", "")).lower(): v for v in versions_list}
    has_a = "controller-a-versions" in ver_by_obj
    has_b = "controller-b-versions" in ver_by_obj

    columns = []
    if has_a:
        columns.append(("Controller A Versions", ver_by_obj["controller-a-versions"]))
    if has_b:
        columns.append(("Controller B Versions", ver_by_obj["controller-b-versions"]))

    lbl_w = max(len(lbl) for lbl, _ in P61070_VERSION_FIELDS) + 3
    row_values = []
    for lbl, key in P61070_VERSION_FIELDS:
        row_values.append((lbl, [_version_value(vdict, key) for _, vdict in columns]))

    col_widths = []
    for idx, (header, _) in enumerate(columns):
        max_len = max([len(header)] + [len(vals[idx]) for _, vals in row_values])
        col_widths.append(max_len + 4)

    lines = ["Versions", "--------"]
    header_parts = [" ".ljust(lbl_w)]
    dash_parts = [" ".ljust(lbl_w)]
    for idx, (header, _) in enumerate(columns):
        w = col_widths[idx]
        if idx == len(columns) - 1:
            header_parts.append(header)
            dash_parts.append("-" * len(header))
        else:
            header_parts.append(header.ljust(w))
            dash_parts.append(("-" * len(header)).ljust(w))
    lines.append("".join(header_parts).rstrip())
    lines.append("".join(dash_parts).rstrip())

    for lbl, vals in row_values:
        parts = [lbl.ljust(lbl_w)]
        for idx, val in enumerate(vals):
            parts.append(val if idx == len(vals) - 1 else val.ljust(col_widths[idx]))
        lines.append("".join(parts).rstrip())
    return lines


def _render_expanders_cli(fru_versions):
    """Render multi-row Root Expander table for the filtered controller."""
    exps = []
    for fv in fru_versions:
        exps.extend(fv.get("expander-versions", []))
    if not exps:
        return []

    r1_rows = [("Name", "Location", "Ctlr")]
    r2_rows = [("Firmware Version", "Firmware Version (full)", "VPD Format Version", "VPD CRC")]
    r3_rows = [("CFG Format Version", "CFG CRC", "Boot Loader Version", "CPLD Version", "Part Number")]
    r4_rows = [("Serial Number",)]
    for exp in exps:
        r1_rows.append((exp.get("name", ""), exp.get("location", ""), exp.get("controller", "")))
        r2_rows.append((
            exp.get("fw-revision", ""),
            exp.get("fw-revision-full", ""),
            exp.get("vpd-format-version", ""),
            exp.get("vpd-crc", ""),
        ))
        r3_rows.append((
            exp.get("cfg-format-version", ""),
            exp.get("cfg-crc", ""),
            exp.get("bootloader-version", ""),
            exp.get("cpld-version", ""),
            exp.get("part-number", ""),
        ))
        r4_rows.append((exp.get("serial-number", ""),))

    w1 = _compute_col_widths(r1_rows, [17, 41, 4])
    w2 = _compute_col_widths(r2_rows, [17, 24, 19, 10])
    w3 = _compute_col_widths(r3_rows, [19, 10, 20, 13, 12])
    rule_len = max(sum(w1[:-1]) + len(r1_rows[0][-1]), sum(w2[:-1]) + len(r2_rows[0][-1]), sum(w3[:-1]) + len(r3_rows[0][-1]), 76)

    lines = [
        _format_table_row(r1_rows[0], w1),
        "  " + _format_table_row(r2_rows[0], w2),
        "  " + _format_table_row(r3_rows[0], w3),
        "  " + r4_rows[0][0],
        "  " + ("-" * rule_len),
    ]
    for i in range(1, len(r1_rows)):
        lines.append(_format_table_row(r1_rows[i], w1))
        lines.append("  " + _format_table_row(r2_rows[i], w2))
        lines.append("  " + _format_table_row(r3_rows[i], w3))
        lines.append("  " + r4_rows[i][0])
    return lines


def _render_ports_cli(ports):
    """Render target controller Ports and nested fc-port SFP tables."""
    main_header = ("Ports", "Media", "Target ID", "Status", "Speed(A)", "Health", "Reason", "Action")
    main_rows = [main_header]
    sub_header = ("Topo(C)", "PID", "SFP Status", "Part Number", "Supported Speeds")
    sub_rows = [sub_header]

    for p in ports:
        actual_spd = str(p.get("actual-speed", "")).strip()
        cfg_spd = str(p.get("configured-speed", "")).strip()
        speed_disp = actual_spd if actual_spd and actual_spd.upper() != "N/A" else cfg_spd
        main_rows.append((
            p.get("port", ""),
            p.get("media", ""),
            p.get("target-id", ""),
            p.get("status", ""),
            speed_disp,
            p.get("health", ""),
            p.get("health-reason", ""),
            "",
        ))
        fc = (p.get("fc-port") or [{}])[0]
        sfp_present = str(fc.get("sfp-present", "")).strip().lower() == "present"
        sfp_status = fc.get("sfp-status", "OK") if sfp_present else "Not present"
        sfp_pn = fc.get("sfp-part-number", "") if sfp_present else ""
        sfp_speeds = fc.get("sfp-supported-speeds", "N/A") if sfp_present else "N/A"
        sub_rows.append((
            fc.get("configured-topology", "PTP"),
            fc.get("primary-loop-id", "N/A"),
            sfp_status,
            sfp_pn,
            sfp_speeds,
        ))

    mw = _compute_col_widths(main_rows, [12, 8, 20, 18, 12, 9, 8, 6])
    sw = _compute_col_widths(sub_rows, [8, 6, 17, 21, 16])
    main_rule = max(100, sum(mw[:-1]) + len(main_header[-1]))
    sub_rule = max(97, sum(sw[:-1]) + len(sub_header[-1]))

    lines = [_format_table_row(main_header, mw), "-" * main_rule]
    for i in range(1, len(main_rows)):
        lines.append(_format_table_row(main_rows[i], mw))
        lines.append("   " + _format_table_row(sub_header, sw))
        lines.append("   " + ("-" * sub_rule))
        lines.append("   " + _format_table_row(sub_rows[i], sw))
    lines.append("-" * main_rule)
    return lines


def _render_certificates_cli(cert_cmd):
    """Render multi-row show certificates table matching OFAIR Section 4 page 8."""
    certs = cert_cmd.get("certificates", [])
    h1 = ("Certificate Name", "Certificate Type", "Controller", "WEB")
    h2 = ("Valid From", "Valid Till")
    h5 = ("State", "Certificate Status")
    h6 = ("Default Services", "Encryption Type")

    r1_rows = [h1]
    r2_rows = [h2]
    r5_rows = [h5]
    r6_rows = [h6]
    for c in certs:
        r1_rows.append((
            c.get("certificate-name", ""),
            c.get("certificate-type", ""),
            c.get("certificate-controller", ""),
            c.get("certificate-service-web", ""),
        ))
        r2_rows.append((c.get("certificate-valid-from", ""), c.get("certificate-valid-till", "")))
        r5_rows.append((c.get("certificate-state", ""), c.get("certificate-status", "")))
        r6_rows.append((c.get("certificate-default-services", ""), c.get("certificate-encryption-type", "")))

    w1 = _compute_col_widths(r1_rows, [22, 19, 12, 5])
    w2 = _compute_col_widths(r2_rows, [27, 27])
    w5 = _compute_col_widths(r5_rows, [15, 20])
    w6 = _compute_col_widths(r6_rows, [21, 18])

    lines = [
        "# show certificates",
        "",
        _format_table_row(h1, w1),
        "   " + _format_table_row(h2, w2),
        "   Issued To",
        "   Issued By",
        "   " + _format_table_row(h5, w5),
        "   " + _format_table_row(h6, w6),
        "-" * 71,
    ]
    for idx, c in enumerate(certs):
        i = idx + 1
        lines.append(_format_table_row(r1_rows[i], w1))
        lines.append("   " + _format_table_row(r2_rows[i], w2))
        lines.append("   " + str(c.get("certificate-issued-to", "")))
        lines.append("   " + str(c.get("certificate-issued-by", "")))
        lines.append("   " + _format_table_row(r5_rows[i], w5))
        lines.append("   " + _format_table_row(r6_rows[i], w6))
    lines.append("-" * 71)
    lines.extend(_format_status_lines(cert_cmd.get("status", [])))
    return lines


def render_p61070_cli_report(filtered_data, target_sn, ctrl_letter):
    """Render FW.txt in MSA CLI format matching Section 4 of the P61070-001 OFAIR PDF."""
    del target_sn, ctrl_letter
    lines = []

    # 1. # show firmware-bundles
    fw_cmd = filtered_data["show firmware-bundles"]
    fw_h = ("Bundle", "Version Build Date", "Status", "Health", "Reason", "Action")
    fw_rows = [fw_h]
    for b in fw_cmd["firmware-bundles"]:
        fw_rows.append((
            b.get("bundle-version", ""),
            b.get("build-date", ""),
            b.get("status", ""),
            b.get("health", ""),
            b.get("health-reason", ""),
            b.get("health-recommendation", ""),
        ))
    fw_w = _compute_col_widths(fw_rows, [15, 24, 15, 9, 8, 6])
    fw_rule = max(76, sum(fw_w[:-1]) + len(fw_h[-1]))
    lines.extend([
        "# show firmware-bundles",
        "",
        _format_table_row(fw_h, fw_w),
        "-" * fw_rule,
    ])
    lines.extend(_format_table_row(row, fw_w) for row in fw_rows[1:])
    lines.append("-" * fw_rule)
    lines.extend(_format_status_lines(fw_cmd["status"]))
    lines.extend(["", ""])

    # 2. # show system
    sys_cmd = filtered_data["show system"]
    lines.append("# show system")
    lines.append("")
    lines.extend(_render_system_info_lines(sys_cmd["system"][0], include_scsi=False, underline="------------------"))
    lines.extend(_format_status_lines(sys_cmd["status"]))
    lines.extend(["", ""])

    # 3. # show frus detail
    frus_cmd = filtered_data["show frus detail"]
    lines.append("# show frus detail")
    lines.append("")
    lines.extend(_render_fru_lines(frus_cmd["enclosure-fru"][0], underline="------", include_enclosure_id=True))
    lines.extend(_format_status_lines(frus_cmd["status"]))
    lines.extend(["", ""])

    # 4. # show configuration
    cfg_cmd = filtered_data["show configuration"]
    lines.append("# show configuration")
    lines.append("")
    lines.extend(_render_system_info_lines(cfg_cmd["system"][0], include_scsi=True, underline="--------------------------"))
    lines.append("")
    lines.extend(_render_controller_lines(cfg_cmd["controllers"][0]))

    for dns in cfg_cmd.get("dns-parameters", []):
        cid = str(dns.get("controller", "")).strip()
        lines.extend([
            "",
            f"Controller {cid}",
            "----------------",
            _kv("Controller", cid),
            _kv("Name Servers", dns.get("name-servers", "")),
            _kv("Search Domains", dns.get("search-domains", "")),
        ])

    for mgmt in cfg_cmd.get("mgmt-hostnames", []):
        lines.extend([
            "",
            "Management Hostnames",
            "---------------------------------",
            _kv("Controller", mgmt.get("controller", "")),
            _kv("DNS management-hostname", mgmt.get("mgmt-hostname", "")),
            _kv("Domain Name(DNS)", mgmt.get("domain-name", "")),
        ])

    lines.append("")
    lines.extend(_render_versions_table_cli(cfg_cmd["versions"]))
    lines.append("")
    lines.extend(_render_expanders_cli(cfg_cmd["fru-versions"]))
    lines.append("")
    lines.extend(_render_ports_cli(cfg_cmd["port"]))
    lines.append("")
    lines.extend(_render_fru_lines(cfg_cmd["enclosure-fru"][0], underline="---", include_enclosure_id=True))
    lines.extend(_format_status_lines(cfg_cmd["status"]))
    lines.extend(["", ""])

    # 5. # show certificates
    lines.extend(_render_certificates_cli(filtered_data["show certificates"]))

    return [line.rstrip() + "\n" for line in lines]


def _dump_raw_node(node, indent, out):
    """Recursively render dict/list structures as indented key: value lines."""
    prefix = "  " * indent
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, (dict, list)):
                out.append(f"{prefix}{k}:")
                _dump_raw_node(v, indent + 1, out)
            else:
                val = "" if v is None else str(v)
                out.append(f"{prefix}{k}: {val}" if val != "" else f"{prefix}{k}:")
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            if isinstance(item, (dict, list)):
                out.append(f"{prefix}[{idx}]:")
                _dump_raw_node(item, indent + 1, out)
            else:
                out.append(f"{prefix}[{idx}]: {item}")
    else:
        out.append(f"{prefix}{node}")


def _escape_md_cell(val):
    """Sanitize a table cell for Markdown rendering."""
    return str(val).replace("|", "\\|").replace("\r", "").replace("\n", " ")


def _render_raw_versions_md_table(versions_list):
    """Render all keys from Controller A & Controller B versions as a clean 2-column Markdown table."""
    ver_by_obj = {str(v.get("object-name", "")).lower(): v for v in versions_list}
    ver_a = ver_by_obj.get("controller-a-versions", {})
    ver_b = ver_by_obj.get("controller-b-versions", {})

    seen_keys = []
    for src in (ver_a, ver_b):
        for k in src:
            if k != "object-name" and k not in seen_keys:
                seen_keys.append(k)

    lines = [
        "### Versions (Controller A vs Controller B)",
        "",
        "| Field Key | Controller A | Controller B |",
        "| --- | --- | --- |",
    ]
    for k in seen_keys:
        va = _escape_md_cell(ver_a.get(k, ""))
        vb = _escape_md_cell(ver_b.get(k, ""))
        lines.append(f"| `{k}` | {va} | {vb} |")
    lines.append("")
    return lines


def render_p61070_raw_report(filtered_data, target_sn, ctrl_letter):
    """Render FW_RAW.md with clean Markdown sections, 2-column versions table, and full key:value dumps."""
    role = "ctrla" if ctrl_letter.upper() == "A" else "ctrlb"
    lines = [
        f"# Raw MSA CLI Data — {P61070_PART_NUMBER}",
        "",
        f"- **Part Number**: `{P61070_PART_NUMBER}`",
        f"- **Target SN**: `{target_sn}`",
        f"- **Controller**: Controller {ctrl_letter.upper()} (`{role}`)",
        "- **Commands**: 5 (`show firmware-bundles`, `show system`, `show frus detail`, `show configuration`, `show certificates`)",
        "",
    ]

    for cmd in P61070_ALL_COMMANDS:
        lines.append(f"## `# {cmd}`")
        lines.append("")
        cmd_data = filtered_data[cmd]
        if cmd == "show configuration" and cmd_data.get("versions"):
            lines.extend(_render_raw_versions_md_table(cmd_data["versions"]))
            lines.append("### Raw Data")
            lines.append("")
        lines.append("```yaml")
        _dump_raw_node(cmd_data, 0, lines)
        lines.append("```")
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return [line.rstrip() + "\n" for line in lines]


def extract_p61070_logs(test_results_dir, target_sn):
    """Extract FW.txt (CLI formatted) and FW_RAW.md (raw key:value) for a P61070-001 controller SN."""
    mfg_log_path = find_p61070_mfg_default_log(test_results_dir)
    cert_log_path = find_p61070_certificates_log(test_results_dir)

    raw_commands = parse_p61070_mfg_default_commands(mfg_log_path)
    raw_commands["show certificates"] = parse_p61070_certificates(cert_log_path)

    controller, ctrl_letter = detect_p61070_controller(
        raw_commands["show configuration"],
        raw_commands["show frus detail"],
        target_sn,
    )
    filtered = filter_p61070_data(raw_commands, target_sn, ctrl_letter)
    cli_lines = render_p61070_cli_report(filtered, target_sn, ctrl_letter)
    raw_lines = render_p61070_raw_report(filtered, target_sn, ctrl_letter)
    return cli_lines, raw_lines, controller
