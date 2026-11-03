"""W47DG Midplane status must come from post-write validation."""
import unittest

from extract_mfg_logs import extract_chassis_5u_midplane_validation


class W47dgFirmwareTest(unittest.TestCase):
    def test_validation_values_are_read_without_hardcoding(self):
        for structure, crc in (("0x14", "0x4BC5F496"), ("0x15", "0x12345678")):
            expected = [
                f"|0250|Midplane VPD structure    : {structure}",
                f"|0250|Midplane VPD CRC          : {crc}",
                "|0250|Midplane CPLD             : 0x20",
            ]
            raw = ["prefix|0250|unrelated"] + ["timestamp|gemcli.py" + row for row in expected]
            self.assertEqual(extract_chassis_5u_midplane_validation(raw), expected)

    def test_missing_or_incomplete_validation_fails(self):
        for lines in ([], ["|0250|Midplane VPD structure : 0x14"], [
            "|0250|Midplane VPD structure : 0x14",
            "|0250|Midplane VPD CRC : 0x4BC5F496",
            "|0250|PCM 1 firmware : 3.0A",
        ]):
            with self.subTest(lines=lines), self.assertRaisesRegex(ValueError, "Step 07"):
                extract_chassis_5u_midplane_validation(lines)
