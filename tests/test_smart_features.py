# -*- coding: utf-8 -*-
"""Bộ kiểm thử tự động cho các tính năng thông minh của JA_MFG_Log_Extractor v1.7.0."""
import csv
import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from contextlib import redirect_stdout

import extract_mfg_logs as app
from module import config as m_config
from module.ip_utils import expand_ip, get_station_line_info, get_station_lookup, normalize_ip
from module.local_config import DEFAULT_SETTINGS, load_local_config
from module.log_finder import (
    RemoteLogEntry,
    _display_width,
    extract_start_epoch_from_name,
    extract_start_time_from_name,
    format_entries_table_colored,
    parse_selection,
)
from module.remote_fetcher import SshLogService
from module.smart_actions import (
    RecentHistoryManager,
    detect_clipboard_ip,
    detect_clipboard_sn,
    export_retry_csv,
    resolve_best_report_target,
)


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text)


class SmartUpgradeFeaturesTest(unittest.TestCase):
    """Kiểm thử toàn diện 5 thành phần nâng cấp thông minh v1.7.0."""

    def setUp(self):
        history_dir = tempfile.TemporaryDirectory()
        self.addCleanup(history_dir.cleanup)
        history_patch = patch.object(m_config, "HISTORY_FILE", Path(history_dir.name) / "history.json")
        history_patch.start()
        self.addCleanup(history_patch.stop)

    def test_1_local_config_credentials_foxconn2610(self):
        """Kiểm tra mật khẩu V1801179 = Foxconn2610 (không có dấu chấm thừa) trong cấu hình JSON."""
        self.assertEqual(DEFAULT_SETTINGS["bridge"]["username"], "V1801179")
        self.assertEqual(DEFAULT_SETTINGS["bridge"]["password"], "Foxconn2610")
        self.assertEqual(DEFAULT_SETTINGS["windows_ssh"]["username"], "V1801179")
        self.assertEqual(DEFAULT_SETTINGS["windows_ssh"]["password"], "Foxconn2610")
        self.assertEqual(DEFAULT_SETTINGS["ssh"]["username"], "root")
        self.assertEqual(DEFAULT_SETTINGS["ssh"]["password"], "seagate")

        with tempfile.TemporaryDirectory() as tmp:
            cfg_file = Path(tmp) / "config.json"
            loaded = load_local_config(cfg_file)
            self.assertEqual(loaded["bridge"]["password"], "Foxconn2610")
            self.assertEqual(loaded["windows_ssh"]["password"], "Foxconn2610")
            self.assertIn("ui", loaded)
            self.assertEqual(loaded["ui"]["max_recent_history"], 5)

    def test_2_start_time_and_mes_end_time_extraction(self):
        """Kiểm tra tách thời gian bắt đầu từ tên gói log và thời gian kết thúc (Đẩy MES) từ mtime."""
        pkg_name = "rbod_bft_test_uut0_60-00000592-02-02_BAFVN262583617D_20260716-100011"
        self.assertEqual(extract_start_time_from_name(pkg_name), "2026-07-16 10:00:11")
        start_ep = extract_start_epoch_from_name(pkg_name)
        self.assertIsNotNone(start_ep)

        raw_output = (
            f"{pkg_name}\t1784199454\td\tPASS\t/CTP/logs/test/{pkg_name}\n"
            f"rbod_bft_test_uut0_BAFVN262583617D_20260630-064538\t1782806320\td\tFAIL\n"
            f"legacy_entry_20260629-035044\t1782715731\td\n"
        )
        entries = SshLogService._parse_find_output(raw_output, "/CTP/logs/test")
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].test_result, "PASS")
        self.assertEqual(entries[0].start_time_str, "2026-07-16 10:00:11")
        self.assertNotEqual(entries[0].start_time_str, entries[0].end_time_str)
        self.assertEqual(entries[1].test_result, "FAIL")
        self.assertEqual(entries[1].start_time_str, "2026-06-30 06:45:38")
        self.assertEqual(entries[2].test_result, "-")
        self.assertEqual(entries[2].start_time_str, "2026-06-29 03:50:44")

    def test_3_parse_selection_pass_fail_ranges(self):
        """Kiểm tra chọn nhanh P (PASS), F (FAIL), L (mới nhất), A (tất cả), và dải số."""
        entries = [
            RemoteLogEntry("pkg1_20260716-100011", "/logs/pkg1", 300.0, "dir", "PASS"),
            RemoteLogEntry("pkg2_20260715-090000", "/logs/pkg2", 200.0, "dir", "FAIL"),
            RemoteLogEntry("pkg3_20260714-080000", "/logs/pkg3", 100.0, "dir", "PASS"),
            RemoteLogEntry("pkg4_20260713-070000", "/logs/pkg4", 50.0, "dir", "FAIL"),
        ]
        self.assertEqual([e.name for e in parse_selection("p", entries)], ["pkg1_20260716-100011", "pkg3_20260714-080000"])
        self.assertEqual([e.name for e in parse_selection("PASS", entries)], ["pkg1_20260716-100011", "pkg3_20260714-080000"])
        self.assertEqual([e.name for e in parse_selection("f", entries)], ["pkg2_20260715-090000", "pkg4_20260713-070000"])
        self.assertEqual([e.name for e in parse_selection("FAIL", entries)], ["pkg2_20260715-090000", "pkg4_20260713-070000"])
        self.assertEqual([e.name for e in parse_selection("l", entries)], ["pkg1_20260716-100011"])
        self.assertEqual(len(parse_selection("a", entries)), 4)
        self.assertEqual([e.name for e in parse_selection("2-3, 1", entries)], [
            "pkg2_20260715-090000",
            "pkg3_20260714-080000",
            "pkg1_20260716-100011",
        ])

    def test_4_anti_break_5_column_table_alignment(self):
        """Kiểm tra bảng 5 cột PASS/FAIL chống vỡ: mọi dòng có cùng độ rộng hiển thị và cùng len()."""
        entries = [
            RemoteLogEntry(
                "rbod_bft_test_uut0_60-00000592-02-02_BAFVN262583617D_20260716-100011",
                "/CTP/logs/test/1",
                1784199454.0,
                "dir",
                "PASS",
            ),
            RemoteLogEntry(
                "rbod_bft_test_uut0_60-00000592-02-02_BAFVN262583617D_20260630-064538",
                "/CTP/logs/test/2",
                1782806320.0,
                "dir",
                "FAIL",
            ),
            RemoteLogEntry(
                "psu_test_uut2_DYJW5_PMV1104029G006Q_PMV1104029G000V_20261001-130549",
                "/CTP/logs/test/3",
                1790861149.0,
                "dir",
                "RUN",
            ),
            RemoteLogEntry(
                "archive_sample_20260901-010203.zip",
                "/CTP/logs/test/4.zip",
                1788224523.0,
                "file",
                "-",
            ),
        ]
        rendered = format_entries_table_colored(entries)
        raw_lines = [_strip_ansi(line) for line in rendered.splitlines()]
        self.assertEqual(len(raw_lines), len(entries) + 4)

        display_widths = {_display_width(line) for line in raw_lines}
        char_lengths = {len(line) for line in raw_lines}
        self.assertEqual(len(display_widths), 1, f"Độ rộng hiển thị không đồng nhất: {display_widths}")
        self.assertEqual(len(char_lengths), 1, f"Độ dài ký tự không đồng nhất: {char_lengths}")

    def test_5_ip_map_and_clipboard_history_helpers(self):
        """Kiểm tra sơ đồ 60 trạm 3 Line, chuẩn hóa IP 1/2/4 octet, Clipboard & RecentHistoryManager."""
        lookup = get_station_lookup()
        self.assertEqual(len(lookup), 60)
        self.assertEqual(expand_ip(".174"), "172.19.116.174")
        self.assertEqual(expand_ip("174"), "172.19.116.174")
        self.assertEqual(expand_ip("116.174"), "172.19.116.174")
        self.assertEqual(expand_ip("116174"), "172.19.116.174")
        self.assertEqual(get_station_line_info("174")["line"], "Line 3")
        self.assertEqual(get_station_line_info(".143")["line"], "Line 2")
        self.assertEqual(get_station_line_info("121")["line"], "Line 1")

        # Clipboard IP & SN detection
        self.assertEqual(detect_clipboard_ip("116.174"), "172.19.116.174")
        self.assertEqual(detect_clipboard_ip(".188"), "172.19.116.188")
        self.assertIsNone(detect_clipboard_ip("174"))  # Bare 3-digit number in clipboard not guessed as IP
        self.assertIsNone(detect_clipboard_ip("SGFVN2633836284"))

        self.assertEqual(detect_clipboard_sn("SGFVN2633836284"), "SGFVN2633836284")
        self.assertEqual(detect_clipboard_sn("PMV1104546G0016\nPMV1104546G0017"), "PMV1104546G0016, PMV1104546G0017")
        self.assertIsNone(detect_clipboard_sn("172.19.116.174"))
        self.assertIsNone(detect_clipboard_sn("D:\\JA_TESTER\\LOGS_ANL"))

        # RecentHistoryManager & export_retry_csv
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            hist = RecentHistoryManager(tmp_path / "recent_history.json", max_items=3)
            hist.record_session(["172.19.116.172", "172.19.116.174"], ["SN001", "SN002"], last_target_path=tmp_path)
            hist.record_session(["172.19.116.172"], ["SN003"])
            self.assertEqual(hist.get_recent_ips(), ["172.19.116.172", "172.19.116.174"])
            self.assertEqual(hist.get_recent_sns(), ["SN003", "SN001", "SN002"])

            results = [
                {"sn": "SN_OK", "status": "SUCCESS", "source_target": "172.19.116.172", "out_dir": str(tmp_path)},
                {"sn": "SN_ERR", "status": "FAIL", "source_target": "172.19.116.174", "output_base": str(tmp_path), "out_dir": "-"},
            ]
            retry_csv = export_retry_csv(results, tmp_path)
            self.assertIsNotNone(retry_csv)
            self.assertTrue(retry_csv.is_file())
            with open(retry_csv, "r", encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1][0], "172.19.116.174")
            self.assertEqual(rows[1][1], "SN_ERR")

            best_dir, select_file = resolve_best_report_target(results, tmp_path)
            self.assertEqual(best_dir, tmp_path)
            self.assertFalse(select_file)

    def test_6_list_only_and_ssh_session_reuse(self):
        """Kiểm tra chế độ --list-only và tái sử dụng phiên SSH (ssh_service) không ngắt kết nối sớm."""
        fake_service = MagicMock()
        fake_service.is_connected = True
        fake_service.remote_os = "linux"
        fake_service.username = "root"
        fake_service.find_matching_entries.return_value = (
            [
                RemoteLogEntry(
                    "rbod_bft_test_uut0_BAFVN262583617D_20260716-100011",
                    "/CTP/logs/test/rbod_bft_test_uut0_BAFVN262583617D_20260716-100011",
                    1784199454.0,
                    "dir",
                    "PASS",
                )
            ],
            "/CTP/logs/test",
        )

        with tempfile.TemporaryDirectory() as tmp:
            m_config.HISTORY_FILE.write_bytes(b'{"last_target_path":"local-report"}')
            history_before = m_config.HISTORY_FILE.read_bytes()
            results = app.process_remote_extraction(
                raw_ip="116.174",
                raw_sn="BAFVN262583617D",
                output_base_raw=tmp,
                list_only=True,
                ssh_service=fake_service,
                export_csv=False,
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "SUCCESS")
            self.assertEqual(results[0]["unit_type"], "LIST-ONLY")
            # Vì truyền ssh_service từ ngoài vào, process_remote_extraction KHÔNG được gọi disconnect()
            fake_service.disconnect.assert_not_called()
            fake_service.fetch_selective_log_to_temp.assert_not_called()
            self.assertEqual(m_config.HISTORY_FILE.read_bytes(), history_before)

    def test_empty_result_filter_prompts_again_before_fetch(self):
        for choice, status in (("P", "FAIL"), ("F", "PASS")):
            with self.subTest(choice=choice):
                service = MagicMock(is_connected=True, remote_os="linux", username="fixture")
                entries = [RemoteLogEntry(f"pkg_SGFTEST_{i}", f"/logs/{i}", i, "dir", status) for i in (1, 2)]
                service.find_matching_entries.return_value = (entries, "/logs")
                prompts = []

                def select(*args, **kwargs):
                    service.fetch_selective_log_to_temp.assert_not_called()
                    prompts.append(True)
                    if len(prompts) == 1:
                        return choice
                    raise KeyboardInterrupt  # User cancels after seeing no matching runs.

                with redirect_stdout(io.StringIO()), patch.object(app.sys.stdin, "isatty", return_value=True), patch.object(app, "safe_input", side_effect=select):
                    with self.assertRaises(KeyboardInterrupt):
                        app.process_remote_extraction(".174", "SGFTEST", interactive=True, export_csv=False, ssh_service=service)
                self.assertEqual(len(prompts), 2)
                service.fetch_selective_log_to_temp.assert_not_called()

    def test_list_only_does_not_create_history(self):
        service = MagicMock(is_connected=True, remote_os="linux", username="fixture")
        service.find_matching_entries.return_value = (
            [RemoteLogEntry("pkg_SGFTEST", "/logs/pkg", 100, "dir", "PASS")], "/logs",
        )
        with redirect_stdout(io.StringIO()):
            results = app.process_remote_extraction(".174", "SGFTEST", list_only=True, export_csv=False, ssh_service=service)
        self.assertEqual(results[0]["status"], "SUCCESS")
        self.assertFalse(m_config.HISTORY_FILE.exists())

    def test_table_fits_narrow_terminal_and_preserves_dates(self):
        entry = RemoteLogEntry("log_測試_" + "long_name_" * 15 + "20261102-090000", "/logs/fixture", 1793584800, "dir", "PASS")
        for columns in (20, 40, 60, 80, 100, 120, 140):
            with self.subTest(columns=columns), patch("module.log_finder.sys.stdout.isatty", return_value=True), patch("module.log_finder.shutil.get_terminal_size", return_value=os.terminal_size((columns, 30))):
                output = _strip_ansi(format_entries_table_colored([entry]))
                self.assertLess(max(_display_width(line) for line in output.splitlines()), columns)
                self.assertIn(entry.start_time_str, output.replace("\n", ""))
                self.assertIn(entry.end_time_str, output.replace("\n", ""))


if __name__ == "__main__":
    unittest.main()
