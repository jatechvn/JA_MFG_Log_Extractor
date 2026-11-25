"""HPE MSA 2070 12Gb SAS SFF Storage Chassis (PN S1H48-62001) FW & Raw CLI log extraction."""

import os

from .extract_p61070 import (
    P61070_VERSION_FIELDS,
    _compute_col_widths,
    _dump_raw_node,
    _find_matching_step_dirs_desc,
    _format_status_lines,
    _format_table_row,
    _kv,
    _render_certificates_cli,
    _render_raw_versions_md_table,
)
from .extract_s1h41 import (
    S1H41_LICENSE_FIELDS,
    _parse_last_xml_command,
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
    _extract_s1h42_mfg_command,
    prepare_s1h42_data,
    validate_s1h42_target_sn,
)
from .extract_s3t80 import S3T80_FRU_SECRETS_FIELDS
from .log_io import find_step_dir, get_log_package_pn, to_long_path

S1H48_PART_NUMBER = "S1H48-62001"
S1H48_CLI_REPORT_NAME = "FW.txt"
S1H48_RAW_REPORT_NAME = "FW_RAW.md"

S1H48_MFG_COMMANDS = S1H42_MFG_COMMANDS
S1H48_ALL_COMMANDS = S1H42_ALL_COMMANDS
S1H48_ADVANCED_SETTINGS_FIELDS = S1H42_ADVANCED_SETTINGS_FIELDS


def _rewrite_pn_prefix(exc):
    """Rewrite S1H42-62001: error prefix from shared validation to S1H48-62001:."""
    msg = str(exc)
    if msg.startswith("S1H42-62001:"):
        return S1H48_PART_NUMBER + ":" + msg[len("S1H42-62001:"):]
    if msg.startswith("S1H41-62001:"):
        return S1H48_PART_NUMBER + ":" + msg[len("S1H41-62001:"):]
    return msg


def check_is_s1h48(folder_name="", part_number=""):
    """Return True when the package or metadata PN is exactly S1H48-62001."""
    pn = (part_number or "").strip().upper()
    if not pn or pn == "-":
        pn = get_log_package_pn(folder_name or "")
    return pn == S1H48_PART_NUMBER


def find_s1h48_mfg_default_log(test_results_dir):
    """Locate the mfg restore default debug.log containing MSA show commands."""
    try:
        step_dir = find_step_dir(test_results_dir, "test_mfg_restore_default_setting")
    except FileNotFoundError:
        step_dir = find_step_dir(test_results_dir, "rbod_test_mfg_default")
    log_path = os.path.join(step_dir, "debug.log")
    if not os.path.isfile(to_long_path(log_path)):
        raise FileNotFoundError(f"S1H48-62001: missing debug.log in {step_dir}")
    return log_path


def find_s1h48_certificates_log(test_results_dir):
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
    raise ValueError("S1H48-62001: missing 'show certificates' XML response in restore_default steps")


def _extract_s1h48_mfg_command(text, cmd):
    """Parse one mfg command from debug.log (dict line first, XML response fallback)."""
    try:
        return _extract_s1h42_mfg_command(text, cmd)
    except ValueError as exc:
        raise ValueError(_rewrite_pn_prefix(exc)) from exc


def parse_s1h48_mfg_default_commands(log_path):
    """Parse all 7 required MSA commands from the mfg_restore_default_setting debug.log."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return {cmd: _extract_s1h48_mfg_command(text, cmd) for cmd in S1H48_MFG_COMMANDS}


def parse_s1h48_certificates(log_path):
    """Parse the LAST valid post-reset <RESPONSE REQUEST='show certificates'> XML block."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    parsed = _parse_last_xml_command(text, "show certificates", "certificates")
    if parsed is not None:
        return parsed
    raise ValueError("S1H48-62001: missing valid 'show certificates' XML response with status")


def validate_s1h48_target_sn(raw_commands, target_sn):
    """Verify target_sn matches chassis midplane, SKU, FRU, and fru-secrets serials."""
    try:
        validate_s1h42_target_sn(raw_commands, target_sn)
    except ValueError as exc:
        raise ValueError(_rewrite_pn_prefix(exc)) from exc


def prepare_s1h48_data(raw_commands, target_sn):
    """Validate and canonically order all 8 MSA commands for chassis S1H48-62001."""
    try:
        return prepare_s1h42_data(raw_commands, target_sn)
    except ValueError as exc:
        raise ValueError(_rewrite_pn_prefix(exc)) from exc


def _render_ports_sas_s1h48(ports):
    """Render SAS Ports A & B tables matching Section 4 pages 16-17 of the S1H48-62001 FAIR PDF."""
    lines = []
    groups = [
        [p for p in ports if str(p.get("controller", "")).strip().upper() == "A"],
        [p for p in ports if str(p.get("controller", "")).strip().upper() == "B"],
    ]
    groups = [g for g in groups if g]

    for g_idx, group in enumerate(groups):
        if g_idx > 0:
            lines.append("")
        main_header = ("Ports", "Media", "Target ID", "Status", "Speed(A)", "Health", "Reason", "Action")
        main_rows = [main_header]
        sub_header = ("Topo(C)", "Lanes Expected", "Active Lanes", "Disabled Lanes")
        sub_rows = [sub_header]

        for p in group:
            actual_spd = str(p.get("actual-speed", "")).strip()
            speed_a = "" if (not actual_spd or actual_spd.upper() == "N/A") else actual_spd
            main_rows.append((
                p.get("port", ""),
                p.get("media", ""),
                p.get("target-id", ""),
                p.get("status", ""),
                speed_a,
                p.get("health", ""),
                p.get("health-reason", ""),
                p.get("health-recommendation", ""),
            ))
            sas = (p.get("sas-port") or [{}])[0]
            sub_rows.append((
                sas.get("configured-topology", "Direct"),
                sas.get("sas-lanes-expected", ""),
                sas.get("sas-active-lanes", ""),
                sas.get("sas-disabled-lanes", ""),
            ))

        mw = _compute_col_widths(main_rows, [8, 8, 19, 10, 11, 9, 8, 6])
        sw = _compute_col_widths(sub_rows, [10, 17, 15, 14])
        main_rule = max(76, sum(mw[:-1]) + len(main_header[-1]))
        sub_rule = max(56, sum(sw[:-1]) + len(sub_header[-1]))

        lines.extend([_format_table_row(main_header, mw), "-" * main_rule])
        for i in range(1, len(main_rows)):
            lines.append(_format_table_row(main_rows[i], mw))
            lines.append("   " + _format_table_row(sub_header, sw))
            lines.append("   " + ("-" * sub_rule))
            lines.append("   " + _format_table_row(sub_rows[i], sw))
        lines.append("-" * main_rule)

    return lines


def render_s1h48_cli_report(data, target_sn):
    """Render FW.txt in MSA CLI format matching Section 4 (pages 6-23) of the S1H48-62001 FAIR PDF."""
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
    lines.extend(_render_ports_sas_s1h48(cfg_cmd["port"]))
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
    lines.extend(_kv(lbl, adv_obj.get(key, "")) for lbl, key in S1H48_ADVANCED_SETTINGS_FIELDS)
    lines.extend(_format_status_lines(adv_cmd["status"]))

    return [line.rstrip() + "\n" for line in lines]


def render_s1h48_raw_report(data, target_sn):
    """Render FW_RAW.md with clean Markdown tables and complete key:value dumps."""
    lines = [
        f"# Raw MSA CLI Data — {S1H48_PART_NUMBER}",
        "",
        f"- **Part Number**: `{S1H48_PART_NUMBER}`",
        f"- **Target SN**: `{target_sn}`",
        "- **Unit Type**: Chassis (`Chas S1H48` / HPE MSA 2070 12Gb SAS SFF Storage)",
        "- **Commands**: 8 (`show firmware-bundles`, `show system`, `show license`, `show frus detail`, `show frus secrets`, `show configuration`, `show certificates`, `show advanced-settings`)",
        "",
    ]

    for cmd in S1H48_ALL_COMMANDS:
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


def extract_s1h48_logs(test_results_dir, target_sn):
    """Extract FW.txt (MSA CLI) and FW_RAW.md (complete raw key:value) for S1H48-62001 chassis."""
    mfg_log_path = find_s1h48_mfg_default_log(test_results_dir)
    cert_log_path = find_s1h48_certificates_log(test_results_dir)

    raw_commands = parse_s1h48_mfg_default_commands(mfg_log_path)
    raw_commands["show certificates"] = parse_s1h48_certificates(cert_log_path)

    prepared = prepare_s1h48_data(raw_commands, target_sn)
    cli_lines = render_s1h48_cli_report(prepared, target_sn)
    raw_lines = render_s1h48_raw_report(prepared, target_sn)
    return cli_lines, raw_lines
