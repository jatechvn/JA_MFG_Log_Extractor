"""HPE MSA 2070 10/25GbE iSCSI SFF Storage Chassis (PN S1H44-62001) FW & Raw CLI log extraction."""

import ast
import os
import re
import xml.etree.ElementTree as ET

from .extract_p61070 import (
    P61070_VERSION_FIELDS,
    _compute_col_widths,
    _dump_raw_node,
    _find_matching_step_dirs_desc,
    _format_status_lines,
    _format_table_row,
    _has_valid_status,
    _kv,
    _parse_xml_response,
    _render_certificates_cli,
    _render_raw_versions_md_table,
)
from .extract_s1h41 import (
    S1H41_LICENSE_FIELDS,
    _render_controller_chassis,
    _render_fru_versions_chassis,
    _render_raw_psu_versions_md_table,
    _render_sku_and_frus_chassis,
    _render_storage_and_enclosure_tables,
    _render_system_info_chassis,
    _render_two_column_kv_table,
)
from .extract_s1h42 import (
    S1H42_ADVANCED_SETTINGS_FIELDS,
    S1H42_ALL_COMMANDS,
    S1H42_MFG_COMMANDS,
    prepare_s1h42_data,
    validate_s1h42_target_sn,
)
from .extract_s3t80 import S3T80_FRU_SECRETS_FIELDS
from .log_io import find_step_dir, get_log_package_pn, to_long_path

S1H44_PART_NUMBER = "S1H44-62001"
S1H44_CLI_REPORT_NAME = "FW.txt"
S1H44_RAW_REPORT_NAME = "FW_RAW.md"

S1H44_MFG_COMMANDS = S1H42_MFG_COMMANDS
S1H44_ALL_COMMANDS = S1H42_ALL_COMMANDS
S1H44_ADVANCED_SETTINGS_FIELDS = S1H42_ADVANCED_SETTINGS_FIELDS

S1H44_ISCSI_PORT_DETAIL_FIELDS = (
    ("IP Version", "ip-version"),
    ("IP Address", "ip-address"),
    ("Gateway", "gateway"),
    ("Netmask", "netmask"),
    ("MAC", "mac-address"),
    ("SFP Status", "sfp-status"),
    ("Part Number", "sfp-part-number"),
    ("10G Compliance", "sfp-10G-compliance"),
    ("Ethernet Compliance", "sfp-ethernet-compliance"),
    ("Cable Technology", "sfp-cable-technology"),
    ("Cable Length", "sfp-cable-length"),
)


def _rewrite_pn_prefix(exc):
    """Rewrite S1H42-62001/S1H41-62001 error prefix to S1H44-62001:."""
    msg = str(exc)
    for prefix in ("S1H42-62001:", "S1H41-62001:"):
        if msg.startswith(prefix):
            return S1H44_PART_NUMBER + ":" + msg[len(prefix):]
    return msg


def check_is_s1h44(folder_name="", part_number=""):
    """Return True when the package or metadata PN is exactly S1H44-62001."""
    pn = (part_number or "").strip().upper()
    if not pn or pn == "-":
        pn = get_log_package_pn(folder_name or "")
    return pn == S1H44_PART_NUMBER


def find_s1h44_mfg_default_log(test_results_dir):
    """Locate the mfg restore default debug.log containing MSA show commands."""
    try:
        step_dir = find_step_dir(test_results_dir, "test_mfg_restore_default_setting")
    except FileNotFoundError:
        step_dir = find_step_dir(test_results_dir, "rbod_test_mfg_default")
    log_path = os.path.join(step_dir, "debug.log")
    if not os.path.isfile(to_long_path(log_path)):
        raise FileNotFoundError(f"S1H44-62001: missing debug.log in {step_dir}")
    return log_path


def find_s1h44_certificates_log(test_results_dir):
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
    raise ValueError("S1H44-62001: missing 'show certificates' XML response in restore_default steps")


def _parse_last_xml_command_s1h44(text, request_cmd, required_key=None):
    """Return the last valid <RESPONSE REQUEST='...'> XML block without letting truncated Bytes read lines swallow later blocks."""
    pattern = r'<RESPONSE\b[^>\r\n]*\bREQUEST="' + re.escape(request_cmd) + r'"[^>\r\n]*>'
    for match in reversed(list(re.finditer(pattern, text))):
        end_idx = text.find("</RESPONSE>", match.end())
        if end_idx == -1:
            continue
        raw_xml = text[match.start():end_idx + len("</RESPONSE>")]
        try:
            parsed = _parse_xml_response(raw_xml)
        except ET.ParseError:
            continue
        if not _has_valid_status(parsed):
            continue
        if required_key and not (isinstance(parsed.get(required_key), list) and parsed.get(required_key)):
            continue
        return parsed
    return None


def _extract_s1h44_mfg_command(text, cmd):
    """Parse one mfg command from debug.log (dict line first, safe XML response fallback)."""
    dict_labels = ("show advanced-settings", "Advanced Settings") if cmd == "show advanced-settings" else (cmd,)
    for label in dict_labels:
        dict_pattern = (
            r"(?:rbod_test_mfg_default\.py\|\d+\||L\d+\s+DEBUG\|\s*)"
            + re.escape(label)
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

    xml_requests = ("show frus secrets", "show fru secrets") if cmd == "show frus secrets" else (cmd,)
    for req_name in xml_requests:
        parsed = _parse_last_xml_command_s1h44(text, req_name)
        if parsed is not None:
            return parsed

    raise ValueError(f"S1H44-62001: missing or incomplete '{cmd}' block with status")


def parse_s1h44_mfg_default_commands(log_path):
    """Parse all 7 required MSA commands from the mfg_restore_default_setting debug.log."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return {cmd: _extract_s1h44_mfg_command(text, cmd) for cmd in S1H44_MFG_COMMANDS}


def parse_s1h44_certificates(log_path):
    """Parse the LAST valid post-reset <RESPONSE REQUEST='show certificates'> XML block."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    parsed = _parse_last_xml_command_s1h44(text, "show certificates", "certificates")
    if parsed is not None:
        return parsed
    raise ValueError("S1H44-62001: missing valid 'show certificates' XML response with status")


def validate_s1h44_target_sn(raw_commands, target_sn):
    """Verify target_sn matches chassis midplane, SKU, FRU, and fru-secrets serials."""
    try:
        validate_s1h42_target_sn(raw_commands, target_sn)
    except ValueError as exc:
        raise ValueError(_rewrite_pn_prefix(exc)) from exc


def prepare_s1h44_data(raw_commands, target_sn):
    """Validate and canonically order all 8 MSA commands for chassis S1H44-62001."""
    try:
        return prepare_s1h42_data(raw_commands, target_sn)
    except ValueError as exc:
        raise ValueError(_rewrite_pn_prefix(exc)) from exc


def _render_ports_iscsi_s1h44(ports):
    """Render iSCSI Ports A & B tables and Port Details matching Section 4 (pages 15-19) of the S1H44-62001 FAIR PDF."""
    lines = []
    groups = [
        [p for p in ports if str(p.get("controller", "")).strip().upper() == "A"],
        [p for p in ports if str(p.get("controller", "")).strip().upper() == "B"],
    ]
    groups = [g for g in groups if g]

    for g_idx, group in enumerate(groups):
        if g_idx > 0:
            lines.append("")
        h1 = ("Ports", "Media", "Target ID", "Status")
        h2 = ("Speed(A)", "Speed(C)", "Health", "Reason", "Action")
        rows1 = [h1]
        rows2 = [h2]

        for p in group:
            actual_spd = str(p.get("actual-speed", "")).strip()
            speed_a = "" if (not actual_spd or actual_spd.upper() == "N/A") else actual_spd
            rows1.append((
                p.get("port", ""),
                p.get("media", ""),
                p.get("target-id", ""),
                p.get("status", ""),
            ))
            rows2.append((
                speed_a,
                p.get("configured-speed", ""),
                p.get("health", ""),
                p.get("health-reason", ""),
                p.get("health-recommendation", ""),
            ))

        w1 = _compute_col_widths(rows1, [8, 8, 52, 6])
        w2 = _compute_col_widths(rows2, [11, 11, 9, 9, 6])
        rule_len = max(79, sum(w1[:-1]) + len(h1[-1]), 3 + sum(w2[:-1]) + len(h2[-1]))

        lines.extend([
            _format_table_row(h1, w1),
            "   " + _format_table_row(h2, w2),
            "-" * rule_len,
        ])

        for idx, p in enumerate(group):
            if idx > 0:
                lines.append("")
            lines.append(_format_table_row(rows1[idx + 1], w1))
            lines.append("   " + _format_table_row(rows2[idx + 1], w2))
            lines.append("")
            lines.extend(["Port Details", "------------"])
            iscsi = (p.get("iscsi-port") or [{}])[0]
            lines.extend(_kv(lbl, iscsi.get(key, "")) for lbl, key in S1H44_ISCSI_PORT_DETAIL_FIELDS)

        lines.append("-" * rule_len)

    return lines


def render_s1h44_cli_report(data, target_sn):
    """Render FW.txt in MSA CLI format matching Section 4 (pages 5-25) of the S1H44-62001 FAIR PDF."""
    del target_sn
    lines = []

    # 1. # show firmware-bundles
    fw_cmd = data["show firmware-bundles"]
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
    fw_w = _compute_col_widths(fw_rows, [17, 23, 10, 9, 9, 6])
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

    # 5. # show frus secrets detail
    secrets_cmd = data["show frus secrets"]
    lines.extend(["# show frus secrets detail", ""])
    for idx, sec in enumerate(secrets_cmd["enclosure-fru-secrets"]):
        if idx > 0:
            lines.append("")
        lines.extend(["Midplane Information", "--------------------"])
        lines.extend(_kv(lbl, sec.get(key, "")) for lbl, key in S3T80_FRU_SECRETS_FIELDS)
    lines.append("")
    lines.extend(_format_status_lines(secrets_cmd["status"]))
    lines.extend(["", ""])

    # 6. # show configuration
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
    lines.extend(_render_ports_iscsi_s1h44(cfg_cmd["port"]))
    lines.append("")
    lines.extend(_render_storage_and_enclosure_tables(cfg_cmd))
    lines.append("")
    lines.extend(_render_sku_and_frus_chassis(cfg_cmd["enclosure-sku"], cfg_cmd["enclosure-fru"]))
    lines.append("")
    lines.extend(_format_status_lines(cfg_cmd["status"]))
    lines.extend(["", ""])

    # 7. # show certificates
    lines.extend(_render_certificates_cli(data["show certificates"]))
    lines.extend(["", ""])

    # 8. # show advanced-settings
    adv_cmd = data["show advanced-settings"]
    adv_obj = adv_cmd["advanced-settings-table"][0]
    lines.extend(["# show advanced-settings", ""])
    lines.extend(_kv(lbl, adv_obj.get(key, "")) for lbl, key in S1H44_ADVANCED_SETTINGS_FIELDS)
    lines.extend(_format_status_lines(adv_cmd["status"]))

    return [line.rstrip() + "\n" for line in lines]


def render_s1h44_raw_report(data, target_sn):
    """Render FW_RAW.md with clean Markdown tables and complete key:value dumps."""
    lines = [
        f"# Raw MSA CLI Data — {S1H44_PART_NUMBER}",
        "",
        f"- **Part Number**: `{S1H44_PART_NUMBER}`",
        f"- **Target SN**: `{target_sn}`",
        "- **Unit Type**: Chassis (`Chas S1H44` / HPE MSA 2070 10/25GbE iSCSI SFF Storage)",
        "- **Commands**: 8 (`show firmware-bundles`, `show system`, `show license`, `show frus detail`, `show frus secrets`, `show configuration`, `show certificates`, `show advanced-settings`)",
        "",
    ]

    for cmd in S1H44_ALL_COMMANDS:
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


def extract_s1h44_logs(test_results_dir, target_sn):
    """Extract FW.txt (MSA CLI) and FW_RAW.md (complete raw key:value) for S1H44-62001 chassis."""
    mfg_log_path = find_s1h44_mfg_default_log(test_results_dir)
    cert_log_path = find_s1h44_certificates_log(test_results_dir)

    raw_commands = parse_s1h44_mfg_default_commands(mfg_log_path)
    raw_commands["show certificates"] = parse_s1h44_certificates(cert_log_path)

    prepared = prepare_s1h44_data(raw_commands, target_sn)
    cli_lines = render_s1h44_cli_report(prepared, target_sn)
    raw_lines = render_s1h44_raw_report(prepared, target_sn)
    return cli_lines, raw_lines
