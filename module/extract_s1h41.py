"""HPE MSA 2070 16Gb FC LFF Storage Chassis (PN S1H41-62001) FW & Raw CLI log extraction."""

import ast
import copy
import os
import re
import xml.etree.ElementTree as ET

from .extract_p61070 import (
    P61070_VERSION_FIELDS,
    _compute_col_widths,
    _dump_raw_node,
    _escape_md_cell,
    _find_matching_step_dirs_desc,
    _format_status_lines,
    _format_table_row,
    _has_valid_status,
    _kv,
    _parse_xml_response,
    _render_certificates_cli,
    _render_raw_versions_md_table,
    _version_value,
)
from .log_io import find_step_dir, get_log_package_pn, to_long_path

S1H41_PART_NUMBER = "S1H41-62001"
S1H41_CLI_REPORT_NAME = "FW.txt"
S1H41_RAW_REPORT_NAME = "FW_RAW.md"

S1H41_MFG_COMMANDS = (
    "show system",
    "show license",
    "show frus detail",
    "show configuration",
)

S1H41_ALL_COMMANDS = (
    "show firmware-bundles all",
    "show system",
    "show license",
    "show frus detail",
    "show configuration",
    "show certificates",
)

S1H41_LICENSE_FIELDS = (
    ("License Key", "license-key"),
    ("Licensing Serial Number", "license-serial-number"),
    ("Maximum Licensable Snapshots", "platform-max-snapshots"),
    ("Base Maximum Snapshots", "base-max-snapshots"),
    ("Licensed Snapshots", "max-snapshots"),
    ("In-Use Snapshots", "in-use-snapshots"),
    ("Snapshots Expire", "max-snapshots-expiry"),
    ("Virtualization", "virtualization"),
    ("Virtualization Expires", "virtualization-expiry"),
    ("Performance Tier", "performance-tier"),
    ("Performance Tier Expires", "performance-tier-expiry"),
    ("Volume Copy", "volume-copy"),
    ("Volume Copy Expires", "volume-copy-expiry"),
    ("Replication", "remote-snapshot-replication"),
    ("Replication Expires", "remote-snapshot-replication-expiry"),
    ("VSS", "vss"),
    ("VSS Expires", "vss-expiry"),
)

S1H41_PSU_VERSION_FIELDS = (
    ("Name:", "name"),
    ("Firmware Version:", "fw-revision"),
    ("PSU DSP version:", "dsp-version"),
    ("VPD Format Version:", "vpd-format-version"),
    ("VPD CRC:", "vpd-crc"),
    ("FRU Descriptor:", "fru-descriptor"),
    ("Part Number:", "part-number"),
    ("Power Supply Serial Number:", "psu-serial-number"),
)


def check_is_s1h41(folder_name="", part_number=""):
    """Return True when the package or metadata PN is exactly S1H41-62001."""
    pn = (part_number or "").strip().upper()
    if not pn or pn == "-":
        pn = get_log_package_pn(folder_name or "")
    return pn == S1H41_PART_NUMBER


def _parse_last_xml_command(text, cmd, list_key):
    """Parse the last valid XML <RESPONSE> for `cmd` with a non-empty `list_key` and status."""
    xml_pattern = r'<RESPONSE\b[^>]*\bREQUEST="' + re.escape(cmd) + r'"[^>]*>.*?</RESPONSE>'
    xml_matches = re.findall(xml_pattern, text, re.DOTALL)
    for raw_xml in reversed(xml_matches):
        try:
            parsed = _parse_xml_response(raw_xml)
        except ET.ParseError:
            continue
        items = parsed.get(list_key)
        if isinstance(items, list) and items and _has_valid_status(parsed):
            return parsed
    return None


def find_s1h41_fw_bundles_all_log(test_results_dir):
    """Locate the debug.log containing valid 'show firmware-bundles all' XML output."""
    search_patterns = ("test_rbod_rfwd", "test_restore_default_factory_firmware")
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
            if _parse_last_xml_command(content, "show firmware-bundles all", "firmware-bundles") is not None:
                return log_path
    raise ValueError("S1H41-62001: missing valid 'show firmware-bundles all' XML response in rfwd/restore_default steps")


def find_s1h41_mfg_default_log(test_results_dir):
    """Locate the mfg restore default debug.log containing MSA show commands."""
    try:
        step_dir = find_step_dir(test_results_dir, "test_mfg_restore_default_setting")
    except FileNotFoundError:
        step_dir = find_step_dir(test_results_dir, "rbod_test_mfg_default")
    log_path = os.path.join(step_dir, "debug.log")
    if not os.path.isfile(to_long_path(log_path)):
        raise FileNotFoundError(f"S1H41-62001: missing debug.log in {step_dir}")
    return log_path


def find_s1h41_certificates_log(test_results_dir):
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
    raise ValueError("S1H41-62001: missing 'show certificates' XML response in restore_default steps")


def parse_s1h41_fw_bundles_all(log_path):
    """Parse the LAST valid <RESPONSE REQUEST='show firmware-bundles all'> XML block."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    parsed = _parse_last_xml_command(text, "show firmware-bundles all", "firmware-bundles")
    if parsed is not None:
        return parsed
    raise ValueError("S1H41-62001: missing valid 'show firmware-bundles all' XML response with status")


def _extract_mfg_command(text, cmd):
    """Parse one mfg command block from Step 62 text (dict line first, XML response fallback)."""
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

    xml_pattern = r'<RESPONSE\b[^>]*\bREQUEST="' + re.escape(cmd) + r'"[^>]*>.*?</RESPONSE>'
    xml_matches = re.findall(xml_pattern, text, re.DOTALL)
    for raw_xml in reversed(xml_matches):
        try:
            parsed = _parse_xml_response(raw_xml)
        except ET.ParseError:
            continue
        if _has_valid_status(parsed):
            return parsed

    raise ValueError(f"S1H41-62001: missing or incomplete '{cmd}' block with status")


def parse_s1h41_mfg_default_commands(log_path):
    """Parse all 4 required MSA commands from the mfg_restore_default_setting debug.log."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return {cmd: _extract_mfg_command(text, cmd) for cmd in S1H41_MFG_COMMANDS}


def parse_s1h41_certificates(log_path):
    """Parse the LAST valid post-reset <RESPONSE REQUEST='show certificates'> XML block."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    parsed = _parse_last_xml_command(text, "show certificates", "certificates")
    if parsed is not None:
        return parsed
    raise ValueError("S1H41-62001: missing valid 'show certificates' XML response with status")


def _get_sku_serial(sku_obj):
    """Read SKU serial number handling both sku_serialnumber and sku-serialnumber keys."""
    if not isinstance(sku_obj, dict):
        return ""
    val = sku_obj.get("sku_serialnumber")
    if not val:
        val = sku_obj.get("sku-serialnumber")
    return str(val or "").strip().upper()


def validate_s1h41_target_sn(raw_commands, target_sn):
    """Verify target_sn matches the chassis midplane/SKU serial across MSA commands."""
    sn_up = (target_sn or "").strip().upper()
    if not sn_up:
        raise ValueError("S1H41-62001: empty target serial number")

    sys_list = raw_commands.get("show system", {}).get("system", [])
    if not sys_list:
        raise ValueError("S1H41-62001: missing system list in 'show system'")
    sys_midplane_sn = str(sys_list[0].get("midplane-serial-number", "")).strip().upper()
    if sys_midplane_sn != sn_up:
        raise ValueError(
            f"S1H41-62001: 'show system' midplane-serial-number '{sys_midplane_sn}' does not match target SN '{sn_up}'"
        )

    frus_cmd = raw_commands.get("show frus detail", {})
    midplane_frus = [
        f for f in frus_cmd.get("enclosure-fru", [])
        if isinstance(f, dict) and str(f.get("name", "")).strip().upper() == "CHASSIS_MIDPLANE"
    ]
    if len(midplane_frus) != 1:
        raise ValueError(
            f"S1H41-62001: expected exactly 1 CHASSIS_MIDPLANE FRU in 'show frus detail', found {len(midplane_frus)}"
        )
    fru_sn = str(midplane_frus[0].get("serial-number", "")).strip().upper()
    if fru_sn != sn_up:
        raise ValueError(
            f"S1H41-62001: CHASSIS_MIDPLANE serial '{fru_sn}' does not match target SN '{sn_up}'"
        )

    checks = []
    for sku in frus_cmd.get("enclosure-sku", []):
        sku_sn = _get_sku_serial(sku)
        if sku_sn:
            checks.append(("show frus detail -> enclosure-sku", sku_sn))

    cfg_cmd = raw_commands.get("show configuration", {})
    for sys_item in cfg_cmd.get("system", []):
        val = str(sys_item.get("midplane-serial-number", "")).strip().upper()
        if val:
            checks.append(("show configuration -> system.midplane-serial-number", val))
    for fv in cfg_cmd.get("fru-versions", []):
        for mpv in fv.get("midplane-versions", []) if isinstance(fv, dict) else []:
            val = str(mpv.get("midplane-serial-number", "")).strip().upper()
            if val:
                checks.append(("show configuration -> midplane-versions.midplane-serial-number", val))
    for enc in cfg_cmd.get("enclosures", []):
        val = str(enc.get("midplane-serial-number", "")).strip().upper()
        if val:
            checks.append(("show configuration -> enclosures.midplane-serial-number", val))
    for sku in cfg_cmd.get("enclosure-sku", []):
        sku_sn = _get_sku_serial(sku)
        if sku_sn:
            checks.append(("show configuration -> enclosure-sku", sku_sn))
    for fru in cfg_cmd.get("enclosure-fru", []):
        if isinstance(fru, dict) and str(fru.get("name", "")).strip().upper() == "CHASSIS_MIDPLANE":
            val = str(fru.get("serial-number", "")).strip().upper()
            if val:
                checks.append(("show configuration -> CHASSIS_MIDPLANE", val))

    for source_label, found_sn in checks:
        if found_sn != sn_up:
            raise ValueError(
                f"S1H41-62001: {source_label} '{found_sn}' contradicts target SN '{sn_up}'"
            )


def _require_controllers_a_and_b(controllers):
    """Return [Controller A, Controller B] from `controllers` or raise ValueError."""
    by_id = {}
    for ctrl in controllers or []:
        if isinstance(ctrl, dict):
            cid = str(ctrl.get("controller-id", "")).strip().upper()
            if cid in ("A", "B"):
                by_id[cid] = copy.deepcopy(ctrl)
    missing = [cid for cid in ("A", "B") if cid not in by_id]
    if missing:
        raise ValueError(f"S1H41-62001: missing controller(s) {missing} in 'show configuration'")
    return [by_id["A"], by_id["B"]]


def _order_by_controller(items, key="controller"):
    """Deep-copy list items ordered Controller A then B (plus any remaining items)."""
    order_map = {"A": 0, "B": 1}
    copied = [copy.deepcopy(item) for item in (items or []) if isinstance(item, dict)]
    copied.sort(key=lambda item: order_map.get(str(item.get(key, "")).strip().upper(), 2))
    return copied


def prepare_s1h41_data(raw_commands, target_sn):
    """Validate and canonically order all 6 MSA commands for chassis S1H41-62001."""
    for cmd in S1H41_ALL_COMMANDS:
        if cmd not in raw_commands or not _has_valid_status(raw_commands[cmd]):
            raise ValueError(f"S1H41-62001: missing required command or status for '{cmd}'")

    validate_s1h41_target_sn(raw_commands, target_sn)

    fw_cmd = copy.deepcopy(raw_commands["show firmware-bundles all"])
    if not fw_cmd.get("firmware-bundles"):
        raise ValueError("S1H41-62001: empty firmware-bundles in 'show firmware-bundles all'")

    sys_cmd = copy.deepcopy(raw_commands["show system"])
    if not sys_cmd.get("system"):
        raise ValueError("S1H41-62001: empty system list in 'show system'")

    lic_cmd = copy.deepcopy(raw_commands["show license"])
    if not lic_cmd.get("license"):
        raise ValueError("S1H41-62001: empty license list in 'show license'")

    frus_cmd = copy.deepcopy(raw_commands["show frus detail"])
    if not frus_cmd.get("enclosure-sku") or not frus_cmd.get("enclosure-fru"):
        raise ValueError("S1H41-62001: missing enclosure-sku or enclosure-fru in 'show frus detail'")

    cfg_cmd = copy.deepcopy(raw_commands["show configuration"])
    if not cfg_cmd.get("system"):
        raise ValueError("S1H41-62001: empty system list in 'show configuration'")

    ordered_ctrls = _require_controllers_a_and_b(cfg_cmd.get("controllers", []))
    cfg_cmd["controllers"] = ordered_ctrls
    cfg_cmd["dns-parameters"] = _order_by_controller(cfg_cmd.get("dns-parameters", []), "controller")
    cfg_cmd["mgmt-hostnames"] = _order_by_controller(cfg_cmd.get("mgmt-hostnames", []), "controller")

    ver_by_obj = {
        str(v.get("object-name", "")).strip().lower(): copy.deepcopy(v)
        for v in cfg_cmd.get("versions", [])
        if isinstance(v, dict)
    }
    if "controller-a-versions" not in ver_by_obj or "controller-b-versions" not in ver_by_obj:
        raise ValueError("S1H41-62001: missing controller-a-versions or controller-b-versions in 'show configuration'")
    cfg_cmd["versions"] = [ver_by_obj["controller-a-versions"], ver_by_obj["controller-b-versions"]]

    fru_versions = cfg_cmd.get("fru-versions", [])
    if not fru_versions:
        raise ValueError("S1H41-62001: missing fru-versions in 'show configuration'")
    has_midplane = False
    exp_ctrls = set()
    has_psus = False
    for fv in fru_versions:
        if not isinstance(fv, dict):
            continue
        if fv.get("midplane-versions"):
            has_midplane = True
        exps = _order_by_controller(fv.get("expander-versions", []), "controller")
        if exps:
            fv["expander-versions"] = exps
            exp_ctrls.update(str(e.get("controller", "")).strip().upper() for e in exps)
        if fv.get("psu-versions"):
            has_psus = True
    if not has_midplane:
        raise ValueError("S1H41-62001: missing midplane-versions in 'show configuration'")
    if not {"A", "B"}.issubset(exp_ctrls):
        raise ValueError("S1H41-62001: missing expander-versions for Controller A or B")
    if not has_psus:
        raise ValueError("S1H41-62001: missing psu-versions in 'show configuration'")

    ports = copy.deepcopy(cfg_cmd.get("port", []))
    if not ports:
        for ctrl in ordered_ctrls:
            ports.extend(copy.deepcopy(ctrl.get("port", [])))
    ports = _order_by_controller(ports, "controller")
    port_ctrls = {str(p.get("controller", "")).strip().upper() for p in ports}
    if not {"A", "B"}.issubset(port_ctrls):
        raise ValueError("S1H41-62001: missing ports for Controller A or B")
    cfg_cmd["port"] = ports

    if not cfg_cmd.get("enclosures"):
        raise ValueError("S1H41-62001: missing enclosures in 'show configuration'")
    if not cfg_cmd.get("enclosure-sku") or not cfg_cmd.get("enclosure-fru"):
        raise ValueError("S1H41-62001: missing enclosure-sku or enclosure-fru in 'show configuration'")

    cert_cmd = copy.deepcopy(raw_commands["show certificates"])
    certs = _order_by_controller(cert_cmd.get("certificates", []), "certificate-controller")
    cert_ctrls = {str(c.get("certificate-controller", "")).strip().upper() for c in certs}
    if not {"A", "B"}.issubset(cert_ctrls):
        raise ValueError("S1H41-62001: missing certificate for Controller A or B")
    cert_cmd["certificates"] = certs

    return {
        "show firmware-bundles all": fw_cmd,
        "show system": sys_cmd,
        "show license": lic_cmd,
        "show frus detail": frus_cmd,
        "show configuration": cfg_cmd,
        "show certificates": cert_cmd,
    }


def _render_system_info_chassis(sys_obj, *, include_scsi=False):
    """Render MSA System Information block including Midplane Serial Number."""
    fields = [
        ("System Name", sys_obj.get("system-name", "")),
        ("System Contact", sys_obj.get("system-contact", "")),
        ("System Location", sys_obj.get("system-location", "")),
        ("System Information", sys_obj.get("system-information", "")),
        ("Midplane Serial Number", sys_obj.get("midplane-serial-number", "")),
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
    lines = ["System Information", "------------------"]
    lines.extend(_kv(lbl, val) for lbl, val in fields)
    return lines


def _render_sku_and_frus_chassis(sku_list, fru_list):
    """Render SKU and full Enclosure FRU blocks (with Configuration SN and PSU Original SN/PN/Rev)."""
    lines = []
    for idx, sku in enumerate(sku_list):
        if idx > 0:
            lines.append("")
        lines.extend([
            "SKU",
            "---",
            _kv("Part Number", sku.get("sku-partnumber", "")),
            _kv("Serial Number", _get_sku_serial(sku)),
            _kv("Revision", sku.get("sku-revision", "")),
            _kv("Enclosure ID", sku.get("enclosure-id", "")),
        ])

    for fru in fru_list:
        if lines:
            lines.append("")
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
            ("Configuration SN", fru.get("configuration-serialnumber", "")),
            ("FRU Status", fru.get("fru-status", "")),
        ]
        orig_sn = fru.get("original-serialnumber", "")
        orig_pn = fru.get("original-partnumber", "")
        orig_rev = fru.get("original-revision", "")
        if str(fru.get("name", "")).strip().upper() == "POWER_SUPPLY" or any((orig_sn, orig_pn, orig_rev)):
            fields.extend([
                ("Original SN", orig_sn),
                ("Original PN", orig_pn),
                ("Original Rev", orig_rev),
            ])
        fields.append(("Enclosure ID", fru.get("enclosure-id", "")))
        lines.extend(["FRU", "---"])
        lines.extend(_kv(lbl, val) for lbl, val in fields)

    return lines


def _render_controller_chassis(ctrl):
    """Render one Controller properties block matching OFAIR Section 5 pages 9-10."""
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
    lines = ["Controller", "----------"]
    lines.extend(_kv(lbl, val) for lbl, val in fields)
    return lines


def _render_two_column_kv_table(columns, field_specs):
    """Render a 2-column aligned key/value table (Versions or PSU Versions) without collisions."""
    lbl_w = max(len(lbl) for lbl, _ in field_specs) + 3
    row_values = [
        (lbl, [_version_value(obj, key) for _, obj in columns])
        for lbl, key in field_specs
    ]
    col_widths = []
    for idx, (header, _) in enumerate(columns):
        max_len = max([len(header)] + [len(vals[idx]) for _, vals in row_values])
        col_widths.append(max_len + 4)

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

    lines = [
        "".join(header_parts).rstrip(),
        "".join(dash_parts).rstrip(),
    ]
    for lbl, vals in row_values:
        parts = [lbl.ljust(lbl_w)]
        for idx, val in enumerate(vals):
            parts.append(val if idx == len(vals) - 1 else val.ljust(col_widths[idx]))
        lines.append("".join(parts).rstrip())
    return lines


def _render_fru_versions_chassis(fru_versions):
    """Render FRU Versions (Midplane Versions, Root Expanders A & B, PSU Versions 2-col table)."""
    lines = ["FRU Versions", "------------"]
    for idx, fv in enumerate(fru_versions):
        if idx > 0:
            lines.append("")
        if "enclosure-id" in fv:
            lines.append(_kv("Enclosure ID", fv.get("enclosure-id", "")))
            lines.append("")

        for mpv in fv.get("midplane-versions", []):
            lines.extend([
                "  Midplane Versions",
                "  -----------------",
                "  " + _kv("VPD Format Version", mpv.get("vpd-format-version", "")),
                "  " + _kv("VPD CRC", mpv.get("vpd-crc", "")),
                "  " + _kv("Config Mismatch Version", mpv.get("cfg-mismatch-version", "")),
                "  " + _kv("CPLD Version", mpv.get("cpld-version", "")),
                "  " + _kv("FRU Descriptor", mpv.get("fru-descriptor", "")),
                "  " + _kv("Part Number", mpv.get("part-number", "")),
                "  " + _kv("Midplane Serial Number", mpv.get("midplane-serial-number", "")),
            ])

        exps = fv.get("expander-versions", [])
        if exps:
            lines.append("")
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
            rule_len = max(
                sum(w1[:-1]) + len(r1_rows[0][-1]),
                sum(w2[:-1]) + len(r2_rows[0][-1]),
                sum(w3[:-1]) + len(r3_rows[0][-1]),
                76,
            )
            lines.extend([
                "  " + _format_table_row(r1_rows[0], w1),
                "    " + _format_table_row(r2_rows[0], w2),
                "    " + _format_table_row(r3_rows[0], w3),
                "    " + r4_rows[0][0],
                "    " + ("-" * rule_len),
            ])
            for i in range(1, len(r1_rows)):
                lines.append("  " + _format_table_row(r1_rows[i], w1))
                lines.append("    " + _format_table_row(r2_rows[i], w2))
                lines.append("    " + _format_table_row(r3_rows[i], w3))
                lines.append("    " + r4_rows[i][0])

        psus = fv.get("psu-versions", [])
        if psus:
            lines.append("")
            lines.extend(_render_two_column_kv_table([("PSU Versions", p) for p in psus], S1H41_PSU_VERSION_FIELDS))

    return lines


def _render_ports_chassis(ports):
    """Render Ports tables grouped by controller (A1-A4 then B1-B4) including Speed(C)."""
    lines = []
    groups = [
        [p for p in ports if str(p.get("controller", "")).strip().upper() == "A"],
        [p for p in ports if str(p.get("controller", "")).strip().upper() == "B"],
    ]
    groups = [g for g in groups if g]

    for g_idx, group in enumerate(groups):
        if g_idx > 0:
            lines.append("")
        main_header = ("Ports", "Media", "Target ID", "Status", "Speed(A)", "Speed(C)", "Health", "Reason", "Action")
        main_rows = [main_header]
        sub_header = ("Topo(C)", "PID", "SFP Status", "Part Number", "Supported Speeds")
        sub_rows = [sub_header]

        for p in group:
            actual_spd = str(p.get("actual-speed", "")).strip()
            cfg_spd = str(p.get("configured-speed", "")).strip()
            speed_a = actual_spd if actual_spd else cfg_spd
            main_rows.append((
                p.get("port", ""),
                p.get("media", ""),
                p.get("target-id", ""),
                p.get("status", ""),
                speed_a,
                cfg_spd,
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

        mw = _compute_col_widths(main_rows, [8, 8, 19, 10, 10, 10, 9, 8, 6])
        sw = _compute_col_widths(sub_rows, [10, 6, 13, 21, 16])
        main_rule = max(76, sum(mw[:-1]) + len(main_header[-1]))
        sub_rule = max(66, sum(sw[:-1]) + len(sub_header[-1]))

        lines.extend([_format_table_row(main_header, mw), "-" * main_rule])
        for i in range(1, len(main_rows)):
            lines.append(_format_table_row(main_rows[i], mw))
            lines.append("   " + _format_table_row(sub_header, sw))
            lines.append("   " + ("-" * sub_rule))
            lines.append("   " + _format_table_row(sub_rows[i], sw))
        lines.append("-" * main_rule)

    return lines


def _render_storage_and_enclosure_tables(cfg_cmd):
    """Render Disks, Enclosure Slots, Disk Groups, Pools, and Enclosures sections."""
    lines = []

    # Disks (empty when Disks: 0)
    lines.extend([
        "Location   Serial Number   Vendor   Rev   Description      Usage   Jobs",
        "   Speed (kr/min)   Size   Sec Fmt   Disk Group   Pool   Tier   Health",
        "-" * 75,
    ])
    for drv in cfg_cmd.get("drives", []):
        lines.append(
            f"{drv.get('location', '')}   {drv.get('serial-number', '')}   "
            f"{drv.get('vendor', '')}   {drv.get('revision', '')}   {drv.get('description', '')}"
        )
    lines.append("-" * 75)
    lines.append("")

    # Enclosure Drive Slots (enclosure-list)
    slots = sorted(
        [s for s in cfg_cmd.get("enclosure-list", []) if isinstance(s, dict)],
        key=lambda s: (int(s.get("enclosure-id", 0) or 0), int(s.get("slot", 0) or 0)),
    )
    if slots:
        slot_header = ("Status", "Encl", "Slot", "Vendor", "Model", "Serial Number", "Size")
        slot_rows = [slot_header]
        for s in slots:
            slot_rows.append((
                s.get("status", ""),
                s.get("enclosure-id", ""),
                s.get("slot", ""),
                s.get("vendor", ""),
                s.get("model", ""),
                s.get("serial-number", ""),
                s.get("size", ""),
            ))
        sw = _compute_col_widths(slot_rows, [14, 7, 7, 9, 10, 16, 4])
        slot_rule = max(75, sum(sw[:-1]) + len(slot_header[-1]))
        lines.extend([_format_table_row(slot_header, sw), "-" * slot_rule])
        lines.extend(_format_table_row(row, sw) for row in slot_rows[1:])
        lines.append("-" * slot_rule)
        lines.append("")

    # Disk Groups & Pools headers (matching Section 5 page 13)
    lines.extend([
        "Name   Size   Free   Pool   Tier   % of Pool   Own   RAID   Disks   Chk   Status",
        "   Current Job   Job%   Sec Fmt   Health",
        "-" * 79,
        "-" * 79,
        "",
        "Name   Serial Number   Blocksize   Total Size   Avail   Snap Size",
        "   OverCommit   Disk Groups   Volumes   Low Thresh   Mid Thresh   High Thresh",
        "   Sec Fmt   Health",
        "-" * 79,
        "-" * 79,
        "",
    ])

    # Enclosures table (page 14)
    enclosures = [e for e in cfg_cmd.get("enclosures", []) if isinstance(e, dict)]
    r1_rows = [("Encl", "Encl WWN", "Name", "Location", "Rack", "Pos")]
    r2_rows = [("Vendor", "Model", "Top Level Assembly Part Number", "EMP A CH:ID Rev")]
    r3_rows = [("EMP B CH:ID Rev", "Midplane Type", "Health", "Reason", "Action")]
    for e in enclosures:
        r1_rows.append((
            e.get("enclosure-id", ""),
            e.get("enclosure-wwn", ""),
            e.get("name", ""),
            e.get("location", ""),
            e.get("rack-number", ""),
            e.get("rack-position", ""),
        ))
        r2_rows.append((
            e.get("vendor", ""),
            e.get("model", ""),
            e.get("fru-tlapn", ""),
            e.get("emp-a-ch-id-rev", ""),
        ))
        r3_rows.append((
            e.get("emp-b-ch-id-rev", ""),
            e.get("midplane-type", ""),
            e.get("health", ""),
            e.get("health-reason", ""),
            e.get("health-recommendation", ""),
        ))

    w1 = _compute_col_widths(r1_rows, [6, 19, 12, 16, 6, 4])
    w2 = _compute_col_widths(r2_rows, [9, 20, 33, 16])
    w3 = _compute_col_widths(r3_rows, [18, 16, 9, 9, 6])
    enc_rule = max(
        79,
        sum(w1[:-1]) + len(r1_rows[0][-1]),
        2 + sum(w2[:-1]) + len(r2_rows[0][-1]),
        2 + sum(w3[:-1]) + len(r3_rows[0][-1]),
    )
    lines.extend([
        _format_table_row(r1_rows[0], w1),
        "  " + _format_table_row(r2_rows[0], w2),
        "  " + _format_table_row(r3_rows[0], w3),
        "-" * enc_rule,
    ])
    for i in range(1, len(r1_rows)):
        lines.append(_format_table_row(r1_rows[i], w1))
        lines.append("  " + _format_table_row(r2_rows[i], w2))
        lines.append("  " + _format_table_row(r3_rows[i], w3))
    lines.append("-" * enc_rule)
    return lines


def render_s1h41_cli_report(data, target_sn):
    """Render FW.txt in MSA CLI format matching Section 5 of the S1H41-62001 PDF."""
    del target_sn
    lines = []

    # 1. # show firmware-bundles all
    fw_cmd = data["show firmware-bundles all"]
    fw_h = ("Bundle Version", "Build Date", "Status", "Health", "Reason", "Action")
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
    fw_w = _compute_col_widths(fw_rows, [17, 23, 17, 9, 9, 6])
    fw_rule = max(76, sum(fw_w[:-1]) + len(fw_h[-1]))
    lines.extend([
        "# show firmware-bundles all",
        "",
        _format_table_row(fw_h, fw_w),
        "-" * fw_rule,
    ])
    lines.extend(_format_table_row(row, fw_w) for row in fw_rows[1:])
    lines.append("-" * fw_rule)
    lines.extend(_format_status_lines(fw_cmd["status"]))
    lines.extend(["", ""])

    # 2. # show system
    sys_cmd = data["show system"]
    lines.extend(["# show system", ""])
    lines.extend(_render_system_info_chassis(sys_cmd["system"][0], include_scsi=False))
    lines.extend(_format_status_lines(sys_cmd["status"]))
    lines.extend(["", ""])

    # 3. # show license
    lic_cmd = data["show license"]
    lic_obj = lic_cmd["license"][0]
    lines.extend(["# show license", ""])
    lines.extend(_kv(lbl, lic_obj.get(key, "")) for lbl, key in S1H41_LICENSE_FIELDS)
    lines.extend(_format_status_lines(lic_cmd["status"]))
    lines.extend(["", ""])

    # 4. # show frus detail
    frus_cmd = data["show frus detail"]
    lines.extend(["# show frus detail", ""])
    lines.extend(_render_sku_and_frus_chassis(frus_cmd["enclosure-sku"], frus_cmd["enclosure-fru"]))
    lines.append("")
    lines.extend(_format_status_lines(frus_cmd["status"]))
    lines.extend(["", ""])

    # 5. # show configuration
    cfg_cmd = data["show configuration"]
    lines.extend(["# show configuration", ""])
    lines.extend(_render_system_info_chassis(cfg_cmd["system"][0], include_scsi=True))

    for ctrl in cfg_cmd["controllers"]:
        lines.append("")
        lines.extend(_render_controller_chassis(ctrl))

    for dns in cfg_cmd.get("dns-parameters", []):
        cid = str(dns.get("controller", "")).strip()
        lines.extend([
            "",
            f"Controller {cid}",
            "------------",
            _kv("Controller", cid),
            _kv("Name Servers", dns.get("name-servers", "")),
            _kv("Search Domains", dns.get("search-domains", "")),
        ])

    for mgmt in cfg_cmd.get("mgmt-hostnames", []):
        lines.extend([
            "",
            "Management Hostnames",
            "--------------------",
            _kv("Controller", mgmt.get("controller", "")),
            _kv("DNS management-hostname", mgmt.get("mgmt-hostname", "")),
            _kv("Domain Name(DNS)", mgmt.get("domain-name", "")),
        ])

    ver_by_obj = {str(v.get("object-name", "")).lower(): v for v in cfg_cmd["versions"]}
    lines.append("")
    lines.extend(_render_two_column_kv_table(
        [
            ("Controller A Versions", ver_by_obj["controller-a-versions"]),
            ("Controller B Versions", ver_by_obj["controller-b-versions"]),
        ],
        P61070_VERSION_FIELDS,
    ))

    lines.append("")
    lines.extend(_render_fru_versions_chassis(cfg_cmd["fru-versions"]))
    lines.append("")
    lines.extend(_render_ports_chassis(cfg_cmd["port"]))
    lines.append("")
    lines.extend(_render_storage_and_enclosure_tables(cfg_cmd))
    lines.append("")
    lines.extend(_render_sku_and_frus_chassis(cfg_cmd["enclosure-sku"], cfg_cmd["enclosure-fru"]))
    lines.append("")
    lines.extend(_format_status_lines(cfg_cmd["status"]))
    lines.extend(["", ""])

    # 6. # show certificates
    lines.extend(_render_certificates_cli(data["show certificates"]))

    return [line.rstrip() + "\n" for line in lines]


def _render_raw_psu_versions_md_table(fru_versions):
    """Render PSU 1 vs PSU 2 version properties as a clean 2-column Markdown table."""
    psus = []
    for fv in fru_versions:
        if isinstance(fv, dict):
            psus.extend(fv.get("psu-versions", []))
    if not psus:
        return []

    psu1 = psus[0] if len(psus) > 0 else {}
    psu2 = psus[1] if len(psus) > 1 else {}
    seen_keys = []
    for src in (psu1, psu2):
        for k in src:
            if k != "object-name" and k not in seen_keys:
                seen_keys.append(k)

    lines = [
        "### PSU Versions (PSU 1 vs PSU 2)",
        "",
        "| Field Key | PSU 1, Left | PSU 2, Right |",
        "| --- | --- | --- |",
    ]
    for k in seen_keys:
        v1 = _escape_md_cell(psu1.get(k, ""))
        v2 = _escape_md_cell(psu2.get(k, ""))
        lines.append(f"| `{k}` | {v1} | {v2} |")
    lines.append("")
    return lines


def render_s1h41_raw_report(data, target_sn):
    """Render FW_RAW.md with clean Markdown tables and complete key:value dumps."""
    lines = [
        f"# Raw MSA CLI Data — {S1H41_PART_NUMBER}",
        "",
        f"- **Part Number**: `{S1H41_PART_NUMBER}`",
        f"- **Target SN**: `{target_sn}`",
        "- **Unit Type**: Chassis (`Chas S1H41` / HPE MSA 2070 16Gb FC LFF Storage)",
        "- **Commands**: 6 (`show firmware-bundles all`, `show system`, `show license`, `show frus detail`, `show configuration`, `show certificates`)",
        "",
    ]

    for cmd in S1H41_ALL_COMMANDS:
        lines.append(f"## `# {cmd}`")
        lines.append("")
        cmd_data = data[cmd]
        if cmd == "show configuration":
            if cmd_data.get("versions"):
                lines.extend(_render_raw_versions_md_table(cmd_data["versions"]))
            if cmd_data.get("fru-versions"):
                lines.extend(_render_raw_psu_versions_md_table(cmd_data["fru-versions"]))
            lines.append("### Raw Data")
            lines.append("")
        lines.append("```yaml")
        _dump_raw_node(cmd_data, 0, lines)
        lines.append("```")
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return [line.rstrip() + "\n" for line in lines]


def extract_s1h41_logs(test_results_dir, target_sn):
    """Extract FW.txt (MSA CLI) and FW_RAW.md (complete raw key:value) for S1H41-62001 chassis."""
    fw_bundles_log = find_s1h41_fw_bundles_all_log(test_results_dir)
    mfg_log_path = find_s1h41_mfg_default_log(test_results_dir)
    cert_log_path = find_s1h41_certificates_log(test_results_dir)

    raw_commands = parse_s1h41_mfg_default_commands(mfg_log_path)
    raw_commands["show firmware-bundles all"] = parse_s1h41_fw_bundles_all(fw_bundles_log)
    raw_commands["show certificates"] = parse_s1h41_certificates(cert_log_path)

    prepared = prepare_s1h41_data(raw_commands, target_sn)
    cli_lines = render_s1h41_cli_report(prepared, target_sn)
    raw_lines = render_s1h41_raw_report(prepared, target_sn)
    return cli_lines, raw_lines
