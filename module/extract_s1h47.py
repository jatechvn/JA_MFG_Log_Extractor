"""HPE MSA 2070 12Gb SAS LFF Storage Chassis (PN S1H47-62001) FW & Raw CLI log extraction."""

import os

from .extract_p61070 import (
    _dump_raw_node,
    _find_matching_step_dirs_desc,
)
from .extract_s1h41 import (
    _parse_last_xml_command,
    _render_raw_psu_versions_md_table,
)
from .extract_p61070 import _render_raw_versions_md_table
from .extract_s1h48 import (
    S1H48_ADVANCED_SETTINGS_FIELDS,
    S1H48_ALL_COMMANDS,
    S1H48_MFG_COMMANDS,
    _extract_s1h48_mfg_command,
    prepare_s1h48_data,
    render_s1h48_cli_report,
    validate_s1h48_target_sn,
)
from .log_io import find_step_dir, get_log_package_pn, to_long_path

S1H47_PART_NUMBER = "S1H47-62001"
S1H47_CLI_REPORT_NAME = "FW.txt"
S1H47_RAW_REPORT_NAME = "FW_RAW.md"

S1H47_MFG_COMMANDS = S1H48_MFG_COMMANDS
S1H47_ALL_COMMANDS = S1H48_ALL_COMMANDS
S1H47_ADVANCED_SETTINGS_FIELDS = S1H48_ADVANCED_SETTINGS_FIELDS


def _rewrite_pn_prefix(exc):
    """Rewrite S1H48-62001/S1H42-62001/S1H41-62001 error prefix to S1H47-62001:."""
    msg = str(exc)
    for prefix in ("S1H48-62001:", "S1H42-62001:", "S1H41-62001:"):
        if msg.startswith(prefix):
            return S1H47_PART_NUMBER + ":" + msg[len(prefix):]
    return msg


def check_is_s1h47(folder_name="", part_number=""):
    """Return True when the package or metadata PN is exactly S1H47-62001."""
    pn = (part_number or "").strip().upper()
    if not pn or pn == "-":
        pn = get_log_package_pn(folder_name or "")
    return pn == S1H47_PART_NUMBER


def find_s1h47_mfg_default_log(test_results_dir):
    """Locate the mfg restore default debug.log containing MSA show commands."""
    try:
        step_dir = find_step_dir(test_results_dir, "test_mfg_restore_default_setting")
    except FileNotFoundError:
        step_dir = find_step_dir(test_results_dir, "rbod_test_mfg_default")
    log_path = os.path.join(step_dir, "debug.log")
    if not os.path.isfile(to_long_path(log_path)):
        raise FileNotFoundError(f"S1H47-62001: missing debug.log in {step_dir}")
    return log_path


def find_s1h47_certificates_log(test_results_dir):
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
    raise ValueError("S1H47-62001: missing 'show certificates' XML response in restore_default steps")


def _extract_s1h47_mfg_command(text, cmd):
    """Parse one mfg command from debug.log (dict line first, XML response fallback)."""
    try:
        return _extract_s1h48_mfg_command(text, cmd)
    except ValueError as exc:
        raise ValueError(_rewrite_pn_prefix(exc)) from exc


def parse_s1h47_mfg_default_commands(log_path):
    """Parse all 7 required MSA commands from the mfg_restore_default_setting debug.log."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return {cmd: _extract_s1h47_mfg_command(text, cmd) for cmd in S1H47_MFG_COMMANDS}


def parse_s1h47_certificates(log_path):
    """Parse the LAST valid post-reset <RESPONSE REQUEST='show certificates'> XML block."""
    with open(to_long_path(log_path), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    parsed = _parse_last_xml_command(text, "show certificates", "certificates")
    if parsed is not None:
        return parsed
    raise ValueError("S1H47-62001: missing valid 'show certificates' XML response with status")


def validate_s1h47_target_sn(raw_commands, target_sn):
    """Verify target_sn matches chassis midplane, SKU, FRU, and fru-secrets serials."""
    try:
        validate_s1h48_target_sn(raw_commands, target_sn)
    except ValueError as exc:
        raise ValueError(_rewrite_pn_prefix(exc)) from exc


def prepare_s1h47_data(raw_commands, target_sn):
    """Validate and canonically order all 8 MSA commands for chassis S1H47-62001."""
    try:
        return prepare_s1h48_data(raw_commands, target_sn)
    except ValueError as exc:
        raise ValueError(_rewrite_pn_prefix(exc)) from exc


def render_s1h47_cli_report(data, target_sn):
    """Render FW.txt in MSA CLI format matching Section 4 (pages 6-22) of the S1H47-62001 FAIR PDF."""
    return render_s1h48_cli_report(data, target_sn)


def render_s1h47_raw_report(data, target_sn):
    """Render FW_RAW.md with clean Markdown tables and complete key:value dumps."""
    lines = [
        f"# Raw MSA CLI Data — {S1H47_PART_NUMBER}",
        "",
        f"- **Part Number**: `{S1H47_PART_NUMBER}`",
        f"- **Target SN**: `{target_sn}`",
        "- **Unit Type**: Chassis (`Chas S1H47` / HPE MSA 2070 12Gb SAS LFF Storage)",
        "- **Commands**: 8 (`show firmware-bundles`, `show system`, `show license`, `show frus detail`, `show frus secrets`, `show configuration`, `show certificates`, `show advanced-settings`)",
        "",
    ]

    for cmd in S1H47_ALL_COMMANDS:
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


def extract_s1h47_logs(test_results_dir, target_sn):
    """Extract FW.txt (MSA CLI) and FW_RAW.md (complete raw key:value) for S1H47-62001 chassis."""
    mfg_log_path = find_s1h47_mfg_default_log(test_results_dir)
    cert_log_path = find_s1h47_certificates_log(test_results_dir)

    raw_commands = parse_s1h47_mfg_default_commands(mfg_log_path)
    raw_commands["show certificates"] = parse_s1h47_certificates(cert_log_path)

    prepared = prepare_s1h47_data(raw_commands, target_sn)
    cli_lines = render_s1h47_cli_report(prepared, target_sn)
    raw_lines = render_s1h47_raw_report(prepared, target_sn)
    return cli_lines, raw_lines
