import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import extract_mfg_logs as app
from module import extract_chassis_5u as chassis_5u


class Dell7PntnReportsTest(unittest.TestCase):
    def test_customer_validation_orders_fields_and_omits_unused_data(self):
        header = ['|3893|Checking chassis customer VPD (ID = 18) ...', '|3894|Name Offset Value', '|3895|---']
        layout = ['FRUID Ver', 'oem_id', 'config_selector', 'reserved']
        identity = ['part_number', 'serial_number', 'revision', 'customer_pn', 'customer_sn', 'customer_rev']

        def field(name):
            return [f'|3903|name: {name}, size: 1', '|3987|a value', '|3993|result: match', '|4010|---']

        raw = header + [row for name in (*layout, *identity, 'crc', 'tla_pn', 'tla_sn', 'tla_pid', 'fru_description') for row in field(name)]
        expected = [row for name in identity for row in field(name)] + [''] + header
        expected += [row for name in layout for row in field(name)] + [''] + field('fru_description')
        self.assertEqual(app.extract_7pntn_customer_validation(['prefix'+row for row in raw]), expected)
        with self.assertRaisesRegex(ValueError, 'missing or incomplete Customer VPD 18 field fru_description'):
            app.extract_7pntn_customer_validation(raw[:-1])
        # A later ID 19 result must never complete an incomplete ID 18 block.
        with self.assertRaisesRegex(ValueError, 'missing or incomplete Customer VPD 18 field fru_description'):
            app.extract_7pntn_customer_validation(raw[:-4] + ['|3893|Checking chassis customer VPD (ID = 19) ...'] + field('fru_description'))

    def test_part_number_from_metadata_or_exact_package_token(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, 'run.log').write_text("Input Dict - {'uut_pn': '7PNTN'}\n", encoding='utf-8')
            pn = app.extract_cycle_time_metadata(temp)['part_number']
        with patch.object(chassis_5u, 'find_step_dir', side_effect=FileNotFoundError):
            self.assertTrue(app.check_is_chassis_5u_dell('unused', 'renamed', pn))
            self.assertTrue(app.check_is_chassis_5u_dell('unused', 'jbod_uut0_7pntn_SGFTEST'))
            self.assertFalse(app.check_is_chassis_5u_dell('unused', 'jbod_uut0_X7PNTN_SGFTEST'))
            self.assertFalse(app.check_is_chassis_5u_dell('unused', 'SGFTEST'))

    def test_strip_only_leading_code(self):
        self.assertEqual(app.strip_5u_log_code('|0250|Sled FW: 1|BL=2|FC=3'), 'Sled FW: 1|BL=2|FC=3')
        self.assertEqual(app.strip_5u_log_code('TWI payload |0509|text'), 'TWI payload |0509|text')

    def test_fan_pairs_are_ordered_and_cannot_mix_snapshots(self):
        midplane = ['|0250|Midplane VPD structure: 0x15', '|0250|Midplane VPD CRC: 0x01', '|0250|Midplane CPLD: 0x20']
        pairs = [f'|0250|Fan Controller {i} {kind}: {i + 5}' for i in range(5) for kind in ('config', 'deviceFW')]
        self.assertEqual(app.extract_7pntn_fan_fw(midplane + pairs[::-1], midplane), [r[6:] for r in pairs])
        with self.assertRaisesRegex(ValueError, 'Step 07.*missing Fan Controller 4 deviceFW'):
            app.extract_7pntn_fan_fw(midplane + pairs[:-1] + midplane + pairs[-1:], midplane)
        with self.assertRaisesRegex(ValueError, 'Step 07.*conflicting Fan Controller 0 config'):
            app.extract_7pntn_fan_fw(midplane + pairs + [pairs[0] + '0'], midplane)

    def test_wwn_pair_before_final_command_and_conflicting_bus(self):
        address = '500c0ff000000001'
        different = '500c0ff000000002'
        expected = [f'get_wwn: WWN = {address}', f'WWN: {address}']
        command = 'Output of cmd "set_midplanevpd 2" is '
        bus2, bus1 = [f'TWI bus {bus} vpd_type 2: [{address}]' for bus in (2, 1)]
        block = [command, bus2, bus1, f'{bus2}; want: [{address}] -> match', f'{bus1}; want: [{address}] -> match']
        raw = [f'|4326|{expected[0]}', f'|3402|{expected[1]}', '|0509|' + command, bus2, bus1]
        self.assertEqual(app.extract_7pntn_wwn(raw, len(raw), block), expected)
        with self.assertRaisesRegex(ValueError, 'WWN mismatch'):
            app.extract_7pntn_wwn(raw, len(raw), [*block[:-1], block[-1].replace(address, different)])
        with self.assertRaisesRegex(ValueError, 'WWN read pair'):
            app.extract_7pntn_wwn([r.replace(address, different) for r in raw], len(raw), block)
        with self.assertRaisesRegex(ValueError, 'missing get_wwn/WWN'):
            app.extract_7pntn_wwn([*raw, '|3673|' + block[-1]], len(raw) + 1, block)
        with self.assertRaisesRegex(ValueError, 'incomplete WWN read pair'):
            app.extract_7pntn_wwn([*raw, '|4326|'+ expected[0]], len(raw) + 1, block)

    def test_fan_vpd_left_column_sorted_and_truncated(self):
        raw = []
        for vpd_id in (124, 126, 123, 125, 122):
            raw.append(f'VPD {vpd_id} (0) - Fan Controller VPD {vpd_id - 121} - (bus=32) | right header')
            raw.extend(f'{offset:04x}:' + ' 01' * 16 + '  ' + '.' * 16 + ' + right data' for offset in range(0, 0x70, 0x10))
        blocks = app.extract_7pntn_fan_vpd(raw)
        self.assertEqual([r[0].split()[1] for r in blocks], ['122', '123', '124', '125', '126'])
        for block in blocks:
            self.assertEqual([r[:5] for r in block[1:]], ['0000:', '0010:', '0020:', '0030:', '0040:', '0050:'])
            self.assertTrue(all('right' not in row for row in block))
        with self.assertRaisesRegex(ValueError, 'Step 06.*missing Fan Controller VPD 122'):
            app.extract_7pntn_fan_vpd(raw[:-8])
        with self.assertRaisesRegex(ValueError, 'Step 06.*VPD 124.*0020'):
            app.extract_7pntn_fan_vpd(raw[:3] + raw[4:])
