"""Juno 4U report extraction from test steps and enclosure logs."""

import glob
import os
import re
import tarfile

from .log_io import (
    find_test_results_dir,
    get_default_reports_dir,
    to_long_path,
    write_extracted_file,
)


def extract_chassis_4u_logs(input_dir, target_sn, output_base):
    """
    Extract Chassis 4U (4U Juno) report files:
    FW.txt, GETVPD.txt, VER.txt, VPD.txt, Provisioning State.txt, Restore Default.txt
    """
    abs_input = os.path.abspath(input_dir.strip(' "\' \t\r\n'))
    test_results_dir = find_test_results_dir(abs_input)
    unit_root = os.path.dirname(test_results_dir)
    if os.path.basename(unit_root) == 'latest' or os.path.basename(unit_root).startswith('job-'):
        unit_root = os.path.dirname(unit_root)
    if not output_base:
        output_base = get_default_reports_dir()

    clean_base = output_base.strip(' "\' \t\r\n')
    abs_base = os.path.abspath(clean_base)

    if os.path.basename(abs_base.rstrip('\\/')) == target_sn:
        output_dir = abs_base
    else:
        output_dir = os.path.join(abs_base, target_sn)

    os.makedirs(to_long_path(output_dir), exist_ok=True)

    saved_paths = []

    # 1. Process FW.txt
    fw_step_dirs = [d for d in os.listdir(to_long_path(test_results_dir)) if 'check_and_load_fw_test' in d and 'test_check_fw_versions' in d]
    if fw_step_dirs:
        fw_debug_log = os.path.join(test_results_dir, fw_step_dirs[0], 'debug.log')
        if os.path.exists(to_long_path(fw_debug_log)):
            with open(to_long_path(fw_debug_log), 'r', encoding='utf-8', errors='ignore') as f:
                raw_lines = f.readlines()

            def clean_4u_log_line(line):
                if '|Received:' in line:
                    line = re.sub(r'^.*?\|Received:\s*', '', line)
                line = re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\|.*?\|\d+\|', '', line)
                line = re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*', '', line)
                return line

            start_idx = None
            for i, l in enumerate(raw_lines):
                if 'Hook post_sequence_hook' in l:
                    start_idx = i
                    break

            end_idx = None
            if start_idx is not None:
                for i in range(start_idx, len(raw_lines)):
                    cl = clean_4u_log_line(raw_lines[i])
                    if re.search(r'exos-.*?:~\$\s*$', cl):
                        end_idx = i
                        break

            if start_idx is not None and end_idx is not None:
                out_lines = []
                for i in range(start_idx, end_idx + 1):
                    if raw_lines[i] == '\n':
                        continue
                    cl = clean_4u_log_line(raw_lines[i])
                    out_lines.append(cl)

                for l in raw_lines:
                    if '|0030|Test Passed' in l:
                        cl = re.sub(r'^\d{4}-\d{2}-\d{2}.*?(\|\d+\|)', r'\1', l)
                        out_lines.append(cl)
                        break

                fw_out_path = os.path.join(output_dir, 'FW.txt')
                write_extracted_file(fw_out_path, out_lines, trim_last_newline=True)
                saved_paths.append(fw_out_path)

    # 2 & 3. Process GETVPD.txt & VER.txt from enc_logs
    enc_dir = os.path.join(unit_root, 'enc_logs')
    log_content = None
    if os.path.exists(to_long_path(enc_dir)):
        extracted_log_path = glob.glob(to_long_path(os.path.join(enc_dir, 'obmcdump_*', 'uut_list_utility_logs.log')))
        if extracted_log_path:
            with open(to_long_path(extracted_log_path[0]), 'r', encoding='utf-8', errors='ignore') as f:
                log_content = f.read()
        else:
            tar_files = glob.glob(to_long_path(os.path.join(enc_dir, '*tar.xz'))) + glob.glob(to_long_path(os.path.join(enc_dir, '*.tar.gz')))
            for tar_path in tar_files:
                try:
                    with tarfile.open(to_long_path(tar_path), 'r:*') as tar:
                        for member in tar.getmembers():
                            if member.name.endswith('uut_list_utility_logs.log'):
                                f = tar.extractfile(member)
                                if f:
                                    log_content = f.read().decode('utf-8', errors='ignore')
                                    break
                except Exception:
                    pass
                if log_content:
                    break

    if log_content:
        blocks = re.split(r'(?=Command identifier:)', log_content)
        folder_name = os.path.basename(unit_root)
        date_match = re.search(r'(\d{4})(\d{2})(\d{2})', folder_name)
        date_str = f'{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}' if date_match else ''

        getvpd_idx = None
        for idx, b in enumerate(blocks):
            if 'Command Executed: getvpd' in b and (not date_str or date_str in b):
                getvpd_idx = idx
                break
        if getvpd_idx is None:
            for idx, b in enumerate(blocks):
                if 'Command Executed: getvpd' in b:
                    getvpd_idx = idx
                    break

        ver_idx = None
        if getvpd_idx is not None:
            getvpd_block = blocks[getvpd_idx]
            lines = [l + '\n' for l in getvpd_block.rstrip('\r\n').splitlines()]
            getvpd_out_path = os.path.join(output_dir, 'GETVPD.txt')
            write_extracted_file(getvpd_out_path, lines, trim_last_newline=True)
            saved_paths.append(getvpd_out_path)

            # Pair ver block with matching timestamp or adjacent block in the same test cycle
            ts_match = re.search(r'Command identifier:\s*gemcli_getvpd_test_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})', getvpd_block)
            if ts_match:
                ts_prefix = ts_match.group(1)
                for idx in range(getvpd_idx + 1, len(blocks)):
                    if 'Command Executed: ver' in blocks[idx] and f'gemcli_ver_test_{ts_prefix}' in blocks[idx]:
                        ver_idx = idx
                        break

            if ver_idx is None:
                for idx in range(getvpd_idx + 1, min(getvpd_idx + 10, len(blocks))):
                    if 'Command Executed: getvpd' in blocks[idx]:
                        break
                    if 'Command Executed: ver' in blocks[idx]:
                        ver_idx = idx
                        break

            if ver_idx is None:
                for b in blocks:
                    if 'Command Executed: ver' in b and 'USM Version' in b and 'Ops Panel Version' in b:
                        ver_block = b
                        break

            if ver_idx is not None:
                ver_block = blocks[ver_idx]
                lines = [l + '\n' for l in ver_block.rstrip('\r\n').splitlines()]
                ver_out_path = os.path.join(output_dir, 'VER.txt')
                write_extracted_file(ver_out_path, lines, trim_last_newline=True)
                saved_paths.append(ver_out_path)

    # Helper function to preserve |XXXX| line-number block while stripping date/thread prefix
    def clean_with_line_block(line):
        m = re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\|.*?\|(\d{4})\|(.*)$', line)
        if m:
            return f'|{m.group(1)}|{m.group(2)}\n'
        return line

    # 4. Process VPD.txt from vpd_validation
    vpd_step_dirs = [d for d in os.listdir(to_long_path(test_results_dir)) if 'vpd_validation' in d and 'test_vpd_validation' in d]
    if not vpd_step_dirs:
        vpd_step_dirs = [d for d in os.listdir(to_long_path(test_results_dir)) if 'vpd_validation' in d]

    if vpd_step_dirs:
        vpd_debug_log = os.path.join(test_results_dir, vpd_step_dirs[0], 'debug.log')
        if os.path.exists(to_long_path(vpd_debug_log)):
            with open(to_long_path(vpd_debug_log), 'r', encoding='utf-8', errors='ignore') as f:
                raw_lines = f.readlines()

            start_idx = None
            for i, l in enumerate(raw_lines):
                if '|          name           | Oper  | CTP status |' in l:
                    start_idx = i
                    break

            end_idx = None
            if start_idx is not None:
                for i in range(len(raw_lines) - 1, start_idx - 1, -1):
                    if 'Skipping VPD Check on Validate for ManufacturingDateTime' in raw_lines[i]:
                        end_idx = i
                        break

            if start_idx is not None and end_idx is not None:
                out_lines = [clean_with_line_block(raw_lines[i]) for i in range(start_idx, end_idx + 1)]
                vpd_out_path = os.path.join(output_dir, 'VPD.txt')
                write_extracted_file(vpd_out_path, out_lines, trim_last_newline=True)
                saved_paths.append(vpd_out_path)

    # 6. Process Restore Default.txt from juno_restore_default
    restore_step_dirs = [d for d in os.listdir(to_long_path(test_results_dir)) if 'restore_default' in d and 'test_restore_default' in d]
    if not restore_step_dirs:
        restore_step_dirs = [d for d in os.listdir(to_long_path(test_results_dir)) if 'restore_default' in d]

    if restore_step_dirs:
        restore_debug_log = os.path.join(test_results_dir, restore_step_dirs[0], 'debug.log')
        if os.path.exists(to_long_path(restore_debug_log)):
            with open(to_long_path(restore_debug_log), 'r', encoding='utf-8', errors='ignore') as f:
                raw_lines = f.readlines()

            start_idx = None
            for i, l in enumerate(raw_lines):
                if 'Verify Factory reset flag state' in l:
                    start_idx = i
                    break

            end_idx = None
            if start_idx is not None:
                for i in range(start_idx, len(raw_lines)):
                    if 'Factory reset successful using Restore Default command' in raw_lines[i]:
                        end_idx = i
                        break

            if start_idx is not None and end_idx is not None:
                out_lines = [clean_with_line_block(raw_lines[i]) for i in range(start_idx, end_idx + 1)]
                restore_out_path = os.path.join(output_dir, 'Restore Default.txt')
                write_extracted_file(restore_out_path, out_lines, trim_last_newline=True)
                saved_paths.append(restore_out_path)

    # 5. Process Provisioning State.txt
    job_log_path = os.path.join(os.path.dirname(test_results_dir), 'job.log')
    if os.path.exists(to_long_path(job_log_path)):
        with open(to_long_path(job_log_path), 'r', encoding='utf-8', errors='ignore') as f:
            raw_lines = f.readlines()

        start_idx = None
        for i, l in enumerate(raw_lines):
            if 'Slot A, Provisioned State: expander_0, development' in l:
                start_idx = i
                break

        end_idx = None
        if start_idx is not None:
            for i in range(start_idx, len(raw_lines)):
                if 'expander_5   development Before Provisioning' in raw_lines[i]:
                    end_idx = i
                    break

        if start_idx is not None and end_idx is not None:
            def clean_job_log_line(line):
                return re.sub(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+\s+.*?\|\s*', '', line)

            out_lines = [clean_job_log_line(raw_lines[i]) for i in range(start_idx, end_idx + 1)]
            out_lines[-1] = out_lines[-1].rstrip() + '\n'

            prov_out_path = os.path.join(output_dir, 'Provisioning State.txt')
            write_extracted_file(prov_out_path, out_lines, trim_last_newline=True)
            saved_paths.append(prov_out_path)

    expected_files = {
        'FW.txt', 'GETVPD.txt', 'VER.txt', 'VPD.txt',
        'Provisioning State.txt', 'Restore Default.txt',
    }
    missing_files = expected_files - {os.path.basename(path) for path in saved_paths}
    if missing_files:
        raise ValueError(
            'Incomplete Chassis 4U extraction; missing reports: '
            + ', '.join(sorted(missing_files))
        )
    return output_dir, saved_paths
