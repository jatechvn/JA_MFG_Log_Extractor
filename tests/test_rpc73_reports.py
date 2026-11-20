import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from extract_mfg_logs import detect_rpc73_controller_from_vpd, extract_rpc73_revision_vpd
from module.extract_rpc73 import extract_iom_rpc73
from module.extraction_workflows import process_single_extraction


def canister(serial, controller, *, validated_serial=None):
    vpd = bytearray(0x380)
    vpd[0x28:0x28 + len(serial)] = serial.encode('ascii')
    rows = ['|0608|VPD 49 (1) - Canister Customer', '|0609|Header: VPD 49 (1) - Canister Customer']
    rows.extend(f'|0509|{offset:04x}: {vpd[offset:offset + 16].hex(" ")}  ................' for offset in range(0, 0x380, 16))
    rows.extend([
        f'|3898|Checking {controller} customer VPD (ID = 49) ...',
        '|3908|name: serial_number, size: 32',
        f'|4001|got: [{validated_serial or serial}]',
        '|4004|result: match', '|4021|---',
        '|3908|name: revision, size: 16', '|4001|got: [B]',
        '|4004|result: match', '|4021|---',
        '|3908|name: customer_pn, size: 32', '|4001|got: [RPC73]',
        '|4004|result: match', '|4021|---',
        '|3908|name: fru_description, size: 64', '|4001|got: [EBOD]',
        '|4004|result: match', '|4021|---',
        '|3908|name: after_description, size: 1',
    ])
    return rows


class Rpc73RevisionReportTest(unittest.TestCase):
    def test_iom_product_line_uses_package_pn_when_log_metadata_disagrees(self):
        target = 'SAFVN26468368FF'
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / f'jbod_cto_test_uut0_9d57g_{target}'
            steps = package / 'latest/test-results'
            fw = steps / '02-check_and_load_fw_test'
            vpd = steps / '07-vpd_validation'
            fw.mkdir(parents=True)
            vpd.mkdir(parents=True)
            (package / 'unit.log').write_text("Input Dict - {'uut_pn': 'RPC73'}\n", encoding='utf-8')
            (fw / 'debug.log').write_text('|0250|Canister firmware : 1.00\n', encoding='utf-8')
            (vpd / 'debug.log').write_text('\n'.join(canister(target, 'ctrlb')), encoding='utf-8')

            console = StringIO()
            with redirect_stdout(console):
                result = process_single_extraction(str(package), target, str(root / 'out'))

            self.assertRegex(console.getvalue(), r'Dòng SP: .*IOM 9D57G')
            self.assertEqual(result['unit_type'], 'IOM 9D57G')
            self.assertEqual(result['metadata']['part_number'], '9D57G')
            self.assertEqual(result['controller'], 'ctrlb')
            report = Path(result['paths'][0]).read_text(encoding='utf-8')
            self.assertIn('|4001|got: [RPC73]', report)
            self.assertTrue(report.endswith('|4021|---\n'))

    def test_report_uses_full_validation_for_9d57g_and_rpc73(self):
        target = 'SAFVN26468368FF'
        rows = canister('SAFVN26468368ED', 'ctrla') + canister(target, 'ctrlb')
        with patch('module.extract_rpc73.find_rpc73_fw_step_dir', return_value='fw'), \
                patch('module.extract_rpc73.find_step_dir', return_value='vpd'), \
                patch('module.extract_rpc73.clean_log_lines', side_effect=lambda path: rows if path.startswith('vpd') else []):
            for pn in ('9D57G', 'RPC73'):
                with self.subTest(pn=pn):
                    report = extract_iom_rpc73('logs', target, 'ctrla', part_number=pn)
                    self.assertIn('|3898|Checking ctrlb customer VPD (ID = 49) ...\n', report)
                    self.assertNotIn('|3898|Checking ctrla customer VPD (ID = 49) ...\n', report)
                    self.assertIn('|4001|got: [RPC73]\n', report)
                    self.assertIn('|4001|got: [EBOD]\n', report)
                    self.assertEqual(report[-1], '|4021|---\n')
                    self.assertFalse(any('after_description' in row for row in report))

            truncated = canister(target, 'ctrlb')[:-2]
            with patch('module.extract_rpc73.clean_log_lines', side_effect=lambda path: truncated if path.startswith('vpd') else []):
                with self.assertRaisesRegex(ValueError, 'incomplete VPD 49 fru_description'):
                    extract_iom_rpc73('logs', target, 'ctrlb', part_number='9D57G')

    def test_full_validation_keeps_customer_fields_through_fru_description(self):
        target = 'SAFVN26468368F7'
        lines = canister(target, 'ctrla') + canister('SAFVN26468368F5', 'ctrlb')
        role, _, validation = extract_rpc73_revision_vpd(lines, target, full_validation=True)
        self.assertEqual(role, 'ctrla')
        self.assertIn('|4001|got: [RPC73]', validation)
        self.assertEqual(validation[-3:], ['|4001|got: [EBOD]', '|4004|result: match', '|4021|---'])
        truncated = canister(target, 'ctrla')[:-2] + canister('SAFVN26468368F5', 'ctrlb')
        with self.assertRaisesRegex(ValueError, 'incomplete VPD 49 fru_description'):
            extract_rpc73_revision_vpd(truncated, target, full_validation=True)

    def test_selects_target_hex_serial_and_ends_at_revision_separator(self):
        lines = canister('SAFVN26468368ED', 'ctrla') + canister('SAFVN26468368FF', 'ctrlb')
        role, dump, validation = extract_rpc73_revision_vpd(lines, 'SAFVN26468368FF')
        self.assertEqual(role, 'ctrlb')
        self.assertEqual(detect_rpc73_controller_from_vpd(lines, 'SAFVN26468368ED'), 'ctrla')
        self.assertIn('36 38 33 36 38 46 46', dump[5])
        self.assertEqual(len(dump), 15)
        self.assertEqual(validation[-1], '|4021|---')
        self.assertFalse(any('fru_description' in row for row in validation))

    def test_rejects_wrong_serial_or_missing_revision_separator(self):
        target = 'SAFVN26468368FF'
        with self.assertRaisesRegex(ValueError, 'validation serial does not match'):
            extract_rpc73_revision_vpd(canister(target, 'ctrlb', validated_serial='SAFVN26468368ED'), target)
        with self.assertRaisesRegex(ValueError, 'incomplete VPD 49 revision'):
            rows = canister(target, 'ctrlb')
            revision = rows.index('|3908|name: revision, size: 16')
            extract_rpc73_revision_vpd(rows[:revision + 3], target)
        with self.assertRaisesRegex(ValueError, 'VPD 49 dump not found'):
            extract_rpc73_revision_vpd(canister('SAFVN26468368ED', 'ctrla'), target)
