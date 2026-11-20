import contextlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape

import extract_mfg_logs as app
from module import extract_s1h41 as s1h41


@contextlib.contextmanager
def _long_temp_dir():
    tmp = tempfile.mkdtemp(prefix="s1h41_test_")
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


def _write_text(path_obj, text):
    """Write UTF-8 text safely across Windows MAX_PATH paths."""
    long_p = app.to_long_path(str(path_obj))
    os.makedirs(os.path.dirname(long_p), exist_ok=True)
    with open(long_p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _sample_s1h41_payloads(
    chassis_sn="1VAD4ZB004",
    sn_a="1VAD4YB00P",
    sn_b="1VAD4YB00R",
    *,
    host_a="HPE00C0FF000000A",
    host_b="HPE00C0FF000000B",
):
    """Create consistent synthetic S1H41-62001 payloads covering all 6 MSA commands."""
    status = lambda ts: [{
        "object-name": "status",
        "response-type": "Success",
        "response": f"Command completed successfully. ({ts})",
        "return-code": "0",
        "time-stamp": ts,
    }]

    fw_bundles_stale = {
        "firmware-bundles": [
            {
                "object-name": "firmware-bundle",
                "bundle-version": "IN300R007",
                "build-date": "2025-07-30T16:48:42Z",
                "status": "Active/Default",
                "health": "OK",
                "health-reason": "",
                "health-recommendation": "",
            },
            {
                "object-name": "firmware-bundle",
                "bundle-version": "IN300M004e",
                "build-date": "2024-09-22T13:00:30Z",
                "status": "Available",
                "health": "OK",
                "health-reason": "",
                "health-recommendation": "",
            },
        ],
        "status": status("2026-11-06 11:29:22"),
    }

    fw_bundles_all_final = {
        "firmware-bundles": [{
            "object-name": "firmware-bundle",
            "bundle-version": "IN300R007",
            "build-date": "2025-07-30T16:48:42Z",
            "status": "Active/Default",
            "health": "OK",
            "health-reason": "",
            "health-recommendation": "",
        }],
        "status": status("2026-11-06 11:34:05"),
    }

    sys_obj = {
        "object-name": "system-information",
        "system-name": "Uninitialized Name",
        "system-contact": "Uninitialized Contact",
        "system-location": "Uninitialized Location",
        "system-information": "Uninitialized Info",
        "midplane-serial-number": chassis_sn,
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
        "status": status("2026-11-06 12:02:36"),
    }

    license_cmd = {
        "license": [{
            "object-name": "license",
            "license-key": "",
            "license-serial-number": "836223",
            "platform-max-snapshots": "1024",
            "base-max-snapshots": "64",
            "max-snapshots": "64",
            "in-use-snapshots": "0",
            "max-snapshots-expiry": "Never",
            "virtualization": "Enabled",
            "virtualization-expiry": "Never",
            "performance-tier": "Disabled",
            "performance-tier-expiry": "Never",
            "volume-copy": "Enabled",
            "volume-copy-expiry": "Never",
            "remote-snapshot-replication": "Disabled",
            "remote-snapshot-replication-expiry": "Never",
            "vds": "Enabled",
            "vss": "Enabled",
            "vss-expiry": "Never",
            "dsd": "Disabled",
            "sra": "Enabled",
        }],
        "status": status("2026-11-06 12:02:37"),
    }

    sku_list = [{
        "object-name": "sku",
        "sku-partnumber": "S1H41A",
        "sku_serialnumber": chassis_sn,
        "sku-revision": "2100",
        "enclosure-id": "1",
    }]

    fru_midplane = {
        "object-name": "fru",
        "name": "CHASSIS_MIDPLANE",
        "description": "SPS-MSA 12G LFF Chassis",
        "part-number": "P62783-001",
        "serial-number": chassis_sn,
        "revision": "DL",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "2026-08-01 09:07:00",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "MID-PLANE SLOT",
        "configuration-serialnumber": chassis_sn,
        "fru-status": "OK",
        "original-serialnumber": "",
        "original-partnumber": "",
        "original-revision": "",
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
        "mfg-date": "2026-08-01 09:07:00",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "UPPER IOM SLOT",
        "configuration-serialnumber": chassis_sn,
        "fru-status": "OK",
        "original-serialnumber": "",
        "original-partnumber": "",
        "original-revision": "",
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
        "mfg-date": "2026-11-06 17:30:00",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "LOWER IOM SLOT",
        "configuration-serialnumber": chassis_sn,
        "fru-status": "OK",
        "original-serialnumber": "",
        "original-partnumber": "",
        "original-revision": "",
        "enclosure-id": "1",
    }
    fru_psu_l = {
        "object-name": "fru",
        "name": "POWER_SUPPLY",
        "description": "SPS-MSA PWR supply OneStor 580W Plat AC",
        "part-number": "P49169-001",
        "serial-number": "1VAD50B004",
        "revision": "D",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "N/A",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "LEFT PSU SLOT",
        "configuration-serialnumber": chassis_sn,
        "fru-status": "OK",
        "original-serialnumber": "PMF1104029P5YJT",
        "original-partnumber": "1104029-05",
        "original-revision": "",
        "enclosure-id": "1",
    }
    fru_psu_r = {
        "object-name": "fru",
        "name": "POWER_SUPPLY",
        "description": "SPS-MSA PWR supply OneStor 580W Plat AC",
        "part-number": "P49169-001",
        "serial-number": "1VAD50B002",
        "revision": "D",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "N/A",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "RIGHT PSU SLOT",
        "configuration-serialnumber": chassis_sn,
        "fru-status": "OK",
        "original-serialnumber": "PMF1104029P5YH4",
        "original-partnumber": "1104029-05",
        "original-revision": "",
        "enclosure-id": "1",
    }

    frus_cmd = {
        "enclosure-sku": sku_list,
        "enclosure-fru": [fru_midplane, fru_a, fru_b, fru_psu_l, fru_psu_r],
        "status": status("2026-11-06 12:02:51"),
    }

    def make_port(cid, idx, wwn):
        return {
            "object-name": "ports",
            "controller": cid,
            "port": f"{cid}{idx}",
            "media": "FC(P)",
            "target-id": wwn,
            "status": "Up",
            "actual-speed": "16Gb",
            "configured-speed": "Auto",
            "health": "OK",
            "health-reason": "",
            "fc-port": [{
                "object-name": "port-details",
                "configured-topology": "PTP",
                "primary-loop-id": "N/A",
                "sfp-status": "OK",
                "sfp-present": "Present",
                "sfp-part-number": "FTLF8529P4BCV-1D",
                "sfp-supported-speeds": "4G,8G,16G",
            }],
        }

    def make_ctrl(cid, sn, mac, ip, pos, wwn_offset):
        return {
            "object-name": "controller",
            "controller-id": cid,
            "serial-number": sn,
            "hardware-version": "2.3",
            "cpld-version": "2.8",
            "mac-address": mac,
            "node-wwn": "208000C0FF836223",
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
            "port": [make_port(cid, i, f"2{i - 1 + wwn_offset}7000c0ff836223") for i in range(1, 5)],
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

    ports_a = [make_port("A", i, f"2{i - 1}7000c0ff836223") for i in range(1, 5)]
    ports_b = [make_port("B", i, f"2{i + 3}7000c0ff836223") for i in range(1, 5)]
    slots = [
        {
            "object-name": "drive",
            "status": "Not Present",
            "enclosure-id": "1",
            "slot": str(idx),
            "vendor": "N/A",
            "model": "N/A",
            "serial-number": "N/A",
            "size": "0B",
        }
        for idx in range(1, 13)
    ]

    config_cmd = {
        "system": [sys_obj],
        "controllers": [
            make_ctrl("A", sn_a, "00:C0:FF:83:62:9F", "10.0.0.2", "Top", 0),
            make_ctrl("B", sn_b, "00:C0:FF:83:62:FC", "10.0.0.3", "Bottom", 4),
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
            "midplane-versions": [{
                "object-name": "midplane-versions",
                "vpd-format-version": "13",
                "vpd-crc": "22E0DE83",
                "cfg-mismatch-version": "00",
                "cpld-version": "2100",
                "fru-descriptor": "81",
                "part-number": "1110278-01",
                "midplane-serial-number": chassis_sn,
            }],
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
                    "serial-number": "BAFVN263383629F",
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
                    "serial-number": "BAFVN26338362FC",
                },
            ],
            "psu-versions": [
                {
                    "object-name": "psu-versions",
                    "name": "PSU 1, Left",
                    "fw-revision": "0303",
                    "dsp-version": "0202",
                    "vpd-format-version": "05",
                    "vpd-crc": "4D503DD4",
                    "fru-descriptor": "FD",
                    "part-number": "1104029-05",
                    "psu-serial-number": "PMF1104029P5YJT",
                },
                {
                    "object-name": "psu-versions",
                    "name": "PSU 2, Right",
                    "fw-revision": "0303",
                    "dsp-version": "0202",
                    "vpd-format-version": "05",
                    "vpd-crc": "4D503DD4",
                    "fru-descriptor": "FD",
                    "part-number": "1104029-05",
                    "psu-serial-number": "PMF1104029P5YH4",
                },
            ],
        }],
        "port": ports_a + ports_b,
        "enclosure-list": slots,
        "enclosures": [{
            "object-name": "enclosures",
            "enclosure-id": "1",
            "enclosure-wwn": "500C0FF08362233C",
            "name": "",
            "location": "",
            "rack-number": "0",
            "rack-position": "0",
            "vendor": "HPE",
            "model": "MSA2070-ENCL-LFF",
            "fru-tlapn": "S1H41A",
            "emp-a-ch-id-rev": "01:127 6036",
            "emp-b-ch-id-rev": "00:127 6036",
            "midplane-type": "2U12-12Gv3",
            "health": "OK",
            "health-reason": "",
            "health-recommendation": "",
            "midplane-serial-number": chassis_sn,
        }],
        "enclosure-sku": sku_list,
        "enclosure-fru": [fru_midplane, fru_a, fru_b, fru_psu_l, fru_psu_r],
        "status": status("2026-11-06 12:02:37"),
    }

    stale_certs = {
        "certificates": [
            {
                "object-name": "certinfo",
                "certificate-name": "gen_cert_a",
                "certificate-type": "Device-Cert",
                "certificate-controller": "A",
                "certificate-service-web": "x",
                "certificate-valid-from": "Oct 14 10:38:58 2026 GMT",
                "certificate-valid-till": "Oct 11 10:38:58 2036 GMT",
                "certificate-issued-to": "HPE00C0FF000000A",
                "certificate-issued-by": "HPE00C0FF000000A",
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
                "certificate-valid-from": "Oct 14 10:36:58 2026 GMT",
                "certificate-valid-till": "Oct 11 10:36:58 2036 GMT",
                "certificate-issued-to": "HPE00C0FF000000B",
                "certificate-issued-by": "HPE00C0FF000000B",
                "certificate-state": "Available",
                "certificate-status": "System-generated",
                "certificate-default-services": "WEB",
                "certificate-encryption-type": "RSA",
            },
        ],
        "status": status("2026-11-06 11:33:50"),
    }

    fresh_certs = {
        "certificates": [
            {
                "object-name": "certinfo",
                "certificate-name": "gen_cert_a",
                "certificate-type": "Device-Cert",
                "certificate-controller": "A",
                "certificate-service-web": "x",
                "certificate-valid-from": "Nov  6 11:37:59 2026 GMT",
                "certificate-valid-till": "Nov  3 11:37:59 2036 GMT",
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
                "certificate-valid-from": "Nov  6 11:40:00 2026 GMT",
                "certificate-valid-till": "Nov  3 11:40:00 2036 GMT",
                "certificate-issued-to": host_b,
                "certificate-issued-by": host_b,
                "certificate-state": "Available",
                "certificate-status": "System-generated",
                "certificate-default-services": "WEB",
                "certificate-encryption-type": "RSA",
            },
        ],
        "status": status("2026-11-06 11:47:08"),
    }

    return {
        "fw_bundles_stale": fw_bundles_stale,
        "show firmware-bundles all": fw_bundles_all_final,
        "show system": system_cmd,
        "show license": license_cmd,
        "show frus detail": frus_cmd,
        "show configuration": config_cmd,
        "stale_certs": stale_certs,
        "fresh_certs": fresh_certs,
    }


def _write_synthetic_s1h41_unit(
    root_dir,
    payloads,
    *,
    mfg_as_xml_only=False,
    include_step57=True,
    include_step55=True,
):
    """Create a synthetic CTP test directory for S1H41-62001."""
    unit_dir = Path(root_dir) / "rbod_fin2_test_uut0_S1H41-62001_1VAD4ZB004_20261106-170516"
    job_dir = unit_dir / "job-2026-11-06T17.05-a4f9a5d"
    tr_dir = job_dir / "test-results"
    step55 = tr_dir / "55-_CTP_testcases_mfg-test_restore_default.py_RestoreDefault.test_restore_default_factory_firmware_-e630"
    step57 = tr_dir / "57-_CTP_testcases_mfg-test_rbod_rfwd_test.py_RbodRFWDTest.test_rbod_rfwd_-e630"
    step58 = tr_dir / "58-_CTP_testcases_mfg-test_restore_default.py_RestoreDefault.test_restore_defaults_factory_remove_certs_-e630"
    step62 = tr_dir / "62-_CTP_testcases_mfg-test_rbod_test_mfg_default.py_Rbod_mfg_restore_default_test.test_mfg_restore_default_setting_-e630"

    _write_text(
        unit_dir / f"{unit_dir.name}.log",
        "2026-11-06 17:05:21| DEBUG | rbod_fin2.py | 1163| Input Dict - {'uut_pn': 'S1H41-62001', 'employee_id': '100001'}\n"
        "2026-11-06 17:05:21| SUM   | Local start time: 2026-11-06 17:04:42\n"
        "2026-11-06 19:19:09| SUM   | Script rbod_fin2_test passed\n"
        "2026-11-06 19:19:09| SUM   | Local end time: 2026-11-06 19:19:09\n"
        "2026-11-06 19:19:09| SUM   | Test duration: 0 days 2 hours 14 minutes 26 seconds\n",
    )
    _write_text(
        unit_dir / "ctp_log_metadata.yaml",
        "HOST_NAME: vnmctp116193\nTEST_NAME: rbod_fin2_test\nTEST_STATUS: COMPLETED\n",
    )
    _write_text(
        job_dir / "results.json",
        '{"time": 8050.0, "pass": 64, "failures": 0, "errors": 0, "skip": 0, "total": 64}',
    )

    if include_step55:
        step55_text = "\n".join([
            '2026-11-06 18:40:47|DEBUG|Bytes read: b\'<RESPONSE VERSION="L100" REQUEST="show firmware-bundles all">\\n<broken>\'</RESPONSE>',
            _build_xml_response("show firmware-bundles all", payloads["fw_bundles_stale"]),
        ])
        _write_text(step55 / "debug.log", step55_text + "\n")

    if include_step57:
        step57_text = "\n\n".join([
            _build_xml_response("show firmware-bundles all", payloads["fw_bundles_stale"]),
            _build_xml_response("show firmware-bundles all", payloads["show firmware-bundles all"]),
        ])
        _write_text(step57 / "debug.log", step57_text + "\n")

    cert_log_text = "\n\n".join([
        "2026-11-06 18:44:50|DEBUG|Bytes read:\n" + _build_xml_response("show certificates", payloads["stale_certs"]),
        "2026-11-06 18:58:09|DEBUG|Bytes read:\n" + _build_xml_response("show certificates", payloads["fresh_certs"]),
    ])
    _write_text(step58 / "debug.log", cert_log_text + "\n")

    mfg_chunks = []
    for cmd in s1h41.S1H41_MFG_COMMANDS:
        if mfg_as_xml_only:
            mfg_chunks.append(_build_xml_response(cmd, payloads[cmd]))
        else:
            mfg_chunks.append(
                f"2026-11-06 19:13:45|DEBUG   |MainThread  |avocado.test|rbod_test_mfg_default.py|0088|{cmd}:\n"
                f"{repr(payloads[cmd])}"
            )
    _write_text(step62 / "debug.log", "\n".join(mfg_chunks) + "\n")
    return unit_dir, step55 / "debug.log", step57 / "debug.log", step58 / "debug.log", step62 / "debug.log"


class S1H41ReportsTest(unittest.TestCase):
    def test_package_pn_and_sn_detection_for_s1h41_without_breaking_legacy(self):
        self.assertEqual(
            app.get_log_package_pn("rbod_fin2_test_uut0_S1H41-62001_1VAD4ZB004_20261106-170516"),
            "S1H41-62001",
        )
        self.assertTrue(s1h41.check_is_s1h41("rbod_fin2_test_uut0_S1H41-62001_1VAD4ZB004_20261106-170516"))
        self.assertTrue(s1h41.check_is_s1h41("renamed_folder", "s1h41-62001"))
        self.assertFalse(s1h41.check_is_s1h41("rbod_fin2_test_uut0_S1H42-62001_1VAD4ZB031_20261008-103324"))
        self.assertFalse(s1h41.check_is_s1h41("rbod_fin2_test_uut0_P61070-001_1VAD4YB000_1VAD4YB007_20260928-155654"))
        self.assertFalse(s1h41.check_is_s1h41("rbod_fin2_test_uut0_XS1H41-62001_1VAD4ZB004_20261106-170516"))

        self.assertEqual(
            app.detect_sns_from_folder(r"D:\logs\rbod_fin2_test_uut0_S1H41-62001_1VAD4ZB004_20261106-170516"),
            ["1VAD4ZB004"],
        )
        self.assertEqual(
            app.detect_sns_from_folder(r"D:\logs\rbod_fin2_test_uut0_S1H41-62001_ACVD1DW001_20240817-022929.zip"),
            ["ACVD1DW001"],
        )
        # Preserve legacy and P61070 detection
        self.assertEqual(
            app.detect_sns_from_folder("rbod_fin2_test_uut0_P61070-001_1VAD4YB000_1VAD4YB007_20260928-155654"),
            ["1VAD4YB000", "1VAD4YB007"],
        )
        self.assertEqual(
            app.detect_sns_from_folder("rbod_bft_test_uut0_BAFVN262583617D_20260716-100011"),
            ["BAFVN262583617D"],
        )
        self.assertEqual(
            app.get_log_package_pn("jbod_cto_test_uut0_7PNTN_SGFVN26428364DE_20261024-074325"),
            "7PNTN",
        )
        self.assertEqual(
            app.get_log_package_pn("jbod_cto_test_uut0_RPC73_SAFVN26468368F7_SAFVN26468368F5_20261111-014122"),
            "RPC73",
        )

    def test_fw_bundles_all_selection_and_step55_fallback(self):
        payloads = _sample_s1h41_payloads()
        with _long_temp_dir() as tmp:
            unit_dir, _, _, _, _ = _write_synthetic_s1h41_unit(tmp, payloads, include_step57=True, include_step55=True)
            tr_dir = unit_dir / "job-2026-11-06T17.05-a4f9a5d" / "test-results"
            chosen_log = s1h41.find_s1h41_fw_bundles_all_log(str(tr_dir))
            self.assertIn("57-", chosen_log)
            parsed = s1h41.parse_s1h41_fw_bundles_all(chosen_log)
            self.assertEqual(len(parsed["firmware-bundles"]), 1)
            self.assertEqual(parsed["firmware-bundles"][0]["status"], "Active/Default")
            self.assertIn("2026-11-06 11:34:05", parsed["status"][0]["response"])

        with _long_temp_dir() as tmp_fb:
            unit_dir, _, _, _, _ = _write_synthetic_s1h41_unit(tmp_fb, payloads, include_step57=False, include_step55=True)
            tr_dir = unit_dir / "job-2026-11-06T17.05-a4f9a5d" / "test-results"
            chosen_log = s1h41.find_s1h41_fw_bundles_all_log(str(tr_dir))
            self.assertIn("55-", chosen_log)
            parsed = s1h41.parse_s1h41_fw_bundles_all(chosen_log)
            self.assertEqual(parsed["firmware-bundles"][0]["status"], "Active/Default")
            self.assertIn("2026-11-06 11:29:22", parsed["status"][0]["response"])

    def test_certificates_picks_last_post_reset_xml_and_keeps_both_controllers(self):
        payloads = _sample_s1h41_payloads()
        with _long_temp_dir() as tmp:
            unit_dir, _, _, step58_log, step62_log = _write_synthetic_s1h41_unit(tmp, payloads)
            raw = s1h41.parse_s1h41_mfg_default_commands(str(step62_log))
            raw["show firmware-bundles all"] = payloads["show firmware-bundles all"]
            raw["show certificates"] = s1h41.parse_s1h41_certificates(str(step58_log))

        prepared = s1h41.prepare_s1h41_data(raw, "1VAD4ZB004")
        certs = prepared["show certificates"]["certificates"]
        self.assertEqual([c["certificate-name"] for c in certs], ["gen_cert_a", "gen_cert_b"])
        self.assertEqual(certs[0]["certificate-valid-from"], "Nov  6 11:37:59 2026 GMT")
        self.assertEqual(certs[1]["certificate-valid-from"], "Nov  6 11:40:00 2026 GMT")
        self.assertIn("2026-11-06 11:47:08", prepared["show certificates"]["status"][0]["response"])

    def test_mfg_default_dict_and_xml_fallback(self):
        payloads = _sample_s1h41_payloads()
        with _long_temp_dir() as tmp_dict, _long_temp_dir() as tmp_xml:
            _, _, _, _, dict_log = _write_synthetic_s1h41_unit(tmp_dict, payloads, mfg_as_xml_only=False)
            _, _, _, _, xml_log = _write_synthetic_s1h41_unit(tmp_xml, payloads, mfg_as_xml_only=True)
            parsed_dict = s1h41.parse_s1h41_mfg_default_commands(str(dict_log))
            parsed_xml = s1h41.parse_s1h41_mfg_default_commands(str(xml_log))

        for cmd in s1h41.S1H41_MFG_COMMANDS:
            self.assertEqual(parsed_xml[cmd]["status"][0]["response"], parsed_dict[cmd]["status"][0]["response"])
        self.assertEqual(len(parsed_xml["show configuration"]["port"]), 8)
        self.assertEqual(len(parsed_xml["show configuration"]["versions"]), 2)
        self.assertEqual(parsed_xml["show license"]["license"][0]["license-serial-number"], "836223")

    def test_target_sn_validation_and_contradiction_rejection(self):
        payloads = _sample_s1h41_payloads()
        raw = {
            "show firmware-bundles all": payloads["show firmware-bundles all"],
            "show system": payloads["show system"],
            "show license": payloads["show license"],
            "show frus detail": payloads["show frus detail"],
            "show configuration": payloads["show configuration"],
            "show certificates": payloads["fresh_certs"],
        }
        s1h41.validate_s1h41_target_sn(raw, "1vad4zb004")

        with self.assertRaisesRegex(ValueError, "does not match target SN"):
            s1h41.validate_s1h41_target_sn(raw, "WRONG_SN")

        bad_sku = _sample_s1h41_payloads()
        bad_sku["show frus detail"]["enclosure-sku"][0]["sku_serialnumber"] = "OTHER_SKU"
        raw_bad_sku = {**raw, "show frus detail": bad_sku["show frus detail"]}
        with self.assertRaisesRegex(ValueError, "enclosure-sku"):
            s1h41.validate_s1h41_target_sn(raw_bad_sku, "1VAD4ZB004")

        bad_mp = _sample_s1h41_payloads()
        bad_mp["show configuration"]["fru-versions"][0]["midplane-versions"][0]["midplane-serial-number"] = "OTHER_MP"
        raw_bad_mp = {**raw, "show configuration": bad_mp["show configuration"]}
        with self.assertRaisesRegex(ValueError, "midplane-versions"):
            s1h41.validate_s1h41_target_sn(raw_bad_mp, "1VAD4ZB004")

        bad_enc = _sample_s1h41_payloads()
        bad_enc["show configuration"]["enclosures"][0]["midplane-serial-number"] = "OTHER_ENC"
        raw_bad_enc = {**raw, "show configuration": bad_enc["show configuration"]}
        with self.assertRaisesRegex(ValueError, "enclosures"):
            s1h41.validate_s1h41_target_sn(raw_bad_enc, "1VAD4ZB004")

    def test_two_column_tables_and_full_chassis_sections(self):
        payloads = _sample_s1h41_payloads()
        raw = {
            "show firmware-bundles all": payloads["show firmware-bundles all"],
            "show system": payloads["show system"],
            "show license": payloads["show license"],
            "show frus detail": payloads["show frus detail"],
            "show configuration": payloads["show configuration"],
            "show certificates": payloads["fresh_certs"],
        }
        prepared = s1h41.prepare_s1h41_data(raw, "1VAD4ZB004")
        cli_text = "".join(s1h41.render_s1h41_cli_report(prepared, "1VAD4ZB004"))
        raw_text = "".join(s1h41.render_s1h41_raw_report(prepared, "1VAD4ZB004"))

        for expected in (
            "# show firmware-bundles all",
            "Active/Default",
            "# show system",
            "Midplane Serial Number: 1VAD4ZB004",
            "# show license",
            "Licensing Serial Number: 836223",
            "VSS Expires: Never",
            "# show frus detail",
            "Part Number: S1H41A",
            "CHASSIS_MIDPLANE",
            "1VAD4YB00P",
            "1VAD4YB00R",
            "Configuration SN: 1VAD4ZB004",
            "Original SN: PMF1104029P5YJT",
            "Original PN: 1104029-05",
            "# show configuration",
            "Controller ID: A",
            "Controller ID: B",
            "Controller A Versions",
            "Controller B Versions",
            "Midplane Versions",
            "Root Expander-A",
            "Root Expander-B",
            "PSU 1, Left",
            "PSU 2, Right",
            "Speed(C)",
            "A1",
            "B4",
            "Not Present",
            "500C0FF08362233C",
            "2U12-12Gv3",
            "# show certificates",
            "gen_cert_a",
            "gen_cert_b",
            "Nov  6 11:37:59 2026 GMT",
            "Nov  6 11:40:00 2026 GMT",
        ):
            self.assertIn(expected, cli_text)

        self.assertNotIn("Rates may vary", cli_text)
        self.assertNotIn("Oct 14", cli_text)

        gem_line = next(line for line in cli_text.splitlines() if line.startswith("GEM Version:"))
        gem_val = "usm-rss_sbbsas_24g_loki_hpe-v6.x_lite-r2025.07.0_rc1_rel_57"
        self.assertIn(f"{gem_val}    {gem_val}", gem_line)

        psu_sn_line = next(line for line in cli_text.splitlines() if line.startswith("Power Supply Serial Number:"))
        self.assertIn("PMF1104029P5YJT    PMF1104029P5YH4", psu_sn_line)

        self.assertIn("### Versions (Controller A vs Controller B)", raw_text)
        self.assertIn(f"| `gem-version` | {gem_val} | {gem_val} |", raw_text)
        self.assertIn("### PSU Versions (PSU 1 vs PSU 2)", raw_text)
        self.assertIn("| `psu-serial-number` | PMF1104029P5YJT | PMF1104029P5YH4 |", raw_text)

    def test_fail_before_write_and_end_to_end_golden_compare(self):
        payloads = _sample_s1h41_payloads()

        with _long_temp_dir() as tmp:
            unit_dir, _, step57_log, step58_log, step62_log = _write_synthetic_s1h41_unit(tmp, payloads)
            out_dir = Path(tmp) / "out"

            # Missing certificates fails before write
            _write_text(step58_log, "no cert xml\n")
            with self.assertRaisesRegex(ValueError, "show certificates"):
                app.process_single_extraction(str(unit_dir), "1VAD4ZB004", str(out_dir), quiet=True)
            self.assertFalse((out_dir / "1VAD4ZB004").exists())

        with _long_temp_dir() as tmp2:
            unit_dir, step55_log, step57_log, _, _ = _write_synthetic_s1h41_unit(tmp2, payloads)
            out_dir = Path(tmp2) / "out"
            _write_text(step55_log, "no bundle xml\n")
            _write_text(step57_log, "no bundle xml\n")
            with self.assertRaisesRegex(ValueError, "show firmware-bundles all"):
                app.process_single_extraction(str(unit_dir), "1VAD4ZB004", str(out_dir), quiet=True)
            self.assertFalse((out_dir / "1VAD4ZB004").exists())

        with _long_temp_dir() as tmp3:
            unit_dir, _, _, _, step62_log = _write_synthetic_s1h41_unit(tmp3, payloads)
            out_dir = Path(tmp3) / "out"
            txt62 = Path(app.to_long_path(str(step62_log))).read_text(encoding="utf-8")
            _write_text(step62_log, txt62.replace("show license:", "show skipped:"))
            with self.assertRaisesRegex(ValueError, "show license"):
                app.process_single_extraction(str(unit_dir), "1VAD4ZB004", str(out_dir), quiet=True)
            self.assertFalse((out_dir / "1VAD4ZB004").exists())

        with _long_temp_dir() as tmp4:
            unit_dir, _, _, _, _ = _write_synthetic_s1h41_unit(tmp4, payloads)
            out_dir = Path(tmp4) / "out"
            res = app.process_single_extraction(str(unit_dir), "1VAD4ZB004", str(out_dir), quiet=True)
            self.assertEqual(res["unit_type"], "Chas S1H41")
            self.assertEqual(res["controller"], "-")
            self.assertEqual(res["warnings"], [])

            fw_bytes = (out_dir / "1VAD4ZB004" / "FW.txt").read_bytes()
            raw_bytes = (out_dir / "1VAD4ZB004" / "FW_RAW.md").read_bytes()
            for raw_b in (fw_bytes, raw_bytes):
                self.assertIn(b"\r\n", raw_b)
                self.assertFalse(raw_b.endswith(b"\r\n"))
                for line in raw_b.decode("utf-8").splitlines():
                    self.assertEqual(line, line.rstrip())

            sample_dir = Path(tmp4) / "sample"
            shutil.copytree(out_dir / "1VAD4ZB004", sample_dir)
            matched, results = app.compare_with_golden_sample(str(out_dir / "1VAD4ZB004"), str(sample_dir))
            self.assertTrue(matched)
            self.assertEqual(sorted(r["file"] for r in results), ["FW.txt", "FW_RAW.md"])

            (sample_dir / "FW_RAW.md").write_text("tampered\n", encoding="utf-8")
            matched_after, _ = app.compare_with_golden_sample(str(out_dir / "1VAD4ZB004"), str(sample_dir))
            self.assertFalse(matched_after)


if __name__ == "__main__":
    unittest.main()
