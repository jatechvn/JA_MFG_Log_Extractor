import contextlib
import csv
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import extract_mfg_logs as app
from module import extract_s1h44 as s1h44


@contextlib.contextmanager
def _long_temp_dir():
    tmp = tempfile.mkdtemp(prefix="s1h44_test_")
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


def _sample_s1h44_payloads(
    chassis_sn="1VAD4ZB02F",
    sn_a="1VAD4YB00Z",
    sn_b="1VAD4YB014",
    *,
    host_a="HPE00C0FF836250A",
    host_b="HPE00C0FF836250B",
    disconnected_ports=False,
):
    """Create consistent synthetic S1H44-62001 (10/25GbE iSCSI SFF 24-slot) payloads covering all 8 MSA commands."""
    status = lambda ts: [{
        "object-name": "status",
        "response-type": "Success",
        "response": f"Command completed successfully. ({ts})",
        "return-code": "0",
        "time-stamp": ts,
    }]

    fw_bundles_cmd = {
        "firmware-bundles": [{
            "object-name": "firmware-bundle",
            "bundle-version": "IN300R007",
            "build-date": "2025-07-30T16:48:42Z",
            "status": "Active",
            "health": "OK",
            "health-reason": "",
            "health-recommendation": "",
        }],
        "status": status("2026-10-14 07:56:22"),
    }

    sys_obj = {
        "object-name": "system-information",
        "system-name": "Uninitialized Name",
        "system-contact": "Uninitialized Contact",
        "system-location": "Uninitialized Location",
        "system-information": "Uninitialized Info",
        "midplane-serial-number": chassis_sn,
        "vendor-name": "HPE",
        "product-id": "MSA 2070 iSCSI",
        "product-brand": "MSA Storage",
        "scsi-vendor-id": "HPE",
        "scsi-product-id": "MSA 2070 iSCSI",
        "enclosure-count": "1",
        "health": "OK",
        "health-reason": "",
        "other-MC-status": "Operational",
        "pfuStatus": "Idle",
        "security-system-management": "Not in use",
        "supported-locales": "English (English), Japanese (日本語), Korean (한국어)",
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
        "status": status("2026-10-14 07:55:58"),
    }

    license_cmd = {
        "license": [{
            "object-name": "license",
            "license-key": "",
            "license-serial-number": "836250",
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
            "vss": "Enabled",
            "vss-expiry": "Never",
        }],
        "status": status("2026-10-14 07:55:59"),
    }

    sku_list = [{
        "object-name": "sku",
        "sku-partnumber": "S1H44A",
        "sku_serialnumber": chassis_sn,
        "sku-revision": "2100",
        "enclosure-id": "1",
    }]

    fru_midplane = {
        "object-name": "fru",
        "name": "CHASSIS_MIDPLANE",
        "description": "SPS-MSA 12G SFF Chassis",
        "part-number": "P62784-001",
        "serial-number": chassis_sn,
        "revision": "DL",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "2026-08-01 08:02:00",
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
        "description": "SPS-MSA 2070 iSCSI Controller",
        "part-number": "P61071-001",
        "serial-number": sn_a,
        "revision": "C",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "2026-10-14 13:15:00",
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
        "description": "SPS-MSA 2070 iSCSI Controller",
        "part-number": "P61071-001",
        "serial-number": sn_b,
        "revision": "C",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "2026-10-14 13:15:00",
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
        "serial-number": "1VAD50B030",
        "revision": "B",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "N/A",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "LEFT PSU SLOT",
        "configuration-serialnumber": chassis_sn,
        "fru-status": "OK",
        "original-serialnumber": "PMF1104029P40BW",
        "original-partnumber": "1104029-05",
        "original-revision": "",
        "enclosure-id": "1",
    }
    fru_psu_r = {
        "object-name": "fru",
        "name": "POWER_SUPPLY",
        "description": "SPS-MSA PWR supply OneStor 580W Plat AC",
        "part-number": "P49169-001",
        "serial-number": "1VAD50B01K",
        "revision": "B",
        "dash-level": "",
        "fru-shortname": "",
        "mfg-date": "N/A",
        "mfg-location": "",
        "mfg-vendor-id": "",
        "fru-location": "RIGHT PSU SLOT",
        "configuration-serialnumber": chassis_sn,
        "fru-status": "OK",
        "original-serialnumber": "PMF1104029P404J",
        "original-partnumber": "1104029-05",
        "original-revision": "",
        "enclosure-id": "1",
    }

    frus_cmd = {
        "enclosure-sku": sku_list,
        "enclosure-fru": [fru_midplane, fru_a, fru_b, fru_psu_l, fru_psu_r],
        "status": status("2026-10-14 07:56:23"),
    }

    secrets_cmd = {
        "enclosure-fru-secrets": [{
            "object-name": "fru-secrets",
            "fru-oui": "000E7F",
            "fru-revlevel": "2.1",
            "fru-supplierpn": "60-00000604-00-01",
            "fru-suppliersn": "BAFVN2630836250",
            "fru-tlapn": "S1H44A",
            "fru-tlasn": chassis_sn,
            "fru-oempn": "P62784-001",
            "fru-oemsn": chassis_sn,
            "fru-vendorid": "HPE",
            "fru-productid": "MSA 2070 iSCSI",
        }],
        "status": status("2026-10-14 07:56:24"),
    }

    def make_port(cid, idx, mac_hex):
        return {
            "object-name": "ports",
            "controller": cid,
            "port": f"{cid}{idx}",
            "media": "iSCSI",
            "target-id": "iqn.2015-11.com.hpe:storage.msa2070.bafvn2630836250",
            "status": "Disconnected" if disconnected_ports else "Up",
            "actual-speed": "N/A" if disconnected_ports else "25Gb",
            "configured-speed": "Auto",
            "health": "OK",
            "health-reason": "",
            "health-recommendation": "",
            "iscsi-port": [{
                "object-name": "port-details",
                "ip-version": "IPv4",
                "ip-address": "0.0.0.0",
                "gateway": "0.0.0.0",
                "netmask": "255.255.255.0",
                "mac-address": mac_hex,
                "sfp-status": "Not Present" if disconnected_ports else "OK",
                "sfp-part-number": "N/A" if disconnected_ports else "SFP-25G-PC03",
                "sfp-10G-compliance": "N/A",
                "sfp-ethernet-compliance": "N/A",
                "sfp-cable-technology": "N/A" if disconnected_ports else "Passive",
                "sfp-cable-length": "0" if disconnected_ports else "3",
            }],
        }

    def make_ctrl(cid, sn, mac, ip, pos, mac_prefix):
        return {
            "object-name": "controller",
            "controller-id": cid,
            "serial-number": sn,
            "hardware-version": "2.3",
            "cpld-version": "2.8",
            "mac-address": mac,
            "node-wwn": "208000C0FF836250",
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
            "port": [make_port(cid, i, f"{mac_prefix}:8{8 - i:X}") for i in range(1, 5)],
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
            "him-rev": "2",
            "him-model": "4",
            "backplane-type": "7",
            "host-channel_revision": "2",
            "disk-channel_revision": "0",
            "mrc-version": "0.1.9.19",
            "ctk-version": "No CTK present",
            "mcos-version": "IPM300R025-01",
            "gem-version": "usm-rss_sbbsas_24g_loki_hpe-v6.x_lite-r2025.07.0_rc1_rel_57",
            "pubs-version": "1.0.0.16",
            "translation-version": "8.3.0.10",
        }

    ports_a = [make_port("A", i, f"00:C0:FF:87:37:{88 - i}") for i in range(1, 5)]
    ports_b = [make_port("B", i, f"00:C0:FF:87:35:0{8 - i}") for i in range(1, 5)]
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
        for idx in range(1, 25)
    ]

    config_cmd = {
        "system": [sys_obj],
        "controllers": [
            make_ctrl("A", sn_a, "00:C0:FF:83:62:CC", "10.0.0.2", "Top", "00:C0:FF:87:37"),
            make_ctrl("B", sn_b, "00:C0:FF:83:62:B5", "10.0.0.3", "Bottom", "00:C0:FF:87:35"),
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
                "vpd-crc": "9B040A81",
                "cfg-mismatch-version": "00",
                "cpld-version": "2100",
                "fru-descriptor": "79",
                "part-number": "1110280-01",
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
                    "serial-number": "BAFVN26308362CC",
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
                    "serial-number": "BAFVN26308362B5",
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
                    "psu-serial-number": "PMF1104029P40BW",
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
                    "psu-serial-number": "PMF1104029P404J",
                },
            ],
        }],
        "port": ports_a + ports_b,
        "enclosure-list": slots,
        "enclosures": [{
            "object-name": "enclosures",
            "enclosure-id": "1",
            "enclosure-wwn": "500C0FF08362503C",
            "name": "",
            "location": "",
            "rack-number": "0",
            "rack-position": "0",
            "vendor": "HPE",
            "model": "MSA2070-ENCL-SFF",
            "fru-tlapn": "S1H44A",
            "emp-a-ch-id-rev": "00:127 6036",
            "emp-b-ch-id-rev": "01:127 6036",
            "midplane-type": "2U24-12Gv3",
            "health": "OK",
            "health-reason": "",
            "health-recommendation": "",
            "midplane-serial-number": chassis_sn,
        }],
        "enclosure-sku": sku_list,
        "enclosure-fru": [fru_midplane, fru_a, fru_b, fru_psu_l, fru_psu_r],
        "status": status("2026-10-14 07:55:59"),
    }

    stale_certs = {
        "certificates": [
            {
                "object-name": "certinfo",
                "certificate-name": "gen_cert_a",
                "certificate-type": "Device-Cert",
                "certificate-controller": "A",
                "certificate-service-web": "x",
                "certificate-valid-from": "Aug 18 15:09:34 2026 GMT",
                "certificate-valid-till": "Aug 15 15:09:34 2036 GMT",
                "certificate-issued-to": "DellEMC00C0FF000000B",
                "certificate-issued-by": "DellEMC00C0FF000000B",
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
                "certificate-valid-from": "Aug 18 15:09:34 2026 GMT",
                "certificate-valid-till": "Aug 15 15:09:34 2036 GMT",
                "certificate-issued-to": "DellEMC00C0FF000000B",
                "certificate-issued-by": "DellEMC00C0FF000000B",
                "certificate-state": "Available",
                "certificate-status": "System-generated",
                "certificate-default-services": "WEB",
                "certificate-encryption-type": "RSA",
            },
        ],
        "status": status("2026-10-14 07:27:37"),
    }

    fresh_certs = {
        "certificates": [
            {
                "object-name": "certinfo",
                "certificate-name": "gen_cert_a",
                "certificate-type": "Device-Cert",
                "certificate-controller": "A",
                "certificate-service-web": "x",
                "certificate-valid-from": "Oct 14 07:30:29 2026 GMT",
                "certificate-valid-till": "Oct 11 07:30:29 2036 GMT",
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
                "certificate-valid-from": "Oct 14 07:29:27 2026 GMT",
                "certificate-valid-till": "Oct 11 07:29:27 2036 GMT",
                "certificate-issued-to": host_b,
                "certificate-issued-by": host_b,
                "certificate-state": "Available",
                "certificate-status": "System-generated",
                "certificate-default-services": "WEB",
                "certificate-encryption-type": "RSA",
            },
        ],
        "status": status("2026-10-14 07:40:34"),
    }

    adv_settings_cmd = {
        "advanced-settings-table": [{
            "object-name": "advanced-settings-table",
            "background-scrub": "Enabled",
            "partner-firmware-upgrade": "Enabled",
            "utility-priority": "High",
            "smart": "Enabled",
            "dynamic-spares": "Enabled",
            "emp-poll-rate": "5",
            "host-cache-control": "Disabled",
            "sync-cache-mode": "Immediate",
            "missing-lun-response": "Illegal Request",
            "controller-failure": "Enabled",
            "super-cap-failure": "Enabled",
            "power-supply-failure": "Disabled",
            "fan-failure": "Disabled",
            "temperature-exceeded": "Disabled",
            "partner-notify": "Enabled",
            "auto-write-back": "Enabled",
            "disk-dsd-enable": "Disabled",
            "disk-dsd-delay": "15",
            "managed-logs": "Disabled",
            "auto-stall-recovery": "Enabled",
            "restart-on-capi-fail": "Enabled",
            "auto-map": "Disabled",
            "auto-unmap": "Disabled",
            "default-mapping": "Disabled",
            "slow-disk-detection": "Enabled",
            "scrub-schedule": "Disabled",
            "disk-firmware-update": "Enabled",
            "pcie-hotplug": "Disabled",
        }],
        "status": status("2026-10-14 07:55:58"),
    }

    return {
        "show firmware-bundles": fw_bundles_cmd,
        "show system": system_cmd,
        "show license": license_cmd,
        "show frus detail": frus_cmd,
        "show frus secrets": secrets_cmd,
        "show configuration": config_cmd,
        "show advanced-settings": adv_settings_cmd,
        "stale_certs": stale_certs,
        "fresh_certs": fresh_certs,
    }


def _write_synthetic_s1h44_unit(
    root_dir,
    payloads,
    *,
    mfg_as_xml_only=False,
    xml_secrets_alias="show fru secrets",
    include_split_bytes_read=True,
):
    """Create a synthetic CTP test directory for S1H44-62001."""
    unit_dir = Path(root_dir) / "rbod_fin2_test_uut0_S1H44-62001_1VAD4ZB02F_20261014-124955"
    job_dir = unit_dir / "latest"
    tr_dir = job_dir / "test-results"
    step58 = tr_dir / "58-_CTP_testcases_mfg-test_restore_default.py_RestoreDefault.test_restore_defaults_factory_remove_certs_-e630"
    step62 = tr_dir / "62-_CTP_testcases_mfg-test_rbod_test_mfg_default.py_Rbod_mfg_restore_default_test.test_mfg_restore_default_setting_-e630"

    _write_text(
        unit_dir / f"{unit_dir.name}.log",
        "2026-10-14 12:50:00| DEBUG | rbod_fin2.py | 1163| Input Dict - {'uut_pn': 'S1H44-62001', 'employee_id': 'V1802359'}\n"
        "2026-10-14 12:50:00| SUM   | Local start time: 2026-10-14 12:48:06\n"
        "2026-10-14 15:07:10| SUM   | Script rbod_fin2_test passed\n"
        "2026-10-14 15:07:10| SUM   | Local end time: 2026-10-14 15:07:10\n"
        "2026-10-14 15:07:10| SUM   | Test duration: 0 days 2 hours 19 minutes 3 seconds\n",
    )
    _write_text(
        unit_dir / "ctp_log_metadata.yaml",
        "HOST_NAME: vnmctp116188\nTEST_NAME: rbod_fin2_test\nTEST_STATUS: COMPLETED\n",
    )
    _write_text(
        job_dir / "results.json",
        '{"time": 8116.04, "pass": 56, "failures": 0, "errors": 0, "skip": 8, "total": 64}',
    )

    cert_chunks = [
        "2026-10-14 14:32:46|INFO|Data string read:\nshow certificates\n" + _build_xml_response("show certificates", payloads["stale_certs"]),
    ]
    if include_split_bytes_read:
        cert_chunks.append(
            "2026-10-14 14:45:37|DEBUG|Bytes read: b'<?xml '\n"
            "2026-10-14 14:45:37|DEBUG|Bytes read: b'version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\\r\\n<RESPONSE VE'\n"
            "2026-10-14 14:45:37|DEBUG|Bytes read: b'RSION=\"L100\" REQUEST=\"show certificates\">\\r\\n  <OBJECT>\\r\\n'"
        )
    cert_chunks.append(
        "2026-10-14 14:45:37|INFO|Data string read:\nshow certificates\n" + _build_xml_response("show certificates", payloads["fresh_certs"]),
    )
    _write_text(step58 / "debug.log", "\n\n".join(cert_chunks) + "\n")

    mfg_chunks = []
    for cmd in s1h44.S1H44_MFG_COMMANDS:
        if mfg_as_xml_only:
            req_name = xml_secrets_alias if cmd == "show frus secrets" else cmd
            mfg_chunks.append(
                f'2026-10-14 14:55:59|DEBUG|Bytes read: b\'<RESPONSE VERSION="L100" REQUEST="{req_name}"><broken>\'</RESPONSE>\n'
                f'2026-10-14 14:55:59|DEBUG|Bytes read: b\'VERSION="L100" REQUEST="{req_name}">\'\n'
                + _build_xml_response(req_name, payloads[cmd])
            )
        else:
            label = "Advanced Settings" if cmd == "show advanced-settings" else cmd
            line_no = "0083" if cmd == "show advanced-settings" else "0088"
            mfg_chunks.append(
                f"2026-10-14 14:55:59|INFO    |MainThread  |avocado.test|rbod_test_mfg_default.py|{line_no}|{label}:\n"
                f"{repr(payloads[cmd])}"
            )
    _write_text(step62 / "debug.log", "\n".join(mfg_chunks) + "\n")
    return unit_dir, step58 / "debug.log", step62 / "debug.log"


def _zip_directory(src_dir, zip_path):
    """Archive src_dir preserving its root folder name (handles Windows MAX_PATH)."""
    base_parent = Path(src_dir).parent
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(app.to_long_path(str(src_dir))):
            clean_root = app.from_long_path(root)
            for fname in files:
                fp = Path(clean_root) / fname
                zf.write(app.to_long_path(str(fp)), arcname=fp.relative_to(base_parent).as_posix())


class S1H44ReportsTest(unittest.TestCase):
    def test_detect_s1h44_sn_and_strict_pn_routing(self):
        self.assertEqual(
            app.get_log_package_pn("rbod_fin2_test_uut0_S1H44-62001_1VAD4ZB02F_20261014-124955"),
            "S1H44-62001",
        )
        self.assertTrue(s1h44.check_is_s1h44("rbod_fin2_test_uut0_S1H44-62001_1VAD4ZB02F_20261014-124955"))
        self.assertTrue(s1h44.check_is_s1h44("renamed_folder", "s1h44-62001"))
        self.assertFalse(s1h44.check_is_s1h44("rbod_fin2_test_uut0_S1H41-62001_1VAD4ZB004_20261106-170516"))
        self.assertFalse(s1h44.check_is_s1h44("rbod_fin2_test_uut0_S1H42-62001_1VAD4ZB031_20261106-161050"))
        self.assertFalse(s1h44.check_is_s1h44("rbod_fin2_test_uut0_S1H47-62001_1VAD4ZB001_20261106-204202"))
        self.assertFalse(s1h44.check_is_s1h44("rbod_fin2_test_uut0_S1H48-62001_1VAD4ZB02C_20261106-054514"))
        self.assertFalse(s1h44.check_is_s1h44("rbod_fin2_test_uut0_S3T80-62001_1VAD4ZB02Z_20261106-170339"))
        self.assertFalse(s1h44.check_is_s1h44("rbod_fin2_test_uut0_P61070-001_1VAD4YB000_1VAD4YB007_20260928-155654"))
        self.assertFalse(s1h44.check_is_s1h44("rbod_fin2_test_uut0_XS1H44-62001_1VAD4ZB02F_20261014-124955"))

        self.assertEqual(
            app.detect_sns_from_folder(r"D:\logs\rbod_fin2_test_uut0_S1H44-62001_1VAD4ZB02F_20261014-124955"),
            ["1VAD4ZB02F"],
        )
        self.assertEqual(
            app.detect_sns_from_folder(r"D:\logs\rbod_fin2_test_uut0_S1H44-62001_2MXD43G04Z_20260310-203038.zip"),
            ["2MXD43G04Z"],
        )

    def test_extract_s1h44_folder_and_zip_byte_identical_reports(self):
        payloads = _sample_s1h44_payloads()
        with _long_temp_dir() as tmp:
            unit_dir, _, _ = _write_synthetic_s1h44_unit(tmp, payloads, mfg_as_xml_only=False)
            zip_path = Path(tmp) / f"{unit_dir.name}.zip"
            _zip_directory(unit_dir, zip_path)

            out_dir = Path(tmp) / "out_dir"
            out_zip = Path(tmp) / "out_zip"
            res_dir = app.process_single_extraction(str(unit_dir), "1VAD4ZB02F", str(out_dir), quiet=True)
            res_zip = app.process_single_extraction(str(zip_path), "1VAD4ZB02F", str(out_zip), quiet=True)

            self.assertEqual(res_dir["unit_type"], "Chas S1H44")
            self.assertEqual(res_dir["controller"], "-")
            self.assertEqual(res_dir["warnings"], [])
            self.assertEqual(res_zip["unit_type"], "Chas S1H44")
            self.assertEqual(res_zip["warnings"], [])

            matched, results = app.compare_with_golden_sample(str(out_zip / "1VAD4ZB02F"), str(out_dir / "1VAD4ZB02F"))
            self.assertTrue(matched)
            self.assertEqual(sorted(r["file"] for r in results), ["FW.txt", "FW_RAW.md"])

            fw_bytes = (out_dir / "1VAD4ZB02F" / "FW.txt").read_bytes()
            raw_bytes = (out_dir / "1VAD4ZB02F" / "FW_RAW.md").read_bytes()
            for raw_b in (fw_bytes, raw_bytes):
                self.assertIn(b"\r\n", raw_b)
                self.assertNotIn(b"\n", raw_b.replace(b"\r\n", b""))
                self.assertFalse(raw_b.endswith(b"\r\n"))
                for line in raw_b.decode("utf-8").splitlines():
                    self.assertEqual(line, line.rstrip())

            cli_text = fw_bytes.decode("utf-8")
            headings = [line.strip() for line in cli_text.splitlines() if line.startswith("# show ")]
            self.assertEqual(
                headings,
                [
                    "# show firmware-bundles",
                    "# show system",
                    "# show license",
                    "# show frus detail",
                    "# show frus secrets detail",
                    "# show configuration",
                    "# show certificates",
                    "# show advanced-settings",
                ],
            )
            self.assertEqual(cli_text.count("Not Present"), 24)
            self.assertRegex(cli_text, r"Not Present\s+1\s+24\s+N/A")
            self.assertIn("Product ID: MSA 2070 iSCSI", cli_text)
            self.assertIn("Part Number: S1H44A", cli_text)
            self.assertIn("P62784-001", cli_text)
            self.assertIn("P61071-001", cli_text)
            self.assertIn("1110280-01", cli_text)
            self.assertIn("iqn.2015-11.com.hpe:storage.msa2070.bafvn2630836250", cli_text)
            self.assertIn("Ports   Media   Target ID", cli_text)
            self.assertIn("   Speed(A)   Speed(C)   Health   Reason   Action", cli_text)
            self.assertEqual(cli_text.count("Port Details\r\n------------"), 8)
            for lbl, _ in s1h44.S1H44_ISCSI_PORT_DETAIL_FIELDS:
                self.assertIn(f"{lbl}: ", cli_text)
            self.assertIn("25Gb       Auto       OK", cli_text)
            self.assertIn("MSA2070-ENCL-SFF", cli_text)
            self.assertIn("2U24-12Gv3", cli_text)
            for lbl, _ in s1h44.S1H44_ADVANCED_SETTINGS_FIELDS:
                self.assertIn(f"{lbl}: ", cli_text)
            self.assertTrue(cli_text.endswith("Success: Command completed successfully. (2026-10-14 07:55:58)"))

            raw_text = raw_bytes.decode("utf-8")
            self.assertIn("`Chas S1H44` / HPE MSA 2070 10/25GbE iSCSI SFF Storage", raw_text)
            self.assertIn("### Versions (Controller A vs Controller B)", raw_text)
            self.assertIn("### PSU Versions (PSU 1 vs PSU 2)", raw_text)
            self.assertIn("iscsi-port:", raw_text)
            self.assertIn("advanced-settings-table:", raw_text)
            for cmd in s1h44.S1H44_ALL_COMMANDS:
                self.assertIn(f"## `# {cmd}`", raw_text)

    def test_extract_s1h44_disconnected_iscsi_port_renders_blank_speed_a(self):
        disc = _sample_s1h44_payloads(disconnected_ports=True)
        disc_raw = {cmd: disc[cmd] for cmd in s1h44.S1H44_MFG_COMMANDS}
        disc_raw["show certificates"] = disc["fresh_certs"]
        disc_cli = "".join(s1h44.render_s1h44_cli_report(s1h44.prepare_s1h44_data(disc_raw, "1VAD4ZB02F"), "1VAD4ZB02F"))
        self.assertIn("Disconnected", disc_cli)
        self.assertIn("              Auto       OK", disc_cli)
        self.assertIn("SFP Status: Not Present", disc_cli)
        self.assertNotIn("N/A        Auto", disc_cli)

    def test_extract_s1h44_rejects_mismatched_target_sn(self):
        payloads = _sample_s1h44_payloads()
        raw = {cmd: payloads[cmd] for cmd in s1h44.S1H44_MFG_COMMANDS}
        raw["show certificates"] = payloads["fresh_certs"]
        s1h44.validate_s1h44_target_sn(raw, "1vad4zb02f")

        bad_tla = _sample_s1h44_payloads()
        bad_tla["show frus secrets"]["enclosure-fru-secrets"][0]["fru-tlasn"] = "OTHER_TLA"
        with self.assertRaisesRegex(ValueError, r"S1H44-62001:.*fru-tlasn"):
            s1h44.validate_s1h44_target_sn({**raw, "show frus secrets": bad_tla["show frus secrets"]}, "1VAD4ZB02F")

        bad_oem = _sample_s1h44_payloads()
        bad_oem["show frus secrets"]["enclosure-fru-secrets"][0]["fru-oemsn"] = "OTHER_OEM"
        with self.assertRaisesRegex(ValueError, r"S1H44-62001:.*fru-oemsn"):
            s1h44.validate_s1h44_target_sn({**raw, "show frus secrets": bad_oem["show frus secrets"]}, "1VAD4ZB02F")

        with _long_temp_dir() as tmp:
            unit_dir, _, _ = _write_synthetic_s1h44_unit(tmp, payloads)
            out_dir = Path(tmp) / "out"
            with self.assertRaisesRegex(ValueError, r"S1H44-62001:.*does not match target SN"):
                app.process_single_extraction(str(unit_dir), "WRONG_SN", str(out_dir), quiet=True)
            self.assertFalse((out_dir / "WRONG_SN").exists())

    def test_extract_s1h44_xml_fallback_when_dict_lines_absent(self):
        payloads = _sample_s1h44_payloads()
        with _long_temp_dir() as tmp_dict, _long_temp_dir() as tmp_xml:
            _, _, dict_log = _write_synthetic_s1h44_unit(tmp_dict, payloads, mfg_as_xml_only=False)
            _, _, xml_log = _write_synthetic_s1h44_unit(tmp_xml, payloads, mfg_as_xml_only=True, xml_secrets_alias="show fru secrets")
            parsed_dict = s1h44.parse_s1h44_mfg_default_commands(str(dict_log))
            parsed_xml = s1h44.parse_s1h44_mfg_default_commands(str(xml_log))

        for cmd in s1h44.S1H44_MFG_COMMANDS:
            self.assertEqual(parsed_xml[cmd]["status"][0]["response"], parsed_dict[cmd]["status"][0]["response"])
        self.assertEqual(parsed_dict["show advanced-settings"]["advanced-settings-table"][0]["background-scrub"], "Enabled")
        self.assertEqual(parsed_xml["show frus secrets"]["enclosure-fru-secrets"][0]["fru-productid"], "MSA 2070 iSCSI")

    def test_extract_s1h44_missing_advanced_settings_or_certs_raises_value_error(self):
        payloads = _sample_s1h44_payloads()
        with _long_temp_dir() as tmp1:
            unit_dir, _, step62_log = _write_synthetic_s1h44_unit(tmp1, payloads)
            out_dir = Path(tmp1) / "out"
            txt62 = Path(app.to_long_path(str(step62_log))).read_text(encoding="utf-8")
            _write_text(step62_log, txt62.replace("Advanced Settings:", "Skipped Section:"))
            with self.assertRaisesRegex(ValueError, r"S1H44-62001:.*show advanced-settings"):
                app.process_single_extraction(str(unit_dir), "1VAD4ZB02F", str(out_dir), quiet=True)
            self.assertFalse((out_dir / "1VAD4ZB02F").exists())

        with _long_temp_dir() as tmp2:
            unit_dir, step58_log, _ = _write_synthetic_s1h44_unit(tmp2, payloads)
            out_dir = Path(tmp2) / "out"
            _write_text(step58_log, "no cert xml\n")
            with self.assertRaisesRegex(ValueError, r"S1H44-62001:.*show certificates"):
                app.process_single_extraction(str(unit_dir), "1VAD4ZB02F", str(out_dir), quiet=True)
            self.assertFalse((out_dir / "1VAD4ZB02F").exists())

    def test_extract_s1h44_uses_last_post_reset_certificates_xml_past_split_bytes_read(self):
        payloads = _sample_s1h44_payloads(host_a="HPE00C0FF836250A", host_b="HPE00C0FF836250B")
        with _long_temp_dir() as tmp:
            unit_dir, step58_log, _ = _write_synthetic_s1h44_unit(tmp, payloads, include_split_bytes_read=True)
            parsed_certs = s1h44.parse_s1h44_certificates(str(step58_log))
            self.assertEqual(parsed_certs["status"][0]["time-stamp"], "2026-10-14 07:40:34")

            out_dir = Path(tmp) / "out"
            app.process_single_extraction(str(unit_dir), "1VAD4ZB02F", str(out_dir), quiet=True)
            cli_text = (out_dir / "1VAD4ZB02F" / "FW.txt").read_text(encoding="utf-8")
            self.assertIn("Oct 14 07:30:29 2026 GMT", cli_text)
            self.assertIn("Oct 14 07:29:27 2026 GMT", cli_text)
            self.assertIn("HPE00C0FF836250A", cli_text)
            self.assertIn("HPE00C0FF836250B", cli_text)
            self.assertNotIn("DellEMC00C0FF000000B", cli_text)

    def test_s1h44_cycle_time_and_report_validation(self):
        payloads = _sample_s1h44_payloads()
        with _long_temp_dir() as tmp:
            parent_dir = Path(tmp) / "logs"
            out_dir = Path(tmp) / "batch_out"
            _write_synthetic_s1h44_unit(parent_dir, payloads)
            items = app.scan_parent_folder_for_logs(str(parent_dir), default_output_base=str(out_dir))
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0][1], "1VAD4ZB02F")

            results = app.run_batch_extraction(items, max_workers=1, export_csv=True)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["unit_type"], "Chas S1H44")
            self.assertEqual(results[0]["status"], "SUCCESS")

            is_valid, warnings = app.validate_extracted_reports("Chas S1H44", results[0]["paths"])
            self.assertTrue(is_valid)
            self.assertEqual(warnings, [])
            is_valid_one, one_warnings = app.validate_extracted_reports("Chas S1H44", results[0]["paths"][:1])
            self.assertFalse(is_valid_one)
            self.assertTrue(any("1/2" in w for w in one_warnings))

            csv_path = out_dir / "Cycle_Time_Summary.csv"
            self.assertTrue(csv_path.is_file())
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Product_Family"], "Chas S1H44")
            self.assertEqual(rows[0]["Part_Number"], "S1H44-62001")
            self.assertEqual(rows[0]["Warnings"], "OK")

            ct_csv = Path(tmp) / "ct.csv"
            ct_res = app.run_cycle_time_analysis(items, output_csv_path=str(ct_csv))
            self.assertEqual(ct_res[0]["unit_type"], "Chas S1H44")
            self.assertTrue(ct_csv.is_file())


if __name__ == "__main__":
    unittest.main()
