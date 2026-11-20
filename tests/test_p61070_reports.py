import contextlib
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape

import extract_mfg_logs as app
from module import extract_p61070 as p61070


@contextlib.contextmanager
def _long_temp_dir():
    tmp = tempfile.mkdtemp(prefix="p61070_test_")
    try:
        yield tmp
    finally:
        shutil.rmtree(app.to_long_path(tmp), ignore_errors=True)


def _dict_to_xml_elements(tag_basetype, obj_dict):
    """Build an MSA XML <OBJECT> element tree matching a parsed dict."""
    obj_name = obj_dict.get("object-name", tag_basetype)
    lines = [f'  <OBJECT basetype="{tag_basetype}" name="{obj_name}">']
    nested = []
    for k, v in obj_dict.items():
        if k == "object-name":
            continue
        if isinstance(v, list):
            for child in v:
                nested.append((k, child))
        else:
            lines.append(f'    <PROPERTY name="{k}" type="string">{escape(str(v))}</PROPERTY>')
    for child_basetype, child_dict in nested:
        child_xml = _dict_to_xml_elements(child_basetype, child_dict)
        lines.extend("  " + row for row in child_xml.splitlines())
    lines.append("  </OBJECT>")
    return "\n".join(lines)


def _build_xml_response(request_cmd, payload_dict):
    """Build a complete <RESPONSE VERSION='L100' REQUEST='...'> XML block."""
    parts = [f'<RESPONSE VERSION="L100" REQUEST="{request_cmd}">']
    for basetype, items in payload_dict.items():
        for item in items:
            parts.append(_dict_to_xml_elements(basetype, item))
    parts.append("</RESPONSE>")
    return "\n".join(parts)


def _sample_p61070_payloads(
    sn_a="1VAD4YB000",
    sn_b="1VAD4YB007",
    *,
    host_a="HPE00C0FF764AD1A",
    host_b="HPE00C0FF764AD1B",
):
    """Create consistent synthetic P61070-001 command payloads for Controllers A & B."""
    status = lambda ts: [{
        "object-name": "status",
        "response-type": "Success",
        "response": f"Command completed successfully. ({ts})",
        "return-code": "0",
        "time-stamp": ts,
    }]

    fw_bundles = {
        "firmware-bundles": [{
            "object-name": "firmware-bundle",
            "bundle-version": "IN300R007",
            "build-date": "2025-07-30T16:48:42Z",
            "status": "Active",
            "health": "OK",
            "health-reason": "",
            "health-recommendation": "",
        }],
        "status": status("2026-09-28 10:59:06"),
    }

    sys_obj = {
        "object-name": "system-information",
        "system-name": "Uninitialized Name",
        "system-contact": "Uninitialized Contact",
        "system-location": "Uninitialized Location",
        "system-information": "Uninitialized Info",
        "midplane-serial-number": "1VAD4WB005",
        "vendor-name": "HPE",
        "product-id": "MSA 2070 FC",
        "product-brand": "MSA Storage",
        "scsi-vendor-id": "HPE",
        "scsi-product-id": "MSA 2070 FC",
        "enclosure-count": "1",
        "health": "OK",
        "health-reason": "",
        "other-MC-status": "Operational",
        "pfuStatus": "Idle",
        "security-system-management": "Not in use",
        "supported-locales": "English (English), Japanese (日本語), Korean (한국어), Chinese-Simplified (简体中文)",
        "redundancy": [{
            "object-name": "system-redundancy",
            "redundancy-mode": "Active-Active ULP",
            "redundancy-status": "Redundant",
            "controller-a-status": "Operational",
            "controller-a-serial-number": sn_a,
            "controller-b-status": "Operational",
            "controller-b-serial-number": sn_b,
        }],
    }

    system_cmd = {
        "system": [sys_obj],
        "status": status("2026-09-28 10:58:51"),
    }

    fru_midplane = {
        "object-name": "fru",
        "name": "CHASSIS_MIDPLANE",
        "description": "SPS-MSA 12G SFF Chassis",
        "part-number": "P62784-001",
        "serial-number": "1VAD4WB005",
        "revision": "DL",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "2026-03-25 02:11:00",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "MID-PLANE SLOT",
        "fru-status": "OK",
        "enclosure-id": "1",
    }
    fru_a = {
        "object-name": "fru",
        "name": "RAID_IOM",
        "description": "SPS-MSA 2070 16G FC Controller",
        "part-number": "P61070-001",
        "serial-number": sn_a,
        "revision": "D",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "2026-09-28 16:20:00",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "UPPER IOM SLOT",
        "fru-status": "OK",
        "enclosure-id": "1",
    }
    fru_b = {
        "object-name": "fru",
        "name": "RAID_IOM",
        "description": "SPS-MSA 2070 16G FC Controller",
        "part-number": "P61070-001",
        "serial-number": sn_b,
        "revision": "D",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "2026-09-28 16:21:00",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "LOWER IOM SLOT",
        "fru-status": "OK",
        "enclosure-id": "1",
    }
    fru_psu = {
        "object-name": "fru",
        "name": "POWER_SUPPLY",
        "description": "SPS-MSA PWR supply OneStor 580W Plat AC",
        "part-number": "P49169-001",
        "serial-number": "1VAD4ZB039",
        "revision": "B",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "N/A",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "LEFT PSU SLOT",
        "fru-status": "OK",
        "enclosure-id": "1",
    }
    frus_cmd = {
        "enclosure-sku": [{"object-name": "sku", "sku-partnumber": "1110280-01", "sku_serialnumber": "1VAD4WB005"}],
        "enclosure-fru": [fru_midplane, fru_a, fru_b, fru_psu],
        "status": status("2026-09-28 10:59:06"),
    }

    def make_port(cid, idx, wwn):
        return {
            "object-name": "ports",
            "controller": cid,
            "port": f"{cid}{idx}",
            "media": "FC(P)",
            "target-id": wwn,
            "status": "Up" if cid == "B" else "Disconnected",
            "actual-speed": "16Gb" if cid == "B" else "N/A",
            "configured-speed": "Auto",
            "health": "OK",
            "health-reason": "",
            "fc-port": [{
                "object-name": "port-details",
                "configured-topology": "PTP",
                "primary-loop-id": "N/A",
                "sfp-status": "OK" if cid == "B" else "Not present",
                "sfp-present": "Present" if cid == "B" else "Not present",
                "sfp-part-number": "FTLF8529P4BCV-1D" if cid == "B" else "",
                "sfp-supported-speeds": "4G,8G,16G" if cid == "B" else "N/A",
            }],
        }

    def make_ctrl(cid, sn, mac, ip, pos, wwn_prefix):
        return {
            "object-name": "controller",
            "controller-id": cid,
            "serial-number": sn,
            "hardware-version": "2.3",
            "cpld-version": "2.8",
            "mac-address": mac,
            "node-wwn": "208000C0FF764AD1",
            "ip-address": ip,
            "ip-subnet-mask": "255.255.255.0",
            "ip-gateway": "10.0.0.254",
            "ip6-link-local-address": "fe80::1" if cid == "A" else "fe80::2",
            "ip6-link-local-gateway": "::",
            "autoconfig": "Enabled",
            "dhcpv6": "::",
            "slaac-ip": "::",
            "ip6-auto-gateway": "::",
            "disks": "0",
            "number-of-storage-pools": "0",
            "virtual-disks": "0",
            "system-memory-size": "24576",
            "host-ports": "4",
            "drive-channels": "4",
            "drive-bus-type": "SAS",
            "status": "Operational",
            "failed-over": "No",
            "fail-over-reason": "Not applicable",
            "multicore": "Enabled",
            "health": "OK",
            "health-reason": "",
            "health-recommendation": "",
            "position": pos,
            "phy-isolation": "Enabled",
            "redundancy-mode": "Active-Active ULP",
            "redundancy-status": "Redundant",
            "port": [make_port(cid, i, f"{wwn_prefix}{i}7000c0ff764ad1") for i in range(1, 5)],
        }

    def make_versions(obj_name):
        return {
            "object-name": obj_name,
            "sc-cpu-type": "D-1627 2900MHz",
            "bundle-version": "IN300R007",
            "bundle-base-version": "I300",
            "build-date": "2025-07-30T16:48:42Z",
            "sc-fw": "INS300R25-01",
            "sc-baselevel": "INS300R25-01",
            "sc-fu-version": "1.76.1ddf7c1",
            "sc-loader": "0.019",
            "capi-version": "3.21",
            "mc-fw": "IXM300R025-01",
            "mc-loader": "1.76.1ddf7c1",
            "ec-fw": "6036",
            "pld-rev": "2.8",
            "hw-rev": "2.3",
            "him-rev": "3",
            "him-model": "2",
            "backplane-type": "7",
            "host-channel_revision": "1",
            "disk-channel_revision": "0",
            "mrc-version": "0.1.9.19",
            "ctk-version": "No CTK present",
            "mcos-version": "IPM300R025-01",
            "gem-version": "usm-rss_sbbsas_24g_loki_hpe-v6.x_lite-r2025.07.0_rc1_rel_57",
            "pubs-version": "1.0.0.16",
            "translation-version": "8.3.0.10",
        }

    ports_a = [make_port("A", i, f"2{i-1}7000c0ff764ad1") for i in range(1, 5)]
    ports_b = [make_port("B", i, f"2{i+3}7000c0ff764ad1") for i in range(1, 5)]

    config_cmd = {
        "system": [sys_obj],
        "controllers": [
            make_ctrl("A", sn_a, "00:C0:FF:83:62:E0", "10.0.0.2", "Top", "2"),
            make_ctrl("B", sn_b, "00:C0:FF:83:62:CA", "10.0.0.3", "Bottom", "2"),
        ],
        "dns-parameters": [
            {"object-name": "controller-a", "controller": "A", "name-servers": "10.0.0.254", "search-domains": ""},
            {"object-name": "controller-b", "controller": "B", "name-servers": "10.0.0.254", "search-domains": ""},
        ],
        "mgmt-hostnames": [
            {"object-name": "mgmt-hostnames", "controller": "A", "mgmt-hostname": host_a, "domain-name": ""},
            {"object-name": "mgmt-hostnames", "controller": "B", "mgmt-hostname": host_b, "domain-name": ""},
        ],
        "versions": [
            make_versions("controller-a-versions"),
            make_versions("controller-b-versions"),
        ],
        "fru-versions": [{
            "object-name": "fru-versions",
            "enclosure-id": "1",
            "midplane-versions": [{"object-name": "midplane-versions", "midplane-serial-number": "1VAD4WB005"}],
            "expander-versions": [
                {
                    "object-name": "expander-versions",
                    "name": "Root Expander-A",
                    "location": "Enclosure 1, Iom A",
                    "controller": "A",
                    "fw-revision": "6036",
                    "fw-revision-full": "06000036",
                    "vpd-format-version": "06",
                    "vpd-crc": "16DA015E",
                    "cfg-format-version": "01",
                    "cfg-crc": "B2FF3D7C",
                    "bootloader-version": "0100",
                    "cpld-version": "0208",
                    "part-number": "6005920202",
                    "serial-number": "BAFVN26338362E0",
                },
                {
                    "object-name": "expander-versions",
                    "name": "Root Expander-B",
                    "location": "Enclosure 1, Iom B",
                    "controller": "B",
                    "fw-revision": "6036",
                    "fw-revision-full": "06000036",
                    "vpd-format-version": "06",
                    "vpd-crc": "16DA015E",
                    "cfg-format-version": "01",
                    "cfg-crc": "B2FF3D7C",
                    "bootloader-version": "0100",
                    "cpld-version": "0208",
                    "part-number": "6005920202",
                    "serial-number": "BAFVN26338362CA",
                },
            ],
            "psu-versions": [{"object-name": "psu-versions", "psu-serial-number": "PMF1104029P4ETR"}],
        }],
        "port": ports_a + ports_b,
        "enclosure-fru": [fru_midplane, fru_a, fru_b, fru_psu],
        "status": status("2026-09-28 10:58:52"),
    }

    stale_certs = {
        "certificates": [
            {
                "object-name": "certinfo",
                "certificate-name": "gen_cert_a",
                "certificate-type": "Device-Cert",
                "certificate-controller": "A",
                "certificate-service-web": "x",
                "certificate-valid-from": "Sep 28 10:22:24 2026 GMT",
                "certificate-valid-till": "Sep 25 10:22:24 2036 GMT",
                "certificate-issued-to": "HPE00C0FF761C95B",
                "certificate-issued-by": "HPE00C0FF761C95B",
                "certificate-state": "Available",
                "certificate-status": "System-generated",
                "certificate-default-services": "WEB",
                "certificate-encryption-type": "RSA",
            },
            {
                "object-name": "certinfo",
                "certificate-name": "gen_cert_b",
                "certificate-type": "Device-Cert",
                "certificate-controller": "B",
                "certificate-service-web": "x",
                "certificate-valid-from": "Sep 28 10:23:02 2026 GMT",
                "certificate-valid-till": "Sep 25 10:23:02 2036 GMT",
                "certificate-issued-to": "HPE00C0FF761C95A",
                "certificate-issued-by": "HPE00C0FF761C95A",
                "certificate-state": "Available",
                "certificate-status": "System-generated",
                "certificate-default-services": "WEB",
                "certificate-encryption-type": "RSA",
            },
        ],
        "status": status("2026-09-28 10:30:12"),
    }

    fresh_certs = {
        "certificates": [
            {
                "object-name": "certinfo",
                "certificate-name": "gen_cert_a",
                "certificate-type": "Device-Cert",
                "certificate-controller": "A",
                "certificate-service-web": "x",
                "certificate-valid-from": "Sep 28 10:33:26 2026 GMT",
                "certificate-valid-till": "Sep 25 10:33:26 2036 GMT",
                "certificate-issued-to": host_a,
                "certificate-issued-by": host_a,
                "certificate-state": "Available",
                "certificate-status": "System-generated",
                "certificate-default-services": "WEB",
                "certificate-encryption-type": "RSA",
            },
            {
                "object-name": "certinfo",
                "certificate-name": "gen_cert_b",
                "certificate-type": "Device-Cert",
                "certificate-controller": "B",
                "certificate-service-web": "x",
                "certificate-valid-from": "Sep 28 10:32:27 2026 GMT",
                "certificate-valid-till": "Sep 25 10:32:27 2036 GMT",
                "certificate-issued-to": host_b,
                "certificate-issued-by": host_b,
                "certificate-state": "Available",
                "certificate-status": "System-generated",
                "certificate-default-services": "WEB",
                "certificate-encryption-type": "RSA",
            },
        ],
        "status": status("2026-09-28 10:42:53"),
    }

    return {
        "show firmware-bundles": fw_bundles,
        "show system": system_cmd,
        "show frus detail": frus_cmd,
        "show configuration": config_cmd,
        "stale_certs": stale_certs,
        "fresh_certs": fresh_certs,
    }


def _write_text(path_obj, text):
    """Write UTF-8 text safely across Windows MAX_PATH paths."""
    long_p = app.to_long_path(str(path_obj))
    os.makedirs(os.path.dirname(long_p), exist_ok=True)
    with open(long_p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _write_synthetic_p61070_unit(root_dir, payloads, *, mfg_as_xml_only=False):
    """Create a minimal synthetic CTP test directory for P61070-001."""
    unit_dir = Path(root_dir) / "rbod_fin2_test_uut0_P61070-001_1VAD4YB000_1VAD4YB007_20260928-155654"
    job_dir = unit_dir / "job-2026-09-28T15.57-b43d831"
    tr_dir = job_dir / "test-results"
    step58 = tr_dir / "58-_CTP_testcases_mfg-test_restore_default.py_RestoreDefault.test_restore_defaults_factory_remove_certs_-e630"
    step62 = tr_dir / "62-_CTP_testcases_mfg-test_rbod_test_mfg_default.py_Rbod_mfg_restore_default_test.test_mfg_restore_default_setting_-e630"

    _write_text(
        unit_dir / f"{unit_dir.name}.log",
        "2026-09-28 15:57:00| DEBUG | rbod_fin2.py | 1163| Input Dict - {'uut_pn': 'P61070-001', 'employee_id': '100001'}\n"
        "2026-09-28 15:57:01| SUM   | Local start time: 2026-09-28 15:55:50\n"
        "2026-09-28 18:07:26| SUM   | Script rbod_fin2_test passed\n"
        "2026-09-28 18:07:26| SUM   | Local end time: 2026-09-28 18:07:26\n"
        "2026-09-28 18:07:26| SUM   | Test duration: 0 days 2 hours 11 minutes 36 seconds\n",
    )
    _write_text(
        unit_dir / "ctp_log_metadata.yaml",
        "HOST_NAME: vnmctp116187\nTEST_NAME: rbod_fin2_test\nTEST_STATUS: COMPLETED\n",
    )
    _write_text(
        job_dir / "results.json",
        '{"time": 7890.0, "pass": 64, "failures": 0, "errors": 0, "skip": 0, "total": 64}',
    )

    cert_log_text = "\n\n".join([
        "2026-09-28 17:33:30|DEBUG|Bytes read:\n" + _build_xml_response("show certificates", payloads["stale_certs"]),
        "2026-09-28 17:45:46|DEBUG|Bytes read:\n" + _build_xml_response("show certificates", payloads["fresh_certs"]),
    ])
    _write_text(step58 / "debug.log", cert_log_text + "\n")

    mfg_chunks = []
    for cmd in p61070.P61070_MFG_COMMANDS:
        if mfg_as_xml_only:
            mfg_chunks.append(_build_xml_response(cmd, payloads[cmd]))
        else:
            mfg_chunks.append(f"2026-09-28 18:01:54|DEBUG   |MainThread  |avocado.test|rbod_test_mfg_default.py|0088|{cmd}:\n{repr(payloads[cmd])}")
    _write_text(step62 / "debug.log", "\n".join(mfg_chunks) + "\n")
    return unit_dir, step58 / "debug.log", step62 / "debug.log"


class P61070ReportsTest(unittest.TestCase):
    def test_package_pn_and_sn_detection_for_p61070_without_breaking_legacy(self):
        self.assertEqual(
            app.get_log_package_pn("rbod_fin2_test_uut0_P61070-001_1VAD4YB000_1VAD4YB007_20260928-155654"),
            "P61070-001",
        )
        self.assertEqual(
            app.get_log_package_pn("rbod_fin2_test_uut0_P61070-001_2MXD2YG0S0_2MXD2YG0S2_20250703-095915"),
            "P61070-001",
        )
        self.assertEqual(
            app.get_log_package_pn("rbod_bft_test_uut0_BAFVN262583617D_20260716-100011"),
            "",
        )
        self.assertEqual(
            app.get_log_package_pn("jbod_cto_test_uut0_7PNTN_SGFVN26428364DE_20261024-074325"),
            "7PNTN",
        )
        self.assertEqual(
            app.get_log_package_pn("jbod_cto_test_uut0_RPC73_SAFVN26468368F7_SAFVN26468368F5_20261111-014122"),
            "RPC73",
        )

        self.assertTrue(p61070.check_is_p61070("rbod_fin2_test_uut0_P61070-001_1VAD4YB000_1VAD4YB007_20260928-155654"))
        self.assertTrue(p61070.check_is_p61070("renamed_folder", "p61070-001"))
        self.assertFalse(p61070.check_is_p61070("rbod_fin2_test_uut0_XP61070-001_1VAD4YB000_1VAD4YB007_20260928-155654"))

        self.assertEqual(
            app.detect_sns_from_folder(r"D:\logs\rbod_fin2_test_uut0_P61070-001_1VAD4YB000_1VAD4YB007_20260928-155654"),
            ["1VAD4YB000", "1VAD4YB007"],
        )
        self.assertEqual(
            app.detect_sns_from_folder(r"D:\logs\rbod_fin2_test_uut0_P61070-001_1VAD4YB000_1VAD4YB007_20260928-155654.zip"),
            ["1VAD4YB000", "1VAD4YB007"],
        )
        self.assertEqual(
            app.detect_sns_from_folder("rbod_bft_test_uut0_BAFVN262583617D_20260716-100011"),
            ["BAFVN262583617D"],
        )

    def test_controller_matching_and_contradiction_rejection(self):
        payloads = _sample_p61070_payloads()
        self.assertEqual(
            p61070.detect_p61070_controller(payloads["show configuration"], payloads["show frus detail"], "1VAD4YB000"),
            ("ctrla", "A"),
        )
        self.assertEqual(
            p61070.detect_p61070_controller(payloads["show configuration"], payloads["show frus detail"], "1vad4yb007"),
            ("ctrlb", "B"),
        )
        with self.assertRaisesRegex(ValueError, "expected exactly 1 controller matching SN"):
            p61070.detect_p61070_controller(payloads["show configuration"], payloads["show frus detail"], "UNKNOWN_SN")

        bad_frus = _sample_p61070_payloads()["show frus detail"]
        bad_frus["enclosure-fru"][2]["fru-location"] = "UPPER IOM SLOT"
        with self.assertRaisesRegex(ValueError, "contradicts FRU location"):
            p61070.detect_p61070_controller(payloads["show configuration"], bad_frus, "1VAD4YB007")

        bad_cfg = _sample_p61070_payloads()["show configuration"]
        bad_cfg["system"][0]["redundancy"][0]["controller-b-serial-number"] = "1VAD4YB000"
        with self.assertRaisesRegex(ValueError, "redundancy controller-b-serial-number"):
            p61070.detect_p61070_controller(bad_cfg, payloads["show frus detail"], "1VAD4YB007")

    def test_certificates_parser_picks_last_post_reset_xml_and_filters_controller(self):
        payloads = _sample_p61070_payloads()
        with _long_temp_dir() as tmp:
            _, step58_log, step62_log = _write_synthetic_p61070_unit(tmp, payloads)
            raw = p61070.parse_p61070_mfg_default_commands(str(step62_log))
            raw["show certificates"] = p61070.parse_p61070_certificates(str(step58_log))

        filtered = p61070.filter_p61070_data(raw, "1VAD4YB007", "B")
        certs = filtered["show certificates"]["certificates"]
        self.assertEqual(len(certs), 1)
        self.assertEqual(certs[0]["certificate-name"], "gen_cert_b")
        self.assertEqual(certs[0]["certificate-issued-to"], "HPE00C0FF764AD1B")
        self.assertIn("2026-09-28 10:42:53", filtered["show certificates"]["status"][0]["response"])

    def test_mfg_default_parser_supports_dict_and_xml_fallback(self):
        payloads = _sample_p61070_payloads()
        with _long_temp_dir() as tmp_dict, _long_temp_dir() as tmp_xml:
            _, _, dict_log = _write_synthetic_p61070_unit(tmp_dict, payloads, mfg_as_xml_only=False)
            _, _, xml_log = _write_synthetic_p61070_unit(tmp_xml, payloads, mfg_as_xml_only=True)
            parsed_dict = p61070.parse_p61070_mfg_default_commands(str(dict_log))
            parsed_xml = p61070.parse_p61070_mfg_default_commands(str(xml_log))

        for cmd in p61070.P61070_MFG_COMMANDS:
            self.assertEqual(parsed_xml[cmd]["status"][0]["response"], parsed_dict[cmd]["status"][0]["response"])
        self.assertEqual(len(parsed_xml["show configuration"]["port"]), 8)
        self.assertEqual(len(parsed_xml["show configuration"]["versions"]), 2)

    def test_versions_keeps_two_columns_and_does_not_glue_long_values(self):
        payloads = _sample_p61070_payloads()
        with _long_temp_dir() as tmp:
            _, step58_log, step62_log = _write_synthetic_p61070_unit(tmp, payloads)
            raw = p61070.parse_p61070_mfg_default_commands(str(step62_log))
            raw["show certificates"] = p61070.parse_p61070_certificates(str(step58_log))

        filtered = p61070.filter_p61070_data(raw, "1VAD4YB007", "B")
        cli_text = "".join(p61070.render_p61070_cli_report(filtered, "1VAD4YB007", "B"))
        raw_text = "".join(p61070.render_p61070_raw_report(filtered, "1VAD4YB007", "B"))

        self.assertIn("Controller A Versions", cli_text)
        self.assertIn("Controller B Versions", cli_text)
        gem_line = next(line for line in cli_text.splitlines() if line.startswith("GEM Version:"))
        gem_val = "usm-rss_sbbsas_24g_loki_hpe-v6.x_lite-r2025.07.0_rc1_rel_57"
        self.assertIn(f"{gem_val}    {gem_val}", gem_line)

        self.assertIn("### Versions (Controller A vs Controller B)", raw_text)
        self.assertIn(f"| `gem-version` | {gem_val} | {gem_val} |", raw_text)
        self.assertIn("object-name: controller-a-versions", raw_text)
        self.assertIn("object-name: controller-b-versions", raw_text)

    def test_fail_before_write_on_missing_required_sections(self):
        payloads = _sample_p61070_payloads()
        with _long_temp_dir() as tmp:
            unit_dir, step58_log, _ = _write_synthetic_p61070_unit(tmp, payloads)
            out_dir = Path(tmp) / "out"

            # Remove certificates XML response
            _write_text(step58_log, "no cert output here\n")
            with self.assertRaisesRegex(ValueError, "show certificates"):
                app.process_single_extraction(str(unit_dir), "1VAD4YB007", str(out_dir), quiet=True)
            self.assertFalse((out_dir / "1VAD4YB007" / "FW.txt").exists())
            self.assertFalse((out_dir / "1VAD4YB007" / "FW_RAW.md").exists())

        # Remove target controller ports -> filter fails
        bad_raw = _sample_p61070_payloads()
        bad_raw["show certificates"] = bad_raw["fresh_certs"]
        bad_raw["show configuration"]["port"] = [
            p for p in bad_raw["show configuration"]["port"] if p["controller"] != "B"
        ]
        bad_raw["show configuration"]["controllers"][1]["port"] = []
        with self.assertRaisesRegex(ValueError, "missing ports for controller B"):
            p61070.filter_p61070_data(bad_raw, "1VAD4YB007", "B")

        # Missing target expander -> filter fails
        bad_raw2 = _sample_p61070_payloads()
        bad_raw2["show certificates"] = bad_raw2["fresh_certs"]
        bad_raw2["show configuration"]["fru-versions"][0]["expander-versions"] = [
            e for e in bad_raw2["show configuration"]["fru-versions"][0]["expander-versions"] if e["controller"] != "B"
        ]
        with self.assertRaisesRegex(ValueError, "missing expander-versions for controller B"):
            p61070.filter_p61070_data(bad_raw2, "1VAD4YB007", "B")

    def test_end_to_end_process_single_extraction_and_golden_compare(self):
        payloads = _sample_p61070_payloads()
        with _long_temp_dir() as tmp:
            unit_dir, _, _ = _write_synthetic_p61070_unit(tmp, payloads)
            out_dir = Path(tmp) / "out"

            res_b = app.process_single_extraction(str(unit_dir), "1VAD4YB007", str(out_dir), quiet=True)
            res_a = app.process_single_extraction(str(unit_dir), "1VAD4YB000", str(out_dir), quiet=True)

            self.assertEqual(res_b["unit_type"], "IO P61070")
            self.assertEqual(res_b["controller"], "ctrlb")
            self.assertEqual(res_b["warnings"], [])
            self.assertEqual(res_a["unit_type"], "IO P61070")
            self.assertEqual(res_a["controller"], "ctrla")
            self.assertEqual(res_a["warnings"], [])

            fw_b_bytes = (out_dir / "1VAD4YB007" / "FW.txt").read_bytes()
            raw_b_bytes = (out_dir / "1VAD4YB007" / "FW_RAW.md").read_bytes()
            self.assertIn(b"\r\n", fw_b_bytes)
            self.assertIn(b"\r\n", raw_b_bytes)
            self.assertFalse(fw_b_bytes.endswith(b"\r\n"))
            self.assertFalse(raw_b_bytes.endswith(b"\r\n"))

            fw_b = fw_b_bytes.decode("utf-8")
            raw_b = raw_b_bytes.decode("utf-8")
            for text in (fw_b, raw_b):
                self.assertIn("1VAD4YB007", text)
                self.assertIn("Root Expander-B", text)
                self.assertIn("B1", text)
                self.assertIn("gen_cert_b", text)
                self.assertIn("HPE00C0FF764AD1B", text)
                self.assertIn("2026-09-28 10:42:53", text)
                # Zero sibling IOM, stale cert, Midplane, or PSU leakage
                for forbidden in (
                    "1VAD4YB000", "00:C0:FF:83:62:E0", "10.0.0.2", "A1",
                    "Root Expander-A", "gen_cert_a", "HPE00C0FF764AD1A",
                    "HPE00C0FF761C95", "CHASSIS_MIDPLANE", "POWER_SUPPLY", "1VAD4ZB039",
                ):
                    self.assertNotRegex(text, r"(?<![A-Za-z0-9_.])" + re.escape(forbidden) + r"(?![A-Za-z0-9_.])")
                self.assertNotIn("HPE00C0FF761C95", text)
            self.assertNotIn("Rates may vary", fw_b)

            fw_a = (out_dir / "1VAD4YB000" / "FW.txt").read_text(encoding="utf-8")
            self.assertIn("UPPER IOM SLOT", fw_a)
            self.assertIn("gen_cert_a", fw_a)
            self.assertNotIn("1VAD4YB007", fw_a)
            self.assertNotIn("gen_cert_b", fw_a)

            sample_dir = Path(tmp) / "sample_b"
            shutil.copytree(out_dir / "1VAD4YB007", sample_dir)
            matched, results = app.compare_with_golden_sample(str(out_dir / "1VAD4YB007"), str(sample_dir))
            self.assertTrue(matched)
            self.assertEqual(sorted(r["file"] for r in results), ["FW.txt", "FW_RAW.md"])

            (sample_dir / "FW_RAW.md").write_text("tampered\n", encoding="utf-8")
            matched_after, _ = app.compare_with_golden_sample(str(out_dir / "1VAD4YB007"), str(sample_dir))
            self.assertFalse(matched_after)


if __name__ == "__main__":
    unittest.main()
