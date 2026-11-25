"""HPE MSA 2070 16Gb FC SFF Storage Chassis (PN S1H42-62001) FW & Raw CLI log extraction."""

import ast
import copy
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
    _order_by_controller,
    _parse_last_xml_command,
    _render_controller_chassis,
    _render_fru_versions_chassis,
    _render_raw_psu_versions_md_table,
    _render_sku_and_frus_chassis,
    _render_storage_and_enclosure_tables,
    _render_system_info_chassis,
    _render_two_column_kv_table,
    _require_controllers_a_and_b,
    validate_s1h41_target_sn,
)
from .extract_s3t80 import S3T80_FRU_SECRETS_FIELDS, _render_ports_s3t80
from .log_io import find_step_dir, get_log_package_pn, to_long_path

S1H42_PART_NUMBER = "S1H42-62001"
S1H42_CLI_REPORT_NAME = "FW.txt"
S1H42_RAW_REPORT_NAME = "FW_RAW.md"

S1H42_MFG_COMMANDS = (
    "show firmware-bundles",
    "show system",
    "show license",
    "show frus detail",
    "show frus secrets",
    "show configuration",
    "show advanced-settings",
)

S1H42_ALL_COMMANDS = (
    "show firmware-bundles",
    "show system",
    "show license",
    "show frus detail",
    "show frus secrets",
    "show configuration",
    "show certificates",
    "show advanced-settings",
)

S1H42_ADVANCED_SETTINGS_FIELDS = (
    ("Disk Group Background Scrub", "background-scrub"),
    ("Partner Firmware Upgrade", "partner-firmware-upgrade"),
    ("Utility Priority", "utility-priority"),
    ("SMART", "smart"),
    ("Dynamic Spare Configuration", "dynamic-spares"),
    ("Enclosure Polling Rate", "emp-poll-rate"),
    ("Host Control of Caching", "host-cache-control"),
    ("Sync Cache Mode", "sync-cache-mode"),
    ("Missing LUN Response", "missing-lun-response"),
    ("Controller Failure", "controller-failure"),
    ("Supercap Failure", "super-cap-failure"),
    ("Power Supply Failure", "power-supply-failure"),
    ("Fan Failure", "fan-failure"),
    ("Temperature Exceeded", "temperature-exceeded"),
    ("Partner Notify", "partner-notify"),
    ("Auto Write Back", "auto-write-back"),
    ("Inactive Drive Spin Down", "disk-dsd-enable"),
    ("Inactive Drive Spin Down Delay", "disk-dsd-delay"),
    ("Managed Logs", "managed-logs"),
    ("Auto Stall Recovery", "auto-stall-recovery"),
    ("Restart on CAPI Fail", "restart-on-capi-fail"),
    ("Auto Map", "auto-map"),
    ("Auto Unmap", "auto-unmap"),
    ("Default Mapping", "default-mapping"),
    ("Slow Disk Detection", "slow-disk-detection"),
    ("Scrub Schedule", "scrub-schedule"),
)


def check_is_s1h42(folder_name="", part_number=""):
    """Return True when the package or metadata PN is exactly S1H42-62001."""
    pn = (part_number or "").strip().upper()
    if not pn or pn == "-":
        pn = get_log_package_pn(folder_name or "")
    return pn == S1H42_PART_NUMBER


def find_s1h42_mfg_default_log(test_results_dir):
    """Locate the mfg restore default debug.log containing MSA show commands."""
    try:
        step_dir = find_step_dir(test_results_dir, "test_mfg_restore_default_setting")
    except FileNotFoundError:
        step_dir = find_step_dir(test_results_dir, "rbod_test_mfg_default")
    log_path = os.path.join(step_dir, "debug.log")
    if not os.path.isfile(to_long_path(log_path)):
        raise FileNotFoundError(f"S1H42-62001: missing debug.log in {step_dir}")
    return log_path


def find_s1h42_certificates_log(test_results_dir):
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
    raise ValueError("S1H42-62001: missing 'show certificates' XML response in restore_default steps")


def _extract_s1h42_mfg_command(text, cmd):
    """Parse one mfg command from debug.log (dict line first, XML response fallback)."""
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
        xml_pattern = r'<RESPONSE\b[^>]*\bREQUEST="' + re.escape(req_name) + r'"[^>]*>.*?</RESPONSE>'
        xml_matches = re.findall(xml_pattern, text, re.DOTALL)
        for raw_xml in reversed(xml_matches):
            try:
                parsed = _parse_xml_response(raw_xml)
            except ET.ParseError:
                continue
            if _has_valid_status(parsed):
                return parsed

    raise ValueError(f"S1H42-62001: missing or incomplete '{cmd}' block with status")


def parse_s1h42_mfg_default_commands(log_path):
    """Parse all 7 required MSA commands from the mfg_restore_default_setting debug.log."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return {cmd: _extract_s1h42_mfg_command(text, cmd) for cmd in S1H42_MFG_COMMANDS}


def parse_s1h42_certificates(log_path):
    """Parse the LAST valid post-reset <RESPONSE REQUEST='show certificates'> XML block."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    parsed = _parse_last_xml_command(text, "show certificates", "certificates")
    if parsed is not None:
        return parsed
    raise ValueError("S1H42-62001: missing valid 'show certificates' XML response with status")


def validate_s1h42_target_sn(raw_commands, target_sn):
    """Verify target_sn matches chassis midplane, SKU, FRU, and fru-secrets serials."""
    try:
        validate_s1h41_target_sn(raw_commands, target_sn)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("S1H41-62001:"):
            msg = S1H42_PART_NUMBER + ":" + msg[len("S1H41-62001:"):]
        raise ValueError(msg) from exc

    sn_up = (target_sn or "").strip().upper()
    secrets_list = raw_commands.get("show frus secrets", {}).get("enclosure-fru-secrets", [])
    if not secrets_list:
        raise ValueError("S1H42-62001: missing enclosure-fru-secrets in 'show frus secrets'")
    for sec in secrets_list:
        if not isinstance(sec, dict):
            raise ValueError("S1H42-62001: invalid enclosure-fru-secrets entry")
        tlasn = str(sec.get("fru-tlasn", "")).strip().upper()
        oemsn = str(sec.get("fru-oemsn", "")).strip().upper()
        if tlasn != sn_up:
            raise ValueError(
                f"S1H42-62001: 'show frus secrets' fru-tlasn '{tlasn}' contradicts target SN '{sn_up}'"
            )
        if oemsn != sn_up:
            raise ValueError(
                f"S1H42-62001: 'show frus secrets' fru-oemsn '{oemsn}' contradicts target SN '{sn_up}'"
            )


def prepare_s1h42_data(raw_commands, target_sn):
    """Validate and canonically order all 8 MSA commands for chassis S1H42-62001."""
    for cmd in S1H42_ALL_COMMANDS:
        if cmd not in raw_commands or not _has_valid_status(raw_commands[cmd]):
            raise ValueError(f"S1H42-62001: missing required command or status for '{cmd}'")

    validate_s1h42_target_sn(raw_commands, target_sn)

    fw_cmd = copy.deepcopy(raw_commands["show firmware-bundles"])
    if not fw_cmd.get("firmware-bundles"):
        raise ValueError("S1H42-62001: empty firmware-bundles in 'show firmware-bundles'")

    sys_cmd = copy.deepcopy(raw_commands["show system"])
    if not sys_cmd.get("system"):
        raise ValueError("S1H42-62001: empty system list in 'show system'")

    lic_cmd = copy.deepcopy(raw_commands["show license"])
    if not lic_cmd.get("license"):
        raise ValueError("S1H42-62001: empty license list in 'show license'")

    frus_cmd = copy.deepcopy(raw_commands["show frus detail"])
    if not frus_cmd.get("enclosure-sku") or not frus_cmd.get("enclosure-fru"):
        raise ValueError("S1H42-62001: missing enclosure-sku or enclosure-fru in 'show frus detail'")

    secrets_cmd = copy.deepcopy(raw_commands["show frus secrets"])
    if not secrets_cmd.get("enclosure-fru-secrets"):
        raise ValueError("S1H42-62001: empty enclosure-fru-secrets in 'show frus secrets'")

    cfg_cmd = copy.deepcopy(raw_commands["show configuration"])
    if not cfg_cmd.get("system"):
        raise ValueError("S1H42-62001: empty system list in 'show configuration'")

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
        raise ValueError("S1H42-62001: missing controller-a-versions or controller-b-versions in 'show configuration'")
    cfg_cmd["versions"] = [ver_by_obj["controller-a-versions"], ver_by_obj["controller-b-versions"]]

    fru_versions = cfg_cmd.get("fru-versions", [])
    if not fru_versions:
        raise ValueError("S1H42-62001: missing fru-versions in 'show configuration'")
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
        raise ValueError("S1H42-62001: missing midplane-versions in 'show configuration'")
    if not {"A", "B"}.issubset(exp_ctrls):
        raise ValueError("S1H42-62001: missing expander-versions for Controller A or B")
    if not has_psus:
        raise ValueError("S1H42-62001: missing psu-versions in 'show configuration'")

    ports = copy.deepcopy(cfg_cmd.get("port", []))
    if not ports:
        for ctrl in ordered_ctrls:
            ports.extend(copy.deepcopy(ctrl.get("port", [])))
    ports = _order_by_controller(ports, "controller")
    port_ctrls = {str(p.get("controller", "")).strip().upper() for p in ports}
    if not {"A", "B"}.issubset(port_ctrls):
        raise ValueError("S1H42-62001: missing ports for Controller A or B")
    cfg_cmd["port"] = ports

    if not cfg_cmd.get("enclosures"):
        raise ValueError("S1H42-62001: missing enclosures in 'show configuration'")
    if not cfg_cmd.get("enclosure-sku") or not cfg_cmd.get("enclosure-fru"):
        raise ValueError("S1H42-62001: missing enclosure-sku or enclosure-fru in 'show configuration'")

    cert_cmd = copy.deepcopy(raw_commands["show certificates"])
    certs = _order_by_controller(cert_cmd.get("certificates", []), "certificate-controller")
    cert_ctrls = {str(c.get("certificate-controller", "")).strip().upper() for c in certs}
    if not {"A", "B"}.issubset(cert_ctrls):
        raise ValueError("S1H42-62001: missing certificate for Controller A or B")
    cert_cmd["certificates"] = certs

    adv_cmd = copy.deepcopy(raw_commands["show advanced-settings"])
    adv_table = adv_cmd.get("advanced-settings-table", [])
    if not isinstance(adv_table, list) or not adv_table or not all(isinstance(row, dict) for row in adv_table):
        raise ValueError("S1H42-62001: empty or invalid advanced-settings-table in 'show advanced-settings'")

    return {
        "show firmware-bundles": fw_cmd,
        "show system": sys_cmd,
        "show license": lic_cmd,
        "show frus detail": frus_cmd,
        "show frus secrets": secrets_cmd,
        "show configuration": cfg_cmd,
        "show certificates": cert_cmd,
        "show advanced-settings": adv_cmd,
    }


def render_s1h42_cli_report(data, target_sn):
    """Render FW.txt in MSA CLI format matching Section 4 (pages 6-24) of the S1H42-62001 FAIR PDF."""
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
    lines.extend(_render_ports_s3t80(cfg_cmd["port"]))
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
    lines.extend(_kv(lbl, adv_obj.get(key, "")) for lbl, key in S1H42_ADVANCED_SETTINGS_FIELDS)
    lines.extend(_format_status_lines(adv_cmd["status"]))

    return [line.rstrip() + "\n" for line in lines]


def render_s1h42_raw_report(data, target_sn):
    """Render FW_RAW.md with clean Markdown tables and complete key:value dumps."""
    lines = [
        f"# Raw MSA CLI Data — {S1H42_PART_NUMBER}",
        "",
        f"- **Part Number**: `{S1H42_PART_NUMBER}`",
        f"- **Target SN**: `{target_sn}`",
        "- **Unit Type**: Chassis (`Chas S1H42` / HPE MSA 2070 16Gb FC SFF Storage)",
        "- **Commands**: 8 (`show firmware-bundles`, `show system`, `show license`, `show frus detail`, `show frus secrets`, `show configuration`, `show certificates`, `show advanced-settings`)",
        "",
    ]

    for cmd in S1H42_ALL_COMMANDS:
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


def extract_s1h42_logs(test_results_dir, target_sn):
    """Extract FW.txt (MSA CLI) and FW_RAW.md (complete raw key:value) for S1H42-62001 chassis."""
    mfg_log_path = find_s1h42_mfg_default_log(test_results_dir)
    cert_log_path = find_s1h42_certificates_log(test_results_dir)

    raw_commands = parse_s1h42_mfg_default_commands(mfg_log_path)
    raw_commands["show certificates"] = parse_s1h42_certificates(cert_log_path)

    prepared = prepare_s1h42_data(raw_commands, target_sn)
    cli_lines = render_s1h42_cli_report(prepared, target_sn)
    raw_lines = render_s1h42_raw_report(prepared, target_sn)
    return cli_lines, raw_lines
